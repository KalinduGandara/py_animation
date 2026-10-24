"""T-304: sample voice (FR-308) and the generated kalimba asset (FR-311)."""

import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from numpy.typing import NDArray

from bouncekit import ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.mixer import mix
from bouncekit.audio.voices import Sample, resolve_voice
from bouncekit.config import AudioConfig
from bouncekit.events import CollisionEvent

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "samples" / "kalimba.wav"


def _sine(hz: float, rate: int, seconds: float = 0.5) -> NDArray[np.float64]:
    t = np.arange(round(seconds * rate)) / rate
    return 0.8 * np.sin(2 * math.pi * hz * t)


def _write(path: Path, data: NDArray[np.float64], rate: int) -> Path:
    sf.write(path, data, rate, subtype="FLOAT")
    return path


def _dominant(y: NDArray[np.float64]) -> float:
    pad = 1 << 20
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), pad))
    return float(np.argmax(spec)) * 48_000 / pad


@pytest.fixture
def a440(tmp_path: Path) -> Path:
    return _write(tmp_path / "a440.wav", _sine(440.0, 48_000), 48_000)


@pytest.mark.parametrize("hz", [880.0, 659.26])
def test_pitch_shift_frequency_and_length(a440: Path, hz: float) -> None:
    smp = S.sample(a440, root="A4")
    y = smp.render(hz, 0)
    ratio = (hz / S.pitch_to_hz("A4")) * (48_000 / 48_000)
    assert len(y) == math.floor((len(smp.data) - 1) / ratio) + 1
    assert _dominant(y) == pytest.approx(hz, rel=0.01)


def test_other_file_rate_keeps_pitch_at_root(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.wav", _sine(440.0, 44_100), 44_100)
    smp = S.sample(path, root="A4")
    assert smp.rate == 44_100
    y = smp.render(440.0, 0)
    assert len(y) == math.floor((len(smp.data) - 1) / (44_100 / 48_000)) + 1
    assert _dominant(y) == pytest.approx(440.0, rel=0.01)


def test_render_is_linear_interpolation(a440: Path) -> None:
    smp = S.sample(a440, root="A4")
    y = smp.render(660.0, 0)
    ratio = 660.0 / 440.0
    ref = np.interp(np.arange(len(y)) * ratio, np.arange(len(smp.data)), smp.data)
    mid = slice(100, len(y) - 300)  # away from the attack and release ramps
    scale = y[mid][np.argmax(np.abs(ref[mid]))] / ref[mid][np.argmax(np.abs(ref[mid]))]
    np.testing.assert_allclose(y[mid], ref[mid] * scale, atol=1e-12)


def test_stereo_file_is_averaged(tmp_path: Path) -> None:
    left = _sine(440.0, 48_000)
    right = 0.5 * _sine(660.0, 48_000)
    path = tmp_path / "st.wav"
    sf.write(path, np.stack([left, right], axis=1), 48_000, subtype="FLOAT")
    smp = S.sample(path)
    assert smp.data.ndim == 1
    np.testing.assert_allclose(smp.data, (left + right) / 2, atol=1e-6)


def test_envelope_and_normalisation(a440: Path) -> None:
    y = S.sample(a440, root="A4").render(523.25, 0)
    assert y[0] == 0.0
    assert y[-1] == 0.0
    assert float(np.abs(y).max()) == 1.0
    assert y.dtype == np.float64


def test_duration_truncates(a440: Path) -> None:
    y = S.sample(a440, root="A4", duration=0.1).render(440.0, 0)
    assert len(y) == 4800
    assert y[-1] == 0.0


def test_seed_is_ignored_and_data_read_only(a440: Path) -> None:
    smp = S.sample(a440)
    np.testing.assert_array_equal(smp.render(300.0, 1), smp.render(300.0, 2))
    with pytest.raises(ValueError):
        smp.data[0] = 1.0


def test_sample_is_identity_hashed_voice(a440: Path) -> None:
    a, b = S.sample(a440), S.sample(a440)
    assert isinstance(a, Sample)
    assert a != b
    assert len({a, b}) == 2
    assert resolve_voice(a) is a


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nope.wav"):
        S.sample(tmp_path / "nope.wav")


def test_garbage_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "junk.wav"
    path.write_bytes(b"not audio at all")
    with pytest.raises(ConfigError, match="junk.wav"):
        S.sample(path)


def test_silent_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "quiet.wav", np.zeros(1000), 48_000)
    with pytest.raises(ConfigError, match="quiet.wav"):
        S.sample(path)


def test_one_frame_file_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "one.wav", np.array([0.5]), 48_000)
    with pytest.raises(ConfigError, match="one.wav"):
        S.sample(path)


@pytest.mark.parametrize("root", ["H4", 5.0, 200, None])
def test_bad_root_raises(a440: Path, root: object) -> None:
    with pytest.raises(ConfigError, match="root"):
        S.sample(a440, root=root)  # type: ignore[arg-type]


@pytest.mark.parametrize("duration", [0, -1.0, math.nan, math.inf, "1", True])
def test_bad_duration_raises(a440: Path, duration: object) -> None:
    with pytest.raises(ConfigError, match="duration"):
        S.sample(a440, duration=duration)  # type: ignore[arg-type]


def test_note_with_sample_voice_plays_through_mixer(a440: Path) -> None:
    smp = S.sample(a440, root="A4")
    s = Scene(width=400, height=400, fps=60, substeps=8, duration=2.0)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    ball = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    s.on_collision("ball", "wall", [A.play(S.note("C5", voice=smp))])
    ev = CollisionEvent(
        kind="collision", step=1, frame=0, time=1 / 480,
        objects=(ball, ring), speed=1500.0, position=(200.0, 50.0),
    )  # fmt: skip
    s._dispatch([ev])
    (trig,) = s.triggers
    assert trig.voice is smp
    buf = mix(s.triggers, length=48_000, config=AudioConfig(), seed=0)
    assert float(np.abs(buf).max()) > 0.5
    assert S.scale("C4", voice=smp).voice is smp


# --- Asset --------------------------------------------------------------------


def test_make_assets_reproduces_kalimba(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_assets.py"), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    assert (tmp_path / "samples" / "kalimba.wav").read_bytes() == ASSET.read_bytes()


def test_kalimba_asset() -> None:
    info = sf.info(str(ASSET))
    assert info.samplerate == 48_000
    assert info.channels == 1
    assert info.subtype == "PCM_16"
    assert info.frames <= 48_000
    smp = S.sample(ASSET, root="A4")
    assert _dominant(smp.render(440.0, 0)) == pytest.approx(440.0, rel=0.01)
