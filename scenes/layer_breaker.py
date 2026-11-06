"""One ball inside 10 spinning rainbow rings; each escape shatters a ring and the ball speeds up.

Render:   uv run bouncekit render scenes/layer_breaker.py
Preview:  uv run bouncekit preview scenes/layer_breaker.py
"""

import colorsys
import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CENTER = (540.0, 960.0)

scene = Scene(duration=45.0, seed=42, background="#06060c", gravity=(0.0, 0.0))

layers = scene.param("layers", 10)
gap = scene.param("gap", 34.0)  # opening per ring, degrees
spin = scene.param("spin", 70.0)  # degrees per second; neighbours spin the other way
speed = scene.param("speed", 650.0)  # ball speed, px/s
boost = scene.param("boost", 1.08)  # ball speed factor per broken ring
# Rings are 40 px apart; an escape only registers while the ball radius < ~16 px.
grow = scene.param("grow", 1.03)  # ball radius factor per broken ring
jitter = scene.param("jitter", 12.0)  # max random turn per wall bounce, degrees


def rainbow(i: int, n: int) -> str:
    r, g, b = colorsys.hsv_to_rgb(i / n * 0.85, 0.85, 1.0)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


rings = []
for i in range(layers):
    ring = scene.add_circle(
        center=CENTER,
        radius=80 + i * 40,
        thickness=7,
        color=rainbow(i, layers),
        gap_degrees=gap,
        angular_velocity=spin * (1 if i % 2 == 0 else -1) * (1 + 0.08 * i),
        glow=1.2,
        tags={"wall"},
    )
    rings.append(ring)

angle = scene.rng.uniform(0.0, 2.0 * math.pi)
scene.add_ball(
    pos=CENTER,
    radius=10,
    velocity=(speed * math.cos(angle), speed * math.sin(angle)),
    color="#ffffff",
    trail=True,
    glow=1.5,
    constant_speed=True,
    tags={"ball"},
)

broken = {"n": 0}
breaks = S.scale("C4", mode="major", octaves=2, voice="marimba")

for ring in rings:

    @scene.on_escape(ring, "ball")
    def shatter(ctx, ball, ring_, event):  # type: ignore[no-untyped-def]
        broken["n"] += 1
        ctx.particles(pos=event.position, count=60, speed=700, lifetime=0.9, size=4,
                      color=ring_.color)
        ctx.destroy(ring_)
        ctx.resize(ball, ball.radius * grow)
        vx, vy = ball.velocity
        ctx.set_velocity(ball, (vx * boost, vy * boost))
        ctx.flash(ball, seconds=0.2, color=ring_.color)
        ctx.play(breaks)
        if broken["n"] == layers:
            ctx.end_after(1.2)


@scene.on_collision("ball", "wall")
def nudge(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    """Turn the bounce a little so the ball never locks into one repeating path."""
    vx, vy = ball.velocity
    t = math.radians(ctx.rng.uniform(-jitter, jitter))
    ctx.set_velocity(ball, (vx * math.cos(t) - vy * math.sin(t),
                            vx * math.sin(t) + vy * math.cos(t)))


scene.on_collision("ball", "wall", [
    A.play(S.scale("C3", mode="major_pentatonic", octaves=3, voice="pluck"), gain=0.6, pan=0.5),
    A.particles(count=5, speed=250, lifetime=0.3, size=2),
])

scene.add_text("Can it break all 10?", pos=(540, 300), size=74, color="#ffffff", end=3.5)
scene.add_text(lambda s: f"LAYER {min(broken['n'] + 1, layers)} / {layers}"
               if broken["n"] < layers else "",
               pos=(540, 1560), size=84, color="#ffe066")
scene.add_text(lambda s: "FREE!" if broken["n"] == layers else "",
               pos=(540, 960), size=180, color="#ffe066")

if __name__ == "__main__":
    scene.run()
