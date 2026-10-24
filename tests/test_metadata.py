"""Render metadata JSON and run_job (FR-405, FR-402 naming, FR-404 cleanup)."""

import importlib.metadata
import json
import os
from collections import Counter
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import bouncekit  # noqa: E402
from bouncekit import cli  # noqa: E402
from bouncekit import scene as scene_module  # noqa: E402
from bouncekit.batch import Job, JobResult, run_job  # noqa: E402
from bouncekit.errors import FfmpegError  # noqa: E402
from bouncekit.export.metadata import EVENT_KINDS, build_metadata, write_metadata  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PARAM = FIXTURES / "param_scene.py"

KEYS = [
    "scene", "video", "seed", "params", "duration", "frames", "fps", "size", "events",
    "sound_triggers", "versions", "render_seconds",
]  # fmt: skip


def _render(out: Path, *extra: str) -> dict[str, object]:
    argv = ["render", str(PARAM), "--set", "vx=250", "--seed", "4", "--duration", "0.6"]
    assert cli.main([*argv, "--out", str(out), *extra]) == 0
    json_path = out.with_suffix(".json")
    text = json_path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    data = json.loads(text)
    assert text == json.dumps(data, indent=2) + "\n"
    return data  # type: ignore[no-any-return]


def test_metadata_fields(tmp_path: Path) -> None:
    out = tmp_path / "v.mp4"
    data = _render(out)
    assert list(data) == KEYS
    ref = cli.load_scene(PARAM, seed=4, duration=0.6, params={"vx": "250"})
    for _ in ref.frames():
        pass
    counts = Counter(e.kind for e in ref.events)
    assert data["scene"] == str(PARAM)
    assert data["video"] == "v.mp4"
    assert data["seed"] == 4
    assert data["params"] == {"vx": 250.0}
    assert data["duration"] == 0.6
    assert data["frames"] == 18 == ref.frame
    assert data["fps"] == 30
    assert data["size"] == [96, 96]
    assert list(data["events"]) == list(EVENT_KINDS)  # type: ignore[arg-type]
    assert data["events"] == {k: counts.get(k, 0) for k in EVENT_KINDS}
    assert data["events"]["collision"] > 0  # type: ignore[index]
    assert data["sound_triggers"] == len(ref.triggers) > 0
    assert data["versions"] == {
        "bouncekit": bouncekit.__version__,
        "pymunk": importlib.metadata.version("pymunk"),
        "pygame": importlib.metadata.version("pygame-ce"),
    }
    seconds = data["render_seconds"]
    assert isinstance(seconds, float) and seconds >= 0
    assert round(seconds, 3) == seconds


def test_two_renders_equal_except_render_seconds(tmp_path: Path) -> None:
    a = _render(tmp_path / "a" / "v.mp4")
    b = _render(tmp_path / "b" / "v.mp4")
    a.pop("render_seconds")
    b.pop("render_seconds")
    assert a == b


def test_build_and_write_metadata(tmp_path: Path) -> None:
    scene = cli.load_scene(PARAM, duration=0.2)
    for _ in scene.frames():
        pass
    video = tmp_path / "x.mp4"
    data = build_metadata(scene, script="s.py", video=video, render_seconds=1.23456)
    assert list(data) == KEYS
    assert data["render_seconds"] == 1.235
    assert data["seed"] == 5 and data["frames"] == 6 and data["params"] == {"vx": 100.0}
    path = write_metadata(video, data)
    assert path == tmp_path / "x.json"
    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.json"]  # no temp files left


def test_scene_render_writes_no_metadata(tmp_path: Path) -> None:
    scene = cli.load_scene(PARAM, duration=0.1)
    scene.render(tmp_path / "v.mp4")
    assert [p.name for p in tmp_path.iterdir()] == ["v.mp4"]


def test_failing_render_leaves_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken_mux(video: Path, wav: Path, out: Path) -> None:
        Path(out).write_bytes(b"partial")
        raise FfmpegError("mux exploded")

    monkeypatch.setattr(scene_module, "mux", broken_mux)
    out = tmp_path / "v.mp4"
    argv = ["render", str(PARAM), "--duration", "0.2", "--out", str(out)]
    assert cli.main(argv) == 2
    assert "mux exploded" in capsys.readouterr().err
    assert not out.exists()
    assert not out.with_suffix(".json").exists()


def test_run_job_success_and_default_name(tmp_path: Path) -> None:
    good = Job(
        index=2, script=PARAM, seed=8, duration=0.2, overrides=(("vx", "60"),),
        out_dir=tmp_path / "o", out=None,
    )  # fmt: skip
    ok = run_job(good)
    assert ok.ok and ok.error is None and ok.index == 2
    assert ok.out == tmp_path / "o" / "param_scene_seed8_vx-60.mp4"
    assert ok.frames == 6 and ok.seconds >= 0
    assert ok.out.is_file() and ok.out.with_suffix(".json").is_file()

    script_seed = Job(
        index=1, script=PARAM, seed=None, duration=0.1, overrides=(("vx", "7 5"),),
        out_dir=tmp_path / "o", out=None,
    )  # fmt: skip
    bad = run_job(script_seed)  # "7 5" is not a float: fails while loading
    assert not bad.ok and bad.error is not None and bad.out is None
    assert bad.error.startswith("ConfigError:") and "vx" in bad.error
    assert bad == JobResult(index=1, out=None, ok=False, frames=0, seconds=bad.seconds,
                            error=bad.error)  # fmt: skip


def test_run_job_uses_script_seed_in_name(tmp_path: Path) -> None:
    job = Job(
        index=1, script=PARAM, seed=None, duration=0.1, overrides=(),
        out_dir=tmp_path, out=None,
    )  # fmt: skip
    result = run_job(job)
    assert result.ok
    assert result.out == tmp_path / "param_scene_seed5.mp4"
    assert result.out.is_file()


def test_run_job_failure_removes_existing_outputs(tmp_path: Path) -> None:
    out = tmp_path / "v.mp4"
    out.write_bytes(b"old")
    out.with_suffix(".json").write_text("{}")
    job = Job(
        index=1, script=PARAM, seed=None, duration=0.1, overrides=(("nope", "1"),),
        out_dir=tmp_path, out=out,
    )  # fmt: skip
    result = run_job(job)
    assert not result.ok
    assert result.error is not None and result.error.startswith("ConfigError:")
    assert result.out == out
    assert not out.exists() and not out.with_suffix(".json").exists()
