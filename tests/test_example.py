"""End-to-end checks for examples/single_ball.py (FR-011, NFR-002)."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from bouncekit import Ball, CircleBoundary
from bouncekit.cli import load_scene, main

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "single_ball.py"


def test_example_layout() -> None:
    scene = load_scene(EXAMPLE, seed=42)
    rings = [o for o in scene.objects if isinstance(o, CircleBoundary)]
    balls = [o for o in scene.objects if isinstance(o, Ball)]
    assert len(rings) == 1 and len(balls) == 1
    assert (scene.config.width, scene.config.height) == (1080, 1920)
    assert tuple(balls[0].body.position) != (0, 0)
    assert rings[0].center == (540, 960) and rings[0].radius == 450
    assert scene.config.gravity[1] > 0


def test_example_initial_velocity_follows_seed() -> None:
    def vx(seed: int) -> float:
        scene = load_scene(EXAMPLE, seed=seed)
        ball = next(o for o in scene.objects if isinstance(o, Ball))
        return float(ball.body.velocity.x)

    assert vx(42) == vx(42)
    assert vx(42) != vx(43)


def test_example_renders_expected_format(tmp_path: Path) -> None:
    out = tmp_path / "single_ball_seed42.mp4"
    code = main(["render", str(EXAMPLE), "--seed", "42", "--duration", "1", "--out", str(out)])
    assert code == 0 and out.exists()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,codec_name,pix_fmt",
            "-of",
            "json",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["width"] == 1080 and stream["height"] == 1920
    assert stream["r_frame_rate"] == "60/1"
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"


def test_readme_has_quickstart_and_api() -> None:
    text = (EXAMPLE.parent.parent / "README.md").read_text()
    assert "bouncekit render" in text
    assert "add_circle" in text and "add_ball" in text


def test_default_output_path_name() -> None:
    scene = load_scene(EXAMPLE, seed=42)
    assert f"{EXAMPLE.stem}_seed{scene.config.seed}.mp4" == "single_ball_seed42.mp4"


@pytest.mark.parametrize("seed", [1, 2])
def test_ball_stays_inside_ring(seed: int) -> None:
    scene = load_scene(EXAMPLE, seed=seed, duration=3)
    ball = next(o for o in scene.objects if isinstance(o, Ball))
    for _ in range(scene.total_frames):
        scene.step_frame()
        x, y = ball.body.position
        assert (x - 540) ** 2 + (y - 960) ** 2 < 450**2


# --- examples/bounce_notes.py (FR-110, NFR-102, NFR-104, NFR-105) ---

NOTES = EXAMPLE.parent / "bounce_notes.py"


def test_bounce_notes_layout() -> None:
    from bouncekit.actions import Play
    from bouncekit.sound import Scale

    scene = load_scene(NOTES, seed=42)
    rings = [o for o in scene.objects if isinstance(o, CircleBoundary)]
    balls = [o for o in scene.objects if isinstance(o, Ball)]
    assert len(rings) == 1 and len(balls) == 1
    assert "wall" in rings[0].tags and "ball" in balls[0].tags
    assert scene.has_sound
    rules = scene._rules
    assert len(rules) == 1 and {rules[0][0], rules[0][1]} == {"ball", "wall"}
    act = rules[0][2][0]
    assert isinstance(act, Play) and isinstance(act.source, Scale)


def test_bounce_notes_render_has_aac_and_aligned_onset(tmp_path: Path) -> None:
    import numpy as np
    import soundfile

    out = tmp_path / "bn.mp4"
    assert main(["render", str(NOTES), "--seed", "42", "--duration", "3", "--out", str(out)]) == 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name,sample_rate,channels", "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    st = json.loads(probe.stdout)["streams"][0]
    assert st["codec_name"] == "aac" and int(st["sample_rate"]) == 48000 and st["channels"] == 2

    scene = load_scene(NOTES, seed=42, duration=3)
    for _ in range(scene.total_frames):
        scene.step_frame()
    assert len(scene.triggers) >= 1
    first = scene.triggers[0]
    wav = tmp_path / "a.wav"
    from bouncekit.export.audio import write_wav

    write_wav(wav, scene.audio_buffer())
    data, _ = soundfile.read(str(wav), dtype="float32")
    nz = np.flatnonzero(np.abs(data).max(axis=1) > 0)
    # voice sample 0 can be exactly zero, so the first audible sample is within 2 of the offset
    assert first.offset <= nz[0] <= first.offset + 2


def test_readme_documents_audio() -> None:
    text = (EXAMPLE.parent.parent / "README.md").read_text()
    for word in ("on_collision", "S.scale", "A.play", "AudioConfig"):
        assert word in text


def test_bounce_notes_aac_does_not_clip(tmp_path: Path) -> None:
    # review finding: seed 42, 8 s decoded to a peak of 1.0288 (+0.25 dBFS)
    import numpy as np

    out = tmp_path / "bn.mp4"
    assert main(["render", str(NOTES), "--seed", "42", "--duration", "8", "--out", str(out)]) == 0
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-map", "0:a:0", "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    pcm = np.frombuffer(raw, dtype=np.float32)
    assert len(pcm) > 0
    assert float(np.abs(pcm).max()) < 1.0
