"""Maze escape: one ball starts in the middle of a round maze and bounces around until it finds
the single exit in the outer wall. Every wall hit plays the next note of Für Elise; a long
trail shows where it has been. Ends right after it escapes ("ESCAPED in 0:23.4"), or says
"TRAPPED!" if it has not escaped by `limit` seconds.

The maze is a random polar maze built from static convex polygons: a spanning tree (one path
between any two cells) with a `braid` share of its inner walls knocked out, so there are loops.
Each seed gives a different maze.

Render:   uv run bouncekit render scenes/maze_escape.py --export
Pick:     uv run bouncekit batch scenes/maze_escape.py --seeds 1-12 --jobs 4
          --score "stats.escaped * 100 - abs(stats.escape_time - 28)" --keep-best 2 --export
Tweak:    --set rings=4 --set cell=130 --set speed=800 --set braid=0.25 --set turn=20 --set doors=3
          --set limit=40
"""

import math
from pathlib import Path

from bouncekit import EffectsConfig, Scene
from bouncekit import actions as A
from bouncekit import sound as S

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CX, CY = 540.0, 960.0
R_OUT = 430.0  # outer wall
HUB = 70.0  # open centre
WALL = 10.0  # wall thickness, px
BALL = 13.0
ARC_STEP = math.radians(5.0)  # arc walls are chains of quads this wide
OVERLAP = math.radians(0.4)  # neighbouring quads overlap a little: no seams to snag on

scene = Scene(duration=48.0, seed=12, background="#08080f", gravity=(0.0, 0.0), loop_fade=0.4,
              effects=EffectsConfig(trail_seconds=5.0))  # fmt: skip
rings = scene.param("rings", 4)  # corridors between the hub and the outer wall
cell = scene.param("cell", 130.0)  # target arc length of one cell, px
speed = scene.param("speed", 800.0)  # ball speed, px/s
limit = scene.param("limit", 40.0)  # if not out by then: "TRAPPED!"
braid = scene.param("braid", 0.25)  # share of inner walls removed (loops: more ways round)
turn_deg = scene.param("turn", 20.0)  # max random turn on each wall hit, degrees
doors = scene.param("doors", 3)  # at least this many openings out of the centre hub

radii = [HUB + k * (R_OUT - HUB) / rings for k in range(rings + 1)]
sectors = [max(6, round(2 * math.pi * (radii[c] + radii[c + 1]) / 2 / cell)) for c in range(rings)]
Cell = tuple[int, int]  # (corridor, sector); (-1, 0) is the hub


def span(c: int, s: int) -> tuple[float, float]:
    width = 2 * math.pi / sectors[c]
    return s * width, (s + 1) * width


def neighbours(node: Cell) -> list[tuple[Cell, tuple]]:
    """Adjacent cells with the wall between them: ("arc", r, a0, a1) or ("radial", a, c)."""
    c, s = node
    out: list[tuple[Cell, tuple]] = []
    if c == -1:
        return [((0, t), ("arc", radii[0], *span(0, t))) for t in range(sectors[0])]
    a0, a1 = span(c, s)
    out.append(((c, (s + 1) % sectors[c]), ("radial", a1, c)))
    out.append(((c, (s - 1) % sectors[c]), ("radial", a0, c)))
    for cc in (c - 1, c + 1):
        if cc == -1:
            out.append(((-1, 0), ("arc", radii[0], a0, a1)))
        elif cc < rings:
            for t in range(sectors[cc]):
                b0, b1 = span(cc, t)
                lo, hi = max(a0, b0), min(a1, b1)
                if hi - lo > 1e-6:
                    out.append(((cc, t), ("arc", radii[max(c, cc)], lo, hi)))
    return out


def wall_key(wall: tuple) -> tuple:
    return tuple(round(v, 6) if isinstance(v, float) else v for v in wall)


# Random depth-first search from the hub: a spanning tree = a perfect maze.
opened: set[tuple] = set()
seen: set[Cell] = {(-1, 0)}
stack: list[Cell] = [(-1, 0)]
while stack:
    here = stack[-1]
    options = [(n, w) for n, w in neighbours(here) if n not in seen]
    if not options:
        stack.pop()
        continue
    nxt, wall = options[scene.rng.randrange(len(options))]
    opened.add(wall_key(wall))
    seen.add(nxt)
    stack.append(nxt)

exit_sector = scene.rng.randrange(sectors[-1])
walls: dict[tuple, tuple] = {}
for c in range(-1, rings):
    for s in range(1 if c == -1 else sectors[c]):
        for _, wall in neighbours((c, s)):
            if wall_key(wall) not in opened:
                walls[wall_key(wall)] = wall
for key in list(walls):  # braid: knock out some inner walls so the maze has loops
    if scene.rng.random() < braid:
        del walls[key]
hub_walls = [k for k, w in walls.items() if w[0] == "arc" and w[1] == radii[0]]
while sectors[0] - len(hub_walls) < doors and hub_walls:  # open the hub so it isn't a trap
    del walls[hub_walls.pop(scene.rng.randrange(len(hub_walls)))]
