"""Climax frame, post text and the --export pack (T-606: FR-609, FR-610, FR-611)."""

import json
import os
from pathlib import Path

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene, cli  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.errors import ConfigError  # noqa: E402

PACK = Path(__file__).parent / "fixtures" / "pack_scene.py"


def _run(**params: str) -> tuple[Scene, list[bytes]]:
    scene = cli.load_scene(PACK, params=params)
    frames = list(scene.frames())
    return scene, frames


def test_mark_climax_sets_next_frame_last_call_wins() -> None:
    scene, frames = _run(mark="0.3")
    assert scene.climax_frame == 9  # at(0.3) fires on frame 8's last step -> frame 9
    assert scene.climax_image == frames[9]
    scene = Scene(width=32, height=32, fps=30, duration=1.0)
    scene.at(0.1, [A.mark_climax()])
    scene.at(0.2, [A.mark_climax()])
    frames = list(scene.frames())
    assert scene.climax_frame == 6 and scene.climax_image == frames[6]


def test_default_climax_is_frame_after_first_end_after() -> None:
    scene, frames = _run()
    assert scene.climax_frame == 21  # end_after applied on frame 20
    assert len(frames) == 24 and scene.climax_image == frames[21]


def test_climax_image_falls_back_to_last_frame() -> None:
    scene = Scene(width=32, height=32, fps=30, duration=0.2)
    frames = list(scene.frames())
    assert scene.climax_frame is None and scene.climax_image == frames[-1]
    scene = Scene(width=32, height=32, fps=30, duration=1.0)
    scene.at(0.1, [A.end_after(0)])
    frames = list(scene.frames())
    assert scene.climax_frame == 3 and len(frames) == 3 and scene.climax_image == frames[-1]


def test_climax_image_is_taken_before_the_loop_fade() -> None:
    scene = Scene(width=32, height=32, fps=30, duration=0.5, loop_fade=0.5, background="#204060")
    scene.add_ball(pos=(16, 4), radius=3, color="#ffffff")
    plain = Scene(width=32, height=32, fps=30, duration=0.5, background="#204060")
    plain.add_ball(pos=(16, 4), radius=3, color="#ffffff")
    list(scene.frames())
    assert scene.climax_image == list(plain.frames())[-1]


def test_marks_do_not_change_the_simulation() -> None:
    a, _ = _run(mark="0.3")
    b, _ = _run()
    assert [(e.kind, e.step) for e in a.events if e.kind != "timer"] == [
        (e.kind, e.step) for e in b.events if e.kind != "timer"
    ]
    assert a.rng.getstate() == b.rng.getstate()


def test_post_text_format_and_validation() -> None:
    scene = Scene(duration=0.1)
    assert scene.post_text() is None
    scene.post(title=lambda s: f"T{s.frame}", description="Line 1\nLine 2", hashtags=["a", "#b"])
    assert scene.post_text() == "TITLE\nT0\n\nDESCRIPTION\nLine 1\nLine 2\n\nHASHTAGS\n#a #b\n"
    scene.post(title="Only")
    assert scene.post_text() == "TITLE\nOnly\n\nDESCRIPTION\n\n\nHASHTAGS\n\n"
    for kwargs, field in [
        ({"title": ""}, "title"), ({"title": "x" * 101}, "title"), ({"title": 3}, "title"),
        ({"title": "t", "description": "x" * 5001}, "description"),
        ({"title": "t", "hashtags": ["two words"]}, "hashtags"),
        ({"title": "t", "hashtags": "abc"}, "hashtags"),
        ({"title": "t", "hashtags": ["#"]}, "hashtags"),
    ]:  # fmt: skip
        with pytest.raises(ConfigError, match=field):
            scene.post(**kwargs)  # type: ignore[arg-type]
    scene.post(title=lambda s: "")
    with pytest.raises(ConfigError, match="title"):
        scene.post_text()


def _render(tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "v.mp4"
    assert cli.main(["render", str(PACK), "--out", str(out), "--quiet", *extra]) == 0
    return out


def test_render_export_writes_thumbnail_and_post(tmp_path: Path) -> None:
    out = _render(tmp_path, "--export")
    thumb, post = tmp_path / "v_thumb.png", tmp_path / "v_post.txt"
    image = pygame.image.load(str(thumb))
    assert image.get_size() == (64, 48)
    scene, _ = _run()
    assert pygame.image.tobytes(image, "RGB") == scene.climax_image
    assert post.read_text(encoding="utf-8") == scene.post_text()
    assert post.read_text(encoding="utf-8").startswith("TITLE\nEnded at frame 24\n")
    assert out.exists() and out.with_suffix(".json").exists()


def test_export_without_post_writes_only_thumbnail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _render(tmp_path, "--export", "--set", "post=false")
    assert (tmp_path / "v_thumb.png").exists() and not (tmp_path / "v_post.txt").exists()
    assert "note: no scene.post(...); wrote only the thumbnail" in capsys.readouterr().out


def test_no_pack_without_export(tmp_path: Path) -> None:
    _render(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["v.json", "v.mp4"]


def test_failed_job_leaves_no_pack(tmp_path: Path) -> None:
    out = tmp_path / "v.mp4"
    code = cli.main(["render", str(PACK), "--out", str(out), "--quiet", "--export",
                     "--set", "fail=true"])  # fmt: skip
    assert code == 2
    assert list(tmp_path.iterdir()) == []


def test_batch_export_and_keep_best_remove_loser_packs(tmp_path: Path) -> None:
    argv = ["batch", str(PACK), "--seeds", "1-2", "--out-dir", str(tmp_path), "--quiet",
            "--export", "--score", "seed", "--keep-best", "1"]  # fmt: skip
    assert cli.main(argv) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "pack_scene_seed2.json", "pack_scene_seed2.mp4", "pack_scene_seed2_post.txt",
        "pack_scene_seed2_thumb.png", "ranking.json",
    ]  # fmt: skip
    assert json.loads((tmp_path / "ranking.json").read_text())[1]["kept"] is False


# Review fixes (2026-11-06).
def test_reexport_without_post_removes_stale_post_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _render(tmp_path, "--export")
    assert (tmp_path / "v_post.txt").exists()
    _render(tmp_path, "--export", "--set", "post=false")
    assert not (tmp_path / "v_post.txt").exists()
    assert "note: no scene.post(...)" in capsys.readouterr().out


def test_title_must_be_one_line() -> None:
    with pytest.raises(ConfigError, match="title"):
        Scene(duration=0.1).post(title="x\nDESCRIPTION")


def test_ctx_mark_climax_and_same_seed_same_thumbnail() -> None:
    def run() -> Scene:
        scene = Scene(width=32, height=32, fps=30, duration=0.5, seed=4)
        scene.add_ball(pos=(16, 8), radius=3, velocity=(scene.rng.uniform(-50, 50), 0))

        @scene.at(0.2)
        def mark(ctx, event):  # type: ignore[no-untyped-def]
            ctx.mark_climax()

        list(scene.frames())
        return scene

    a, b = run(), run()
    assert a.climax_frame == 6 and a.climax_image == b.climax_image
