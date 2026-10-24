"""Fixture: a tiny scene with a str param ``mode``; ``mode=bad`` makes the script raise."""

from bouncekit import Scene

scene = Scene(width=64, height=64, fps=30, duration=0.2, seed=7, max_speed=1000)
mode = scene.param("mode", "a")
if mode == "bad":
    raise RuntimeError("flaky scene refuses mode=bad")
scene.add_circle(center=(32, 32), radius=28, segments=24, tags={"wall"})
scene.add_ball(pos=(32, 28), radius=4, velocity=(60.0, 0.0), color="#40ff80", tags={"ball"})
