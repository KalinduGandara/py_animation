"""An outbreak: red balls infect white ones on touch, but every infected ball dies after a
few seconds. Does the infection burn out before it reaches everyone?

Render:   uv run bouncekit render scenes/last_survivor.py
Preview:  uv run bouncekit preview scenes/last_survivor.py
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CENTER = (540.0, 960.0)
RED = (255, 45, 85)
DARK = (70, 10, 25)
WHITE = "#f2f2f7"

scene = Scene(duration=45.0, seed=5, background="#0a0a10", gravity=(0.0, 0.0))

count = scene.param("count", 60)
speed = scene.param("speed", 80.0)  # px/s
radius = scene.param("radius", 14.0)
lifespan = scene.param("lifespan", 4.0)  # seconds an infected ball lives

ring = scene.add_circle(center=CENTER, radius=450, thickness=10, color="#5a5a72", glow=0.6,
                        tags={"wall"})

balls = []
placed: list[tuple[float, float]] = []
while len(placed) < count:
    r = 410 * math.sqrt(scene.rng.random())
    a = scene.rng.uniform(0.0, 2.0 * math.pi)
    p = (CENTER[0] + r * math.cos(a), CENTER[1] + r * math.sin(a))
    if all(math.dist(p, q) > 2 * radius + 4 for q in placed):
        placed.append(p)
for i, p in enumerate(placed):
    a = scene.rng.uniform(0.0, 2.0 * math.pi)
    balls.append(scene.add_ball(
        pos=p, radius=radius, velocity=(speed * math.cos(a), speed * math.sin(a)),
        color=RED if i == 0 else WHITE, trail=True, glow=0.8 if i == 0 else 0.0,
        constant_speed=True, tags={"ball"},
    ))

infected = {balls[0]: 0}  # ball -> frame it was infected (insertion-ordered)
dead: set[object] = set()
state = {"over": False}
infect_notes = S.scale("A3", mode="minor_pentatonic", octaves=3, voice="pluck")
death_note = S.note("A2", voice="marimba")


def survivors() -> int:
    return count - len(infected) - len(dead)


def finish(ctx) -> None:  # type: ignore[no-untyped-def]
    if not state["over"]:
        state["over"] = True
        ctx.end_after(3.0)


@scene.on_collision("ball", "ball")
def touch(ctx, a, b, event):  # type: ignore[no-untyped-def]
    if a in dead or b in dead or (a in infected) == (b in infected):
        return
    victim = b if a in infected else a
    infected[victim] = ctx.scene.frame
    ctx.recolor(victim, RED)
    ctx.flash(victim, seconds=0.15, color="#ffffff")
    ctx.particles(pos=event.position, count=16, speed=350, lifetime=0.5, size=3, color=RED)
    ctx.play(infect_notes)
    if survivors() == 0:
        finish(ctx)


@scene.every(0.1)
def age(ctx, event):  # type: ignore[no-untyped-def]
    life = lifespan * ctx.scene.config.fps
    for ball, since in list(infected.items()):
        t = (ctx.scene.frame - since) / life
        if t >= 1.0:
            del infected[ball]
            dead.add(ball)
            ctx.particles(pos=ball.position, count=30, speed=450, lifetime=0.7, size=3,
                          color=RED)
            ctx.play(death_note, gain=0.7)
            ctx.destroy(ball)
        else:
            fade = tuple(round(r + (d - r) * t) for r, d in zip(RED, DARK, strict=True))
            ctx.recolor(ball, fade)
    if not infected:
        finish(ctx)


scene.on_collision("ball", "wall", [A.play(S.note("E2", voice="marimba"), gain=0.2)])


def verdict(s: Scene) -> str:
    if not state["over"]:
        return f"SURVIVORS: {survivors()}"
    return "NOBODY SURVIVED" if survivors() == 0 else f"{survivors()} SURVIVED!"


scene.add_text("Will anyone survive?", pos=(540, 300), size=76, color="#ffffff", end=3.5)
scene.add_text(verdict, pos=(540, 1540), size=84, color="#ffffff")
scene.add_text(lambda s: f"infected: {len(infected)}   dead: {len(dead)}",
               pos=(540, 1640), size=44, color="#ff2d55")

if __name__ == "__main__":
    scene.run()
