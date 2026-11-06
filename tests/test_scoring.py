"""Batch seed scoring: --score, ranking.json, --keep-best (T-602: FR-603, FR-604)."""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import cli  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.scoring import ScoreError, compile_score  # noqa: E402

STATS = Path(__file__).parent / "fixtures" / "stats_scene.py"
META: dict[str, object] = {
    "seed": 4, "duration": 2.5, "frames": 150, "sound_triggers": 9,
    "params": {"gap": 30.0, "name": "x"}, "events": {"escape": 3, "spawn": 0},
    "stats": {"blue": 0.3, "pink": 0.22, "won": True},
}  # fmt: skip


@pytest.mark.parametrize(
    ("expr", "value"),
    [
        ("1", 1.0),
        ("-abs(stats.blue - stats.pink)", -0.08),
        ("duration * 2 + frames // 7 - seed % 3", 5.0 + 21 - 1),
        ("max(events.escape, 1, 2) ** 2 / 3", 3.0),
        ("min(params.gap, 10) + round(2.6)", 13.0),
        ("+sound_triggers - -1", 10.0),
        ("stats.won * 5", 5.0),
    ],
)
def test_evaluates_allowed_expressions(expr: str, value: float) -> None:
    assert compile_score(expr).evaluate(META) == pytest.approx(value)


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')", "stats.blue.real", "(lambda: 1)()", "stats.blue > 1", "stats['blue']",
        "open", "abs", "len(stats)", "stats", "x if 1 else 2", "1 +", "", "'a'", "abs(x=1)",
        "seed.real", "stats.__class__", "[1]",
    ],
)  # fmt: skip
def test_rejects_disallowed_expressions(expr: str) -> None:
    with pytest.raises(ConfigError, match="--score"):
        compile_score(expr)


@pytest.mark.parametrize("expr", ["stats.missing", "params.name", "1 / (frames - 150)"])
def test_unscorable_metadata_raises_score_error(expr: str) -> None:
    with pytest.raises(ScoreError):
        compile_score(expr).evaluate(META)


def _batch(tmp_path: Path, *extra: str) -> int:
    argv = ["batch", str(STATS), "--duration", "0.5", "--out-dir", str(tmp_path), "--quiet"]
    return cli.main([*argv, *extra])


def _ranking(tmp_path: Path) -> list[dict[str, object]]:
    return json.loads((tmp_path / "ranking.json").read_text())  # type: ignore[no-any-return]


def test_batch_writes_ranking_sorted_by_score(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _batch(tmp_path, "--seeds", "1-4", "--score", "stats.hits * 0 + seed % 2") == 0
    entries = _ranking(tmp_path)
    assert [e["seed"] for e in entries] == [1, 3, 2, 4]  # ties keep job order
    assert [e["rank"] for e in entries] == [1, 2, 3, 4]
    assert [e["score"] for e in entries] == [1.0, 1.0, 0.0, 0.0]
    assert entries[0]["video"] == "stats_scene_seed1.mp4"
    assert entries[0]["params"] == {"stop": 0.0, "missing": False}
    assert all(e["kept"] is True for e in entries)
    assert "best: stats_scene_seed1.mp4 (score 1)" in capsys.readouterr().out


def test_unscorable_job_ranks_last_with_error(tmp_path: Path) -> None:
    code = _batch(tmp_path, "--seeds", "1", "--grid", "missing=true,false", "--score", "stats.hits")
    assert code == 0
    entries = _ranking(tmp_path)
    assert entries[0]["video"] == "stats_scene_seed1_missing-false.mp4"
    assert isinstance(entries[0]["score"], float)
    assert entries[1]["score"] is None and "hits" in str(entries[1]["error"])


@pytest.mark.parametrize(
    "extra",
    [("--score", "stats.hits >"), ("--keep-best", "1"), ("--score", "1", "--keep-best", "0")],
)
def test_bad_score_options_exit_2_before_any_job(tmp_path: Path, extra: tuple[str, ...]) -> None:
    assert _batch(tmp_path, "--seeds", "1", *extra) == 2
    assert not list(tmp_path.glob("*.mp4"))


def test_keep_best_deletes_the_rest(tmp_path: Path) -> None:
    assert _batch(tmp_path, "--seeds", "1-3", "--score", "seed", "--keep-best", "1") == 0
    entries = _ranking(tmp_path)
    assert [(e["seed"], e["kept"]) for e in entries] == [(3, True), (2, False), (1, False)]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ranking.json", "stats_scene_seed3.json", "stats_scene_seed3.mp4",
    ]  # fmt: skip


def test_no_ranking_without_score(tmp_path: Path) -> None:
    assert _batch(tmp_path, "--seeds", "1") == 0
    assert not (tmp_path / "ranking.json").exists()
