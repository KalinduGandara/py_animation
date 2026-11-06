"""Fixture: tiny scene that reports stats (``hits``, ``ended``) and can end early (``stop``)."""

from bouncekit import Scene
from bouncekit import actions as A

scene = Scene(width=96, height=96, fps=30, duration=1.0, seed=3, gravity=(0.0, 300.0),
              max_speed=1000)  # fmt: skip
stop = scene.param("stop", 0.0)
missing = scene.param("missing", False)
scene.add_circle(center=(48, 48), radius=40, segments=32, tags={"wall"})
scene.add_ball(pos=(48, 40), radius=5, velocity=(scene.rng.uniform(-90, 90), 50.0),
               tags={"ball"})  # fmt: skip
hits = {"n": 0}
if not missing:
    scene.stat("hits", 0)
    scene.stat("seed_x2", scene.config.seed * 2)


@scene.on_collision("ball", "wall")
def count(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    hits["n"] += 1
    if not missing:
        scene.stat("hits", hits["n"])


if stop > 0:
    scene.at(stop, [A.end_after(0)])
