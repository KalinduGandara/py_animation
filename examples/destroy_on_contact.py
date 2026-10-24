"""Balls rain onto a hazard and are destroyed on contact; the video ends after the fifth.

``every`` spawns a new ball each half second, a Python callback counts the hits, and
``when`` + ``end_after`` ends the video a second after the fifth one.

Render:   uv run bouncekit render examples/destroy_on_contact.py --seed 42
Preview:  uv run bouncekit preview examples/destroy_on_contact.py   (silent)
"""

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CENTER = (540.0, 960.0)
KILLS_TO_END = 5

scene = Scene(duration=30.0, seed=42, background="#140c14")

scene.add_circle(center=CENTER, radius=450, thickness=8, color="#ffffff", tags={"wall"})
scene.add_circle(center=CENTER, radius=90, thickness=16, color="#e63946", tags={"hazard"})
scene.add_ball(pos=(500, 560), radius=26, color="#ffd166", tags={"ball"})

kills: list[int] = []


def drop_pos(ctx):  # type: ignore[no-untyped-def]
    """A spot near the top of the ring, jittered with ``ctx.rng``."""
    return (CENTER[0] + ctx.rng.uniform(-80.0, 80.0), 600.0)


scene.every(
    0.5,
    [A.spawn(pos=drop_pos, radius=26, color="#ffd166", max_total=12)],
)
scene.on_collision("ball", "wall", [A.play(S.scale("E4", voice="pluck"))])


@scene.on_collision("ball", "hazard")
def on_hit(ctx, ball, hazard, event):  # type: ignore[no-untyped-def]
    """Count the hit, flash the hazard and destroy the ball."""
    kills.append(event.frame)
    ctx.flash(hazard, color="#ffffff")
    ctx.destroy(ball)
    ctx.play(S.note("C3", voice="marimba"))


scene.when(lambda s: len(kills) >= KILLS_TO_END, [A.end_after(1.0)])

if __name__ == "__main__":
    scene.run()
