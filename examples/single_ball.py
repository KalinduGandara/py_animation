"""One ball bouncing under gravity inside a ring.

Render:   uv run bouncekit render examples/single_ball.py --seed 42
Preview:  uv run bouncekit preview examples/single_ball.py
"""

from bouncekit import Scene

scene = Scene(duration=10.0, seed=42, background="#101018")

scene.add_circle(center=(540, 960), radius=450, thickness=8, color="#ffffff")
scene.add_ball(
    pos=(540, 700),
    radius=30,
    velocity=(scene.rng.uniform(-300.0, 300.0), 0.0),
    color="#ff5a5f",
)

if __name__ == "__main__":
    scene.run()
