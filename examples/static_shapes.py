"""Static shapes (M5 early): balls drop through polygon pegs; pegs change colour per hit and
break after 5 hits; landed balls turn into hexagon stones that pile up.

Shows: scene.add_polygon (setup), ctx.add_polygon (runtime, queued), ctx.recolor/flash/destroy
on polygons, on_destroy, every + A.spawn with C.by_speed under gravity, a callable counter.

Render:   uv run bouncekit render examples/static_shapes.py
Preview:  uv run bouncekit preview examples/static_shapes.py
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

CX, CY = 540.0, 960.0
R = 450.0
PEG_COLORS = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"]  # hit 0..4

scene = Scene(duration=20.0, seed=42, background="#0b0b12", gravity=(0.0, 900.0))
rate = scene.param("rate", 0.35)  # seconds between dropped balls
hits_to_break = scene.param("hits", 5)

scene.add_circle(center=(CX, CY), radius=R, thickness=10, color="#e8e8ff", glow=1.0, tags={"wall"})

# A staggered grid of diamond pegs (static convex polygons).
hits: dict[object, int] = {}
for row in range(5):
    y = 760 + row * 110
    for col in range(-3, 4):
        x = CX + col * 110 + (55 if row % 2 else 0)
        if math.hypot(x - CX, y - CY) > R - 60:
            continue
        peg = scene.add_polygon(
            points=[(x, y - 22), (x + 22, y), (x, y + 22), (x - 22, y)],
            color=PEG_COLORS[0],
            tags={"peg"},
        )
        hits[peg] = 0


def drop_pos(ctx):  # type: ignore[no-untyped-def]
    return (CX + ctx.rng.uniform(-200, 200), CY - 330)


scene.every(
    rate,
    [
        A.spawn(
            pos=drop_pos,
            radius=12,
            velocity=(0.0, 0.0),
            tags=("ball",),
            color=C.by_speed(slow="#7df9ff", fast="#ff4d6d", max_speed=1400),
            trail=True,
            glow=0.8,
            max_total=60,
        )
    ],
)

notes = S.scale("C4", mode="major_pentatonic", octaves=2, voice="marimba")


@scene.on_collision("ball", "peg")
def bump(ctx, ball, peg, event):  # type: ignore[no-untyped-def]
    hits[peg] += 1
    ctx.play(notes, pan=0.6)
    if hits[peg] >= hits_to_break:
        ctx.destroy(peg)
    else:
        ctx.recolor(peg, PEG_COLORS[hits[peg]])
        ctx.flash(peg, seconds=0.1)


@scene.on_destroy("peg")
def shatter(ctx, peg, event):  # type: ignore[no-untyped-def]
    ctx.particles(pos=event.position, count=40, speed=500, lifetime=0.7, size=3, color="#ffbe0b")
    ctx.play(S.note("C6", voice="pluck"))


settled: set[object] = set()  # a ball touching two things in one step settles once


def settle(ctx, ball, other, event) -> None:  # type: ignore[no-untyped-def]
    """Replace a landed ball with a hexagon stone at the same spot (queued, FIFO)."""
    if ball in settled:
        return
    settled.add(ball)
    x, y = ball.position
    ctx.destroy(ball)  # applied first, so the new stone does not overlap it
    ctx.add_polygon(
        points=[
            (x + 14 * math.cos(a), y + 14 * math.sin(a))
            for a in (k * math.pi / 3 for k in range(6))
        ],
        color="#cfd2ff",
        tags={"stone"},
    )
    ctx.play(S.note("G2", voice="marimba"), gain=0.6)


@scene.on_collision("ball", "wall")
def land_on_floor(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    if event.position[1] > CY + 250:  # only the bottom of the ring
        settle(ctx, ball, wall, event)


scene.on_collision("ball", "stone", [settle])  # landing on the pile grows it

scene.add_text("Pegs break after 5 hits", pos=(540, 330), size=64, end=3.0)
scene.add_text(
    lambda s: f"pegs {s.count('peg')}   stones {s.count('stone')}",
    pos=(540, 1600),
    size=56,
    color="#cfd2ff",
)

if __name__ == "__main__":
    scene.run()
