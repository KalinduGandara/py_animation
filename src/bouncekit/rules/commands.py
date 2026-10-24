"""Queued world changes, applied in FIFO order after dispatch (FR-203, FR-205..FR-210).

Handlers never touch the physics space; they append commands to the scene's
queue. ``apply`` runs them in the window after dispatch and before the next
``space.step``. A command whose target is no longer alive is skipped silently.
Split, spawn and resize commands that would exceed the ball cap or let a ball
tunnel through a ring are refused as a whole, without an error (C8).
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bouncekit.colors import Color, ColorSource
from bouncekit.config import Vec
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = [
    "BallSpec",
    "Command",
    "DestroyCmd",
    "EndCmd",
    "FlashCmd",
    "RecolorCmd",
    "ResizeCmd",
    "SpawnCmd",
    "SplitCmd",
    "VelocityCmd",
    "apply",
]


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
    """Fully resolved options of one ball to spawn.

    ``color`` is a colour or a colour mode, resolved when the ball is added (FR-306).
    """

    pos: Vec
    radius: float
    velocity: Vec
    color: ColorSource
    tags: frozenset[str]
    elasticity: float
    constant_speed: bool = False
    trail: bool = False
    glow: float = 0.0


@dataclass(frozen=True, eq=False)
class SpawnCmd:
    """Add ``balls`` (all or none)."""

    balls: tuple[BallSpec, ...]
    max_total: int | None


@dataclass(frozen=True, eq=False)
class EndCmd:
    """End the video ``frames`` frames after the frames simulated so far (FR-209)."""

    frames: int


@dataclass(frozen=True, eq=False)
class RecolorCmd:
    """Set ``obj``'s base colour (a colour mode for balls, resolved when applied)."""

    obj: Ball | CircleBoundary
    color: ColorSource


@dataclass(frozen=True, eq=False)
class ResizeCmd:
    """Set ``ball``'s radius to ``radius``, or to its radius at apply time times ``scale``."""

    ball: Ball
    radius: float | None
    scale: float | None


@dataclass(frozen=True, eq=False)
class VelocityCmd:
    """Set ``ball``'s velocity, or rescale it to ``speed`` keeping its direction at apply time."""

    ball: Ball
    velocity: Vec | None
    speed: float | None


@dataclass(frozen=True, eq=False)
class FlashCmd:
    """Draw ``obj`` blended from ``color`` back to its base colour over ``frames`` frames."""

    obj: Ball | CircleBoundary
    color: Color
    frames: int


type Command = (
    DestroyCmd | SplitCmd | SpawnCmd | EndCmd | RecolorCmd | ResizeCmd | VelocityCmd | FlashCmd
)


def apply(scene: "Scene", cmd: Command) -> None:
    """Apply one queued command to ``scene`` (no-op if its target is dead)."""
    if isinstance(cmd, DestroyCmd):
        if cmd.obj.alive:
            scene._remove(cmd.obj)
    elif isinstance(cmd, SplitCmd):
        _split(scene, cmd)
    elif isinstance(cmd, EndCmd):
        scene.total_frames = min(scene.total_frames, scene._frames_done + cmd.frames)
    elif isinstance(cmd, RecolorCmd):
        if isinstance(cmd.obj, Ball):
            if cmd.obj.alive:
                scene._set_ball_color(cmd.obj, cmd.color)
        elif cmd.obj.alive and isinstance(cmd.color, tuple):
            cmd.obj.color = cmd.color
    elif isinstance(cmd, ResizeCmd):
        _resize(scene, cmd)
    elif isinstance(cmd, VelocityCmd):
        _set_velocity(scene, cmd)
    elif isinstance(cmd, FlashCmd):
        if cmd.obj.alive:
            # Starts at the next drawn frame: the frame count once the current frame completes.
            scene._flash[scene._indices[cmd.obj]] = (cmd.color, scene._frames_done, cmd.frames)
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
    speed = parent.target_speed if parent.constant_speed else math.hypot(vx, vy)
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
    positions = _clear_of_rings(scene, parent.position, [pos for pos, _ in states], r2)
    states = [(pos, vel) for pos, (_, vel) in zip(positions, states, strict=True)]
    parent.set_radius(r2)
    parent.position, parent.velocity = states[0]
    parent.generation += 1
    # New children: the parent's draw-time mode, else the next hue of its hue
    # cycle, else its colour; the parent (child 0) keeps its colour (FR-306).
    child_color: ColorSource = parent.color_mode or parent.hue_mode or parent.color
    for pos, vel in states[1:]:
        spec = BallSpec(
            pos,
            r2,
            vel,
            child_color,
            parent.tags,
            parent.shape.elasticity,
            parent.constant_speed,
            parent.trail,
            parent.glow,
        )
        child = scene._spawn_ball(spec, generation=parent.generation)
        scene._inherit(parent, child)


