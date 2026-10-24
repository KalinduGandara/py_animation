"""Built-in rule actions (FR-104, FR-206..FR-210).

play, destroy, split, spawn, recolor, resize, set_velocity, flash and end_after.

Actions are immutable values compared by identity. When a rule fires, each action's
``run(ctx)`` resolves its target and calls the matching :class:`ActionContext`
method, so built-ins and Python callbacks go through the same path. Every action
except ``play`` only queues a command; the scene applies it after dispatch.

A play's final gain also depends on impact speed (FR-106, see ``AudioConfig``).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.config import (
    Vec,
    _finite_number,
    _non_negative_number,
    _positive_int,
    _positive_number,
    _tags,
    _vec,
)
from bouncekit.errors import ConfigError
from bouncekit.sound import Note, Scale, Source
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.rules.context import ActionContext

__all__ = [
    "Action",
    "Destroy",
    "EndAfter",
    "Flash",
    "Handler",
    "Play",
    "Recolor",
    "Resize",
    "SetVelocity",
    "Spawn",
    "Split",
    "Target",
    "destroy",
    "end_after",
    "flash",
    "play",
    "recolor",
    "resize",
    "set_velocity",
    "spawn",
    "split",
]

type Target = Literal["a", "b"] | Ball | CircleBoundary
"""Which object an action acts on: the rule's subject ``"a"``/``"b"`` or an object handle."""


def _target(value: object) -> Target:
    if value in ("a", "b") or isinstance(value, Ball | CircleBoundary):
        return value
    raise ConfigError(f"target must be 'a', 'b' or a ball/ring handle; got {value!r}")


@dataclass(frozen=True, eq=False)
class Play:
    """Play a note from ``source`` at ``gain`` when the rule fires.

    Compared by identity: each ``play(...)`` call is a distinct action. Not
    subject to rule cooldowns; the audio trigger policy applies (FR-106).
    """

    source: Source
    gain: float = 1.0

    def run(self, ctx: "ActionContext") -> None:
        """Trigger the note now (audio only)."""
        ctx._play_action(self)


@dataclass(frozen=True, eq=False)
class Destroy:
    """Remove the target ball or ring from the scene after dispatch."""

    target: Target = "a"

    def run(self, ctx: "ActionContext") -> None:
        """Queue the target's removal (no-op if the subject is missing)."""
        obj = ctx._resolve(self.target)
        if obj is not None:
            ctx.destroy(obj)


@dataclass(frozen=True, eq=False)
class Split:
    """Split the target ball into ``into`` balls after dispatch (see :func:`split`)."""

    into: int = 2
    spread_degrees: float = 30.0
    radius_scale: float = 1.0
    max_total: int | None = None
    target: Target = "a"

    def run(self, ctx: "ActionContext") -> None:
        """Queue the split (no-op if the subject is missing or is not a ball)."""
        obj = ctx._resolve(self.target)
        if isinstance(obj, Ball):
            ctx._split_action(obj, self)


type Value[T] = T | Callable[["ActionContext"], T]
"""A value, or a callable ``f(ctx)`` evaluated per ball while the rule runs."""


@dataclass(frozen=True, eq=False)
class Spawn:
    """Add ``count`` new balls after dispatch (see :func:`spawn`).

    ``pos``, ``velocity`` and ``color`` are validated values or callables ``f(ctx)``.
    """

    pos: Value[Vec]
    radius: float
    velocity: Value[Vec] = (0.0, 0.0)
    count: int = 1
    color: Value[Color] = (255, 255, 255)
    tags: frozenset[str] = frozenset({"ball"})
    elasticity: float = 1.0
    max_total: int | None = None
    constant_speed: bool = False

    def run(self, ctx: "ActionContext") -> None:
        """Evaluate the values now (in ball order) and queue the new balls."""
        ctx._spawn_action(self)


@dataclass(frozen=True, eq=False)
class EndAfter:
    """End the video ``seconds`` after the current frame (see :func:`end_after`)."""

    seconds: float

    def run(self, ctx: "ActionContext") -> None:
        """Queue the new end."""
        ctx.end_after(self.seconds)


