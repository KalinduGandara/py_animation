"""ActionContext: what a rule handler sees and can do (FR-203)."""

import random
from typing import TYPE_CHECKING

from bouncekit.actions import Play, Target, play
from bouncekit.errors import ConfigError
from bouncekit.events import Event, WorldObject
from bouncekit.rules.commands import DestroyCmd
from bouncekit.sound import Source
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["ActionContext"]


class ActionContext:
    """Passed to every handler as ``ctx``; one per (event, rule).

    Methods that change the world (``destroy``) only queue a command: the change is
    applied after the step's dispatch, never while handlers run. ``play`` produces a
    note trigger immediately (audio only). Bad arguments raise ``ConfigError`` at
    the call.

    Attributes:
        scene: the scene being simulated.
        event: the event being dispatched.
        a: the rule's first subject (collision: the object carrying ``tag_a``;
            destroy: the destroyed object), or ``None``.
        b: the rule's second subject (collision: the object carrying ``tag_b``), or
            ``None``.
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

    def play(self, source: Source, *, gain: float = 1.0) -> None:
        """Trigger ``source`` now, subject to the audio trigger policy (FR-106, FR-211).

        Calls with an equal ``(source, gain)`` share one retrigger timer per subject
        ``a``, like a single ``A.play`` action.

        Raises:
            ConfigError: if ``source`` is not a sound source or ``gain`` is negative.
        """
        action = play(source, gain=gain)
        self._play_action(self.scene._engine.shared_play(action))

    def _play_action(self, action: Play) -> None:
        self.scene._trigger(action, self.event, self.a)
