"""Pitch parsing, note source and play action (FR-102, FR-104, FR-105 Sine)."""

import dataclasses
import math

import pytest

from bouncekit import ConfigError
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.voices import ADSR, Sine


@pytest.mark.parametrize(
    ("pitch", "hz"),
    [
        ("A4", 440.0),
        ("A5", 880.0),
        ("C4", 261.6255653005986),
        ("C5", 523.2511306011972),
        ("F#4", 369.9944227116344),
        ("Gb4", 369.9944227116344),
        ("Bb3", 233.08188075904496),
        ("B#3", 261.6255653005986),
        ("Cb4", 246.94165062806206),
        (69, 440.0),
        (60, 261.6255653005986),
        (127, 12543.853951415975),
        (440.0, 440.0),
        (1000.5, 1000.5),
    ],
)
def test_pitch_to_hz(pitch: str | int | float, hz: float) -> None:
    assert S.pitch_to_hz(pitch) == pytest.approx(hz, rel=1e-12)


def test_octave_range_bounds() -> None:
    assert S.pitch_to_hz("C9") == pytest.approx(8372.018089619156)
    assert S.pitch_to_hz("A0") == pytest.approx(27.5)


@pytest.mark.parametrize(
    "pitch",
    ["H4", "C", "C10", "c4", "C#b4", "C4x", "", "A-2", "A-1", -1, 128, 0, 15, 0.0, -440.0,
     math.inf, math.nan, 10.0, 25000.0, True, None, (440,)],
)  # fmt: skip
def test_bad_pitch_raises(pitch: object) -> None:
    with pytest.raises(ConfigError, match="pitch") as err:
        S.pitch_to_hz(pitch)  # type: ignore[arg-type]
    assert repr(pitch) in str(err.value)


def test_note_source() -> None:
    n = S.note("A4")
    assert n.hz == pytest.approx(440.0)
    assert n.voice == Sine()
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.hz = 1.0  # type: ignore[misc]
    custom = Sine(duration=0.3, envelope=ADSR(attack=0.01))
    assert S.note(60, voice=custom).voice is custom
    assert S.note(440.0, voice="sine").voice == Sine()


def test_note_rejects_bad_voice() -> None:
    with pytest.raises(ConfigError, match="voice.*sine"):
        S.note("C4", voice="kazoo")
    with pytest.raises(ConfigError, match="voice"):
        S.note("C4", voice=3)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="pitch"):
        S.note("Q4")


def test_play_action() -> None:
    n = S.note("C4")
    p = A.play(n)
    assert p.source is n and p.gain == 1.0
    assert A.play(n, gain=0.0).gain == 0.0
    assert A.play(n) != A.play(n)  # identity semantics (eq=False)
    for bad in (-0.1, math.nan, math.inf, "1"):
        with pytest.raises(ConfigError, match="gain"):
            A.play(n, gain=bad)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="source"):
        A.play("C4")  # type: ignore[arg-type]


def test_sine_voice_render() -> None:
    v = Sine()
    y = v.render(440.0, 0)
    assert y.dtype.name == "float64"
    assert len(y) == round(v.duration * 48000)
    assert y[0] == 0.0
    assert y[1] != 0.0
    assert float(abs(y).max()) <= 1.0
    # roughly 440 Hz: count rising zero crossings over the first 0.5 s
    seg = y[:24000]
    crossings = int(((seg[:-1] < 0) & (seg[1:] >= 0)).sum())
    assert abs(crossings - 220) <= 2
    assert abs(y[-50:]).max() < 0.01  # released to ~0 at the end


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"duration": 0.0}, "duration"),
        ({"duration": -1.0}, "duration"),
        ({"envelope": ADSR(sustain=1.0)}, None),
    ],
)
def test_sine_validation(kwargs: dict[str, object], field: str | None) -> None:
    if field is None:
        Sine(**kwargs)  # type: ignore[arg-type]
        return
    with pytest.raises(ConfigError, match=field):
        Sine(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"attack": -0.1}, "attack"),
        ({"decay": -0.1}, "decay"),
        ({"release": -0.1}, "release"),
        ({"sustain": 1.5}, "sustain"),
        ({"sustain": -0.5}, "sustain"),
    ],
)
def test_adsr_validation(kwargs: dict[str, float], field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        ADSR(**kwargs)