@dataclass(frozen=True, eq=False)
class Recolor:
    """Set the target's base colour after dispatch (see :func:`recolor`)."""

    color: Value[Color]
    target: Target = "a"

    def run(self, ctx: "ActionContext") -> None:
        """Evaluate the colour now and queue the change (no-op if the subject is missing)."""
        obj = ctx._resolve(self.target)
        if obj is not None:
            ctx.recolor(obj, ctx._eval(self.color))  # type: ignore[arg-type]


@dataclass(frozen=True, eq=False)
class Resize:
    """Change the target ball's radius after dispatch (see :func:`resize`)."""

    radius: float | None = None
    scale: float | None = None
    target: Target = "a"

    def run(self, ctx: "ActionContext") -> None:
        """Queue the resize (no-op if the subject is missing or is not a ball)."""
        obj = ctx._resolve(self.target)
        if isinstance(obj, Ball):
            ctx._resize_action(obj, self.radius, self.scale)


@dataclass(frozen=True, eq=False)
class SetVelocity:
    """Set or rescale the target ball's velocity after dispatch (see :func:`set_velocity`)."""

    velocity: Value[Vec] | None = None
    speed: float | None = None
    target: Target = "a"

    def run(self, ctx: "ActionContext") -> None:
        """Evaluate the velocity now and queue the change (no-op unless the subject is a ball)."""
        obj = ctx._resolve(self.target)
        if not isinstance(obj, Ball):
            return
        if self.velocity is None:
            ctx._velocity_action(obj, None, self.speed)
        else:
            ctx.set_velocity(obj, ctx._eval(self.velocity))  # type: ignore[arg-type]


@dataclass(frozen=True, eq=False)
class Flash:
    """Briefly draw the target in another colour (see :func:`flash`); visual only."""

    target: Target = "a"
    seconds: float = 0.08
    color: Color = (255, 255, 255)

    def run(self, ctx: "ActionContext") -> None:
        """Queue the flash (no-op if the subject is missing)."""
        obj = ctx._resolve(self.target)
        if obj is not None:
            ctx.flash(obj, seconds=self.seconds, color=self.color)


type Action = Play | Destroy | Split | Spawn | Recolor | Resize | SetVelocity | Flash | EndAfter
"""Any built-in action."""

type Handler = Action | Callable[..., object]
"""A rule handler: a built-in action or a Python callable (see ``Scene.on_collision``)."""

ACTION_TYPES: tuple[type, ...] = (
    Play,
    Destroy,
    Split,
    Spawn,
    Recolor,
    Resize,
    SetVelocity,
    Flash,
    EndAfter,
)


def play(source: Source, *, gain: float = 1.0) -> Play:
    """Return an action that plays ``source`` (``S.note(...)``/``S.scale(...)``) at ``gain`` (>= 0).

    Raises:
        ConfigError: if ``source`` is not a sound source or ``gain`` is negative.
    """
    if not isinstance(source, Note | Scale):
        raise ConfigError(
            f"source must be a sound source such as S.note(...) or S.scale(...); got {source!r}"
        )
    return Play(source=source, gain=_non_negative_number("gain", gain))


def destroy(*, target: Target = "a") -> Destroy:
    """Return an action that removes ``target`` (a ball or ring) from the scene.

    The object leaves the physics space, ``scene.objects`` and the drawing after the
    step's dispatch, ``obj.alive`` becomes ``False`` and one ``"destroy"`` event is
    logged (dispatched to ``on_destroy`` rules at the next step).

    Raises:
        ConfigError: if ``target`` is not ``"a"``, ``"b"`` or a ball/ring handle.
    """
    return Destroy(target=_target(target))


def _max_total(value: object) -> int | None:
    if value is not None:
        _positive_int("max_total", value)
    return value  # type: ignore[return-value]


