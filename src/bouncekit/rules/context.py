"""ActionContext: what a rule handler sees and can do (FR-203)."""

import random
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from bouncekit.actions import (
    Particles,
    Play,
    Spawn,
    Split,
    Target,
    Value,
    end_after,
    flash,
    particles,
    play,
    resize,
    set_velocity,
    spawn,
    split,
)
from bouncekit.colors import (
    ByGeneration,
    BySpeed,
    ColorLike,
    ColorSpec,
    HueCycle,
    color_source,
    ring_color,
)
from bouncekit.config import Vec, _vec
from bouncekit.errors import ConfigError
from bouncekit.events import Event, WorldObject
from bouncekit.rules.commands import (
    BallSpec,
    DestroyCmd,
    EndCmd,
    FlashCmd,
    RecolorCmd,
    ResizeCmd,
    SpawnCmd,
    SplitCmd,
    VelocityCmd,
)
from bouncekit.sound import Source
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["ActionContext"]


class ActionContext:
    """Passed to every handler as ``ctx``; one per (event, rule).

    Methods that change the world (``destroy``, ``split``, ``spawn``, ``recolor``,
    ``resize``, ``set_velocity``, ``flash``, ``end_after``) only queue a command: the
    change is applied after the step's dispatch, never while handlers run. ``play``
    produces a note trigger immediately (audio only); ``particles`` creates a
    visual-only burst immediately. Bad arguments raise
    ``ConfigError`` at the call.

    Attributes:
        scene: the scene being simulated.
        event: the event being dispatched.
        a: the rule's first subject (collision: the object carrying ``tag_a``;
            escape: the ball; spawn/destroy: the object), or ``None`` (timer,
            condition).
        b: the rule's second subject (collision: the object carrying ``tag_b``;
            escape: the ring), or ``None``.
        rng: ``scene.rng``; use it for any randomness so renders stay deterministic.
        time: ``event.time`` in seconds.
    """

    def __init__(
        self, scene: "Scene", event: Event, a: WorldObject | None, b: WorldObject | None
    ) -> None:
        """Create a context for dispatching ``event`` with subjects ``a`` and ``b``."""
        self.scene = scene
        self.event = event
        self.a = a
        self.b = b
        self.rng: random.Random = scene.rng
        self.time: float = event.time

    def _resolve(self, target: Target) -> WorldObject | None:
        if target == "a":
            return self.a
        if target == "b":
            return self.b
        return target

    def destroy(self, obj: WorldObject) -> None:
        """Queue removal of ``obj`` (a ball or ring) after dispatch.

        Raises:
            ConfigError: if ``obj`` is not a ball or ring handle.
        """
        if not isinstance(obj, Ball | CircleBoundary):
            raise ConfigError(f"obj must be a ball or ring handle; got {obj!r}")
        self.scene._queue.append(DestroyCmd(obj))

    def split(
        self,
        ball: Ball,
        *,
        into: int = 2,
        spread_degrees: float = 30.0,
        radius_scale: float = 1.0,
        max_total: int | None = None,
    ) -> None:
        """Queue a split of ``ball``; options and refusal rules as ``A.split`` (FR-206).

        A ring is accepted and ignored (no-op).

        Raises:
            ConfigError: for bad options, or if ``ball`` is not a ball or ring handle.
        """
        action = split(
            into=into, spread_degrees=spread_degrees, radius_scale=radius_scale, max_total=max_total
        )
        if not isinstance(ball, Ball | CircleBoundary):
            raise ConfigError(f"ball must be a ball handle; got {ball!r}")
        if isinstance(ball, Ball):
            self._split_action(ball, action)

    def _split_action(self, ball: Ball, action: Split) -> None:
        self.scene._queue.append(
            SplitCmd(
                ball, action.into, action.spread_degrees, action.radius_scale, action.max_total
            )
        )

    def spawn(
        self,
        *,
        pos: Value[Vec],
        radius: float,
        velocity: Value[Vec] = (0.0, 0.0),
        count: int = 1,
        color: Value[ColorSpec] = "#ffffff",
        tags: Iterable[str] = ("ball",),
        elasticity: float = 1.0,
        constant_speed: bool = False,
        max_total: int | None = None,
        trail: bool = False,
        glow: float | bool = 0.0,
    ) -> None:
        """Queue ``count`` new balls; options and refusal rules as ``A.spawn`` (FR-207).

        Callable ``pos``/``velocity``/``color`` are evaluated now, per ball, in ball order.
        ``color`` may be a colour mode (FR-306), resolved when the balls are added.

        Raises:
            ConfigError: for bad options or a callable returning an invalid value
                (with ``constant_speed``, also a speed of 0 or above ``max_speed``).
        """
        self._spawn_action(
            spawn(
                pos=pos,
                radius=radius,
                velocity=velocity,
                count=count,
                color=color,
                tags=tags,
                elasticity=elasticity,
                constant_speed=constant_speed,
                max_total=max_total,
                trail=trail,
                glow=glow,
            )
        )

    def _spawn_action(self, action: Spawn) -> None:
        specs: list[BallSpec] = []
        step = 2 * action.radius + 1
        for i in range(action.count):
            x, y = _vec("pos", self._eval(action.pos))
            velocity = _vec("velocity", self._eval(action.velocity))
            color = color_source(self._eval(action.color))
            if action.constant_speed:
                self.scene._check_constant_speed(velocity)
            offset = (i - (action.count - 1) / 2) * step
            specs.append(
                BallSpec(
                    (x + offset, y),
                    action.radius,
                    velocity,
                    color,
                    action.tags,
                    action.elasticity,
                    action.constant_speed,
                    action.trail,
                    action.glow,
                )
            )
        self.scene._queue.append(SpawnCmd(tuple(specs), action.max_total))

    def _eval(self, value: object) -> object:
        if callable(value):
            fn: Callable[[ActionContext], object] = value
            return fn(self)
        return value

    def recolor(self, obj: WorldObject, color: ColorSpec) -> None:
        """Queue setting the base colour of ``obj`` (a ball or ring) (FR-210, FR-306).

        A ball takes a colour value or any colour mode (a hue cycle advances when the
        command is applied); a ring takes a colour value or ``C.fixed(...)`` only.

        Raises:
            ConfigError: if ``obj`` is not a ball or ring handle or ``color`` is invalid.
        """
        _check_object("obj", obj)
        if isinstance(obj, CircleBoundary):
            self.scene._queue.append(RecolorCmd(obj, ring_color(color)))
        else:
            self.scene._queue.append(RecolorCmd(obj, color_source(color)))

    def resize(self, ball: Ball, radius: float) -> None:
        """Queue changing ``ball``'s radius; refusal rules as ``A.resize`` (FR-210).

        A ring is accepted and ignored (no-op).

        Raises:
            ConfigError: if ``radius`` is not positive and finite, or ``ball`` is not a
                ball or ring handle.
        """
        action = resize(radius=radius)
        _check_object("ball", ball)
        if isinstance(ball, Ball):
            self._resize_action(ball, action.radius, None)

    def _resize_action(self, ball: Ball, radius: float | None, scale: float | None) -> None:
        self.scene._queue.append(ResizeCmd(ball, radius, scale))

    def set_velocity(self, ball: Ball, velocity: Vec) -> None:
        """Queue setting ``ball``'s velocity, clamped to ``max_speed`` (FR-210).

        A constant-speed ball's ``target_speed`` becomes the new speed. A ring is
        accepted and ignored (no-op).

        Raises:
            ConfigError: if ``velocity`` is not two finite numbers, or ``ball`` is not a
                ball or ring handle.
        """
        value = _vec("velocity", velocity)
        set_velocity(velocity=value)
        _check_object("ball", ball)
        if isinstance(ball, Ball):
            self._velocity_action(ball, value, None)

    def _velocity_action(self, ball: Ball, velocity: Vec | None, speed: float | None) -> None:
        self.scene._queue.append(VelocityCmd(ball, velocity, speed))

    def flash(
        self, obj: WorldObject, *, seconds: float = 0.08, color: ColorLike = "#ffffff"
    ) -> None:
        """Queue a flash of ``obj`` (a ball or ring); visual only, as ``A.flash`` (FR-210).

        Raises:
            ConfigError: if ``obj`` is not a ball or ring handle, ``seconds`` is
                negative or not finite, or ``color`` is invalid.
        """
        action = flash(obj, seconds=seconds, color=color)
        frames = max(1, round(action.seconds * self.scene.config.fps))
        self.scene._queue.append(FlashCmd(obj, action.color, frames))

    def particles(
        self,
        *,
        pos: Vec,
        count: int = 12,
        speed: float = 400.0,
        lifetime: float = 0.5,
        size: float = 3.0,
        color: ColorSpec | None = None,
        drag: float = 2.0,
    ) -> None:
        """Burst impact particles at ``pos`` now; options as ``A.particles`` (FR-305).

        Visual only: draws from ``scene.fx_rng``, never ``scene.rng``.

        Raises:
            ConfigError: for bad options or a ``pos`` that is not a 2-vector.
        """
        action = particles(
            count=count,
            speed=speed,
            lifetime=lifetime,
            size=size,
            color=color,
            drag=drag,
            pos=_vec("pos", pos),
        )
        self._particles_action(action)

    def _particles_action(self, action: Particles) -> None:
        scene = self.scene
        pos = action.pos if action.pos is not None else self.event.position
        if pos is None:
            return  # unreachable for registered rules (checked at registration)
        spec = action.color
        a = self.a
        if spec is None:
            color = (255, 255, 255) if a is None else a.color
        elif isinstance(spec, HueCycle):
            color = scene._fx.next_hue(spec, burst=True)
        elif isinstance(spec, BySpeed):
            color = spec.color_for(a.velocity if isinstance(a, Ball) else (0.0, 0.0))
        elif isinstance(spec, ByGeneration):
            color = spec.color_for(a.generation if isinstance(a, Ball) else 0)
        else:
            color = spec
        cfg = scene.config
        scene._fx.burst(
            scene.fx_rng,
            pos=pos,
            count=action.count,
            speed=action.speed,
            lifetime=action.lifetime,
            size=action.size,
            color=color,
            drag=action.drag,
            fps=cfg.fps,
            capacity=cfg.effects.max_particles,
        )

    def play(self, source: Source, *, gain: float = 1.0, pan: float = 0.0) -> None:
        """Trigger ``source`` now, subject to the audio trigger policy (FR-106, FR-211).

        Calls with an equal ``(source, gain, pan)`` share one retrigger timer per
        subject ``a``, like a single ``A.play`` action. ``pan`` in [0, 1] pans the
        note by the event's x position, as for ``A.play`` (FR-309).

        Raises:
            ConfigError: if ``source`` is not a sound source, ``gain`` is negative or
                ``pan`` is not a number in [0, 1].
        """
        action = play(source, gain=gain, pan=pan)
        self._play_action(self.scene._engine.shared_play(action))

    def _play_action(self, action: Play) -> None:
        self.scene._trigger(action, self.event, self.a)

    def end_after(self, seconds: float) -> None:
        """Queue ending the video ``seconds`` after the current frame (FR-209).

        ``scene.total_frames`` becomes ``min(total_frames, F + round(seconds * fps))``,
        where ``F`` is the number of frames simulated once the current frame
        completes. The earliest end wins.

        Raises:
            ConfigError: if ``seconds`` is not a finite number >= 0.
        """
        action = end_after(seconds)
        frames = round(action.seconds * self.scene.config.fps)
        self.scene._queue.append(EndCmd(frames))


def _check_object(name: str, obj: object) -> None:
    if not isinstance(obj, Ball | CircleBoundary):
        raise ConfigError(f"{name} must be a ball or ring handle; got {obj!r}")
