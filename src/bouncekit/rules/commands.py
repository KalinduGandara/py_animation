"""Queued world changes, applied in FIFO order after dispatch (FR-203).

Handlers never touch the physics space; they append commands to the scene's
queue. ``apply`` runs them in the window after dispatch and before the next
``space.step``. A command whose target is no longer alive is skipped silently.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["Command", "DestroyCmd", "apply"]


@dataclass(frozen=True, eq=False)
class DestroyCmd:
    """Remove ``obj`` from the space, the scene's objects and the drawing."""

    obj: Ball | CircleBoundary


type Command = DestroyCmd


def apply(scene: "Scene", cmd: Command) -> None:
    """Apply one queued command to ``scene`` (no-op if its target is dead)."""
    if not cmd.obj.alive:
        return
    scene._remove(cmd.obj)