def split(
    *,
    into: int = 2,
    spread_degrees: float = 30.0,
    radius_scale: float = 1.0,
    max_total: int | None = None,
    target: Target = "a",
) -> Split:
    """Return an action that splits the target ball into ``into`` balls (FR-206).

    The ball itself stays (same handle) as child 0 and ``into - 1`` new balls are
    added. With ``s`` the ball's speed and ``theta`` its direction, child ``i`` moves at
    ``s`` in direction ``theta + spread * (i / (into - 1) - 1/2)`` and is placed
    ``(i - (into - 1) / 2) * (2 r' + 1)`` px from the ball's centre, perpendicular to
    ``theta``, where ``r' = radius * radius_scale`` is every child's radius. Children
    get ``generation + 1``, the ball's colour, tags and elasticity, and its rule
    cooldowns and note retrigger times. Each new child logs a ``"spawn"`` event.

    The split is refused (nothing changes, no error) when the live ball count would
    exceed ``config.max_balls`` or ``max_total``, or when ``r'`` could tunnel through
    a live ring. A ring target is a no-op.

    Raises:
        ConfigError: if ``into`` is not an int >= 2, ``spread_degrees`` is not in
            [0, 360], ``radius_scale`` is not positive and finite, ``max_total`` is
            not ``None`` or a positive int, or ``target`` is invalid.
    """
    if type(into) is not int or into < 2:
        raise ConfigError(f"into must be an integer >= 2; got {into!r}")
    spread = _finite_number("spread_degrees", spread_degrees)
    if not 0 <= spread <= 360:
        raise ConfigError(f"spread_degrees must be in [0, 360]; got {spread_degrees!r}")
    return Split(
        into=into,
        spread_degrees=spread,
        radius_scale=_positive_number("radius_scale", radius_scale),
        max_total=_max_total(max_total),
        target=_target(target),
    )


def _value[T](name: str, value: object, check: Callable[[str, object], T]) -> "Value[T]":
    if callable(value):
        return value
    return check(name, value)


def _color(name: str, value: object) -> Color:
    return parse_color(value)  # type: ignore[arg-type]


def spawn(
    *,
    pos: Value[Vec],
    radius: float,
    velocity: Value[Vec] = (0.0, 0.0),
    count: int = 1,
    color: Value[ColorLike] = "#ffffff",
    tags: Iterable[str] = ("ball",),
    elasticity: float = 1.0,
    constant_speed: bool = False,
    max_total: int | None = None,
) -> Spawn:
    """Return an action that adds ``count`` balls of ``radius`` (FR-207).

    ``pos``, ``velocity`` and ``color`` each take a value or a callable ``f(ctx)``,
    evaluated once per ball, in ball order, when the rule runs (use ``ctx.rng`` for
    randomness). Ball ``i`` is offset from ``pos`` by
    ``(i - (count - 1) / 2) * (2 * radius + 1)`` px along +x. Each new ball has
    generation 0 and logs a ``"spawn"`` event (dispatched at the next step).

    The whole spawn is refused (no balls, no error) when the live ball count would
    exceed ``config.max_balls`` or ``max_total``, or when ``radius`` could tunnel
    through a live ring.

    With ``constant_speed=True`` each ball keeps its initial speed (FR-212, see
    ``Scene.add_ball``); that speed must be > 0 and <= ``config.max_speed``.

    Raises:
        ConfigError: for an invalid value (a callable's result is checked when it
            is evaluated), a non-positive ``radius`` or ``count``, a bad
            ``max_total``, or ``constant_speed`` with a zero speed (a speed above
            ``max_speed`` raises when the rule runs).
    """
    _positive_int("count", count)
    _bool("constant_speed", constant_speed)
    if constant_speed and not callable(velocity) and _vec("velocity", velocity) == (0.0, 0.0):
        raise ConfigError("constant_speed needs a non-zero velocity; got (0, 0)")
    return Spawn(
        pos=_value("pos", pos, _vec),
        radius=_positive_number("radius", radius),
        velocity=_value("velocity", velocity, _vec),
        count=count,
        color=_value("color", color, _color),
        tags=_tags(tags),
        elasticity=_non_negative_number("elasticity", elasticity),
        max_total=_max_total(max_total),
        constant_speed=constant_speed,
    )


