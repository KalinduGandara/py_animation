"""T-304: stereo pan by x-position (FR-309)."""

import math

import numpy as np
import pytest

from bouncekit import ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.mixer import NOTE_LEVEL, NoteTrigger, mix, pan_gains
from bouncekit.audio.voices import Sine
from bouncekit.config import AudioConfig
from bouncekit.events import CollisionEvent
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

SQ2 = math.sqrt(2.0)
CFG = AudioConfig()


# --- pan_gains ------------------------------------------------------------------


def test_pan_gains_extremes_and_centre() -> None:
    assert pan_gains(-1.0) == (SQ2, 0.0)
    assert pan_gains(1.0) == (0.0, SQ2)
    assert pan_gains(0.0) == (1.0, 1.0)


@pytest.mark.parametrize("pan", list(np.linspace(-1.0, 1.0, 41)) + [1e-9, -1e-9, 0.3333])
def test_pan_gains_equal_power_and_mirrored(pan: float) -> None:
    left, right = pan_gains(pan)
    assert left**2 + right**2 == pytest.approx(2.0, abs=1e-12)
    assert left >= 0.0 and right >= 0.0
    assert pan_gains(-pan) == (right, left)


def test_pan_gains_matches_spec_formula() -> None:
    for pan in np.linspace(-1.0, 1.0, 17):
        if pan == 0.0:
            continue
        theta = (pan + 1) * math.pi / 4
        assert pan_gains(pan) == pytest.approx((SQ2 * math.cos(theta), SQ2 * math.sin(theta)))


# --- mixer -----------------------------------------------------------------------


def _trig(offset: int, hz: float, pan: float = 0.0, gain: float = 1.0) -> NoteTrigger:
    return NoteTrigger(step=offset, offset=offset, voice=Sine(), hz=hz, gain=gain, pan=pan)


def test_note_trigger_pan_defaults_to_zero() -> None:
    t = NoteTrigger(step=0, offset=0, voice=Sine(), hz=440.0, gain=1.0)
    assert t.pan == 0.0


def _m1_reference(triggers: list[NoteTrigger], length: int) -> np.ndarray:
    """The M1 centred mix for non-overlapping notes, computed independently."""
    acc = np.zeros(length)
    for t in triggers:
        note = t.voice.render(t.hz, 0)
        end = min(t.offset + len(note), length)
        acc[t.offset : end] += note[: end - t.offset] * (t.gain * NOTE_LEVEL)
    out = np.tanh(acc)
    out *= 10 ** (CFG.peak_dbfs / 20) / np.abs(out).max()
    out[length - 240 :] *= np.linspace(1.0, 0.0, 240)
    return np.stack([out, out], axis=1).astype(np.float32)


def test_unpanned_mix_is_the_m1_path() -> None:
    trigs = [_trig(0, 440.0), _trig(48_000, 660.0, gain=0.5)]
    out = mix(trigs, length=96_000, config=CFG, seed=0)
    assert out.tobytes() == _m1_reference(trigs, 96_000).tobytes()


def test_hard_left_is_silent_right() -> None:
    out = mix([_trig(100, 440.0, pan=-1.0)], length=48_000, config=CFG, seed=0)
    assert not np.any(out[:, 1])
    assert float(np.abs(out[:, 0]).max()) == pytest.approx(10 ** (CFG.peak_dbfs / 20), rel=1e-6)


def test_hard_right_is_silent_left() -> None:
    out = mix([_trig(100, 440.0, pan=1.0)], length=48_000, config=CFG, seed=0)
    assert not np.any(out[:, 0])
    assert np.any(out[:, 1])


def test_stereo_mix_shares_one_peak_normalisation() -> None:
    trigs = [_trig(0, 440.0, pan=-0.5), _trig(10_000, 660.0, pan=0.8, gain=0.4)]
    out = mix(trigs, length=48_000, config=CFG, seed=0)
    peak = float(np.abs(out.astype(np.float64)).max())
    assert peak == pytest.approx(10 ** (CFG.peak_dbfs / 20), rel=1e-6)
    left_peak = float(np.abs(out[:10_000, 0]).max())
    right_peak = float(np.abs(out[:10_000, 1]).max())
    assert left_peak > right_peak > 0.0  # the image is kept, not normalised per channel
    assert out[-1, 0] == 0.0 and out[-1, 1] == 0.0  # end fade on both channels


def test_mixed_panned_and_centred_notes() -> None:
    centred = [_trig(0, 440.0)]
    both = [*centred, _trig(30_000, 880.0, pan=-1.0)]
    out = mix(both, length=60_000, config=CFG, seed=0)
    # Before the panned note starts, a centred note is identical in both channels.
    np.testing.assert_array_equal(out[:30_000, 0], out[:30_000, 1])


