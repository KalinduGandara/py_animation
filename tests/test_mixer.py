"""Mixer, sample offsets and master bus (FR-107, NFR-102, NFR-103)."""

import numpy as np
import pytest

from bouncekit import AudioConfig, ConfigError, Scene
from bouncekit.audio.mixer import SAMPLE_RATE, NoteTrigger, mix, num_samples, sample_offset
from bouncekit.audio.voices import Sine

PEAK = 10 ** (-1 / 20)


@pytest.mark.parametrize(
    ("step", "fps", "substeps", "expected"),
    [
        (0, 60, 8, 0),
        (1, 60, 8, 100),
        (7, 60, 8, 700),
        (1, 60, 7, 114),  # 114.2857
        (3, 60, 7, 343),  # 342.857
        (1, 60, 320, 3),  # 2.5 -> half up (Python round() would give 2)
        (3, 60, 320, 8),  # 7.5 -> 8
        (5, 60, 320, 13),  # 12.5 -> 13
        (10**9, 60, 8, 10**11),  # exact for huge steps
        (1, 24, 5, 400),
        (1, 1, 96000, 1),  # 0.5 -> 1
    ],
)
def test_sample_offset(step: int, fps: int, substeps: int, expected: int) -> None:
    assert sample_offset(step, fps, substeps) == expected


@pytest.mark.parametrize(
    ("frames", "fps", "expected"),
    [(0, 60, 0), (1, 60, 800), (600, 60, 480000), (1, 7, 6857), (1, 768, 63), (3, 768, 188)],
)
def test_num_samples(frames: int, fps: int, expected: int) -> None:
    assert num_samples(frames, fps) == expected


def _trig(offset: int, gain: float = 1.0, hz: float = 440.0) -> NoteTrigger:
    return NoteTrigger(step=0, offset=offset, voice=Sine(), hz=hz, gain=gain)


def test_isolated_note_starts_exactly_at_offset() -> None:
    buf = mix([_trig(1000)], length=SAMPLE_RATE, config=AudioConfig(), seed=0)
    assert buf.dtype == np.float32
    assert buf.shape == (SAMPLE_RATE, 2)
    assert np.array_equal(buf[:, 0], buf[:, 1])
    assert not buf[:1000].any()
    nz = int(np.flatnonzero(buf[:, 0])[0])
    assert nz in (1000, 1001)


def test_two_hundred_full_gain_triggers_respect_headroom() -> None:
    trigs = [_trig(100 + i, hz=200.0 + 7 * i) for i in range(200)]
    buf = mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=0)
    peak = float(np.abs(buf).max())
    assert peak <= 1.0
    assert peak == pytest.approx(PEAK, abs=1e-6)


def test_quiet_mix_is_normalised_to_peak_dbfs() -> None:
    buf = mix([_trig(0, gain=0.01)], length=SAMPLE_RATE, config=AudioConfig(), seed=0)
    assert float(np.abs(buf).max()) == pytest.approx(PEAK, abs=1e-6)
    buf6 = mix(
        [_trig(0, gain=0.01)], length=SAMPLE_RATE, config=AudioConfig(peak_dbfs=-6.0), seed=0
    )
    assert float(np.abs(buf6).max()) == pytest.approx(10 ** (-6 / 20), abs=1e-6)


def test_silence_stays_zero_and_end_is_faded() -> None:
    assert not mix([], length=4800, config=AudioConfig(), seed=0).any()
    assert mix([], length=0, config=AudioConfig(), seed=0).shape == (0, 2)
    # a note still sounding at the end is faded to 0 over the last 5 ms (240 samples)
    buf = mix([_trig(0)], length=12000, config=AudioConfig(), seed=0)
    assert buf[-1, 0] == 0.0
    tail = np.abs(buf[-240:, 0])
    assert tail.max() < np.abs(buf[-1000:-240, 0]).max()


def test_samples_past_the_end_are_dropped() -> None:
    buf = mix([_trig(4790), _trig(10_000)], length=4800, config=AudioConfig(), seed=0)
    assert buf.shape == (4800, 2)
    assert buf[4795:].any() or buf[4791:4795].any()


def test_mix_is_deterministic() -> None:
    trigs = [_trig(i * 333, gain=0.3 + 0.01 * i, hz=300 + i) for i in range(20)]
    a = mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=1)
    b = mix(trigs, length=SAMPLE_RATE, config=AudioConfig(), seed=1)
    assert a.tobytes() == b.tobytes()


def test_audio_config_defaults_and_scene() -> None:
    c = AudioConfig()
    assert (
        c.min_impact_speed, c.reference_speed, c.min_retrigger_interval,
        c.max_triggers_per_frame, c.max_polyphony, c.peak_dbfs,
    ) == (40.0, 1500.0, 0.05, 6, 24, -1.0)  # fmt: skip
    s = Scene(width=100, height=100, duration=0.5)
    assert s.config.audio == AudioConfig()
    custom = AudioConfig(peak_dbfs=-3.0)
    assert Scene(width=100, height=100, duration=0.5, audio=custom).config.audio is custom
    with pytest.raises(ConfigError, match="peak_dbfs"):
        AudioConfig(peak_dbfs=0.5)
    with pytest.raises(ConfigError, match="audio"):
        Scene(width=100, height=100, duration=0.5, audio="loud")  # type: ignore[arg-type]


def test_scene_audio_buffer_length_follows_simulated_frames() -> None:
    s = Scene(width=100, height=100, fps=7, duration=1.0)
    assert s.audio_buffer().shape == (0, 2)
    for _ in range(3):
        s.step_frame()
    buf = s.audio_buffer()
    assert buf.shape == (num_samples(3, 7), 2)
    assert buf.dtype == np.float32
    assert not buf.any()