def _bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ConfigError(f"{name} must be True or False; got {value!r}")
    return value


def recolor(color: Value[ColorLike], *, target: Target = "a") -> Recolor:
    """Return an action that sets the target's base colour (FR-210).

    ``color`` is a colour value or a callable ``f(ctx)`` evaluated when the rule
    runs. Works on balls and rings.

    Raises:
        ConfigError: if ``color`` is not a colour or callable, or ``target`` is invalid.
    """
    return Recolor(color=_value("color", color, _color), target=_target(target))


def _exactly_one(names: str, a: object, b: object) -> None:
    if (a is None) == (b is None):
        raise ConfigError(f"give exactly one of {names}; got {a!r} and {b!r}")


def resize(
    *, radius: float | None = None, scale: float | None = None, target: Target = "a"
) -> Resize:
    """Return an action that changes the target ball's radius (FR-210).

    Give exactly one of ``radius`` (new radius in px) or ``scale`` (factor applied to
    the radius when the command is applied). Mass (pi r^2) and moment follow. The
    resize is refused (no change, no error) when the new radius could tunnel
    through a live ring; a ring target is a no-op.

    Raises:
        ConfigError: unless exactly one of ``radius``/``scale`` is a positive finite
            number, or if ``target`` is invalid.
    """
    _exactly_one("radius, scale", radius, scale)
    return Resize(
        radius=None if radius is None else _positive_number("radius", radius),
        scale=None if scale is None else _positive_number("scale", scale),
        target=_target(target),
    )


def set_velocity(
    *,
    velocity: Value[Vec] | None = None,
    speed: float | None = None,
    target: Target = "a",
) -> SetVelocity:
    """Return an action that sets the target ball's velocity (FR-210).

    Give exactly one of ``velocity`` (px/s, a value or a callable ``f(ctx)``
    evaluated when the rule runs) or ``speed`` (rescale the current velocity to this
    speed, keeping its direction; a resting ball stays at rest). The result is
    clamped to ``config.max_speed``, and a constant-speed ball's ``target_speed``
    becomes the new speed. A ring target is a no-op.

    Raises:
        ConfigError: unless exactly one of ``velocity``/``speed`` is given and valid
            (``speed`` finite and >= 0), or if ``target`` is invalid.
    """
    _exactly_one("velocity, speed", velocity, speed)
    return SetVelocity(
        velocity=None if velocity is None else _value("velocity", velocity, _vec),
        speed=None if speed is None else _non_negative_number("speed", speed),
        target=_target(target),
    )


def flash(target: Target = "a", *, seconds: float = 0.08, color: ColorLike = "#ffffff") -> Flash:
    """Return an action that flashes the target (ball or ring); visual only (FR-210).

    For ``max(1, round(seconds * fps))`` frames from the next drawn frame, the target
    is drawn in a colour blended linearly from ``color`` back to its base colour.
    Physics is unaffected. A new flash on the same object replaces the old one.

    Raises:
        ConfigError: if ``target`` is invalid, ``seconds`` is negative or not finite,
            or ``color`` is not a colour.
    """
    return Flash(
        target=_target(target),
        seconds=_non_negative_number("seconds", seconds),
        color=parse_color(color),
    )


def end_after(seconds: float) -> EndAfter:
    """Return an action that ends the video ``seconds`` after the current frame (FR-209).

    With ``F`` the number of frames simulated once the current frame completes,
    ``scene.total_frames`` becomes ``min(total_frames, F + round(seconds * fps))``, so
    ``frames()``, ``render()``, ``preview()`` and ``audio_buffer()`` stop there.
    Repeated calls keep the earliest end.

    Raises:
        ConfigError: if ``seconds`` is not a finite number >= 0.
    """
    return EndAfter(seconds=_non_negative_number("seconds", seconds))
