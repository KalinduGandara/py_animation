"""WAV writing and AAC muxing (FR-109, NFR-102)."""

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.errors import FfmpegError  # noqa: E402
from bouncekit.export import ffmpeg as ff  # noqa: E402
from bouncekit.export.audio import write_wav  # noqa: E402
from bouncekit.export.ffmpeg import mux  # noqa: E402


def _streams(path: Path) -> list[dict[str, object]]:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,sample_rate,channels,duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    streams: list[dict[str, object]] = json.loads(out)["streams"]
    return streams


def _tiny_scene(sound: bool) -> Scene:
    s = Scene(width=160, height=160, fps=30, duration=1.0, max_speed=1000)
    s.add_circle(center=(80, 80), radius=60, thickness=6, tags={"wall"})
    s.add_ball(pos=(80, 80), radius=6, tags={"ball"})
    if sound:
        s.on_collision("ball", "wall", [A.play(S.note("C5"))])
    return s


def test_write_wav_float32_roundtrip(tmp_path: Path) -> None:
    buf = (np.linspace(-0.9, 0.9, 960, dtype=np.float32)[:, None] * [1, -1]).astype(np.float32)
    path = tmp_path / "a.wav"
    write_wav(path, buf)
    info = soundfile.info(str(path))
    assert (info.samplerate, info.channels, info.subtype) == (48000, 2, "FLOAT")
    data, _ = soundfile.read(str(path), dtype="float32")
    assert np.array_equal(data, buf)


def test_render_with_sound_muxes_aac(tmp_path: Path) -> None:
    s = _tiny_scene(sound=True)
    out = tmp_path / "sub" / "out.mp4"
    assert s.render(out) == out
    assert len(s.triggers) >= 1
    streams = _streams(out)
    video = [x for x in streams if x["codec_type"] == "video"]
    audio = [x for x in streams if x["codec_type"] == "audio"]
    assert len(video) == 1 and len(audio) == 1
    assert audio[0]["codec_name"] == "aac"
    assert audio[0]["sample_rate"] == "48000"
    assert audio[0]["channels"] == 2
    assert abs(float(str(audio[0]["duration"])) - float(str(video[0]["duration"]))) < 0.05
    assert abs(float(str(video[0]["duration"])) - 1.0) < 0.05
    assert sorted(p.name for p in out.parent.iterdir()) == ["out.mp4"]  # temp files gone


def test_render_without_sound_rules_has_no_audio_stream(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    _tiny_scene(sound=False).render(out)
    assert [x["codec_type"] for x in _streams(out)] == ["video"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.mp4"]


def test_temp_files_removed_when_mux_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import bouncekit.scene as scene_mod

    def boom(*_a: object) -> None:
        raise FfmpegError("mux failed")

    monkeypatch.setattr(scene_mod, "mux", boom)
    with pytest.raises(FfmpegError, match="mux failed"):
        _tiny_scene(sound=True).render(tmp_path / "out.mp4")
    assert list(tmp_path.iterdir()) == []


def test_mux_failure_raises_with_stderr(tmp_path: Path) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"not a video")
    wav = tmp_path / "a.wav"
    write_wav(wav, np.zeros((480, 2), dtype=np.float32))
    with pytest.raises(FfmpegError, match="v.mp4") as err:
        mux(video, wav, tmp_path / "out.mp4")
    assert "ffmpeg" in str(err.value)


def test_mux_command_flags() -> None:
    cmd = ff._mux_command("ffmpeg", Path("v.mp4"), Path("a.wav"), Path("o.mp4"))
    joined = " ".join(cmd)
    for part in ("-c:v copy", "-c:a aac", "-b:a 192k", "-ar 48000", "-ac 2",
                 "-movflags +faststart", "-map 0:v:0", "-map 1:a:0"):  # fmt: skip
        assert part in joined
