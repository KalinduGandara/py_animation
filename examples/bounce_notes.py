"""A ball bouncing in a ring; every wall hit plays the next note of a pentatonic scale.

Render:   uv run bouncekit render examples/bounce_notes.py --seed 42
Preview:  uv run bouncekit preview examples/bounce_notes.py   (silent)
"""

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

scene = Scene(duration=10.0, seed=42, background="#101018")

scene.add_circle(center=(540, 960), radius=450, thickness=8, color="#ffffff", tags={"wall"})
scene.add_ball(
    pos=(540, 700),
    radius=30,
    velocity=(scene.rng.uniform(-300.0, 300.0), 0.0),
    color="#ff5a5f",
    tags={"ball"},
)
scene.on_collision("ball", "wall", [A.play(S.scale("C4", voice="pluck"))])

if __name__ == "__main__":
    scene.run()
