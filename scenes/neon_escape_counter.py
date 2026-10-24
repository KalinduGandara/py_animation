"""Neon: 3 balls in a spinning ring with a small gap; every escapee is replaced by 2 new ones.

A live counter shows how many balls have escaped.

Render:   uv run bouncekit render scenes/neon_escape_counter.py
Preview:  uv run bouncekit preview scenes/neon_escape_counter.py
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

CENTER = (540.0, 960.0)

scene = Scene(duration=40.0, seed=42, background="#05020d", gravity=(0.0, 0.0), max_balls=300)

gap = scene.param("gap", 28.0)  # degrees of opening
spin = scene.param("spin", 60.0)  # ring rotation, degrees per second
speed = scene.param("speed", 700.0)  # ball speed, px/s
cap = scene.param("cap", 250)  # most balls alive at once

ring = scene.add_circle(
    center=CENTER,
    radius=430,
    thickness=10,
    color="#ff2bd6",
    gap_degrees=gap,
    angular_velocity=spin,
    glow=2.0,
    tags={"wall"},
)

neon = C.hue_cycle(start=180, step=47)
for i in range(3):
    angle = scene.rng.uniform(0.0, 2.0 * math.pi)
    scene.add_ball(
        pos=(CENTER[0] + (i - 1) * 90.0, CENTER[1]),
        radius=20,
        velocity=(speed * math.cos(angle), speed * math.sin(angle)),
        color=neon,
        trail=True,
        glow=1.5,
        constant_speed=True,
        tags={"ball"},
    )


def random_velocity(ctx):  # type: ignore[no-untyped-def]
    """``speed`` px/s in a random direction (ctx.rng keeps it deterministic)."""
    a = ctx.rng.uniform(0.0, 2.0 * math.pi)
    return (speed * math.cos(a), speed * math.sin(a))


escaped = {"n": 0}


@scene.on_escape(ring, "ball")
def count_escape(ctx, ball, ring_, event):  # type: ignore[no-untyped-def]
    escaped["n"] += 1


scene.on_escape(
    ring,
    "ball",
    [
        A.destroy(),
        A.spawn(
            count=2,
            pos=CENTER,
            radius=20,
            velocity=random_velocity,
            color=neon,
            trail=True,
            glow=1.5,
            constant_speed=True,
            max_total=cap,
        ),
        A.flash(ring, seconds=0.15, color="#00f0ff"),
        A.particles(count=24, speed=600, lifetime=0.7, size=4),
        A.play(
            S.scale("A4", mode="minor_pentatonic", octaves=2, voice="marimba"), gain=1.0, pan=0.6
        ),
    ],
)

scene.on_collision(
    "ball",
    "wall",
    [
        A.play(S.scale("A2", mode="minor_pentatonic", octaves=2, voice="pluck"), gain=0.5, pan=0.6),
        A.particles(count=6, speed=300, lifetime=0.35, size=2),
    ],
)

scene.add_text("Can they escape?", pos=(540, 330), size=76, color="#00f0ff", end=3.0)
scene.add_text(
    lambda s: f"ESCAPED: {escaped['n']}", pos=(540, 1500), size=88, color="#ff2bd6"
)
scene.add_text(
    lambda s: f"{s.count('ball')} inside", pos=(540, 1600), size=44, color="#9be7ff"
)

if __name__ == "__main__":
    scene.run()