# Clearance kept between a split child and a ring's surface, px.
_WALL_CLEARANCE = 0.5
# Translation passes per ring; each pass fixes the worst child exactly.
_CLEAR_PASSES = 8


def _clear_of_rings(scene: "Scene", origin: Vec, positions: list[Vec], radius: float) -> list[Vec]:
    """Translate the split formation so no child overlaps a ring wall (C16).

    For each live ring (insertion order) whose band the parent centre ``origin`` is
    clearly inside or outside of, the whole formation is shifted radially, worst
    child first, until every child of ``radius`` is at least ``_WALL_CLEARANCE`` px
    clear of the ring's inner surface (chord midpoints) or outer surface. Spacing
    between children is unchanged. A parent inside the band (passing a gap) leaves
    that ring alone.
    """
    pts = list(positions)
    for ring in scene._rings:
        cx, cy = ring.center
        half = ring.thickness / 2
        d0 = math.hypot(origin[0] - cx, origin[1] - cy)
        if d0 <= ring.radius - half:
            inside = True
            limit = ring.radius * math.cos(math.pi / ring._segment_count) - half
            limit -= radius + _WALL_CLEARANCE
        elif d0 >= ring.radius + half:
            inside = False
            limit = ring.radius + half + radius + _WALL_CLEARANCE
        else:
            continue
        for _ in range(_CLEAR_PASSES):
            worst = 0.0
            ux = uy = 0.0
            for x, y in pts:
                d = math.hypot(x - cx, y - cy)
                excess = d - limit if inside else limit - d
                if excess > worst:
                    worst = excess
                    if d > 0:
                        ux, uy = (x - cx) / d, (y - cy) / d
                    else:
                        ux, uy = 1.0, 0.0
            if worst <= 0:
                break
            sign = -1.0 if inside else 1.0
            dx, dy = sign * worst * ux, sign * worst * uy
            pts = [(x + dx, y + dy) for x, y in pts]
    return pts


def _spawn(scene: "Scene", cmd: SpawnCmd) -> None:
    if not cmd.balls or not _allowed(scene, len(cmd.balls), cmd.max_total, cmd.balls[0].radius):
        return
    for spec in cmd.balls:
        scene._spawn_ball(spec, generation=0)


def _resize(scene: "Scene", cmd: ResizeCmd) -> None:
    ball = cmd.ball
    if not ball.alive:
        return
    radius = cmd.radius if cmd.scale is None else ball.radius * cmd.scale
    if radius is None or not math.isfinite(radius) or radius <= 0:
        return
    if any(scene._tunnels(radius, ring) for ring in scene._rings):
        return
    ball.set_radius(radius)


def _set_velocity(scene: "Scene", cmd: VelocityCmd) -> None:
    ball = cmd.ball
    if not ball.alive:
        return
    if cmd.velocity is not None:
        ball.velocity = cmd.velocity
    elif cmd.speed is not None:
        vx, vy = ball.velocity
        speed = math.hypot(vx, vy)
        if speed > 0:
            # min() first so a huge speed cannot overflow the product.
            scale = min(cmd.speed, scene.config.max_speed) / speed
            ball.velocity = (vx * scale, vy * scale)
    ball.clamp_speed(scene.config.max_speed)
    if ball.constant_speed:
        ball.target_speed = math.hypot(*ball.velocity)
