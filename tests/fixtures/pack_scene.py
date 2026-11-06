"""Fixture: tiny scene for climax marks, post text and the export pack (T-606)."""

from bouncekit import Scene
from bouncekit import actions as A

scene = Scene(width=64, height=48, fps=30, duration=1.0, seed=2, gravity=(0.0, 300.0),
              max_speed=1000)  # fmt: skip
mark = scene.param("mark", 0.0)
post = scene.param("post", True)
fail = scene.param("fail", False)
scene.add_circle(center=(32, 24), radius=20, segments=32, tags={"wall"})
scene.add_ball(pos=(32, 20), radius=4, velocity=(90, 0), color="#ffcc00", tags={"ball"})
if mark > 0:
    scene.at(mark, [A.mark_climax()])
scene.at(0.7, [A.end_after(0.1)])
if post:
    scene.post(title=lambda s: f"Ended at frame {s.frame}", description="Tiny test",
               hashtags=["physics", "#satisfying"])  # fmt: skip
if fail:
    scene.every(0.5, [lambda ctx: 1 / 0])  # type: ignore[list-item]
