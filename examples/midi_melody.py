"""Hue-cycling balls with trails and glow play "Ode to Joy" off a glowing ring.

Every wall hit plays the next chord of the MIDI file with a kalimba sample, panned by
where the ball hits, bursts particles and flashes the ring. A hit also splits the ball
(up to a small cap) so the tune speeds up.

Render:   uv run bouncekit render examples/midi_melody.py --seed 42
Preview:  uv run bouncekit preview examples/midi_melody.py   (silent, hot-reloads on save)
"""

from pathlib import Path

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CAP = 10

scene = Scene(duration=30.0, seed=42, background="#07070d", gravity=(0.0, 0.0), max_balls=CAP)

ring = scene.add_circle(
    center=(540, 960), radius=450, thickness=8, color="#e8e8ff", glow=1.0, tags={"wall"}
)
hues = C.hue_cycle(step=37)
scene.add_ball(
    pos=(540, 800),
    radius=22,
    velocity=(scene.rng.uniform(-700.0, 700.0), scene.rng.uniform(500.0, 900.0)),
    color=hues,
    trail=True,
    glow=1.0,
    tags={"ball"},
    constant_speed=True,
)

tune = S.melody(
    ASSETS / "midi" / "ode_to_joy.mid",
    voice=S.sample(ASSETS / "samples" / "kalimba.wav", root="A4"),
)
scene.on_collision(
    "ball",
    "wall",
    [
        A.play(tune, pan=0.8),
        A.particles(count=14, speed=450, lifetime=0.5),
        A.flash("b", seconds=0.1),
        A.split(into=2, spread_degrees=40, max_total=CAP),
    ],
)

if __name__ == "__main__":
    scene.run()
