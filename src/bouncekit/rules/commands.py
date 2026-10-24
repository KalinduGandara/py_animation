"""Queued world changes, applied in FIFO order after dispatch (FR-203, FR-205..FR-207).

Handlers never touch the physics space; they append commands to the scene's
queue. ``apply`` runs them in the window after dispatch and before the next
``space.step``. A command whose target is no longer alive is skipped silently.
Split and spawn commands that would exceed the ball cap or let a ball tunnel
through a ring are refused as a whole, without an error (C8).
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bouncekit.colors import Color
from bouncekit.config import Vec
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["BallSpec", "Command", "DestroyCmd", "EndCmd", "SpawnCmd", "SplitCmd", "apply"]


@dataclass(frozen=True, eq=False)
class DestroyCmd:
    """Remove ``obj`` from the space, the scene's objects and the drawing."""

    obj: Ball | CircleBoundary


@dataclass(frozen=True, eq=False)
class SplitCmd:
    """Split ``ball`` (validated options, see ``actions.split``)."""

    ball: Ball
    into: int
    spread_degrees: float
    radius_scale: float
    max_total: int | None


@dataclass(frozen=True)
class BallSpec:
    """Fully resolved options of one ball to spawn."""

    pos: Vec
    radius: float
    velocity: Vec
    color: Color
    tags: frozenset[str]
    elasticity: float


@dataclass(frozen=True, eq=False)
class SpawnCmd:
    """Add ``balls`` (all or none)."""

    balls: tuple[BallSpec, ...]
    max_total: int | None


@dataclass(frozen=True, eq=False)
class EndCmd:
    """End the video ``frames`` frames after the frames simulated so far (FR-209)."""

    frames: int


type Command = DestroyCmd | SplitCmd | SpawnCmd | EndCmd


def apply(scene: "Scene", cmd: Command) -> None:
    """Apply one queued command to ``scene`` (no-op if its target is dead)."""
    if isinstance(cmd, DestroyCmd):
        if cmd.obj.alive:
            scene._remove(cmd.obj)
    elif isinstance(cmd, SplitCmd):
        _split(scene, cmd)
    elif isinstance(cmd, EndCmd):
        scene.total_frames = min(scene.total_frames, scene._frames_done + cmd.frames)
    else:
        _spawn(scene, cmd)


def _allowed(scene: "Scene", added: int, max_total: int | None, radius: float) -> bool:
    """Whether ``added`` more balls fit under the caps and ``radius`` cannot tunnel."""
    limit = scene.config.max_balls if max_total is None else min(scene.config.max_balls, max_total)
    if len(scene._balls) + added > limit:
        return False
    return not any(scene._tunnels(radius, ring) for ring in scene._rings)


def _split(scene: "Scene", cmd: SplitCmd) -> None:
    parent = cmd.ball
    if not parent.alive:
        return
    r2 = parent.radius * cmd.radius_scale
    if not _allowed(scene, cmd.into - 1, cmd.max_total, r2):
        return
    vx, vy = parent.velocity
    speed = math.hypot(vx, vy)
    theta = math.atan2(vy, vx) if speed > 0 else 0.0
    spread = math.radians(cmd.spread_degrees)
    px, py = parent.position
    nx, ny = -math.sin(theta), math.cos(theta)
    gap = 2 * r2 + 1
    states: list[tuple[Vec, Vec]] = []
    for i in range(cmd.into):
        phi = theta + spread * (i / (cmd.into - 1) - 0.5)
        k = (i - (cmd.into - 1) / 2) * gap
        states.append(((px + k * nx, py + k * ny), (speed * math.cos(phi), speed * math.sin(phi))))
    parent.set_radius(r2)
    parent.position, parent.velocity = states[0]
    parent.generation += 1
    for pos, vel in states[1:]:
        spec = BallSpec(pos, r2, vel, parent.color, parent.tags, parent.shape.elasticity)
        child = scene._spawn_ball(spec, generation=parent.generation)
        scene._inherit(parent, child)


def _spawn(scene: "Scene", cmd: SpawnCmd) -> None:
    if not cmd.balls or not _allowed(scene, len(cmd.balls), cmd.max_total, cmd.balls[0].radius):
        return
    for spec in cmd.balls:
        scene._spawn_ball(spec, generation=0)
