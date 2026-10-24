"""Built-in rule actions (FR-104, FR-206, FR-207): play, destroy, split, spawn.

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
    "Handler",
    "Play",
    "Spawn",
    "Split",
    "Target",
    "destroy",
    "play",
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

    def run(self, ctx: "ActionContext") -> None:
        """Evaluate the values now (in ball order) and queue the new balls."""
        ctx._spawn_action(self)


type Action = Play | Destroy | Split | Spawn
"""Any built-in action."""

type Handler = Action | Callable[..., object]
"""A rule handler: a built-in action or a Python callable (see ``Scene.on_collision``)."""

ACTION_TYPES: tuple[type, ...] = (Play, Destroy, Split, Spawn)


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

    Raises:
        ConfigError: for an invalid value (a callable's result is checked when it
            is evaluated), a non-positive ``radius`` or ``count``, or a bad
            ``max_total``.
    """
    _positive_int("count", count)
    return Spawn(
        pos=_value("pos", pos, _vec),
        radius=_positive_number("radius", radius),
        velocity=_value("velocity", velocity, _vec),
        count=count,
        color=_value("color", color, _color),
        tags=_tags(tags),
        elasticity=_non_negative_number("elasticity", elasticity),
        max_total=_max_total(max_total),
    )
