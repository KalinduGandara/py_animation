"""Built-in rule actions (FR-104, FR-207): ``A.play(...)``, ``A.destroy(...)``.

Actions are immutable values compared by identity. When a rule fires, each action's
``run(ctx)`` resolves its target and calls the matching :class:`ActionContext`
method, so built-ins and Python callbacks go through the same path. Every action
except ``play`` only queues a command; the scene applies it after dispatch.

A play's final gain also depends on impact speed (FR-106, see ``AudioConfig``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from bouncekit.config import _non_negative_number
from bouncekit.errors import ConfigError
from bouncekit.sound import Note, Scale, Source
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.rules.context import ActionContext

__all__ = ["Action", "Destroy", "Handler", "Play", "Target", "destroy", "play"]

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


type Action = Play | Destroy
"""Any built-in action."""

type Handler = Action | Callable[..., object]
"""A rule handler: a built-in action or a Python callable (see ``Scene.on_collision``)."""

ACTION_TYPES: tuple[type, ...] = (Play, Destroy)


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
