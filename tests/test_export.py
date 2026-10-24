"""ffmpeg export tests (FR-007, NFR-002)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402
from bouncekit.errors import FfmpegError  # noqa: E402
from bouncekit.export import ffmpeg as ff  # noqa: E402
from bouncekit.export.ffmpeg import FfmpegWriter, require_ffmpeg  # noqa: E402


def _probe(path: Path) -> dict[str, str]:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_frames",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    streams: list[dict[str, str]] = json.loads(out)["streams"]
    return streams[0]


def test_require_ffmpeg_returns_path() -> None:
    assert Path(require_ffmpeg()).name.startswith("ffmpeg")


def test_require_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda _name: None)
    with pytest.raises(FfmpegError, match="install"):
        require_ffmpeg()


def test_writer_real_encode(tmp_path: Path) -> None:
    out = tmp_path / "t.mp4"
    frame = bytes([200, 50, 50]) * (64 * 48)
    with FfmpegWriter(out, 64, 48, 30) as w:
        for _ in range(10):
            w.write(frame)
    info = _probe(out)
    assert info["codec_name"] == "h264"
    assert info["pix_fmt"] == "yuv420p"
    assert (info["width"], info["height"]) == (64, 48)  # type: ignore[comparison-overlap]
    assert info["r_frame_rate"] == "30/1"
    assert info["nb_frames"] == "10"


def test_writer_bad_frame_length(tmp_path: Path) -> None:
    with (
        pytest.raises(FfmpegError, match="frame"),
        FfmpegWriter(tmp_path / "x.mp4", 64, 48, 30) as w,
    ):
        w.write(b"\x00" * 10)


def test_writer_missing_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda _name: None)
    with pytest.raises(FfmpegError, match="install"):
        FfmpegWriter(tmp_path / "x.mp4", 64, 48, 30).__enter__()


def test_writer_ffmpeg_failure_includes_stderr(tmp_path: Path) -> None:
    bad = tmp_path / "no_such_dir" / "x.mp4"
    with pytest.raises(FfmpegError) as exc, FfmpegWriter(bad, 64, 48, 30) as w:
        frame = bytes(64 * 48 * 3)
        for _ in range(50):
            w.write(frame)
    assert "no_such_dir" in str(exc.value)


def test_scene_render(tmp_path: Path) -> None:
    scene = Scene(width=64, height=48, fps=30, duration=0.5, gravity=(0.0, 0.0), max_speed=1500)
    scene.add_circle(center=(32, 24), radius=20, segments=32)
    scene.add_ball(pos=(32, 24), radius=4, velocity=(30, 20), color="#ff0000")
    out = scene.render(tmp_path / "sub" / "o.mp4")
    assert out == tmp_path / "sub" / "o.mp4"
    info = _probe(out)
    assert info["nb_frames"] == "15"
    assert scene.frame == 15


def test_scene_render_fails_before_simulating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda _name: None)
    scene = Scene(width=64, height=48, fps=30, duration=0.5)
    with pytest.raises(FfmpegError, match="install"):
        scene.render(tmp_path / "o.mp4")
    assert scene.frame == 0
    assert not (tmp_path / "o.mp4").exists()


def test_command_uses_crf18_faststart_h264() -> None:
    cmd = FfmpegWriter(Path("x.mp4"), 64, 48, 30)._command("ffmpeg")
    joined = " ".join(cmd)
    for part in (
        "-c:v libx264",
        "-crf 18",
        "-pix_fmt yuv420p",
        "-movflags +faststart",
        "-f rawvideo",
        "-pix_fmt rgb24",
        "-s 64x48",
        "-r 30",
        "-i -",
    ):
        assert part in joined, part


def _top_level_boxes(path: Path) -> list[str]:
    data = path.read_bytes()
    boxes, i = [], 0
    while i + 8 <= len(data):
        size = int.from_bytes(data[i : i + 4], "big")
        boxes.append(data[i + 4 : i + 8].decode("latin-1"))
        if size == 1:
            size = int.from_bytes(data[i + 8 : i + 16], "big")
        if size < 8:
            break
        i += size
    return boxes


def test_real_encode_is_faststart(tmp_path: Path) -> None:
    out = tmp_path / "fs.mp4"
    with FfmpegWriter(out, 64, 48, 30) as w:
        for _ in range(5):
            w.write(bytes(64 * 48 * 3))
    boxes = _top_level_boxes(out)
    assert boxes.index("moov") < boxes.index("mdat")
