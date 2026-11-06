"""Ball labels (T-604: FR-605, NFR-601)."""

import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene, cli  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.colors import Color  # noqa: E402
from bouncekit.config import Vec  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.render.base import GlowArc, GlowDisc  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.world.ball import Ball  # noqa: E402

EXAMPLES = Path(__file__).parent.parent / "examples"
# examples/midi_melody.py, 0.5 s, recorded before T-604 (commit 16e36b4).
GOLDEN_MIDI_MELODY = "3cc487e9f1cf3aa6a827a224528e5308d2e6c91e7454cb424fbf299db0eef158"


class Spy(PygameRenderer):
    def __init__(self, width: int, height: int) -> None:
        super().__init__(width, height)
        self.calls: list[tuple[object, ...]] = []

    def text(self, text: str, center: Vec, size: float, color: Color) -> None:
        self.calls.append(("text", text, center, size, color))
        super().text(text, center, size, color)

    def glow(self, lights: object, *, blur: float) -> None:
        self.calls.append(("glow",))
        super().glow(lights, blur=blur)  # type: ignore[arg-type]


def _scene() -> Scene:
    return Scene(width=200, height=200, duration=1.0, gravity=(0.0, 0.0))


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [({"label": 5}, "label"), ({"label_color": "nope"}, "label_color"),
     ({"label_scale": 0}, "label_scale"), ({"label_scale": float("nan")}, "label_scale")],
)  # fmt: skip
def test_bad_label_options_raise(kwargs: dict[str, object], field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        _scene().add_ball(pos=(100, 100), radius=10, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match=field):
        A.spawn(pos=(100, 100), radius=10, **kwargs)  # type: ignore[arg-type]


def test_label_drawn_after_glow_before_overlay_with_auto_contrast() -> None:
    scene = _scene()
    scene.add_ball(pos=(50, 100), radius=20, color="#ffd400", label="BR", glow=1.0)
    scene.add_ball(pos=(150, 100), radius=10, color="#101040", label="\U0001f525",
                   label_scale=1.5)  # fmt: skip
    scene.add_ball(pos=(100, 40), radius=10, color="#101040", label="x", label_color="#ff0000")
    scene.add_ball(pos=(100, 160), radius=10)  # unlabelled
    scene.add_text("HOOK", pos=(100, 20), size=12)
    spy = Spy(200, 200)
    scene.draw(spy)
    assert spy.calls == [
        ("glow",),
        ("text", "BR", (50.0, 100.0), 20.0, (17, 17, 17)),
        ("text", "\U0001f525", (150.0, 100.0), 15.0, (255, 255, 255)),
        ("text", "x", (100.0, 40.0), 10.0, (255, 0, 0)),
        ("text", "HOOK", (100.0, 20.0), 12, (255, 255, 255)),
    ]


def test_split_and_spawn_carry_labels_and_attributes_are_settable() -> None:
    scene = _scene()
    scene.add_circle(center=(100, 100), radius=90, tags={"wall"})
    ball = scene.add_ball(pos=(100, 100), radius=8, velocity=(300, 0), label="A",
                          label_color="#00ff00", label_scale=0.8, tags={"ball"})  # fmt: skip
    scene.on_collision("ball", "wall", [A.split(into=2, max_total=3)])
    scene.at(0.05, [A.spawn(pos=(60, 60), radius=6, label="S", tags=("spawned",))])
    for _ in range(40):
        scene.step_frame()
    balls = [o for o in scene.objects if isinstance(o, Ball)]
    labelled = [(b.label, b.label_color, b.label_scale) for b in balls if "ball" in b.tags]
    assert labelled == [("A", (0, 255, 0), 0.8)] * 2
    assert [(b.label, b.label_color, b.label_scale) for b in balls if "spawned" in b.tags] == [
        ("S", None, 1.0)
    ]
    ball.label = "Z"
    spy = Spy(200, 200)
    scene.draw(spy)
    assert ("text", "Z") in [c[:2] for c in spy.calls]


def test_labels_do_not_change_the_simulation() -> None:
    def run(label: str | None) -> Scene:
        scene = Scene(width=200, height=200, duration=1.0, seed=2)
        scene.add_circle(center=(100, 100), radius=90, tags={"wall"})
        scene.add_ball(pos=(100, 80), radius=8, velocity=(scene.rng.uniform(-200, 200), 0),
                       label=label, tags={"ball"})  # fmt: skip
        scene.on_collision("ball", "wall", [A.split(max_total=8)])
        for _ in scene.frames():
            pass
        return scene

    a, b = run("L"), run(None)
    assert [(e.kind, e.frame, e.step) for e in a.events] == [
        (e.kind, e.frame, e.step) for e in b.events
    ]
    assert a.rng.getstate() == b.rng.getstate()


def test_label_free_example_keeps_frame_bytes() -> None:
    scene = cli.load_scene(EXAMPLES / "midi_melody.py", duration=0.5)
    digest = hashlib.sha256()
    for frame in scene.frames():
        digest.update(frame)
    assert digest.hexdigest() == GOLDEN_MIDI_MELODY


def test_glow_types_unchanged() -> None:  # labels never become lights
    scene = _scene()
    scene.add_ball(pos=(50, 100), radius=20, label="BR", glow=1.0)
    lights: list[object] = []

    class Lights(PygameRenderer):
        def glow(self, ls: object, *, blur: float) -> None:
            lights.extend(ls)  # type: ignore[call-overload]

    scene.draw(Lights(200, 200))
    assert len(lights) == 1 and isinstance(lights[0], GlowDisc | GlowArc)


# Review fixes (2026-11-06).
def test_sub_pixel_label_is_skipped_not_a_crash() -> None:
    scene = _scene()
    scene.add_ball(pos=(100, 100), radius=20, label="x", label_scale=0.0001)
    spy = Spy(200, 200)
    scene.draw(spy)
    assert not [c for c in spy.calls if c[0] == "text"]


def test_ctx_spawn_validates_label() -> None:
    scene = _scene()
    scene.add_ball(pos=(100, 100), radius=5, tags={"ball"})

    @scene.at(0.01)
    def boom(ctx, event):  # type: ignore[no-untyped-def]
        ctx.spawn(pos=(50, 50), radius=5, label_scale=-1)

    with pytest.raises(ConfigError, match="label_scale"):
        for _ in range(3):
            scene.step_frame()


def test_auto_contrast_follows_the_flash_colour() -> None:
    scene = _scene()
    ball = scene.add_ball(pos=(100, 100), radius=20, color="#101040", label="A", tags={"b"})
    scene.at(0.01, [A.flash(target=ball, color="#ffffff", seconds=1.0)])
    for _ in range(2):
        scene.step_frame()
    spy = Spy(200, 200)
    scene.draw(spy)
    assert [c[4] for c in spy.calls if c[0] == "text"] == [(17, 17, 17)]
