"""Escape race: four animal balls bounce inside one ring with a narrow spinning gap; the first
one out wins. Each animal has its own notes; near misses (a ball hitting the wall right next to
the gap) flash the ring. Ends shortly after the first escape ("🦊 ESCAPED FIRST!"), or "NOBODY
ESCAPED!" if none is out by `limit` seconds.

Render:   uv run bouncekit render scenes/escape_race.py --export
Pick:     uv run bouncekit batch scenes/escape_race.py --seeds 1-12 --jobs 4
          --score "stats.escaped * 100 - abs(stats.escape_time - 24) + stats.near_misses"
          --keep-best 2 --export
Tweak:    --set gap=14 --set spin=70 --set speed=650 --set limit=38
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CX, CY = 540.0, 960.0
R = 420.0
BALL = 32.0
TEAMS = (
    ("\U0001f438", "#58d68d", S.scale("C4", mode="major_pentatonic", voice="marimba")),
    ("\U0001f431", "#f5b041", S.scale("E4", mode="major_pentatonic", voice="pluck")),
    ("\U0001f436", "#5dade2", S.scale("G3", mode="major_pentatonic", voice="marimba")),
    ("\U0001f98a", "#ec7063", S.scale("A4", mode="minor_pentatonic", voice="pluck")),
)

scene = Scene(duration=44.0, seed=12, background="#0b0b14", gravity=(0.0, 0.0), loop_fade=0.4)
gap = scene.param("gap", 14.0)  # opening, degrees
spin = scene.param("spin", 70.0)  # ring rotation, degrees per second
speed = scene.param("speed", 650.0)  # ball speed, px/s
limit = scene.param("limit", 38.0)  # nobody out by then: "NOBODY ESCAPED!"

ring = scene.add_circle(center=(CX, CY), radius=R, thickness=12, color="#e8e8ff", glow=1.0,
                        gap_degrees=gap, angular_velocity=spin, tags={"wall"})  # fmt: skip
balls = []
for k, (icon, color, _) in enumerate(TEAMS):
    a = scene.rng.uniform(0.0, 2.0 * math.pi)
    x = CX + 110 * math.cos(math.radians(45 + 90 * k))
    y = CY + 110 * math.sin(math.radians(45 + 90 * k))
    balls.append(scene.add_ball(
        pos=(x, y), radius=BALL, velocity=(speed * math.cos(a), speed * math.sin(a)),
        color=color, label=icon, label_scale=1.15, trail=True, glow=0.8, constant_speed=True,
        tags={"ball", f"team{k}"},
    ))  # fmt: skip
    scene.on_collision(f"team{k}", "wall", [A.play(TEAMS[k][2], pan=0.6)])

state: dict[str, object] = {"winner": None, "near": 0, "over": False}
scene.stat("escaped", False)
scene.stat("escape_time", limit)
scene.stat("near_misses", 0)


def gap_offset(px: float, py: float) -> float:
    """Degrees between a wall hit and the middle of the gap (the ring's local angle 0)."""
    hit = math.degrees(math.atan2(py - CY, px - CX))
    centre = ring.angle_degrees  # the gap is centred on the ring's local angle 0
    return abs((hit - centre + 180) % 360 - 180)


@scene.on_collision("ball", "wall")
def bounce(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    """Turn a few degrees per hit (no endless loops); count near misses next to the gap."""
    vx, vy = ball.velocity
    turn = math.radians(ctx.rng.uniform(-10.0, 10.0))
    c, s = math.cos(turn), math.sin(turn)
    ctx.set_velocity(ball, (vx * c - vy * s, vx * s + vy * c))
    if not state["winner"] and gap_offset(*event.position) < gap / 2 + 12:
        state["near"] += 1  # type: ignore[operator]
        scene.stat("near_misses", state["near"])  # type: ignore[arg-type]
        ctx.flash(ring, color="#ffe66d", seconds=0.25)


@scene.on_escape(ring, "ball")
def first_out(ctx, ball, _ring, event):  # type: ignore[no-untyped-def]
    if state["winner"] or state["over"]:
        return
    state["winner"] = ball.label
    scene.stat("escaped", True)
    scene.stat("escape_time", round(ctx.time, 2))
    scene.stat("winner_index", balls.index(ball))
    ctx.particles(pos=ball.position, count=120, speed=700, lifetime=1.2, size=4,
                  color=ball.color)  # fmt: skip
    ctx.mark_climax()
    ctx.end_after(2.5)


@scene.at(limit)
def time_up(ctx, event):  # type: ignore[no-untyped-def]
    if not state["winner"]:
        state["over"] = True
        ctx.mark_climax()
        ctx.end_after(2.5)


def headline(s: Scene) -> str:
    if state["winner"]:
        return f"{state['winner']} ESCAPED FIRST!"
    if state["over"]:
        return "NOBODY ESCAPED!"
    return f"{s.time:4.1f}s"


scene.add_text("Which one escapes first? \U0001f447", pos=(540, 300), size=68, end=4.0)
scene.add_text("  ".join(icon for icon, _, _ in TEAMS), pos=(540, 400), size=80, end=4.0)
scene.add_text(headline, pos=(540, 1530), size=88)
scene.add_text(lambda s: f"near misses: {state['near']}", pos=(540, 1625), size=40,
               color="#9a9ab0")  # fmt: skip
scene.post(
    title=lambda s: (f"{state['winner']} escaped first! Which one did you pick?"
                     if state["winner"] else "Nobody escaped the spinning ring!"),
    description="Four animals, one tiny spinning gap, one winner. Pick your animal before "
                "you watch!",
    hashtags=["physics", "satisfying", "race", "simulation", "shorts"],
)

if __name__ == "__main__":
    scene.run()
