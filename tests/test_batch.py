"""Batch planning and execution (FR-403, FR-404, FR-402, NFR-401 batch part)."""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import cli  # noqa: E402
from bouncekit.batch import parse_grid, parse_seeds, plan_jobs  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.export import ffmpeg as ff  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
PARAM = FIXTURES / "param_scene.py"
FLAKY = FIXTURES / "flaky_scene.py"


# --- parsing --------------------------------------------------------------------


def test_parse_seeds() -> None:
    assert parse_seeds("3,1-2,2") == [3, 1, 2]
    assert parse_seeds("7") == [7]
    assert parse_seeds("0-2") == [0, 1, 2]


@pytest.mark.parametrize("spec", ["5-3", "-1", "a", "", "1,,2", "1-", "1.5"])
def test_parse_seeds_rejects(spec: str) -> None:
    with pytest.raises(ConfigError, match="--seeds"):
        parse_seeds(spec)


def test_parse_grid() -> None:
    assert parse_grid(["gap=,x"]) == [("gap", ["", "x"])]
    assert parse_grid(["gap="]) == [("gap", [""])]
    assert parse_grid(["a=1,2", "b=x"]) == [("a", ["1", "2"]), ("b", ["x"])]


@pytest.mark.parametrize("items", [["gap"], ["=1"], ["1x=3"], ["a=1", "a=2"]])
def test_parse_grid_rejects(items: list[str]) -> None:
    with pytest.raises(ConfigError, match="--grid"):
        parse_grid(items)


# --- planning -------------------------------------------------------------------


def test_plan_jobs_product_order_and_names(tmp_path: Path) -> None:
    jobs = plan_jobs(
        PARAM,
        seeds=[1, 2],
        sets=[("theme", "a")],
        grid=[("gap", ["10", "20"]), ("speed", ["1", "2"])],
        duration=0.5,
        out_dir=tmp_path,
    )
    assert len(jobs) == 8
    assert [j.index for j in jobs] == list(range(1, 9))
    assert [j.seed for j in jobs] == [1] * 4 + [2] * 4
    assert all(j.duration == 0.5 for j in jobs)
    assert jobs[0].overrides == (("theme", "a"), ("gap", "10"), ("speed", "1"))
    assert [dict(j.overrides)["speed"] for j in jobs[:4]] == ["1", "2", "1", "2"]
    assert [dict(j.overrides)["gap"] for j in jobs[:4]] == ["10", "10", "20", "20"]
    assert jobs[0].out == tmp_path / "param_scene_seed1_theme-a_gap-10_speed-1.mp4"
    assert jobs[-1].out == tmp_path / "param_scene_seed2_theme-a_gap-20_speed-2.mp4"


def test_plan_jobs_without_seeds_resolves_name_later(tmp_path: Path) -> None:
    jobs = plan_jobs(PARAM, seeds=None, sets=[], grid=[("vx", ["1", "2"])], duration=None,
                     out_dir=tmp_path)  # fmt: skip
    assert [j.seed for j in jobs] == [None, None]
    assert [j.out for j in jobs] == [None, None]


def test_plan_jobs_rejects_name_collision(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="same file"):
        plan_jobs(PARAM, seeds=[1], sets=[], grid=[("mode", ["a b", "a_b"])], duration=None,
                  out_dir=tmp_path)  # fmt: skip
    with pytest.raises(ConfigError, match="same file"):
        plan_jobs(PARAM, seeds=None, sets=[], grid=[("mode", ["a/b", "a:b"])], duration=None,
                  out_dir=tmp_path)  # fmt: skip


def test_plan_jobs_rejects_key_in_set_and_grid(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="mode"):
        plan_jobs(PARAM, seeds=[1], sets=[("mode", "a")], grid=[("mode", ["b"])],
                  duration=None, out_dir=tmp_path)  # fmt: skip


# --- CLI ------------------------------------------------------------------------


def _batch(tmp_path: Path, *extra: str) -> int:
    return cli.main(["batch", str(FLAKY), "--out-dir", str(tmp_path), *extra])


