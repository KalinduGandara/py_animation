"""Scene: configuration, seeded RNG, object registry, fixed-step loop and frames."""

import math
import random
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import TypeVar, overload

import numpy as np
import pymunk
from numpy.typing import NDArray

from bouncekit.actions import ACTION_TYPES, Handler, Particles, Play
from bouncekit.audio.mixer import (
    NoteTrigger,
    limit_true_peak,
    mix,
    num_samples,
    sample_offset,
)
from bouncekit.colors import (
    ByGeneration,
    BySpeed,
    Color,
    ColorLike,
    ColorSource,
    ColorSpec,
    Fixed,
    HueCycle,
    color_source,
)
from bouncekit.config import (
    AudioConfig,
    EffectsConfig,
    SceneConfig,
    Vec,
    _non_negative_number,
    _positive_number,
    _vec,
)
from bouncekit.errors import ConfigError
from bouncekit.events import Event, EventRecorder, WorldObject
from bouncekit.export.audio import write_wav
from bouncekit.export.ffmpeg import FfmpegWriter, mux, require_ffmpeg
from bouncekit.render.base import GlowArc, GlowDisc, Renderer
from bouncekit.render.effects import Effects, TrailBall
from bouncekit.render.pygame_renderer import PygameRenderer
from bouncekit.rules.commands import BallSpec, Command, apply
from bouncekit.rules.engine import SUBJECTS, Rule, RuleEngine, RuleKind
from bouncekit.sound import Melody, Note, Scale
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

__all__ = ["Scene", "WorldObject"]

# Overrides (``seed``, ``duration``) set by the CLI while it executes a scene script.
# ``Scene.__init__`` applies them before creating ``rng``.
_overrides: dict[str, object] = {}

F = TypeVar("F", bound=Callable[..., object])

