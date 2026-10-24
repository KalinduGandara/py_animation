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


# --- M2 examples (FR-213, NFR-201, NFR-205) ---

M2 = {
    n: EXAMPLE.parent / f"{n}.py"
    for n in ("split_on_wall", "escape_rotating_gap", "destroy_on_contact")
}


def _run(scene: object) -> None:
    for _ in range(scene.total_frames):  # type: ignore[attr-defined]
        scene.step_frame()  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", list(M2))
def test_m2_example_loads_with_rules_and_sound(name: str) -> None:
    scene = load_scene(M2[name], seed=42)
    assert scene.has_sound
    assert len(scene._engine.rules) >= 1
    kinds = {r.kind for r in scene._engine.rules}
    expected = {
        "split_on_wall": {"collision"},
        "escape_rotating_gap": {"escape"},
        "destroy_on_contact": {"collision", "timer", "condition"},
    }[name]
    assert kinds == expected


@pytest.mark.parametrize("name", list(M2))
def test_m2_example_renders_h264_and_aac(name: str, tmp_path: Path) -> None:
    out = tmp_path / f"{name}.mp4"
    assert (
        main(["render", str(M2[name]), "--seed", "42", "--duration", "2", "--out", str(out)]) == 0
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    streams = {s["codec_name"]: s for s in json.loads(probe.stdout)["streams"]}
    assert set(streams) == {"h264", "aac"}
    assert int(streams["aac"]["sample_rate"]) == 48000 and streams["aac"]["channels"] == 2


def test_split_example_doubles_then_caps() -> None:
    scene = load_scene(M2["split_on_wall"], seed=42)
    counts: list[int] = []
    for _ in range(scene.total_frames):
        scene.step_frame()
        n = scene.count("ball")
        if not counts or n != counts[-1]:
            counts.append(n)
    assert counts[:2] == [1, 2]
    assert 4 in counts  # the second generation hits the wall and doubles again
    assert counts == sorted(counts)
    assert max(counts) <= 256
    assert max(counts) > 8


def test_escape_example_grows_by_one_per_escape_up_to_cap() -> None:
    scene = load_scene(M2["escape_rotating_gap"], seed=42)
    _run(scene)
    escapes = [e for e in scene.events if e.kind == "escape"]
    assert len(escapes) >= 1
    assert scene.count("ball") == min(1 + len(escapes), 40)


def test_destroy_example_destroys_and_ends_early() -> None:
    scene = load_scene(M2["destroy_on_contact"], seed=42)
    full = scene.total_frames
    _run(scene)
    assert any(e.kind == "destroy" for e in scene.events)
    assert scene.total_frames <= full


def test_destroy_example_exercises_wall_sound_and_spawn_cap() -> None:
    # Balls must reach the wall (pluck rule), several must be live at once, and the
    # every-spawn cap must be reached, not only the hazard path.
    scene = load_scene(M2["destroy_on_contact"], seed=42)
    most = 0
    for _ in range(scene.total_frames):
        scene.step_frame()
        most = max(most, scene.count("ball"))
        if scene.frame >= scene.total_frames:
            break
    walls = [
        e
        for e in scene.events
        if e.kind == "collision" and {t for o in e.objects for t in o.tags} == {"ball", "wall"}
    ]
    assert walls
    assert most == 6


def test_split_example_is_deterministic() -> None:
    def run(seed: int) -> tuple[bytes, list[tuple[int, str]]]:
        scene = load_scene(M2["split_on_wall"], seed=seed, duration=4)
        _run(scene)
        return scene.audio_buffer().tobytes(), [(e.step, e.kind) for e in scene.events]

    assert run(42) == run(42)
    assert run(42) != run(43)


def test_readme_covers_m2() -> None:
    text = (EXAMPLE.parent.parent / "README.md").read_text()
    for word in ("on_collision", "on_escape", "every", "when", "A.split", "A.spawn",
                 "A.destroy", "end_after", "ctx"):  # fmt: skip
        assert word in text


# --- T-306: MIDI melody example (FR-311, NFR-301, NFR-303, NFR-305) ---

MELODY_EXAMPLE = EXAMPLE.parent / "midi_melody.py"


def test_midi_melody_example_layout() -> None:
    from bouncekit import actions as A
    from bouncekit import colors as C
    from bouncekit import sound as S

    scene = load_scene(MELODY_EXAMPLE, seed=42)
    rings = [o for o in scene.objects if isinstance(o, CircleBoundary)]
    balls = [o for o in scene.objects if isinstance(o, Ball)]
    assert rings and all(r.glow > 0 for r in rings)
    assert balls
    for b in balls:
        assert b.trail and b.glow > 0 and isinstance(b.hue_mode, C.HueCycle)
    handlers = [h for r in scene._engine.rules for h in r.handlers]
    plays = [h for h in handlers if isinstance(h, A.Play) and isinstance(h.source, S.Melody)]
    assert plays and all(p.pan > 0 for p in plays)
    assert any(isinstance(h, A.Particles) for h in handlers)


def test_midi_melody_render_has_stereo_aac(tmp_path: Path) -> None:
    out = tmp_path / "melody.mp4"
    args = ["render", str(MELODY_EXAMPLE), "--seed", "42", "--duration", "3", "--out", str(out)]
    assert main(args) == 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    streams = {s["codec_name"]: s for s in json.loads(probe.stdout)["streams"]}
    assert set(streams) == {"h264", "aac"}
    assert int(streams["aac"]["sample_rate"]) == 48000 and streams["aac"]["channels"] == 2


def test_midi_melody_audio_is_stereo_and_triggers_follow_melody() -> None:
    import numpy as np

    from bouncekit import sound as S

    scene = load_scene(MELODY_EXAMPLE, seed=42)
    for _ in range(min(scene.total_frames, 480)):
        scene.step_frame()
    audio = scene.audio_buffer()
    assert audio.ndim == 2 and audio.shape[1] == 2
    assert not np.array_equal(audio[:, 0], audio[:, 1])
    melody = next(
        h.source
        for r in scene._engine.rules
        for h in r.handlers
        if hasattr(h, "source") and isinstance(h.source, S.Melody)
    )
    expected = [hz for chord in melody.chords for hz, _ in chord]
    got = [t.hz for t in scene.triggers]
    n = min(len(got), 8)
    assert n >= 3
    assert got[:n] == expected[:n]


def test_readme_covers_m3() -> None:
    text = (EXAMPLE.parent.parent / "README.md").read_text()
    for word in ("trail", "glow", "A.particles", "C.hue_cycle", "S.melody", "S.sample",
                 "pan", "EffectsConfig", "hot-reload"):  # fmt: skip
        assert word in text
