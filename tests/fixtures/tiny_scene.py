"""Fixture: one tiny scene whose ball velocity comes from ``scene.rng``."""

from bouncekit import Scene

scene = Scene(width=64, height=48, fps=30, duration=0.5, seed=7, gravity=(0.0, 0.0))
vx = scene.rng.uniform(-50.0, 50.0)
scene.add_circle(center=(32, 24), radius=20, segments=32)
ball = scene.add_ball(pos=(32, 24), radius=4, velocity=(vx, 10.0), color="#ff0000")
same = scene  # a second name for the same instance still counts as one scene

if __name__ == "__main__":
    scene.run()
