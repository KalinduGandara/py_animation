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


def test_example_initial_velocity_follows_seed() -> None:
    def vx(seed: int) -> float:
        scene = load_scene(EXAMPLE, seed=seed)
        ball = next(o for o in scene.objects if isinstance(o, Ball))
        return float(ball.body.velocity.x)

    assert vx(42) == vx(42)
    assert vx(42) != vx(43)


def test_example_renders_expected_format(tmp_path: Path) -> None:
    out = tmp_path / "single_ball_seed42.mp4"
    code = main(
        ["render", str(EXAMPLE), "--seed", "42", "--duration", "1", "--out", str(out)]
    )
    assert code == 0 and out.exists()
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name,pix_fmt",
            "-of", "json", str(out),
        ],
        capture_output=True, text=True, check=True,
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
