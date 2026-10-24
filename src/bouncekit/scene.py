"""Scene: configuration, seeded RNG, object registry, fixed-step loop and frames."""

import random
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

import pymunk

from bouncekit.colors import ColorLike
from bouncekit.config import SceneConfig, Vec
from bouncekit.errors import ConfigError
from bouncekit.export.ffmpeg import FfmpegWriter, require_ffmpeg
from bouncekit.render.base import Renderer
from bouncekit.render.pygame_renderer import PygameRenderer
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

WorldObject = CircleBoundary | Ball

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
    ) -> None:
        """Validate the settings and create an empty world.

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

    @property
    def time(self) -> float:
        """Simulated time in seconds (``frame / fps``)."""
        return self.frame / self.config.fps

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        """All world objects in insertion order."""
        return tuple(self._objects)

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
        for _ in range(self.config.substeps):
            self.space.step(self._dt)
            # Clamp after the whole step: collision impulses land after velocity
            # integration, so a clamp inside velocity_func would miss them.
            for ball in self._balls:
                ball.clamp_speed(max_speed)
        self.frame += 1

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

        Parent directories are created. ffmpeg is checked before simulating.

        Raises:
            FfmpegError: if ffmpeg is missing or fails.
        """
        require_ffmpeg()
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = self.config
        with FfmpegWriter(path, cfg.width, cfg.height, cfg.fps) as writer:
            for frame in self.frames():
                writer.write(frame)
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
