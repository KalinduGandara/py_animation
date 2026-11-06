"""Plinko prediction: 100 balls drop through a field of pegs into 5 numbered slots. Live counts
under each slot; when the last ball has landed, the fullest slot wins ("SLOT 3 WINS!", or "TIE!"
when the top two are level). Balls start at random x across the top, so the middle slot is
not a sure thing.

Render:   uv run bouncekit render scenes/plinko.py --export
Pick:     uv run bouncekit batch scenes/plinko.py --seeds 1-10 --jobs 4
          --score "-abs(stats.margin - 1) - stats.middle_wins * 3" --keep-best 2 --export
Tweak:    --set balls=100 --set rate=0.17 --set spread=0.6 --set rows=11
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

LEFT, RIGHT = 150.0, 930.0  # board walls (inner edges)
TOP = 430.0  # first peg row
SLOT_TOP = 1200.0  # top of the slot dividers
FLOOR = 1470.0
SLOTS = 5
BALL = 11.0
PEG = 9.0
WALL = 14.0
SLOT_W = (RIGHT - LEFT) / SLOTS
SLOT_COLORS = ["#ff4d6d", "#ffb703", "#3ddc97", "#4cc9f0", "#b388ff"]

scene = Scene(duration=40.0, seed=1, background="#0a0a12", gravity=(0.0, 1500.0),
              max_balls=200, loop_fade=0.4)  # fmt: skip
balls_total = scene.param("balls", 100)
rate = scene.param("rate", 0.17)  # seconds between drops
spread = scene.param("spread", 0.6)  # drop x range as a share of the board width
rows = scene.param("rows", 11)


def box(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def peg(x: float, y: float) -> list[tuple[float, float]]:
    """A 12-gon with a vertex on top, so nothing can balance on it."""
    return [(x + PEG * math.cos(math.radians(-90 + 30 * k)),
             y + PEG * math.sin(math.radians(-90 + 30 * k))) for k in range(12)]  # fmt: skip


# Board: side walls, floor, slot dividers with pointed tops, staggered pegs.
scene.add_polygon(points=box(LEFT - WALL, TOP - 90, LEFT, FLOOR + WALL), color="#3a3a5a",
                  elasticity=0.5, tags={"frame"})  # fmt: skip
scene.add_polygon(points=box(RIGHT, TOP - 90, RIGHT + WALL, FLOOR + WALL), color="#3a3a5a",
                  elasticity=0.5, tags={"frame"})  # fmt: skip
scene.add_polygon(points=box(LEFT - WALL, FLOOR, RIGHT + WALL, FLOOR + WALL), color="#3a3a5a",
                  elasticity=0.2, tags={"frame"})  # fmt: skip
for k in range(1, SLOTS):
    x = LEFT + k * SLOT_W
    scene.add_polygon(points=[(x, SLOT_TOP - 12), (x + 4, SLOT_TOP), (x + 4, FLOOR),
                              (x - 4, FLOOR), (x - 4, SLOT_TOP)],
                      color="#5a5a80", elasticity=0.3, tags={"frame"})  # fmt: skip
pitch = (RIGHT - LEFT) / 9  # horizontal peg spacing
row_gap = (SLOT_TOP - 60 - TOP) / (rows - 1)
for row in range(rows):
    y = TOP + row * row_gap
    offset = pitch / 2 if row % 2 else 0.0
    x = LEFT + pitch / 2 + offset - pitch / 2
    while x <= RIGHT - PEG - 2 * BALL:
        if x >= LEFT + PEG + 2 * BALL:
            scene.add_polygon(points=peg(x, y), color="#d8d8f0", elasticity=0.6, tags={"peg"})
        x += pitch
    if row % 2 == 0:  # wall bumpers close the wide lanes beside the walls on even rows
        reach = pitch / 2
        scene.add_polygon(points=[(LEFT, y - 22), (LEFT + reach, y), (LEFT, y + 22)],
                          color="#5a5a80", elasticity=0.6, tags={"peg"})  # fmt: skip
        scene.add_polygon(points=[(RIGHT, y - 22), (RIGHT, y + 22), (RIGHT - reach, y)],
                          color="#5a5a80", elasticity=0.6, tags={"peg"})  # fmt: skip

HUES = C.hue_cycle(step=37)  # one cycle shared by every ball: each drop gets the next hue
counts = [0] * SLOTS
landed: set[object] = set()
state: dict[str, object] = {"done": False, "dropped": 0}
for k in range(SLOTS):
    scene.stat(f"slot{k + 1}", 0)


def drop_pos(ctx):  # type: ignore[no-untyped-def]
    half = (RIGHT - LEFT) * spread / 2
    return (ctx.rng.uniform(540 - half, 540 + half), TOP - 80)


@scene.every(rate)
def drop(ctx, event):  # type: ignore[no-untyped-def]
    if state["dropped"] >= balls_total:  # type: ignore[operator]
        return
    state["dropped"] += 1  # type: ignore[operator]
    ctx.spawn(pos=drop_pos(ctx), radius=BALL, velocity=(ctx.rng.uniform(-30, 30), 0.0),
              color=HUES, elasticity=0.5, trail=True, glow=0.6,
              tags=("ball",))  # fmt: skip


for k in range(5):  # motion from frame 1: a few balls are already falling
    state["dropped"] += 1  # type: ignore[operator]
    half = (RIGHT - LEFT) * spread / 2
    scene.add_ball(pos=(scene.rng.uniform(540 - half, 540 + half), TOP - 60 + 70 * k),
                   radius=BALL, velocity=(scene.rng.uniform(-30, 30), 250.0 + 120 * k),
                   color=HUES, elasticity=0.5, trail=True, glow=0.6, tags={"ball"})  # fmt: skip

notes = S.scale("C4", mode="major_pentatonic", octaves=3, voice="marimba")
scene.on_collision("ball", "peg", [A.play(notes, pan=0.7), A.flash(target="b", seconds=0.12)])


@scene.every(1 / 60)
def count(ctx, event):  # type: ignore[no-untyped-def]
    if state["done"]:
        return
    for obj in ctx.scene.objects:
        if "ball" in obj.tags and obj not in landed and obj.position[1] > SLOT_TOP + BALL:
            k = min(SLOTS - 1, max(0, int((obj.position[0] - LEFT) // SLOT_W)))
            landed.add(obj)
            counts[k] += 1
            scene.stat(f"slot{k + 1}", counts[k])
            ctx.play(S.note(["C5", "D5", "E5", "G5", "A5"][k], voice="pluck"), gain=0.5)
    if len(landed) >= balls_total:
        state["done"] = True
        top = sorted(counts, reverse=True)
        winner = counts.index(top[0])
        state["winner"] = None if top[0] == top[1] else winner
        scene.stat("margin", top[0] - top[1])
        scene.stat("middle_wins", winner == SLOTS // 2 and top[0] != top[1])
        if state["winner"] is not None:
            cx = LEFT + (winner + 0.5) * SLOT_W
            ctx.particles(pos=(cx, SLOT_TOP), count=120, speed=800, lifetime=1.2, size=4,
                          color=SLOT_COLORS[winner])  # fmt: skip
        ctx.mark_climax()
        ctx.end_after(2.5)


def result(s: Scene) -> str:
    if not state["done"]:
        return f"{len(landed)} / {balls_total}"
    if state["winner"] is None:
        return "TIE!"
    return f"SLOT {state['winner'] + 1} WINS!"  # type: ignore[operator]


scene.add_text("Which slot wins? \U0001f447", pos=(540, 290), size=76, end=4.0)
scene.add_text(result, pos=(540, 290), size=80, start=4.0)
for k in range(SLOTS):
    cx = LEFT + (k + 0.5) * SLOT_W
    scene.add_text(str(k + 1), pos=(cx, 1525), size=64, color=SLOT_COLORS[k])
    scene.add_text(lambda s, k=k: str(counts[k]), pos=(cx, 1600), size=52, color="#e8e8ff")
scene.post(
    title=lambda s: (f"Slot {state['winner'] + 1} won! Did you call it?"  # type: ignore[operator]
                     if state.get("winner") is not None else "100 balls, 5 slots: it's a tie!"),
    description="100 balls drop through the pegs. Which slot ends up with the most? "
                "Comment your pick before the last ball lands!",
    hashtags=["plinko", "physics", "satisfying", "prediction", "shorts"],
)

if __name__ == "__main__":
    scene.run()
