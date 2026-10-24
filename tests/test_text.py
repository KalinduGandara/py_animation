"""Text overlay (FR-406, FR-407, NFR-401, NFR-402)."""

import os
from typing import Any

import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import ConfigError, Scene, Text  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402

WHITE = (255, 255, 255)


def _img(r: PygameRenderer) -> np.ndarray:
    return np.frombuffer(r.to_rgb_bytes(), np.uint8).reshape(r.height, r.width, 3)


def _bbox(img: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(img.any(axis=2))
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _black(w: int = 400, h: int = 200) -> PygameRenderer:
    r = PygameRenderer(w, h)
    r.clear((0, 0, 0))
    return r


def _scene(**kw: Any) -> Scene:
    return Scene(width=200, height=120, fps=30, duration=2.0, seed=3, **kw)


def _frames(scene: Scene) -> list[bytes]:
    return list(scene.frames())


def test_renderer_text_is_centred_and_bounded() -> None:
    r = _black()
    r.text("Hi", (200, 100), 48, WHITE)
    x0, x1, y0, y1 = _bbox(_img(r))
    assert abs((x0 + x1) / 2 - 200) <= 3
    assert abs((y0 + y1) / 2 - 100) <= 3
    assert x0 >= 100 and x1 <= 300 and y0 >= 60 and y1 <= 140


def test_renderer_text_deterministic_and_blank_noop() -> None:
    a, b = _black(), _black()
    a.text("Hi", (200, 100), 48, WHITE)
    b.text("Hi", (200, 100), 48, WHITE)
    assert a.to_rgb_bytes() == b.to_rgb_bytes()
    c = _black()
    before = c.to_rgb_bytes()
    c.text("", (200, 100), 48, WHITE)
    c.text("  ", (200, 100), 48, WHITE)
    assert c.to_rgb_bytes() == before


def test_visibility_is_frame_exact() -> None:
    plain = _frames(_scene())
    s = _scene()
    t = s.add_text("A", pos=(100, 60), size=40, start=0.5, end=1.0)
    assert isinstance(t, Text)
    assert (t.start_frame, t.end_frame) == (15, 30)
    assert t.visible(15) and t.visible(29) and not t.visible(14) and not t.visible(30)
    with_text = _frames(s)
    for f, (a, b) in enumerate(zip(plain, with_text, strict=True)):
        assert (a != b) == (15 <= f < 30), f


def test_open_ended_text() -> None:
    t = _scene().add_text("A", pos=(1, 1), start=1.0)
    assert t.end_frame is None and t.visible(10**6) and not t.visible(29)


def test_two_lines_spacing() -> None:
    size = 30
    s = _scene()
    s.add_text("I\nI", pos=(100, 60), size=size)
    r = PygameRenderer(200, 120)
    s.draw(r)
    img = _img(r)
    rows = np.nonzero(img.any(axis=2).any(axis=1))[0]
    # split into two clusters
    gap = np.nonzero(np.diff(rows) > 1)[0]
    assert len(gap) == 1
    first = rows[: gap[0] + 1]
    second = rows[gap[0] + 1 :]
    assert second[0] - first[0] == round(1.2 * size)


def test_callable_text_changes_and_bad_return() -> None:
    s = _scene()
    s.add_text(lambda sc: f"{sc.frame}", pos=(100, 60), size=40)
    r1, r2 = PygameRenderer(200, 120), PygameRenderer(200, 120)
    s.draw(r1)
    s.step_frame()
    s.draw(r2)
    assert r1.to_rgb_bytes() != r2.to_rgb_bytes()
    bad = _scene()
    bad.add_text(lambda sc: 3, pos=(100, 60))  # type: ignore[arg-type,return-value]
    with pytest.raises(ConfigError, match="text"):
        bad.draw(PygameRenderer(200, 120))


def test_text_drawn_over_glow() -> None:
    s = Scene(width=200, height=120, fps=30, duration=1.0, seed=1)
    s.add_ball(pos=(100, 60), radius=50, color="#ff00ff", glow=2.0)
    s.add_text("MMMM", pos=(100, 60), size=60, color="#00ff00")
    r = PygameRenderer(200, 120)
    s.draw(r)
    img = _img(r)
    assert ((img == (0, 255, 0)).all(axis=2)).sum() > 50


@pytest.mark.parametrize(
    ("arg", "value"),
    [
        ("pos", (1,)),
        ("pos", "ab"),
        ("size", 0),
        ("size", -3),
        ("size", float("nan")),
        ("size", 1001),
        ("size", True),
        ("color", "notacolor"),
        ("start", -1),
        ("start", float("inf")),
        ("end", float("nan")),
        ("end", 0.0),
        ("text", 5),
    ],
)
def test_bad_arguments_name_the_argument(arg: str, value: object) -> None:
    kw: dict[str, Any] = {"text": "x", "pos": (10, 10)}
    kw[arg] = value
    with pytest.raises(ConfigError, match=arg):
        _scene().add_text(kw.pop("text"), **kw)


def test_end_not_after_start_in_frames() -> None:
    with pytest.raises(ConfigError, match="end"):
        _scene().add_text("x", pos=(1, 1), start=0.5, end=0.51)


def test_text_not_an_object_and_listed() -> None:
    s = _scene()
    t = s.add_text("x", pos=(1, 1))
    assert s.objects == () and s.count() == 0
    assert s.texts == (t,)


def test_text_does_not_change_simulation() -> None:
    def build(with_text: bool) -> Scene:
        s = Scene(width=200, height=200, fps=30, duration=1.5, seed=9)
        s.add_circle(center=(100, 100), radius=80, gap_degrees=30, angular_velocity=40)
        s.add_ball(pos=(100, 80), radius=14, velocity=(50, 20))
        s.on_collision("ball", "wall", [A.recolor("#ff0000")])
        if with_text:
            s.add_text(lambda sc: f"{sc.frame}", pos=(100, 100))
        return s

    a, b = build(False), build(True)
    ra, rb = PygameRenderer(200, 200), PygameRenderer(200, 200)
    for _ in range(a.total_frames):
        a.draw(ra)
        b.draw(rb)
        a.step_frame()
        b.step_frame()
        assert [o.position for o in a._balls] == [o.position for o in b._balls]
        assert a.rng.getstate() == b.rng.getstate()
    key = lambda e: (e.kind, e.step, e.frame, e.speed, e.position)  # noqa: E731
    assert [key(e) for e in a.events] == [key(e) for e in b.events]
    assert a.events


def test_text_free_scene_makes_no_text_calls() -> None:
    class Spy(PygameRenderer):
        calls = 0

        def text(self, *args: Any, **kw: Any) -> None:
            Spy.calls += 1

    s = _scene()
    s.draw(Spy(200, 120))
    assert Spy.calls == 0
