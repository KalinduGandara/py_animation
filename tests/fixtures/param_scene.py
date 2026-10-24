"""Fixture: a tiny scene whose ball speed is a param (``vx``), with sound and rng use."""

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

scene = Scene(
    width=96, height=96, fps=30, duration=1.0, seed=5, gravity=(0.0, 300.0), max_speed=1000
)
vx = scene.param("vx", 100.0)
vy = scene.rng.uniform(-80.0, 80.0)
scene.add_circle(center=(48, 48), radius=40, segments=32, tags={"wall"})
scene.add_ball(pos=(48, 40), radius=5, velocity=(vx, vy), color="#ff4060", tags={"ball"})
scene.on_collision("ball", "wall", [A.play(S.scale("C4"))])
