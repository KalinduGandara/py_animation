"""Voices, voice lookup, parameter validation and the render cache (FR-102, FR-105, NFR-101)."""

import numpy as np
import pytest
from numpy.typing import NDArray

from bouncekit import AudioConfig, ConfigError
from bouncekit import sound as S
from bouncekit.audio.mixer import SAMPLE_RATE, NoteTrigger, mix
from bouncekit.audio.voices import ADSR, VOICES, Marimba, Pluck, Sine, Triangle, resolve_voice

ALL_VOICES = [Sine(), Triangle(), Pluck(), Marimba()]
IDS = ["sine", "triangle", "pluck", "marimba"]


def _dominant_hz(y: NDArray[np.float64]) -> float:
    n = 1 << (len(y) * 4 - 1).bit_length()  # zero-pad for fine bins
    spectrum = np.abs(np.fft.rfft(y * np.hanning(len(y)), n))
    return float(np.argmax(spectrum)) * SAMPLE_RATE / n


def _fundamental_hz(y: NDArray[np.float64]) -> float:
    """Pitch from the autocorrelation's strongest peak after its first zero crossing.

    A plucked string's loudest partial can be a harmonic (random excitation), so
    the FFT peak is not its pitch; the period is.
    """
    n = len(y)
    r = np.fft.irfft(np.abs(np.fft.rfft(y, 2 * n)) ** 2)[:n]
    start = int(np.argmax(r < 0))
    lag = start + int(np.argmax(r[start : SAMPLE_RATE // 50]))
    a, b, c = r[lag - 1], r[lag], r[lag + 1]
    shift = 0.5 * (a - c) / (a - 2 * b + c)  # parabolic interpolation
    return SAMPLE_RATE / (lag + shift)


@pytest.mark.parametrize("voice", ALL_VOICES, ids=IDS)
def test_render_shape_start_peak_finite(voice: object) -> None:
    assert hasattr(voice, "render")
    y = voice.render(440.0, 3)  # type: ignore[attr-defined]
    assert y.dtype == np.float64
    assert y.ndim == 1
    assert len(y) == round(voice.duration * SAMPLE_RATE)  # type: ignore[attr-defined]
    assert y[0] == 0.0
    assert np.isfinite(y).all()
    assert float(np.abs(y).max()) <= 1.0
    assert float(np.abs(y).max()) > 0.1


@pytest.mark.parametrize("voice", ALL_VOICES, ids=IDS)
@pytest.mark.parametrize("hz", [220.0, 440.0, 880.0])
def test_dominant_frequency_within_two_percent(voice: object, hz: float) -> None:
    y = voice.render(hz, 11)  # type: ignore[attr-defined]
    assert _fundamental_hz(y) == pytest.approx(hz, rel=0.02)
    if not isinstance(voice, Pluck):
        assert _dominant_hz(y) == pytest.approx(hz, rel=0.02)


def test_triangle_is_a_triangle_wave() -> None:
    v = Triangle(envelope=ADSR(attack=0.0, decay=0.0, sustain=1.0, release=0.0))
    y = v.render(400.0, 0)  # 120 samples per period
    assert y[30] == pytest.approx(1.0, abs=1e-9)  # quarter period peak
    assert y[15] == pytest.approx(0.5, abs=1e-9)  # linear rise
    assert y[90] == pytest.approx(-1.0, abs=1e-9)


def test_pluck_same_seed_and_pitch_identical_different_seed_differs() -> None:
    a = Pluck().render(330.0, 5)
    assert np.array_equal(a, Pluck().render(330.0, 5))
    assert not np.array_equal(a, Pluck().render(330.0, 6))
    assert not np.array_equal(a, Pluck(damping=0.99).render(330.0, 5))
    # negative and huge seeds are accepted
    assert np.isfinite(Pluck().render(330.0, -1)).all()
    assert np.isfinite(Pluck().render(330.0, 2**70)).all()


def test_pluck_decays() -> None:
    y = Pluck().render(440.0, 0)
    head = float(np.abs(y[:4800]).max())
    tail = float(np.abs(y[-4800:]).max())
    assert tail < head * 0.5


def test_marimba_drops_partials_above_20khz() -> None:
    # at 4 kHz the 9.3x partial (37.2 kHz) would alias to 10.8 kHz; the 3.93x one (15.72 kHz) stays
    y = Marimba().render(4000.0, 0)
    n = len(y)
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)

    def band(f: float) -> float:
        return float(spec[(freqs > f - 100) & (freqs < f + 100)].max())

    floor = float(spec.max())
    assert band(15720.0) > floor * 0.05
    assert band(10800.0) < floor * 1e-3
    # at 1 kHz all three partials are present (9.3 kHz)
    y1 = Marimba().render(1000.0, 0)
    spec1 = np.abs(np.fft.rfft(y1))
    f1 = np.fft.rfftfreq(len(y1), 1 / SAMPLE_RATE)
    assert float(spec1[(f1 > 9200) & (f1 < 9400)].max()) > float(spec1.max()) * 0.01


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (lambda: Triangle(duration=0.0), "duration"),
        (lambda: Triangle(duration=-1.0), "duration"),
        (lambda: Triangle(envelope="adsr"), "envelope"),
        (lambda: Pluck(duration=0.0), "duration"),
        (lambda: Pluck(damping=0.0), "damping"),
        (lambda: Pluck(damping=1.0), "damping"),
        (lambda: Pluck(damping=1.5), "damping"),
        (lambda: Pluck(damping=float("nan")), "damping"),
        (lambda: Pluck(damping="x"), "damping"),
        (lambda: Marimba(duration=-0.5), "duration"),
        (lambda: Marimba(decay=0.0), "decay"),
        (lambda: Marimba(decay=float("inf")), "decay"),
        (lambda: Sine(envelope=ADSR(sustain=1.5)), "sustain"),
        (lambda: ADSR(release=-0.1), "release"),
    ],
)
def test_parameter_validation_names_field(factory: object, field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        factory()  # type: ignore[operator]


def test_voice_name_lookup() -> None:
    assert set(VOICES) == {"sine", "triangle", "pluck", "marimba"}
    assert resolve_voice("triangle") == Triangle()
    assert resolve_voice("pluck") == Pluck()
    assert resolve_voice("marimba") == Marimba()
    custom = Pluck(duration=0.5, damping=0.99)
    assert resolve_voice(custom) is custom
    assert S.note("C4", voice="pluck").voice == Pluck()
    assert S.note("C4", voice=Marimba(decay=0.2)).voice == Marimba(decay=0.2)
    with pytest.raises(ConfigError, match="marimba.*pluck.*sine.*triangle"):
        resolve_voice("kazoo")
    with pytest.raises(ConfigError, match="voice"):
        resolve_voice(ADSR())


def test_voices_are_hashable_and_reexported() -> None:
    assert len({Pluck(), Pluck(), Marimba(), Triangle(), Sine()}) == 4
    assert S.Triangle is Triangle and S.Pluck is Pluck and S.Marimba is Marimba


def test_render_cache_one_render_per_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[float, int]] = []
    original = Pluck.render

    def counting(self: Pluck, hz: float, seed: int) -> NDArray[np.float64]:
        calls.append((hz, seed))
        return original(self, hz, seed)

    monkeypatch.setattr(Pluck, "render", counting)
    v = Pluck(duration=0.1)

    def trig(offset: int, hz: float) -> NoteTrigger:
        return NoteTrigger(step=0, offset=offset, voice=v, hz=hz, gain=1.0)

    trigs = [trig(0, 440.0), trig(1000, 440.0), trig(2000, 330.0), trig(3000, 440.0)]
    mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=9)
    assert sorted(calls) == [(330.0, 9), (440.0, 9)]

    # a cache hit reuses samples equal to a fresh render: two overlapping hits mix exactly
    calls.clear()
    pair = mix([trig(0, 440.0), trig(100, 440.0)], length=SAMPLE_RATE, config=AudioConfig(), seed=9)
    assert len(calls) == 1  # the second trigger is a cache hit
    note = original(v, 440.0, 9)
    acc = np.zeros(SAMPLE_RATE)
    acc[: len(note)] += note * 0.5
    acc[100 : 100 + len(note)] += note * 0.5
    out = np.tanh(acc)
    out *= float(np.abs(pair[:, 0]).max()) / float(np.abs(out).max())
    assert np.allclose(pair[: SAMPLE_RATE - 240, 0], out[: SAMPLE_RATE - 240], atol=1e-6)


def test_mix_with_every_voice_is_deterministic() -> None:
    trigs = [
        NoteTrigger(step=0, offset=i * 4000, voice=VOICES[name], hz=262.0, gain=1.0)
        for i, name in enumerate(IDS)
    ]
    a = mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=1)
    b = mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=1)
    assert np.array_equal(a, b)
