"""One ball in a ring; every wall hit splits it in two, up to a cap, playing a note.

Render:   uv run bouncekit render examples/split_on_wall.py --seed 42
Preview:  uv run bouncekit preview examples/split_on_wall.py   (silent)
"""

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CAP = 128

scene = Scene(duration=20.0, seed=42, background="#0b0b14", gravity=(0.0, 0.0), max_balls=CAP)

scene.add_circle(center=(540, 960), radius=450, thickness=8, color="#ffffff", tags={"wall"})
scene.add_ball(
    pos=(540, 960),
    radius=18,
    velocity=(scene.rng.uniform(-500.0, 500.0), scene.rng.uniform(300.0, 600.0)),
    color="#ffb703",
    tags={"ball"},
    constant_speed=True,
)
scene.on_collision(
    "ball",
    "wall",
    [A.split(into=2, spread_degrees=40, max_total=CAP), A.play(S.scale("C4", voice="marimba"))],
)

if __name__ == "__main__":
    scene.run()
