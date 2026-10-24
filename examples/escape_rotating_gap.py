"""A ring with a rotating gap: each ball that escapes is replaced by two new ones inside.

Render:   uv run bouncekit render examples/escape_rotating_gap.py --seed 42
Preview:  uv run bouncekit preview examples/escape_rotating_gap.py   (silent)
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CAP = 40
CENTER = (540.0, 960.0)

scene = Scene(duration=20.0, seed=42, background="#10101a", gravity=(0.0, 0.0))

ring = scene.add_circle(
    center=CENTER, radius=420, thickness=8, color="#ffffff", gap_degrees=40, angular_velocity=45
)
scene.add_ball(
    pos=CENTER,
    radius=20,
    velocity=(scene.rng.uniform(-400.0, 400.0), scene.rng.uniform(300.0, 500.0)),
    color="#4cc9f0",
    tags={"ball"},
    constant_speed=True,
)


def random_velocity(ctx):  # type: ignore[no-untyped-def]
    """A velocity of 450 px/s in a random direction (uses ``ctx.rng`` for determinism)."""
    angle = ctx.rng.uniform(0.0, 2.0 * math.pi)
    return (450.0 * math.cos(angle), 450.0 * math.sin(angle))


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
            color="#4cc9f0",
            constant_speed=True,
            max_total=CAP,
        ),
        A.play(S.scale("A3", mode="minor_pentatonic", voice="pluck")),
    ],
)

if __name__ == "__main__":
    scene.run()
