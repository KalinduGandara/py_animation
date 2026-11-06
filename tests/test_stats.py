"""Scene stats and metadata additions (T-601: FR-601, FR-602, NFR-601)."""

import json
import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene, cli  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402
from bouncekit.world.ball import Ball  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
STATS = FIXTURES / "stats_scene.py"
M4_KEYS = [
    "scene", "video", "seed", "params", "duration", "frames", "fps", "size", "events",
    "sound_triggers", "versions", "render_seconds",
]  # fmt: skip


def test_stat_records_replaces_and_keeps_order() -> None:
    scene = Scene(duration=0.1)
    scene.stat("b", 1)
    scene.stat("a", 2.5)
    scene.stat("b", True)
    assert scene.stats == {"b": True, "a": 2.5}
    assert list(scene.stats) == ["b", "a"]
    copy = scene.stats
    copy["z"] = 1
    assert "z" not in scene.stats


@pytest.mark.parametrize(
    ("name", "value", "field"),
    [("", 1, "name"), (3, 1, "name"), ("x", "1", "value"), ("x", math.nan, "value"),
     ("x", math.inf, "value"), ("x", None, "value")],
)  # fmt: skip
def test_stat_rejects_bad_input(name: object, value: object, field: str) -> None:
    scene = Scene(duration=0.1)
    with pytest.raises(ConfigError, match=field):
        scene.stat(name, value)  # type: ignore[arg-type]


def _render(tmp_path: Path, *sets: str) -> dict[str, object]:
    out = tmp_path / "v.mp4"
    argv = ["render", str(STATS), "--out", str(out), "--quiet"]
    for item in sets:
        argv += ["--set", item]
    assert cli.main(argv) == 0
    return json.loads(out.with_suffix(".json").read_text())  # type: ignore[no-any-return]


def test_metadata_has_stats_after_sound_triggers(tmp_path: Path) -> None:
    data = _render(tmp_path)
    keys = list(data)
    assert keys == [*M4_KEYS[:10], "stats", *M4_KEYS[10:]]
    ref = cli.load_scene(STATS)
    for _ in ref.frames():
        pass
    assert data["stats"] == ref.stats == {"hits": ref.stats["hits"], "seed_x2": 6}
    assert ref.stats["hits"] > 0


def test_metadata_without_stats_keeps_m4_keys(tmp_path: Path) -> None:
    assert list(_render(tmp_path, "missing=true")) == M4_KEYS


def test_duration_is_rendered_length(tmp_path: Path) -> None:
    data = _render(tmp_path, "stop=0.5")
    assert data["frames"] == 15  # at(0.5) fires on the last step of frame 14
    assert data["duration"] == round(15 / 30, 6)
    assert _render(tmp_path / "b")["duration"] == 1.0


def test_stats_do_not_change_simulation() -> None:
    a = cli.load_scene(STATS)
    b = cli.load_scene(STATS, params={"missing": "true"})
    for _ in range(30):
        a.step_frame()
        b.step_frame()
    assert [(e.kind, e.frame, e.step) for e in a.events] == [
        (e.kind, e.frame, e.step) for e in b.events
    ]
    assert a.rng.getstate() == b.rng.getstate()
    assert [x.position for x in a.objects if isinstance(x, Ball)] == [
        x.position for x in b.objects if isinstance(x, Ball)
    ]
