"""Scale source and its per-scene cursor (FR-103)."""

import pytest

from bouncekit import ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.voices import Pluck, Sine
from bouncekit.config import AudioConfig
from bouncekit.events import CollisionEvent
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary


def _hz(names: list[str]) -> list[float]:
    return [S.pitch_to_hz(n) for n in names]


def test_c4_major_pentatonic_one_octave() -> None:
    sc = S.scale("C4", octaves=1)
    assert sc.hz == pytest.approx(_hz(["C4", "D4", "E4", "G4", "A4", "C5"]))
    assert sc.voice == Sine()


def test_defaults_two_octaves_with_top_root() -> None:
    sc = S.scale()
    assert sc.hz == pytest.approx(
        _hz(["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5", "G5", "A5", "C6"])
    )


@pytest.mark.parametrize(
    ("mode", "intervals"),
    [
        ("major", [0, 2, 4, 5, 7, 9, 11]),
        ("minor", [0, 2, 3, 5, 7, 8, 10]),
        ("major_pentatonic", [0, 2, 4, 7, 9]),
        ("minor_pentatonic", [0, 3, 5, 7, 10]),
        ("chromatic", list(range(12))),
    ],
)
def test_mode_intervals(mode: str, intervals: list[int]) -> None:
    sc = S.scale(57, mode=mode, octaves=2)  # A3
    semis = [*intervals, *(i + 12 for i in intervals), 24]
    assert sc.hz == pytest.approx([S.pitch_to_hz(57 + k) for k in semis])


def test_root_as_hz_and_voice() -> None:
    sc = S.scale(440.0, mode="major", octaves=1, voice="pluck")
    assert sc.hz[0] == pytest.approx(440.0)
    assert sc.hz[-1] == pytest.approx(880.0)
    assert sc.voice == Pluck()
    custom = Pluck(duration=0.5)
    assert S.scale("C4", voice=custom).voice is custom


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"mode": "dorian"}, "mode"),
        ({"mode": 3}, "mode"),
        ({"octaves": 0}, "octaves"),
        ({"octaves": 9}, "octaves"),
        ({"octaves": 1.0}, "octaves"),
        ({"octaves": True}, "octaves"),
        ({"voice": "kazoo"}, "voice"),
        ({"root": "H4"}, "pitch"),
        ({"root": "G9", "octaves": 1}, "20 kHz"),  # top note would exceed 20 kHz
    ],
)
def test_bad_scale_raises(kwargs: dict[str, object], field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        S.scale(**kwargs)  # type: ignore[arg-type]


def test_scale_is_compared_by_identity() -> None:
    a, b = S.scale("C4"), S.scale("C4")
    assert a != b
    assert len({a, b}) == 2
    assert A.play(a).source is a


# --- Cursor behaviour --------------------------------------------------------


def _scene(**audio: float) -> tuple[Scene, Ball, Ball, CircleBoundary]:
    s = Scene(width=400, height=400, fps=60, substeps=8, duration=10.0,
              audio=AudioConfig(**audio))  # type: ignore[arg-type]  # fmt: skip
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    b1 = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    b2 = s.add_ball(pos=(150, 200), radius=10, tags={"ball"})
    return s, b1, b2, ring


def _ev(step: int, a: Ball, b: Ball | CircleBoundary, speed: float = 1500.0) -> CollisionEvent:
    return CollisionEvent(
        kind="collision", step=step, frame=(step - 1) // 8, time=step / 480,
        objects=(a, b), speed=speed, position=(0.0, 0.0),
    )  # fmt: skip


def test_cursor_advances_and_wraps() -> None:
    s, b1, _, ring = _scene()
    sc = S.scale("C4", octaves=1)
    s.on_collision("ball", "wall", [A.play(sc)])
    for i in range(8):
        s._dispatch([_ev(1 + 100 * i, b1, ring)])
    assert [t.hz for t in s.triggers] == [*sc.hz, sc.hz[0], sc.hz[1]]


def test_dropped_triggers_do_not_advance_cursor() -> None:
    s, b1, _, ring = _scene()
    sc = S.scale("C4", octaves=1)
    s.on_collision("ball", "wall", [A.play(sc)])
    s._dispatch([_ev(1, b1, ring)])
    s._dispatch([_ev(2, b1, ring)])  # within the retrigger interval: dropped
    s._dispatch([_ev(200, b1, ring, speed=10.0)])  # below min impact speed: dropped
    s._dispatch([_ev(400, b1, ring)])
    assert [t.hz for t in s.triggers] == list(sc.hz[:2])


def test_shared_instance_shares_cursor_across_rules() -> None:
    s, b1, b2, ring = _scene()
    sc = S.scale("C4", octaves=1)
    s.on_collision("ball", "wall", [A.play(sc)])
    s.on_collision("ball", "ball", [A.play(sc, gain=0.5)])
    s._dispatch([_ev(1, b1, ring), _ev(2, b1, b2), _ev(3, b2, ring)])
    assert [t.hz for t in s.triggers] == list(sc.hz[:3])


def test_separate_instances_have_separate_cursors() -> None:
    s, b1, b2, ring = _scene()
    s.on_collision("ball", "wall", [A.play(S.scale("C4", octaves=1))])
    s.on_collision("ball", "wall", [A.play(S.scale("C4", octaves=1))])
    s._dispatch([_ev(1, b1, ring)])
    c4 = S.pitch_to_hz("C4")
    assert [t.hz for t in s.triggers] == pytest.approx([c4, c4])


def test_fresh_scene_restarts_at_first_note() -> None:
    sc = S.scale("C4", octaves=1)
    for _ in range(2):
        s, b1, _, ring = _scene()
        s.on_collision("ball", "wall", [A.play(sc)])
        s._dispatch([_ev(1, b1, ring)])
        s._dispatch([_ev(100, b1, ring)])
        assert [t.hz for t in s.triggers] == list(sc.hz[:2])
