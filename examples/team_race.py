"""Three labelled balls race to escape a spinning gap; the first one out wins (M6 features).

Shows ball labels (with an emoji), ``scene.stat`` for batch scoring, ``loop_fade``,
``A.mark_climax`` for the thumbnail and ``scene.post`` for the upload text.

Render:   uv run bouncekit render examples/team_race.py --export
Pick:     uv run bouncekit batch examples/team_race.py --seeds 1-6 --score "-stats.escape_time"
          --keep-best 2 --export
Preview:  uv run bouncekit preview examples/team_race.py   (silent)
"""

import math

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

CENTER = (540.0, 960.0)
TEAMS = (("\U0001f525", "#ff5a36"), ("ICE", "#7fd6ff"), ("GO", "#ffe14d"))

scene = Scene(duration=25.0, seed=3, background="#0b0b14", gravity=(0.0, 0.0), loop_fade=0.4)
speed = scene.param("speed", 520.0)
gap = scene.param("gap", 26.0)

ring = scene.add_circle(center=CENTER, radius=420, thickness=10, color="#e8e8ff", glow=0.8,
                        gap_degrees=gap, angular_velocity=60, tags={"wall"})  # fmt: skip
balls = []
for k, (label, color) in enumerate(TEAMS):
    angle = scene.rng.uniform(0.0, 2.0 * math.pi)
    balls.append(
        scene.add_ball(
            pos=(CENTER[0] + (k - 1) * 90.0, CENTER[1]),
            radius=34,
            velocity=(speed * math.cos(angle), speed * math.sin(angle)),
            color=color,
            label=label,
            constant_speed=True,
            trail=True,
            tags={"ball"},
        )
    )
winner: dict[str, object] = {}
scene.stat("escape_time", scene.config.duration)  # replaced when someone escapes


@scene.on_collision("ball", "wall")
def nudge(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    """Turn a few degrees on each hit so no ball settles into a loop that misses the gap."""
    vx, vy = ball.velocity
    turn = math.radians(ctx.rng.uniform(-8.0, 8.0))
    c, s = math.cos(turn), math.sin(turn)
    ctx.set_velocity(ball, (vx * c - vy * s, vx * s + vy * c))


scene.on_collision("ball", "wall", [A.play(S.scale("C4", mode="major_pentatonic", voice="pluck"))])


@scene.on_escape(ring, "ball")
def first_out(ctx, ball, _ring, event):  # type: ignore[no-untyped-def]
    if winner:
        return
    winner["label"] = ball.label
    scene.stat("winner_index", balls.index(ball))
    scene.stat("escape_time", round(scene.time, 3))
    ctx.mark_climax()
    ctx.end_after(2.0)


scene.add_text("Which one escapes first?", pos=(540, 330), size=64, end=3.0)
scene.add_text(lambda s: f"{winner['label']} WINS!" if winner else "", pos=(540, 1560), size=96)
scene.post(
    title=lambda s: f"{winner.get('label', 'Nobody')} escaped first! Which one did you pick?",
    description="Three balls, one spinning gap. Pick yours before it starts.",
    hashtags=["physics", "satisfying", "shorts"],
)

if __name__ == "__main__":
    scene.run()