def test_cli_collisions_and_repeats_exit_2_before_rendering(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _batch(tmp_path, "--seeds", "1", "--grid", "mode=a b,a_b") == 2
    assert "error:" in capsys.readouterr().err
    assert _batch(tmp_path, "--set", "mode=a", "--grid", "mode=b,c") == 2
    assert "error:" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "extra",
    [
        ["--seeds", "5-3"],
        ["--grid", "mode"],
        ["--set", "=3"],
        ["--jobs", "0"],
        ["--duration", "-1"],
        ["--duration", "nan"],
    ],
)
def test_cli_invalid_options_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    assert _batch(tmp_path, *extra) == 2
    assert "error:" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_cli_failure_isolation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _batch(tmp_path, "--seeds", "1", "--grid", "mode=a,bad,b,c")
    out, err = capsys.readouterr()
    assert code == 1
    for mode in ("a", "b", "c"):
        assert (tmp_path / f"flaky_scene_seed1_mode-{mode}.mp4").is_file()
        assert (tmp_path / f"flaky_scene_seed1_mode-{mode}.json").is_file()
    assert not (tmp_path / "flaky_scene_seed1_mode-bad.mp4").exists()
    assert not (tmp_path / "flaky_scene_seed1_mode-bad.json").exists()
    assert "[2/4] FAILED" in err
    assert "flaky_scene_seed1_mode-bad.mp4" in err
    assert "RuntimeError: flaky scene refuses mode=bad" in err
    assert "FAILED" not in out
    assert "[1/4] wrote" in out and "[4/4] wrote" in out
    assert "(6 frames," in out
    assert "batch: 3 ok, 1 failed" in out


def test_cli_unknown_param_fails_job(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _batch(tmp_path, "--grid", "nope=1") == 1
    _out, err = capsys.readouterr()
    assert "FAILED" in err and "ConfigError" in err
    assert list(tmp_path.iterdir()) == []


def test_cli_all_ok_exit_0_and_script_seed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _batch(tmp_path, "--grid", "mode=a,b") == 0
    out = capsys.readouterr().out
    assert "batch: 2 ok, 0 failed" in out
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [
        "flaky_scene_seed7_mode-a.json", "flaky_scene_seed7_mode-a.mp4",
        "flaky_scene_seed7_mode-b.json", "flaky_scene_seed7_mode-b.mp4",
    ]  # fmt: skip
    data = json.loads((tmp_path / "flaky_scene_seed7_mode-b.json").read_text())
    assert data["seed"] == 7 and data["params"] == {"mode": "b"}


def test_cli_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _batch(tmp_path, "--seeds", "1-2", "--quiet") == 0
    out = capsys.readouterr().out
    assert "wrote" not in out
    assert "batch: 2 ok, 0 failed" in out
    assert (tmp_path / "flaky_scene_seed2.mp4").is_file()


def test_cli_creates_out_dir_and_duration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "nested" / "dir"
    assert cli.main(["batch", str(FLAKY), "--out-dir", str(out_dir), "--duration", "0.1"]) == 0
    data = json.loads((out_dir / "flaky_scene_seed7.json").read_text())
    assert data["frames"] == 3 and data["duration"] == 0.1


def test_cli_missing_ffmpeg_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ff.shutil, "which", lambda _name: None)
    assert _batch(tmp_path, "--seeds", "1") == 2
    assert "install" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def _outputs(out_dir: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    for path in sorted(out_dir.iterdir()):
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            data.pop("render_seconds")
            result[path.name] = data
        else:
            result[path.name] = None
    return result


def test_parallel_matches_sequential(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seq, par = tmp_path / "seq", tmp_path / "par"
    args = ["--seeds", "1-2", "--grid", "mode=a,bad"]
    assert cli.main(["batch", str(FLAKY), "--out-dir", str(seq), *args]) == 1
    assert cli.main(["batch", str(FLAKY), "--out-dir", str(par), "--jobs", "2", *args]) == 1
    out = capsys.readouterr().out
    assert out.count("batch: 2 ok, 2 failed") == 2
    assert _outputs(seq) == _outputs(par)
    assert len(_outputs(seq)) == 4
