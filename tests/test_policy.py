"""Trigger policy, voice stealing and AudioConfig validation (FR-106, FR-108)."""

import math

import numpy as np
import pytest

from bouncekit import AudioConfig, ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.mixer import NoteTrigger, mix
from bouncekit.audio.voices import Sine
from bouncekit.events import CollisionEvent
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

RATE = 480  # fps * substeps used below


def _scene(audio: AudioConfig | None = None) -> tuple[Scene, Ball, Ball, CircleBoundary]:
    s = Scene(width=400, height=400, fps=60, substeps=8, duration=10.0, audio=audio)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    b1 = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    b2 = s.add_ball(pos=(150, 200), radius=10, tags={"ball"})
    return s, b1, b2, ring


def _ev(step: int, a: Ball, b: Ball | CircleBoundary, speed: float = 1500.0) -> CollisionEvent:
    return CollisionEvent(
        kind="collision", step=step, frame=(step - 1) // 8, time=step / RATE,
        objects=(a, b), speed=speed, position=(0.0, 0.0),
    )  # fmt: skip


# --- Gain curve and min impact speed ------------------------------------------


@pytest.mark.parametrize(
    ("speed", "expected"),
    [(0.0, 0.0), (375.0, 0.5), (1500.0, 1.0), (3000.0, 1.0)],
)
def test_gain_curve(speed: float, expected: float) -> None:
    s, b1, _, ring = _scene(AudioConfig(min_impact_speed=0.0))
    s.on_collision("ball", "wall", [A.play(S.note("C4"), gain=0.8)])
    s._dispatch([_ev(1, b1, ring, speed=speed)])
    assert [t.gain for t in s.triggers] == pytest.approx([0.8 * expected])


def test_gain_uses_reference_speed() -> None:
    s, b1, _, ring = _scene(AudioConfig(reference_speed=400.0))
    s.on_collision("ball", "wall", [A.play(S.note("C4"))])
    s._dispatch([_ev(1, b1, ring, speed=100.0)])
    assert s.triggers[0].gain == pytest.approx(0.5)


def test_below_min_impact_speed_is_ignored() -> None:
    s, b1, _, ring = _scene(AudioConfig(min_impact_speed=40.0))
    s.on_collision("ball", "wall", [A.play(S.note("C4"))])
    s._dispatch([_ev(1, b1, ring, speed=39.9)])
    assert s.triggers == ()
    s._dispatch([_ev(2, b1, ring, speed=40.0)])
    assert len(s.triggers) == 1


# --- Retrigger interval ---------------------------------------------------------


def test_retrigger_interval_per_play_and_object() -> None:
    s, b1, b2, ring = _scene(AudioConfig(min_retrigger_interval=0.1))  # 48 steps
    play = A.play(S.note("C4"))
    other = A.play(S.note("E4"))
    s.on_collision("ball", "wall", [play, other])
    s._dispatch([_ev(10, b1, ring)])  # b1: both play
    s._dispatch([_ev(20, b2, ring)])  # b2 is a different object: both play
    s._dispatch([_ev(40, b1, ring)])  # 30 steps after b1's notes: dropped
    s._dispatch([_ev(58, b1, ring)])  # 48 steps = 0.1 s later: plays again
    s._dispatch([_ev(60, b2, ring)])  # 40 steps after b2's notes: dropped
    got = [(t.step, round(t.hz)) for t in s.triggers]
    assert got == [(10, 262), (10, 330), (20, 262), (20, 330), (58, 262), (58, 330)]


def test_retrigger_interval_counts_from_last_played_note() -> None:
    s, b1, _, ring = _scene(AudioConfig(min_retrigger_interval=0.1))
    s.on_collision("ball", "wall", [A.play(S.note("C4"))])
    for step in (1, 30, 49, 60, 97):
        s._dispatch([_ev(step, b1, ring)])
    # 30 is dropped (does not reset the clock), 49 plays, 60 dropped, 97 plays.
    assert [t.step for t in s.triggers] == [1, 49, 97]


# --- Per-frame cap ------------------------------------------------------------------


def test_per_frame_cap_drops_later_events_in_order() -> None:
    s, b1, b2, ring = _scene(AudioConfig(max_triggers_per_frame=3, min_retrigger_interval=0.0))
    s.on_collision("ball", "wall", [A.play(S.note("C4")), A.play(S.note("E4"))])
    s._dispatch([_ev(1, b1, ring), _ev(2, b2, ring), _ev(3, b1, ring)])
    assert [(t.step, round(t.hz)) for t in s.triggers] == [(1, 262), (1, 330), (2, 262)]
    s._dispatch([_ev(9, b2, ring)])  # next frame: the count starts again
    assert len(s.triggers) == 5


