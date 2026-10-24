"""A parameter sweep: a ring with a rotating gap; escaped balls are replaced by new ones.

Render:   uv run bouncekit render examples/param_sweep.py --set gap=60 --set speed=450
Sweep:    uv run bouncekit batch examples/param_sweep.py --seeds 1-3 --grid gap=30,60 --jobs 2
Preview:  uv run bouncekit preview examples/param_sweep.py   (silent)
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

CAP = 60
CENTER = (540.0, 960.0)

scene = Scene(duration=20.0, seed=1, background="#08080f", gravity=(0.0, 0.0))
gap = float(scene.param("gap", 40.0))  # ring gap in degrees
speed = float(scene.param("speed", 400.0))  # ball speed in px/s
hue_step = float(scene.param("hue_step", 25.0))  # hue change per new ball, degrees

ring = scene.add_circle(
    center=CENTER,
    radius=430,
    thickness=8,
    color="#e8e8ff",
    gap_degrees=gap,
    angular_velocity=40,
    tags={"ring"},
)
# The first ball's direction comes from the seed, so seeds differ from frame 0.
start = scene.rng.uniform(0.0, 2.0 * math.pi)
scene.add_ball(
    pos=CENTER,
    radius=20,
    velocity=(speed * math.cos(start), speed * math.sin(start)),
    color=C.hue_cycle(step=hue_step),
    tags={"ball"},
    constant_speed=True,
)
scene.add_text("Can it escape?", pos=(540, 260), size=72, end=3.0)
scene.add_text(lambda s: f"balls: {s.count('ball')}", pos=(540, 1700), size=48, color="#9fa8ff")


def random_velocity(ctx):  # type: ignore[no-untyped-def]
    """A velocity of ``speed`` px/s in a random direction (uses ``ctx.rng``)."""
    angle = ctx.rng.uniform(0.0, 2.0 * math.pi)
    return (speed * math.cos(angle), speed * math.sin(angle))


# A soft tick on every ring hit, so even a short sweep is audible.
scene.on_collision("ball", "ring", [A.play(S.scale("A4", mode="minor_pentatonic", voice="pluck"))])

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
            color=C.hue_cycle(step=hue_step),
            constant_speed=True,
            max_total=CAP,
        ),
        A.play(S.scale("A3", mode="minor_pentatonic", voice="pluck")),
    ],
)

if __name__ == "__main__":
    scene.run()