for s in range(sectors[-1]):
    if s != exit_sector:
        walls[("outer", s)] = ("arc", R_OUT, *span(rings - 1, s))


def at(r: float, a: float) -> tuple[float, float]:
    return (CX + r * math.cos(a), CY + r * math.sin(a))


def hue(c: float) -> str:
    """Walls shade from violet (centre) to cyan (outside)."""
    t = c / max(1, rings)
    r, g, b = (round(170 - 120 * t), round(120 + 110 * t), 255)
    return f"#{r:02x}{g:02x}{b:02x}"


for wall in walls.values():
    if wall[0] == "arc":
        _, r, a0, a1 = wall
        n = max(1, math.ceil((a1 - a0) / ARC_STEP))
        ring_index = min(range(rings + 1), key=lambda k: abs(radii[k] - r))
        for i in range(n):
            u0 = a0 + (a1 - a0) * i / n - OVERLAP
            u1 = a0 + (a1 - a0) * (i + 1) / n + OVERLAP
            pts = [at(r - WALL / 2, u0), at(r + WALL / 2, u0), at(r + WALL / 2, u1),
                   at(r - WALL / 2, u1)]  # fmt: skip
            scene.add_polygon(points=pts, color=hue(ring_index), tags={"wall"})
    else:
        _, a, c = wall
        r0, r1 = radii[c] - WALL / 2, radii[c + 1] + WALL / 2
        nx, ny = -math.sin(a) * WALL / 2, math.cos(a) * WALL / 2
        p0, p1 = at(r0, a), at(r1, a)
        pts = [(p0[0] - nx, p0[1] - ny), (p1[0] - nx, p1[1] - ny), (p1[0] + nx, p1[1] + ny),
               (p0[0] + nx, p0[1] + ny)]  # fmt: skip
        scene.add_polygon(points=pts, color=hue(c + 0.5), tags={"wall"})

start = scene.rng.uniform(0.0, 2.0 * math.pi)
ball = scene.add_ball(pos=(CX, CY), radius=BALL, velocity=(speed * math.cos(start),
                      speed * math.sin(start)), color="#ffffff", trail=True, glow=1.5,
                      constant_speed=True, tags={"ball"})  # fmt: skip
state: dict[str, object] = {"escaped": False, "time": None}
scene.stat("escaped", False)
scene.stat("escape_time", limit)


@scene.on_collision("ball", "wall")
def nudge(ctx, b, wall, event):  # type: ignore[no-untyped-def]
    """Turn a few degrees on each hit so the ball keeps exploring new corridors."""
    vx, vy = b.velocity
    turn = math.radians(ctx.rng.uniform(-turn_deg, turn_deg))
    c, s = math.cos(turn), math.sin(turn)
    ctx.set_velocity(b, (vx * c - vy * s, vx * s + vy * c))


scene.on_collision("ball", "wall", [
    A.play(S.melody(ASSETS / "midi" / "fur_elise.mid", voice="marimba"), pan=0.5),
    A.particles(count=6, speed=200, lifetime=0.35, size=2),
])  # fmt: skip


def outside(s: Scene) -> bool:
    x, y = ball.position
    return not state["escaped"] and math.hypot(x - CX, y - CY) > R_OUT + WALL + 2 * BALL


@scene.when(outside)
def escaped(ctx, event):  # type: ignore[no-untyped-def]
    state.update(escaped=True, time=ctx.time)
    scene.stat("escaped", True)
    scene.stat("escape_time", round(ctx.time, 2))
    ctx.particles(pos=ball.position, count=120, speed=700, lifetime=1.2, size=4,
                  color="#7ff5ff")  # fmt: skip
    ctx.mark_climax()
    ctx.end_after(2.5)


@scene.at(limit)
def trapped(ctx, event):  # type: ignore[no-untyped-def]
    if not state["escaped"]:
        state["time"] = "trapped"
        ctx.mark_climax()
        ctx.end_after(2.5)


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def headline(s: Scene) -> str:
    if state["escaped"]:
        return f"ESCAPED in {clock(state['time'])}!"  # type: ignore[arg-type]
    if state["time"] == "trapped":
        return "TRAPPED!"
    return clock(s.time)


exit_angle = sum(span(rings - 1, exit_sector)) / 2
scene.add_text("EXIT", pos=at(R_OUT + 48, exit_angle), size=40, color="#7ff5ff")
scene.add_text("Can it find the exit?", pos=(540, 300), size=76, end=3.5)
scene.add_text(headline, pos=(540, 1560), size=84)
scene.post(
    title=lambda s: (f"The ball escaped the maze in {clock(state['time'])}! Did you guess right?"  # type: ignore[arg-type]
                     if state["escaped"] else "Can the ball find the exit?"),
    description="One ball, one random maze, one way out. Every wall hit plays the next note "
                "of Für Elise. Guess the time in the comments!",
    hashtags=["maze", "physics", "satisfying", "simulation", "shorts"],
)

if __name__ == "__main__":
    scene.run()