# --- Play / scene ----------------------------------------------------------------


def _scene() -> tuple[Scene, Ball, CircleBoundary]:
    s = Scene(width=400, height=400, fps=60, substeps=8, duration=3.0)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    ball = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    return s, ball, ring


def _ev(step: int, a: Ball, b: CircleBoundary, x: float) -> CollisionEvent:
    return CollisionEvent(
        kind="collision", step=step, frame=(step - 1) // 8, time=step / 480,
        objects=(a, b), speed=1500.0, position=(x, 100.0),
    )  # fmt: skip


@pytest.mark.parametrize(
    ("x", "pan", "expected"),
    [(0.0, 1.0, -1.0), (400.0, 1.0, 1.0), (100.0, 0.5, -0.25), (-50.0, 1.0, -1.0),
     (900.0, 0.7, 0.7), (200.0, 1.0, 0.0), (0.0, 0.0, 0.0)],
)  # fmt: skip
def test_trigger_pan_from_event_x(x: float, pan: float, expected: float) -> None:
    s, ball, ring = _scene()
    s.on_collision("ball", "wall", [A.play(S.note("A4"), pan=pan)])
    s._dispatch([_ev(1, ball, ring, x)])
    (trig,) = s.triggers
    assert trig.pan == pytest.approx(expected, abs=1e-15)


def test_left_edge_hit_is_silent_right() -> None:
    s, ball, ring = _scene()
    s.on_collision("ball", "wall", [A.play(S.note("A4"), pan=1.0)])
    s._dispatch([_ev(1, ball, ring, 0.0)])
    out = mix(s.triggers, length=48_000, config=CFG, seed=0)
    assert not np.any(out[:, 1])
    assert np.any(out[:, 0])


def test_centre_hit_equals_m1_note() -> None:
    s, ball, ring = _scene()
    s.on_collision("ball", "wall", [A.play(S.note("A4"), pan=1.0)])
    s._dispatch([_ev(1, ball, ring, 200.0)])
    (trig,) = s.triggers
    assert trig.pan == 0.0
    m1 = NoteTrigger(step=trig.step, offset=trig.offset, voice=trig.voice, hz=trig.hz,
                     gain=trig.gain)  # fmt: skip
    assert mix([trig], length=48_000, config=CFG, seed=0).tobytes() == (
        mix([m1], length=48_000, config=CFG, seed=0).tobytes()
    )


def test_events_without_position_are_centred() -> None:
    s, _, _ = _scene()
    s.every(0.1, [A.play(S.note("A4"), pan=1.0), lambda ctx, ev: ctx.play(S.note("E5"), pan=1.0)])
    for _ in range(12):
        s.step_frame()
    assert len(s.triggers) >= 2
    assert all(t.pan == 0.0 for t in s.triggers)


def test_ctx_play_pan() -> None:
    s, ball, ring = _scene()
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: ctx.play(S.note("A4"), pan=1.0)])
    s._dispatch([_ev(1, ball, ring, 0.0)])
    assert s.triggers[0].pan == -1.0


def test_play_pan_field_and_default() -> None:
    assert A.play(S.note("A4")).pan == 0.0
    assert A.play(S.note("A4"), pan=0.4).pan == 0.4


@pytest.mark.parametrize("pan", [-0.1, 1.5, math.nan, math.inf, "0.5", True])
def test_bad_pan_raises(pan: object) -> None:
    with pytest.raises(ConfigError, match="pan"):
        A.play(S.note("A4"), pan=pan)  # type: ignore[arg-type]
    s, ball, ring = _scene()
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: ctx.play(S.note("A4"), pan=pan)])
    with pytest.raises(ConfigError, match="pan"):
        s._dispatch([_ev(1, ball, ring, 0.0)])


def test_pan_does_not_change_physics() -> None:
    def build(pan: float) -> Scene:
        s = Scene(width=400, height=400, fps=60, substeps=8, duration=3.0, seed=3)
        s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
        s.add_ball(pos=(150, 200), radius=10, velocity=(700, 300), tags={"ball"})
        s.on_collision("ball", "wall", [A.play(S.note("A4"), pan=pan)])
        for _ in range(90):
            s.step_frame()
        return s

    plain, panned = build(0.0), build(1.0)
    assert [(e.kind, e.step) for e in plain.events] == [(e.kind, e.step) for e in panned.events]
    assert plain.rng.getstate() == panned.rng.getstate()
    assert [t.hz for t in plain.triggers] == [t.hz for t in panned.triggers]
    assert any(t.pan != 0.0 for t in panned.triggers)