def test_per_frame_cap_in_simulation() -> None:
    s = Scene(width=400, height=400, fps=30, duration=2.0, seed=1, max_speed=2000,
              audio=AudioConfig(max_triggers_per_frame=1))  # fmt: skip
    s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    for _ in range(6):
        v = (s.rng.uniform(-800, 800), s.rng.uniform(-800, 800))
        s.add_ball(pos=(200, 200), radius=10, velocity=v, tags={"ball"})
    s.on_collision("ball", "wall", [A.play(S.note("C5"))])
    for _ in range(s.total_frames):
        s.step_frame()
    frames = [(t.step - 1) // s.config.substeps for t in s.triggers]
    assert frames
    assert len(frames) == len(set(frames))  # at most one note per frame


# --- Voice stealing ----------------------------------------------------------------

STEAL_AT = 10_000
FADE = 240


def _mix(polyphony: int) -> np.ndarray:
    v = Sine()
    trigs = [
        NoteTrigger(step=0, offset=0, voice=v, hz=440.0, gain=1.0),
        NoteTrigger(step=0, offset=100, voice=v, hz=660.0, gain=0.0),
        NoteTrigger(step=0, offset=STEAL_AT, voice=v, hz=550.0, gain=0.0),
    ]
    return mix(trigs, length=48_000, config=AudioConfig(max_polyphony=polyphony), seed=0)[:, 0]


def test_polyphony_steals_oldest_with_linear_5ms_fade() -> None:
    full, cut = _mix(3), _mix(2)
    assert np.array_equal(full[:STEAL_AT], cut[:STEAL_AT])
    assert not cut[STEAL_AT + FADE :].any()
    assert full[STEAL_AT + FADE : STEAL_AT + 2 * FADE].any()
    # Only the first note is audible: out = tanh(0.5 * note) * g in both mixes (same
    # peak, in the attack), so undoing tanh gives the steal fade applied to the note.
    note = Sine().render(440.0, 0)
    g = 10 ** (-1 / 20) / math.tanh(0.5 * float(np.abs(note).max()))
    window = slice(STEAL_AT, STEAL_AT + FADE)
    pre_cut = np.arctanh(cut[window].astype(np.float64) / g)
    pre_full = 0.5 * note[window]
    nz = np.abs(pre_full) > 1e-3
    ratio = pre_cut[nz] / pre_full[nz]
    expected = np.linspace(1.0, 0.0, FADE)[nz]
    assert ratio == pytest.approx(expected, abs=2e-3)


def test_finished_notes_do_not_count_as_sounding() -> None:
    v = Sine(duration=0.1)  # 4800 samples
    trigs = [
        NoteTrigger(step=0, offset=0, voice=v, hz=440.0, gain=1.0),
        NoteTrigger(step=0, offset=4800, voice=v, hz=440.0, gain=1.0),
    ]
    one = mix(trigs, length=12_000, config=AudioConfig(max_polyphony=1), seed=0)
    many = mix(trigs, length=12_000, config=AudioConfig(max_polyphony=24), seed=0)
    assert np.array_equal(one, many)


# --- AudioConfig validation ----------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("min_impact_speed", -1.0),
        ("min_impact_speed", math.nan),
        ("min_impact_speed", "40"),
        ("reference_speed", 0.0),
        ("reference_speed", -5.0),
        ("reference_speed", math.inf),
        ("min_retrigger_interval", -0.01),
        ("min_retrigger_interval", None),
        ("max_triggers_per_frame", 0),
        ("max_triggers_per_frame", 2.0),
        ("max_triggers_per_frame", True),
        ("max_polyphony", 0),
        ("max_polyphony", -3),
        ("max_polyphony", 1.5),
        ("peak_dbfs", 0.5),
        ("peak_dbfs", math.nan),
    ],
)
def test_bad_audio_config_names_field_and_value(field: str, bad: object) -> None:
    with pytest.raises(ConfigError, match=field) as e:
        AudioConfig(**{field: bad})  # type: ignore[arg-type]
    assert repr(bad) in str(e.value)


def test_audio_config_edge_values_and_coercion() -> None:
    c = AudioConfig(min_impact_speed=0, reference_speed=1, min_retrigger_interval=0,
                    max_triggers_per_frame=1, max_polyphony=1, peak_dbfs=0)  # fmt: skip
    assert c.min_impact_speed == 0.0 and isinstance(c.min_impact_speed, float)
    assert isinstance(c.reference_speed, float) and isinstance(c.peak_dbfs, float)
    assert isinstance(c.min_retrigger_interval, float)