SPATIAL_HASH_BALLS = 100
"""Live ball count at which the space switches to pymunk's spatial hash (FR-212, C14)."""
SPATIAL_HASH_COUNT = 10_000
"""``count`` passed to ``space.use_spatial_hash`` (FR-212, C14)."""


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
        rule_cooldown: float = 0.05,
        max_balls: int = 1000,
        effects: EffectsConfig | None = None,
    ) -> None:
        """Validate the settings and create an empty world.

        ``audio`` defaults to ``AudioConfig()``. ``rule_cooldown`` is the default
        per-pair cooldown of collision rules in seconds (see :meth:`on_collision`).
        ``max_balls`` caps the live balls: ``add_ball`` beyond it raises, and splits or
        spawns beyond it are refused at runtime. ``effects`` defaults to
        ``EffectsConfig()`` (trail length, glow blur, particle cap).

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
            "rule_cooldown": rule_cooldown,
            "max_balls": max_balls,
            "effects": EffectsConfig() if effects is None else effects,
        }
        options.update(_overrides)
        self.config: SceneConfig = SceneConfig(**options)  # type: ignore[arg-type]
        self.rng: random.Random = random.Random(self.config.seed)
        self.fx_rng: random.Random = random.Random(f"bouncekit-fx:{self.config.seed}")
        """Random stream for visual effects only (FR-301); never affects physics."""
        self._fx = Effects()  # effect state, drawing only (FR-301)
        self.frame: int = 0
        # Frame of the latest simulated step: event ``frame`` for commands applied
        # after the frame (``when`` rules) as well as during it (FR-201).
        self._sim_frame: int = 0
        self.total_frames: int = round(self.config.duration * self.config.fps)
        self.space = pymunk.Space()
        self.space.gravity = self.config.gravity
        self.space.iterations = 10
        self.space.damping = 1.0
        self._rate = self.config.fps * self.config.substeps
        self._dt = 1.0 / self._rate
        self._objects: list[WorldObject] = []  # live objects, insertion order
        self._balls: list[Ball] = []
        self._rings: list[CircleBoundary] = []
        # Monotonic object indices (never reused); lookup only, keys hash by identity.
        self._indices: dict[WorldObject, int] = {}
        self._next_index = 0
        self._step = 0
        self._in_frame = False  # True while step_frame runs the current frame's steps
        self._events: list[Event] = []
        self._engine = RuleEngine(self)
        self._queue: list[Command] = []  # FIFO, applied after each step's dispatch
        self._cascade: list[Event] = []  # spawn/destroy events for the next step
        self._triggers: list[NoteTrigger] = []
        # Lookup-only state for the trigger policy (FR-103, FR-106); keys hash by identity.
        self._cursor: dict[Scale | Melody, int] = {}
        self._last_trigger: dict[tuple[Play, WorldObject | None], int] = {}  # -> step
        self._frame_triggers: dict[int, int] = {}  # event.frame -> notes started
        # Visual-only flash state (FR-210): object index -> (colour, first frame, frames).
        self._flash: dict[int, tuple[Color, int, int]] = {}
        self._hashed = False  # switched to the spatial hash (FR-212)
        self._recorder = EventRecorder(self._rate)
        self._recorder.install(self.space)

    @property
    def time(self) -> float:
        """Simulated time in seconds (``frame / fps``)."""
        return self.frame / self.config.fps

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        """Live world objects in insertion order (destroyed objects are removed)."""
        return tuple(self._objects)

    def count(self, tag: str | None = None) -> int:
        """Number of live objects carrying ``tag`` (all live objects for ``None``)."""
        if tag is None:
            return len(self._objects)
        return sum(1 for obj in self._objects if tag in obj.tags)

    @property
    def events(self) -> tuple[Event, ...]:
        """Events recorded so far (collisions, destroys, ...), in log order."""
        return tuple(self._events)

    @property
    def triggers(self) -> tuple[NoteTrigger, ...]:
        """Notes triggered by sound rules so far, in trigger order."""
        return tuple(self._triggers)

    @property
    def has_sound(self) -> bool:
        """Whether any rule has an ``A.play`` handler.

        ``render`` muxes an audio track when this is true or any note was triggered
        (e.g. by ``ctx.play`` in a callback).
        """
        return self._engine.has_play

    @property
    def _rules(self) -> list[tuple[str, str, tuple[Handler, ...]]]:
        """M1 view of the collision rules as ``(tag_a, tag_b, handlers)`` tuples."""
        return [
            (r.tag_a or "", r.tag_b or "", r.handlers)
            for r in self._engine.rules
            if r.kind == "collision"
        ]

    @overload
    def on_collision(
        self,
        tag_a: str,
        tag_b: str,
        handlers: None = None,
        *,
        cooldown: float | None = None,
        object_cooldown: float = 0.0,
    ) -> Callable[[F], F]: ...

    @overload
    def on_collision(
        self,
        tag_a: str,
        tag_b: str,
        handlers: Sequence[Handler],
        *,
        cooldown: float | None = None,
        object_cooldown: float = 0.0,
    ) -> None: ...

    def on_collision(
        self,
        tag_a: str,
        tag_b: str,
        handlers: Sequence[Handler] | None = None,
        *,
        cooldown: float | None = None,
        object_cooldown: float = 0.0,
    ) -> Callable[[F], F] | None:
        """When objects tagged ``tag_a`` and ``tag_b`` start touching, run ``handlers``.

        Tags match in either order; subject ``a`` is the object carrying ``tag_a``.
        ``handlers`` is a list of built-in actions (``A.play``, ``A.destroy``) and
        callables ``f(ctx, a, b, event)``, run in order after the physics step,
        never inside it. Without ``handlers``, returns a decorator that registers
        the decorated function and returns it unchanged.

        Non-play handlers are skipped for a pair that fired this rule less than
        ``cooldown`` seconds earlier (default ``config.rule_cooldown``) and, when
        ``object_cooldown > 0``, for an ``a`` that fired it with any partner less than
        ``object_cooldown`` earlier. ``A.play`` keeps the audio trigger policy only.

        Raises:
            ConfigError: for an empty or non-string tag, bad handlers, a negative or
                non-finite cooldown, or an action targeting a missing subject.
        """
        for name, tag in (("tag_a", tag_a), ("tag_b", tag_b)):
            _check_tag(name, tag)
        pair = (
            self.config.rule_cooldown
            if cooldown is None
            else _non_negative_number("cooldown", cooldown)
        )
        per_object = _non_negative_number("object_cooldown", object_cooldown)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("collision", items, len(self._engine.rules), tag_a, tag_b, pair, per_object)

        return self._register("collision", "on_collision", handlers, make)

    @overload
    def on_escape(
        self, ring: CircleBoundary, tag: str, handlers: None = None, *, margin: float = 0.0
    ) -> Callable[[F], F]: ...

    @overload
    def on_escape(
        self,
        ring: CircleBoundary,
        tag: str,
        handlers: Sequence[Handler],
        *,
        margin: float = 0.0,
    ) -> None: ...

    def on_escape(
        self,
        ring: CircleBoundary,
        tag: str,
        handlers: Sequence[Handler] | None = None,
        *,
        margin: float = 0.0,
    ) -> Callable[[F], F] | None:
        """When a ball carrying ``tag`` leaves ``ring``, run ``handlers`` (FR-208).

        A ball has escaped once its centre is farther than
        ``ring.radius + ring.thickness / 2 + ball.radius + margin`` from the ring's
        centre after a step; each (ring, ball) pair escapes at most once. Callables are
        called as ``f(ctx, ball, ring, event)``; subject ``a`` is the ball and ``b`` the
        ring. Without ``handlers``, returns a decorator.

        Raises:
            ConfigError: if ``ring`` is not a ring handle, for an empty or non-string
                tag, a negative or non-finite margin, or bad handlers.
        """
        if not isinstance(ring, CircleBoundary):
            raise ConfigError(f"ring must be a ring handle from add_circle; got {ring!r}")
        _check_tag("tag", tag)
        extra = _non_negative_number("margin", margin)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("escape", items, len(self._engine.rules), tag, ring=ring, margin=extra)

        return self._register("escape", "on_escape", handlers, make)

    @overload
    def on_spawn(self, tag: str, handlers: None = None) -> Callable[[F], F]: ...

    @overload
    def on_spawn(self, tag: str, handlers: Sequence[Handler]) -> None: ...

    def on_spawn(
        self, tag: str, handlers: Sequence[Handler] | None = None
    ) -> Callable[[F], F] | None:
        """When a ball carrying ``tag`` is spawned (``A.spawn`` or a split child), run ``handlers``.

        Callables are called as ``f(ctx, obj, event)``; subject ``a`` is the new ball
        (there is no ``b``). The spawn event is dispatched at the step after the one
        that created the ball, so spawn chains grow one level per step. Without
        ``handlers``, returns a decorator.

        Raises:
            ConfigError: for an empty or non-string tag, bad handlers, or an action
                targeting subject ``"b"``.
        """
        _check_tag("tag", tag)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("spawn", items, len(self._engine.rules), tag)

        return self._register("spawn", "on_spawn", handlers, make)

    @overload
    def on_destroy(self, tag: str, handlers: None = None) -> Callable[[F], F]: ...

    @overload
    def on_destroy(self, tag: str, handlers: Sequence[Handler]) -> None: ...

    def on_destroy(
        self, tag: str, handlers: Sequence[Handler] | None = None
    ) -> Callable[[F], F] | None:
        """When an object carrying ``tag`` is destroyed, run ``handlers``.

        Callables are called as ``f(ctx, obj, event)``; subject ``a`` is the destroyed
        object (there is no ``b``). The destroy event is dispatched at the step after
        the one that destroyed the object. Without ``handlers``, returns a decorator.

        Raises:
            ConfigError: for an empty or non-string tag, bad handlers, or an action
                targeting subject ``"b"``.
        """
        _check_tag("tag", tag)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("destroy", items, len(self._engine.rules), tag)

        return self._register("destroy", "on_destroy", handlers, make)

    @overload
    def every(self, seconds: float, handlers: None = None) -> Callable[[F], F]: ...

    @overload
    def every(self, seconds: float, handlers: Sequence[Handler]) -> None: ...

    def every(
        self, seconds: float, handlers: Sequence[Handler] | None = None
    ) -> Callable[[F], F] | None:
        """Run ``handlers`` every ``seconds`` of simulated time (FR-202, FR-209).

        With ``n = round(seconds * fps * substeps)``, the rule fires at steps ``n``,
        ``2n``, ... Each firing logs a ``"timer"`` event. Callables are called as
        ``f(ctx, event)``; there are no subjects, so actions must target an object
        handle. Without ``handlers``, returns a decorator.

        Raises:
            ConfigError: if ``seconds`` is not a positive finite number or rounds to 0
                steps, for bad handlers, or an action targeting ``"a"``/``"b"``.
        """
        period = self._timer_steps(seconds)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("timer", items, len(self._engine.rules), period=period)

        return self._register("timer", "every", handlers, make)

    @overload
    def at(self, seconds: float, handlers: None = None) -> Callable[[F], F]: ...

    @overload
    def at(self, seconds: float, handlers: Sequence[Handler]) -> None: ...

    def at(
        self, seconds: float, handlers: Sequence[Handler] | None = None
    ) -> Callable[[F], F] | None:
        """Run ``handlers`` once, at step ``round(seconds * fps * substeps)``.

        Logs one ``"timer"`` event. Callables are called as ``f(ctx, event)``; there
        are no subjects. Without ``handlers``, returns a decorator.

        Raises:
            ConfigError: if ``seconds`` is not a positive finite number or rounds to
                step 0, for bad handlers, or an action targeting ``"a"``/``"b"``.
        """
        at_step = self._timer_steps(seconds)

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("timer", items, len(self._engine.rules), at_step=at_step)

        return self._register("timer", "at", handlers, make)

    def _timer_steps(self, seconds: object) -> int:
        steps = round(_positive_number("seconds", seconds) * self._rate)
        if steps == 0:
            raise ConfigError(
                f"seconds must be at least half a physics step (1/{self._rate} s); got {seconds!r}"
            )
        return steps

    @overload
    def when(
        self, predicate: Callable[["Scene"], object], handlers: None = None
    ) -> Callable[[F], F]: ...

    @overload
    def when(self, predicate: Callable[["Scene"], object], handlers: Sequence[Handler]) -> None: ...

    def when(
        self, predicate: Callable[["Scene"], object], handlers: Sequence[Handler] | None = None
    ) -> Callable[[F], F] | None:
        """Run ``handlers`` once, the first time ``predicate(scene)`` is true.

        The predicate is evaluated after every frame's last step and command
        application (``scene.frame`` already counts that frame). When it first returns
        true, one ``"condition"`` event is logged, the handlers run and their commands
        are applied at once; the rule never fires again. Callables are called as
        ``f(ctx, event)``; there are no subjects. Without ``handlers``, returns a
        decorator.

        Raises:
            ConfigError: if ``predicate`` is not callable, for bad handlers, or an
                action targeting ``"a"``/``"b"``.
        """
        if not callable(predicate) or isinstance(predicate, ACTION_TYPES):
            raise ConfigError(f"predicate must be a callable f(scene) -> bool; got {predicate!r}")

        def make(items: tuple[Handler, ...]) -> Rule:
            return Rule("condition", items, len(self._engine.rules), predicate=predicate)

        return self._register("condition", "when", handlers, make)

    def _register(
        self,
        kind: RuleKind,
        method: str,
        handlers: Sequence[Handler] | None,
        make: Callable[[tuple[Handler, ...]], Rule],
    ) -> Callable[[F], F] | None:
        if handlers is None:

            def decorator(fn: F) -> F:
                if not callable(fn) or isinstance(fn, ACTION_TYPES):
                    raise ConfigError(f"handler must be a callable; got {fn!r}")
                self._engine.add(make((fn,)))
                return fn

            return decorator
        if not isinstance(handlers, list | tuple) or not all(
            isinstance(h, ACTION_TYPES) or callable(h) for h in handlers
        ):
            raise ConfigError(
                "handlers must be a list of actions such as A.play(...) or callables; "
                f"got {handlers!r}"
            )
        for h in handlers:
            if isinstance(h, Particles) and h.pos is None and kind in ("timer", "condition"):
                raise ConfigError(
                    f"pos is required for A.particles on a {kind} rule ({method}): its events "
                    "have no position; pass A.particles(pos=(x, y))"
                )
            target = getattr(h, "target", None)
            if isinstance(target, str) and target not in SUBJECTS[kind]:
                raise ConfigError(
                    f"{h!r} targets subject {target!r}, which a {kind} rule ({method}) "
                    f"does not have; target an object handle instead"
                )
        self._engine.add(make(tuple(handlers)))
        return None

    def _dispatch(self, events: Sequence[Event]) -> None:
        """Run the rules for ``events`` (outside collision callbacks).

        Built-in actions and callbacks only queue world changes (applied by
        ``_apply_commands``); play handlers trigger notes at once via ``_trigger``.
        """
        self._engine.dispatch(tuple(events))

    def _trigger(self, play: Play, ev: Event, a: WorldObject | None) -> None:
        """Start a note for ``play`` on ``ev`` if the trigger policy allows (FR-106, FR-211).

        Impacts slower than ``min_impact_speed`` are ignored (events without a speed
        are exempt and play at ``play.gain``); one play action re-triggers for the
        same subject ``a`` only after ``min_retrigger_interval``; at most
        ``max_triggers_per_frame`` notes start per ``ev.frame`` (later ones dropped in
        dispatch order). Only notes that play advance a ``Scale``'s cursor (FR-103).
        A ``Melody`` hit plays its next chord: one note per chord note at the same
        offset, each at the hit's gain times its velocity, counted as one trigger for
        the per-frame cap and the retrigger interval (FR-307).
        """
        cfg = self.config
        audio = cfg.audio
        speed = ev.speed
        if speed is not None and speed < audio.min_impact_speed:
            return
        last = self._last_trigger.get((play, a))
        # One correctly rounded division of the exact step gap: a gap of exactly the
        # interval is never misjudged as shorter.
        if last is not None and (ev.step - last) / self._rate < audio.min_retrigger_interval:
            return
        started = self._frame_triggers.get(ev.frame)
        if started is None:
            for old in [f for f in self._frame_triggers if f < ev.frame]:
                del self._frame_triggers[old]
            started = 0
        if started >= audio.max_triggers_per_frame:
            return
        src = play.source
        notes: tuple[tuple[float, float], ...]  # (hz, gain factor)
        if isinstance(src, Note):
            notes = ((src.hz, 1.0),)
        elif isinstance(src, Scale):
            index = self._cursor.get(src, 0)
            self._cursor[src] = (index + 1) % len(src.hz)
            notes = ((src.hz[index], 1.0),)
        else:
            index = self._cursor.get(src, 0)
            self._cursor[src] = (index + 1) % len(src.chords)
            notes = src.chords[index]
        gain = play.gain
        if speed is not None:
            gain *= min(1.0, speed / audio.reference_speed) ** 0.5
        offset = sample_offset(ev.step, cfg.fps, cfg.substeps)
        for hz, factor in notes:
            self._triggers.append(
                NoteTrigger(
                    step=ev.step,
                    offset=offset,
                    voice=src.voice,
                    hz=hz,
                    gain=gain * factor,
                )
            )
        self._last_trigger[(play, a)] = ev.step
        self._frame_triggers[ev.frame] = started + 1

    @property
    def _frames_done(self) -> int:
        """Frames simulated once the current frame completes (``F`` of FR-209)."""
        return self.frame + 1 if self._in_frame else self.frame

    def _apply_commands(self) -> None:
        """Apply the queued commands in FIFO order and empty the queue."""
        queue, self._queue = self._queue, []
        for cmd in queue:
            apply(self, cmd)

    def _register_object(self, obj: WorldObject, shapes: Iterable[pymunk.Shape]) -> None:
        index = self._next_index
        self._next_index += 1
        self._indices[obj] = index
        self._recorder.register(index, obj, shapes)
        self._objects.append(obj)

    def _remove(self, obj: WorldObject) -> None:
        """Destroy a live ``obj`` now and log its destroy event (for the next step)."""
        shapes: list[pymunk.Shape]
        if isinstance(obj, Ball):
            shapes = [obj.shape]
            speed = math.hypot(*obj.velocity)
            position = obj.position
            self._balls.remove(obj)
        else:
            shapes = list(obj.shapes)
            speed = 0.0
            position = obj.center
            self._rings.remove(obj)
        # Removing runs the recorder's ``separate`` for current contacts right here.
        self.space.remove(obj.body, *shapes)
        for shape in shapes:
            self._recorder.owners.pop(shape, None)
        self._objects.remove(obj)
        obj.alive = False
        ev = Event(
            "destroy", self._step, self._sim_frame, self._step / self._rate, (obj,), speed, position
        )
        self._events.append(ev)
        self._cascade.append(ev)

    def _set_ball_color(self, ball: Ball, source: ColorSource) -> None:
        """Give ``ball`` a colour or mode; a hue cycle takes its next hue now (FR-306)."""
        if isinstance(source, HueCycle):
            ball._set_color(self._fx.next_hue(source), None, source)
        elif isinstance(source, BySpeed | ByGeneration):
            ball._set_color(ball.color, source, None)
        else:
            ball._set_color(source, None, None)

    def _spawn_ball(self, spec: BallSpec, *, generation: int) -> Ball:
        """Add a ball now (command application) and log its spawn event (for the next step)."""
        plain = isinstance(spec.color, tuple)
        ball = Ball(
            self.space,
            pos=spec.pos,
            radius=spec.radius,
            velocity=spec.velocity,
            elasticity=spec.elasticity,
            color=spec.color if isinstance(spec.color, tuple) else (255, 255, 255),
            tags=spec.tags,
            trail=spec.trail,
            glow=spec.glow,
        )
        ball.generation = generation
        if not plain:
            self._set_ball_color(ball, spec.color)
        if spec.constant_speed:
            ball.constant_speed = True
            ball.target_speed = math.hypot(*ball.velocity)
        self._register_object(ball, [ball.shape])
        self._balls.append(ball)
        ev = Event(
            "spawn",
            self._step,
            self._sim_frame,
            self._step / self._rate,
            (ball,),
            math.hypot(*ball.velocity),
            ball.position,
        )
        self._events.append(ev)
        self._cascade.append(ev)
        return ball

    def _inherit(self, parent: Ball, child: Ball) -> None:
        """Copy ``parent``'s rule cooldown and note retrigger timestamps to ``child`` (C7)."""
        self._engine.inherit(self._indices[parent], self._indices[child])
        for (action, obj), step in list(self._last_trigger.items()):
            if obj is parent:
                self._last_trigger[(action, child)] = step

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
        color: ColorLike | Fixed = "#ffffff",
        gap_degrees: float = 0.0,
        angular_velocity: float = 0.0,
        segments: int = 128,
        elasticity: float = 1.0,
        tags: Iterable[str] = (),
        glow: float | bool = 0.0,
    ) -> CircleBoundary:
        """Add a ring boundary; see :class:`CircleBoundary`.

        ``angular_velocity`` is in degrees per second, positive = clockwise.
        ``color`` is a colour value or ``C.fixed(...)`` (no dynamic modes, FR-306).
        ``glow`` (0..4, or a bool for 1/0) adds a blurred light along the drawn arc,
        in the colour the ring is drawn in (FR-304); visual only.

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
            glow=glow,
        )
        for ball in self._balls:
            self._check_tunnelling(ball, ring)
        self._register_object(ring, ring.shapes)
        self._rings.append(ring)
        return ring

    def add_ball(
        self,
        *,
        pos: Vec,
        radius: float,
        velocity: Vec = (0.0, 0.0),
        elasticity: float = 1.0,
        color: ColorSpec = "#ffffff",
        tags: Iterable[str] = (),
        constant_speed: bool = False,
        trail: bool = False,
        glow: float | bool = 0.0,
    ) -> Ball:
        """Add a dynamic ball; its speed is clamped to ``config.max_speed``.

        With ``constant_speed=True``, after every step (after the clamp) the velocity
        is rescaled to the initial speed ``|velocity|`` (``ball.target_speed``),
        keeping its direction; a zero velocity stays zero (FR-212).

        ``color`` is a colour value or a colour mode (FR-306): ``C.fixed(c)`` is ``c``;
        ``C.hue_cycle()`` gives each new ball the mode's next hue; ``C.by_speed()`` and
        ``C.by_generation()`` are evaluated whenever the ball is drawn.

        Visual only (FR-303, FR-304): ``trail=True`` leaves a fading trail of the
        ball's diameter (length ``effects.trail_seconds``); ``glow`` (0..4, or a bool
        for 1/0) adds a blurred light in the ball's drawn colour. Split children and
        spawned balls inherit both from their parent.

        Raises:
            ConfigError: if any option is invalid, the scene already has
                ``config.max_balls`` live balls, a ball at ``max_speed`` could pass
                through a ring in one step (see ``_check_tunnelling``), or
                ``constant_speed`` is set with an initial speed of 0 or above
                ``max_speed``.
        """
        source = color_source(color)
        if type(constant_speed) is not bool:
            raise ConfigError(f"constant_speed must be True or False; got {constant_speed!r}")
        if constant_speed:
            self._check_constant_speed(_vec("velocity", velocity))
        if len(self._balls) >= self.config.max_balls:
            raise ConfigError(
                f"max_balls is {self.config.max_balls}; cannot add another ball "
                f"(raise Scene(max_balls=...))"
            )
        ball = Ball(
            self.space,
            pos=pos,
            radius=radius,
            velocity=velocity,
            elasticity=elasticity,
            color=source if isinstance(source, tuple) else (255, 255, 255),
            tags=tags,
            trail=trail,
            glow=glow,
        )
        for ring in self._rings:
            self._check_tunnelling(ball, ring)
        if not isinstance(source, tuple):
            self._set_ball_color(ball, source)
        if constant_speed:
            ball.constant_speed = True
            ball.target_speed = math.hypot(*ball.velocity)
        self._register_object(ball, [ball.shape])
        self._balls.append(ball)
        return ball

    def _check_constant_speed(self, velocity: Vec) -> None:
        """Reject a constant-speed initial velocity of speed 0 or above ``max_speed``."""
        speed = math.hypot(*velocity)
        if not 0 < speed <= self.config.max_speed:
            raise ConfigError(
                f"constant_speed needs an initial speed in (0, max_speed={self.config.max_speed}]; "
                f"got velocity {velocity!r} (speed {speed:g})"
            )

    def _check_tunnelling(self, ball: Ball, ring: CircleBoundary) -> None:
        """Reject a ball/ring pair that a ball at ``max_speed`` could pass through.

        A collision is caught only if the ball cannot move past a segment's centre
        line in one step, so per-step travel must be below ``radius + thickness / 2``.
        """
        if self._tunnels(ball.radius, ring):
            travel = self.config.max_speed * self._dt
            reach = ball.radius + ring.thickness / 2
            raise ConfigError(
                f"ball radius {ball.radius} with ring thickness {ring.thickness} could tunnel: "
                f"at max_speed {self.config.max_speed} a ball moves {travel:.2f} px per step "
                f"but radius + thickness/2 is only {reach:.2f} px; increase substeps, "
                f"lower max_speed, or use a larger ball or thicker ring"
            )

    def _tunnels(self, radius: float, ring: CircleBoundary) -> bool:
        """Whether a ball of ``radius`` at ``max_speed`` could pass through ``ring`` in one step."""
        return self.config.max_speed * self._dt >= radius + ring.thickness / 2

    def step_frame(self) -> None:
        """Advance the simulation by one frame (``substeps`` fixed physics steps).

        After each step: collect its collision events, clamp speeds, detect escapes,
        emit due timer events, dispatch the previous step's spawn/destroy events and
        then this step's events to the rules, and apply the queued commands (FR-203).
        After the frame, ``when`` predicates are checked (FR-209), then impact
        particles advance by one frame (FR-305, visual only).
        """
        max_speed = self.config.max_speed
        rec = self._recorder
        engine = self._engine
        frame = self.frame
        rec.frame = frame
        self._sim_frame = frame
        self._in_frame = True
        try:
            for _ in range(self.config.substeps):
                self._step += 1
                step = self._step
                rec.step = step
                self.space.step(self._dt)
                events = rec.flush()
                self._events.extend(events)
                # Clamp after the whole step: collision impulses land after velocity
                # integration, so a clamp inside velocity_func would miss them.
                for ball in self._balls:
                    ball.clamp_speed(max_speed)
                    if ball.constant_speed:
                        ball.renormalize()
                escapes = engine.escapes(step, frame)
                self._events.extend(escapes)
                timers = engine.due_timers(step, frame)
                self._events.extend(ev for _, ev in timers)
                pending = self._cascade + events + escapes
                self._cascade = []
                if engine.rules and pending:
                    self._dispatch(pending)
                for rule, ev in timers:
                    engine.run(rule, ev)
                if self._queue:
                    self._apply_commands()
                if not self._hashed and len(self._balls) >= SPATIAL_HASH_BALLS:
                    self._use_spatial_hash()
        finally:
            self._in_frame = False
        self.frame += 1
        engine.conditions(self._step, frame)
        fx = self._fx
        if fx.particles or fx.pending:
            fx.advance(self.config.fps)

    def _use_spatial_hash(self) -> None:
        """Switch the space to pymunk's spatial hash, once (FR-212, C14)."""
        self._hashed = True
        dim = 2 * max(ball.radius for ball in self._balls)
        self.space.use_spatial_hash(dim, SPATIAL_HASH_COUNT)

    def draw(self, renderer: Renderer) -> None:
        """Draw the background, trails, every live object and glows (FR-303, FR-304).

        Order: background; the trail layer (only while a ball has ``trail``); objects
        in insertion order; impact particles (FR-305); the glow layer (only while an
        object has ``glow``). An
        object flashing at the current frame (``A.flash``) is drawn, and glows, in its
        flash colour blended linearly back to its base colour. Drawing never changes
        the simulation; it only updates effect state keyed on ``frame``, so redrawing
        a frame gives the same image.
        """
        renderer.clear(self.config.background)
        effects = self.config.effects
        fx = self._fx
        indices = self._indices
        trail_balls: list[TrailBall] = [
            (indices[b], b.position, b.radius, b.color) for b in self._balls if b.trail
        ]
        if trail_balls or fx.trail_active is not None:
            update = fx.trail_update(trail_balls, self.frame, effects.trail_keep(self.config.fps))
            if update is not None:
                segments, keep, reset = update
                renderer.trails(segments, keep=keep, reset=reset)
        flashes = self._flash
        lights: list[GlowDisc | GlowArc] = []
        for obj in self._objects:
            color: Color | None = None
            if flashes:
                state = flashes.get(indices[obj])
                if state is not None:
                    color = _flash_color(state, obj.color, self.frame)
            obj.draw(renderer, color)
            if obj.glow > 0:
                drawn = obj.color if color is None else color
                if isinstance(obj, Ball):
                    lights.append(GlowDisc(obj.position, obj.radius, drawn, obj.glow))
                else:
                    light = obj.glow_light(drawn)
                    if light is not None:
                        lights.append(light)
        for p in fx.particles:
            renderer.circle((p.x, p.y), p.size, p.color, alpha=1 - p.age / p.life)
        if lights:
            renderer.glow(lights, blur=effects.glow_blur)

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

        Parent directories are created. ffmpeg is checked before simulating. If
        any rule has an ``A.play`` or any note was triggered, the mix is limited to a
        true peak of ``audio.peak_dbfs`` and muxed in as 48 kHz stereo AAC; otherwise
        the MP4 has no audio stream.

        Raises:
            FfmpegError: if ffmpeg is missing or fails.
        """
        require_ffmpeg()
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        cfg = self.config
        if not self._engine.rules:
            with FfmpegWriter(path, cfg.width, cfg.height, cfg.fps) as writer:
                for frame in self.frames():
                    writer.write(frame)
            return path
        with tempfile.TemporaryDirectory(dir=path.parent, prefix=".bouncekit-") as tmp:
            video, wav = Path(tmp) / "video.mp4", Path(tmp) / "audio.wav"
            with FfmpegWriter(video, cfg.width, cfg.height, cfg.fps) as writer:
                for frame in self.frames():
                    writer.write(frame)
            if not (self.has_sound or self._triggers):
                video.replace(path)
                return path
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


def _check_tag(name: str, tag: object) -> None:
    if not isinstance(tag, str) or not tag:
        raise ConfigError(f"{name} must be a non-empty string; got {tag!r}")


def _flash_color(state: tuple[Color, int, int], base: Color, frame: int) -> Color | None:
    """The flash colour of ``state`` at ``frame``, or ``None`` outside the flash."""
    color, start, frames = state
    k = frame - start
    if not 0 <= k < frames:
        return None
    t = k / frames
    r, g, b = (round(f + (c - f) * t) for f, c in zip(color, base, strict=True))
    return (r, g, b)
