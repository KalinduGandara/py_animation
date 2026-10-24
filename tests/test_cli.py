"""CLI tests: scene loading, overrides, subcommands, error exits (FR-010, FR-006)."""

import os
import random
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene, cli  # noqa: E402
from bouncekit import scene as scene_module  # noqa: E402
from bouncekit.errors import SceneLoadError  # noqa: E402
from bouncekit.export import ffmpeg as ff  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
TINY = FIXTURES / "tiny_scene.py"


def _expected_vx(seed: int) -> float:
    return random.Random(seed).uniform(-50.0, 50.0)


# --- load_scene ---------------------------------------------------------------


def test_load_single_scene() -> None:
    scene = cli.load_scene(TINY)
    assert isinstance(scene, Scene)
    assert scene.config.seed == 7
    assert scene.config.duration == 0.5
    assert scene.frame == 0
    assert len(scene.objects) == 2


def test_load_accepts_str_path() -> None:
    assert isinstance(cli.load_scene(str(TINY)), Scene)


def test_load_zero_scenes() -> None:
    with pytest.raises(SceneLoadError, match="found 0"):
        cli.load_scene(FIXTURES / "zero_scenes.py")


def test_load_many_scenes() -> None:
    with pytest.raises(SceneLoadError, match="found 2"):
        cli.load_scene(FIXTURES / "two_scenes.py")


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SceneLoadError, match="not found"):
        cli.load_scene(tmp_path / "nope.py")


def test_load_skips_main_block() -> None:
    scene = cli.load_scene(FIXTURES / "main_guard.py")
    assert isinstance(scene, Scene)


def test_overrides_apply_before_script_code() -> None:
    scene = cli.load_scene(TINY, seed=123, duration=0.2)
    assert scene.config.seed == 123
    assert scene.config.duration == 0.2
    assert scene.total_frames == 6
    ball = scene.objects[1]
    assert ball.velocity[0] == pytest.approx(_expected_vx(123))
    assert _expected_vx(123) != pytest.approx(_expected_vx(7))


def test_no_overrides_keep_script_values() -> None:
    ball = cli.load_scene(TINY).objects[1]
    assert ball.velocity[0] == pytest.approx(_expected_vx(7))


def test_overrides_cleared_after_load() -> None:
    cli.load_scene(TINY, seed=5)
    assert scene_module._overrides == {}
    assert Scene(width=64, height=48).config.seed == 0


def test_overrides_cleared_after_failed_load() -> None:
    with pytest.raises(SceneLoadError):
        cli.load_scene(FIXTURES / "zero_scenes.py", seed=5, duration=1.0)
    assert scene_module._overrides == {}


# --- main: render ---------------------------------------------------------------


def test_render_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "sub" / "v.mp4"
    code = cli.main(["render", str(TINY), "--seed", "3", "--duration", "0.2", "--out", str(out)])
    assert code == 0
    assert out.is_file() and out.stat().st_size > 0
    stdout = capsys.readouterr().out
    assert "wrote" in stdout and "6 frames" in stdout


def test_render_default_out_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["render", str(TINY), "--seed", "9", "--duration", "0.1"]) == 0
    assert (tmp_path / "out" / "tiny_scene_seed9.mp4").is_file()


def test_render_default_out_uses_script_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["render", str(TINY), "--duration", "0.1"]) == 0
    assert (tmp_path / "out" / "tiny_scene_seed7.mp4").is_file()


# --- main: preview --------------------------------------------------------------


def test_preview_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Callable[[], Scene], float]] = []
    monkeypatch.setattr(cli, "run_preview", lambda make, scale, **_kw: calls.append((make, scale)))
    code = cli.main(["preview", str(TINY), "--seed", "11", "--duration", "0.3", "--scale", "0.5"])
    assert code == 0
    assert len(calls) == 1
    make, scale = calls[0]
    assert scale == 0.5
    first, second = make(), make()
    assert first is not second
    assert first.config.seed == 11 and first.config.duration == 0.3
    assert first.objects[1].velocity[0] == pytest.approx(_expected_vx(11))


def test_preview_default_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    scales: list[float] = []
    monkeypatch.setattr(cli, "run_preview", lambda _make, scale, **_kw: scales.append(scale))
    assert cli.main(["preview", str(TINY)]) == 0
    assert scales == [0.45]


def test_preview_load_error_before_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(cli, "run_preview", lambda _make, _scale, **_kw: called.append(True))
    assert cli.main(["preview", str(tmp_path / "missing.py")]) == 2
    assert called == []
    assert "error:" in capsys.readouterr().err


# --- main: errors ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "message"),
    [("zero_scenes.py", "found 0"), ("two_scenes.py", "found 2"), ("bad_config.py", "width")],
)
def test_error_exit_code(name: str, message: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["render", str(FIXTURES / name)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert message in err
    assert "Traceback" not in err


def test_missing_file_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["render", str(tmp_path / "nope.py")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "nope.py" in err


def test_invalid_override_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["render", str(TINY), "--duration", "-1"]) == 2
    assert "duration" in capsys.readouterr().err


def test_missing_ffmpeg_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda _name: None)
    assert cli.main(["render", str(TINY), "--out", str(tmp_path / "o.mp4")]) == 2
    assert "install" in capsys.readouterr().err
    assert not (tmp_path / "o.mp4").exists()


def test_usage_error_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])
    assert exc.value.code != 0


# --- default scene / Scene.run --------------------------------------------------


def test_default_scene_without_subcommand_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    seeds: list[int] = []
    monkeypatch.setattr(
        cli, "run_preview", lambda make, _scale, **_kw: seeds.append(make().config.seed)
    )
    assert cli.main(["--seed", "4"], default_scene=TINY) == 0
    assert cli.main([], default_scene=TINY) == 0
    assert seeds == [4, 7]


def test_default_scene_with_render(tmp_path: Path) -> None:
    out = tmp_path / "d.mp4"
    code = cli.main(["render", "--duration", "0.1", "--out", str(out)], default_scene=TINY)
    assert code == 0
    assert out.is_file()


def test_scene_run_dispatches_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[list[str], Path | None]] = []

    def fake_main(argv: list[str], default_scene: Path | None = None) -> int:
        seen.append((list(argv), default_scene))
        return 0

    monkeypatch.setattr(cli, "main", fake_main)
    monkeypatch.setattr(sys, "argv", [str(TINY), "render", "--seed", "2"])
    with pytest.raises(SystemExit) as exc:
        Scene(width=64, height=48).run()
    assert exc.value.code == 0
    assert seen == [(["render", "--seed", "2"], TINY)]


def test_script_run_as_main_renders(tmp_path: Path) -> None:
    out = tmp_path / "m.mp4"
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy"}
    proc = subprocess.run(
        [sys.executable, str(TINY), "render", "--seed", "1", "--duration", "0.1",
         "--out", str(out)],
        capture_output=True, text=True, env=env, timeout=60,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
