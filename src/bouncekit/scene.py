"""Scene: configuration, seeded RNG, object registry, fixed-step loop and frames."""

import random
import sys
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

import numpy as np
import pymunk
from numpy.typing import NDArray

from bouncekit.actions import Play
from bouncekit.audio.mixer import (
    NoteTrigger,
    limit_true_peak,
    mix,
    num_samples,
    sample_offset,
)
from bouncekit.colors import ColorLike
from bouncekit.config import AudioConfig, SceneConfig, Vec
from bouncekit.errors import ConfigError
from bouncekit.events import CollisionEvent, EventRecorder, WorldObject
from bouncekit.export.audio import write_wav
from bouncekit.export.ffmpeg import FfmpegWriter, mux, require_ffmpeg
from bouncekit.render.base import Renderer
from bouncekit.render.pygame_renderer import PygameRenderer
from bouncekit.sound import Scale
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

__all__ = ["Scene", "WorldObject"]

# Overrides (``seed``, ``duration``) set by the CLI while it executes a scene script.
# ``Scene.__init__`` applies them before creating ``rng``.
_overrides: dict[str, object] = {}


class Scene:
    """One video: settings, a pymunk space and the objects in it.

    Coordinates are screen pixels, origin top-left, +y down. The simulation
    advances only through :meth:`step_frame`, by ``substeps`` fixed steps of
    ``1 / (fps * substeps)`` seconds; it never reads wall-clock time.
    """

    def __init__(
        self,
        *,
        width: int = 1080,
        height: int = 1920,
        fps: int = 60,
        duration: float = 60.0,
        seed: int = 0,
        background: ColorLike = "#000000",
        gravity: Vec = (0.0, 900.0),
        substeps: int = 8,
        max_speed: float = 4000.0,
        audio: AudioConfig | None = None,
    ) -> None:
        """Validate the settings and create an empty world.

        ``audio`` defaults to ``AudioConfig()``.

        Raises:
            ConfigError: if any setting is invalid.
        """
        options: dict[str, object] = {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "seed": seed,
            "background": background,
            "gravity": gravity,
            "substeps": substeps,
            "max_speed": max_speed,
            "audio": AudioConfig() if audio is None else audio,
        }
        options.update(_overrides)
        self.config: SceneConfig = SceneConfig(**options)  # type: ignore[arg-type]
        self.rng: random.Random = random.Random(self.config.seed)
        self.frame: int = 0
        self.total_frames: int = round(self.config.duration * self.config.fps)
        self.space = pymunk.Space()
        self.space.gravity = self.config.gravity
        self.space.iterations = 10
        self.space.damping = 1.0
        self._dt = 1.0 / (self.config.fps * self.config.substeps)
        self._objects: list[WorldObject] = []
        self._balls: list[Ball] = []
        self._rings: list[CircleBoundary] = []
        self._step = 0
        self._events: list[CollisionEvent] = []
        self._rules: list[tuple[str, str, tuple[Play, ...]]] = []
        self._triggers: list[NoteTrigger] = []
        # Lookup-only state for the trigger policy (FR-103, FR-106); keys hash by identity.
        self._cursor: dict[Scale, int] = {}
        self._last_trigger: dict[tuple[Play, WorldObject], int] = {}  # -> step
        self._recorder = EventRecorder(self.config.fps * self.config.substeps)
        self._recorder.install(self.space)

    @property
    def time(self) -> float:
        """Simulated time in seconds (``frame / fps``)."""
        return self.frame / self.config.fps

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        """All world objects in insertion order."""
        return tuple(self._objects)

    @property
    def events(self) -> tuple[CollisionEvent, ...]:
        """Collision events recorded so far, in recording order."""
        return tuple(self._events)

    @property
    def triggers(self) -> tuple[NoteTrigger, ...]:
        """Notes triggered by sound rules so far, in trigger order."""
        return tuple(self._triggers)

    @property
    def has_sound(self) -> bool:
        """Whether any rule plays sound (then ``render`` muxes an audio track)."""
        return any(actions for _, _, actions in self._rules)

    def on_collision(self, tag_a: str, tag_b: str, actions: Sequence[Play]) -> None:
        """When objects tagged ``tag_a`` and ``tag_b`` start touching, run ``actions``.

        Tags match in either order. In this version every action must be an
        ``A.play(...)``. Rules run after each frame's physics, in registration order.

        Raises:
            ConfigError: for an empty or non-string tag, or ``actions`` that is not a
                list/tuple of play actions.
        """
        for name, tag in (("tag_a", tag_a), ("tag_b", tag_b)):
            if not isinstance(tag, str) or not tag:
                raise ConfigError(f"{name} must be a non-empty string; got {tag!r}")
        if not isinstance(actions, list | tuple) or not all(
            isinstance(act, Play) for act in actions
        ):
            raise ConfigError(
                f"actions must be a list of actions such as A.play(...); got {actions!r}"
            )
        self._rules.append((tag_a, tag_b, tuple(actions)))

    def _dispatch(self, events: Sequence[CollisionEvent]) -> None:
        """Turn one frame's events into note triggers (outside collision callbacks).

        Applies the trigger policy (FR-106): impacts slower than
        ``min_impact_speed`` are ignored; one play action re-triggers for the same
        object ``a`` only after ``min_retrigger_interval``; at most
        ``max_triggers_per_frame`` notes start in this frame (later ones dropped in
        event order). Only notes that play advance a ``Scale``'s cursor (FR-103).
        """
        cfg = self.config
        audio = cfg.audio
        rate = cfg.fps * cfg.substeps
        started = 0
        for ev in events:
            first, second = ev.objects
            for tag_a, tag_b, actions in self._rules:
                if tag_a in first.tags and tag_b in second.tags:
                    a = first
                elif tag_a in second.tags and tag_b in first.tags:
                    a = second
                else:
                    continue
                for act in actions:
                    if ev.speed < audio.min_impact_speed:
                        continue
                    last = self._last_trigger.get((act, a))
                    # One correctly rounded division of the exact step gap: a gap of
                    # exactly the interval is never misjudged as shorter.
                    if last is not None and (ev.step - last) / rate < audio.min_retrigger_interval:
                        continue
                    if started >= audio.max_triggers_per_frame:
                        continue
                    src = act.source
                    if isinstance(src, Scale):
                        index = self._cursor.get(src, 0)
                        hz = src.hz[index]
                        self._cursor[src] = (index + 1) % len(src.hz)
                    else:
                        hz = src.hz
                    gain = act.gain * min(1.0, ev.speed / audio.reference_speed) ** 0.5
                    self._triggers.append(
                        NoteTrigger(
                            step=ev.step,
                            offset=sample_offset(ev.step, cfg.fps, cfg.substeps),
                            voice=src.voice,
                            hz=hz,
                            gain=gain,
                        )
                    )
                    self._last_trigger[(act, a)] = ev.step
                    started += 1

    def audio_buffer(self) -> NDArray[np.float32]:
        """Mix the notes triggered so far: float32, shape ``(n, 2)``, 48 kHz.

        ``n`` is ``round(frame * 48000 / fps)`` for the frames simulated so far.
        """
        cfg = self.config
        return mix(
            self._triggers,
            length=num_samples(self.frame, cfg.fps),
            config=cfg.audio,
            seed=cfg.seed,
        )

    def add_circle(
        self,
        *,
        center: Vec,
        radius: float,
        thickness: float = 8.0,
        color: ColorLike = "#ffffff",
        gap_degrees: float = 0.0,
        angular_velocity: float = 0.0,
        segments: int = 128,
        elasticity: float = 1.0,
        tags: Iterable[str] = (),
    ) -> CircleBoundary:
        """Add a ring boundary; see :class:`CircleBoundary`.

        ``angular_velocity`` is in degrees per second, positive = clockwise.

        Raises:
            ConfigError: if any option is invalid, or a ball at ``max_speed`` could
                pass through a ring in one step (see ``_check_tunnelling``).
        """
        ring = CircleBoundary(
            self.space,
            center=center,
            radius=radius,
            thickness=thickness,
            color=color,
            gap_degrees=gap_degrees,
            angular_velocity=angular_velocity,
            segments=segments,
            elasticity=elasticity,
            tags=tags,
        )
        for ball in self._balls:
            self._check_tunnelling(ball, ring)
        self._recorder.register(len(self._objects), ring, ring.shapes)
        self._objects.append(ring)
        self._rings.append(ring)
        return ring

    def add_ball(
        self,
        *,
        pos: Vec,
        radius: float,
        velocity: Vec = (0.0, 0.0),
        elasticity: float = 1.0,
        color: ColorLike = "#ffffff",
        tags: Iterable[str] = (),
    ) -> Ball:
        """Add a dynamic ball; its speed is clamped to ``config.max_speed``.

        Raises:
            ConfigError: if any option is invalid, or a ball at ``max_speed`` could
                pass through a ring in one step (see ``_check_tunnelling``).
        """
        ball = Ball(
            self.space,
            pos=pos,
            radius=radius,
            velocity=velocity,
            elasticity=elasticity,
            color=color,
            tags=tags,
        )
        for ring in self._rings:
            self._check_tunnelling(ball, ring)
        self._recorder.register(len(self._objects), ball, [ball.shape])
        self._objects.append(ball)
        self._balls.append(ball)
        return ball

    def _check_tunnelling(self, ball: Ball, ring: CircleBoundary) -> None:
        """Reject a ball/ring pair that a ball at ``max_speed`` could pass through.

        A collision is caught only if the ball cannot move past a segment's centre
        line in one step, so per-step travel must be below ``radius + thickness / 2``.
        """
        travel = self.config.max_speed * self._dt
        reach = ball.radius + ring.thickness / 2
        if travel >= reach:
            raise ConfigError(
                f"ball radius {ball.radius} with ring thickness {ring.thickness} could tunnel: "
                f"at max_speed {self.config.max_speed} a ball moves {travel:.2f} px per step "
                f"but radius + thickness/2 is only {reach:.2f} px; increase substeps, "
                f"lower max_speed, or use a larger ball or thicker ring"
            )

    def step_frame(self) -> None:
        """Advance the simulation by one frame (``substeps`` fixed physics steps)."""
        max_speed = self.config.max_speed
        rec = self._recorder
        rec.frame = self.frame
        first_event = len(self._events)
        for _ in range(self.config.substeps):
            self._step += 1
            rec.step = self._step
            self.space.step(self._dt)
            self._events.extend(rec.flush())
            # Clamp after the whole step: collision impulses land after velocity
            # integration, so a clamp inside velocity_func would miss them.
            for ball in self._balls:
                ball.clamp_speed(max_speed)
        self.frame += 1
        if self._rules:
            self._dispatch(self._events[first_event:])

    def draw(self, renderer: Renderer) -> None:
        """Draw the background and every object, in insertion order.

        Drawing only reads world state; it never changes the simulation.
        """
        renderer.clear(self.config.background)
        for obj in self._objects:
            obj.draw(renderer)

    def frames(self) -> Iterator[bytes]:
        """Yield each remaining frame as RGB24 bytes, then advance one frame.

        The first frame yielded shows the current state (frame 0 for a new scene);
        frames are produced until ``frame`` reaches ``total_frames``. Nothing is
        reset, so a scene is meant to be simulated once.
        """
        renderer = PygameRenderer(self.config.width, self.config.height)
        while self.frame < self.total_frames:
            self.draw(renderer)
            yield renderer.to_rgb_bytes()
            self.step_frame()

    def render(self, out: str | Path) -> Path:
        """Simulate and encode the whole scene to an H.264 MP4 at ``out``.

        Parent directories are created. ffmpeg is checked before simulating. If the
        scene has sound rules, the mix is limited to a true peak of
        ``audio.peak_dbfs`` and muxed in as 48 kHz stereo AAC; otherwise the MP4 has
        no audio stream.

        Raises:
            FfmpegError: if ffmpeg is missing or fails.
        """
        require_ffmpeg()
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = self.config
        if not self.has_sound:
            with FfmpegWriter(path, cfg.width, cfg.height, cfg.fps) as writer:
                for frame in self.frames():
                    writer.write(frame)
            return path
        with tempfile.TemporaryDirectory(dir=path.parent, prefix=".bouncekit-") as tmp:
            video, wav = Path(tmp) / "video.mp4", Path(tmp) / "audio.wav"
            with FfmpegWriter(video, cfg.width, cfg.height, cfg.fps) as writer:
                for frame in self.frames():
                    writer.write(frame)
            # mix() normalises the sample peak; AAC needs true-peak headroom too.
            write_wav(wav, limit_true_peak(self.audio_buffer(), peak_dbfs=cfg.audio.peak_dbfs))
            mux(video, wav, path)
        return path

    def preview(self, scale: float = 0.45) -> None:
        """Play this scene in a live window (Space pause, Right step, R restart, Esc/Q quit).

        The first run uses this instance; restarting reloads the running script
        (``sys.argv[0]``) with this scene's seed and duration, since a scene is
        simulated only once.

        Raises:
            SceneLoadError: on restart, if the running script cannot be reloaded.
        """
        from bouncekit import cli  # local import: cli imports this module
        from bouncekit.render.preview import run_preview

        first = [self]

        def make() -> "Scene":
            if first:
                return first.pop()
            return cli.load_scene(
                Path(sys.argv[0]), seed=self.config.seed, duration=self.config.duration
            )

        run_preview(make, scale)

    def run(self) -> None:
        """Dispatch to the ``bouncekit`` CLI using ``sys.argv``; call from ``__main__``.

        The running script (``sys.argv[0]``) is the scene file and is reloaded by the
        CLI so ``--seed``/``--duration`` apply; with no subcommand it previews.
        Exits the process with the CLI's exit code.
        """
        from bouncekit import cli  # local import: cli imports this module

        raise SystemExit(cli.main(sys.argv[1:], default_scene=Path(sys.argv[0])))
