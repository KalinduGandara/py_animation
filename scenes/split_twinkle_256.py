"""One ball in a ring; every wall hit splits it in two and plays the next note of
"Twinkle Twinkle Little Star". The video stops when there are 256 balls.

Render:   uv run bouncekit render scenes/split_twinkle_256.py
Preview:  uv run bouncekit preview scenes/split_twinkle_256.py
"""

from pathlib import Path

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CENTER = (540.0, 960.0)
TARGET = 256

scene = Scene(duration=60.0, seed=42, background="#07070d", gravity=(0.0, 0.0), max_balls=TARGET)

speed = scene.param("speed", 520.0)
ball_radius = scene.param("ball_radius", 14.0)
hold = scene.param("hold", 1.0)  # seconds shown after reaching 256 balls

ring = scene.add_circle(
    center=CENTER, radius=450, thickness=8, color="#e8e8ff", glow=1.0, tags={"wall"}
)

angle_x = scene.rng.uniform(-0.6, 0.6)
scene.add_ball(
    pos=(540, 860),
    radius=ball_radius,
    velocity=(speed * angle_x, speed * (1 - angle_x * angle_x) ** 0.5),
    color=C.hue_cycle(step=29),
    trail=True,
    glow=1.0,
    constant_speed=True,
    tags={"ball"},
)

twinkle = S.melody(
    ASSETS / "midi" / "twinkle.mid",
    voice=S.sample(ASSETS / "samples" / "kalimba.wav", root="A4"),
)

scene.on_collision(
    "ball",
    "wall",
    [
        A.play(twinkle, pan=0.6),
        A.split(into=2, spread_degrees=40, max_total=TARGET),
        A.particles(count=8, speed=350, lifetime=0.4),
    ],
)

scene.when(lambda s: s.count("ball") >= TARGET, [A.end_after(hold)])

scene.add_text("1 ball. Every bounce = 2", pos=(540, 300), size=60, end=3.5)
scene.add_text(lambda s: f"{s.count('ball')} / {TARGET} balls", pos=(540, 1600), size=56)

if __name__ == "__main__":
    scene.run()
