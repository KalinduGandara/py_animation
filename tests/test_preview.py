"""Tests for the live preview (FR-009), run headless with the dummy SDL driver."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from bouncekit import Scene
from bouncekit.cli import load_scene
from bouncekit.render.preview import Preview, run_preview


def make_scene() -> Scene:
    scene = Scene(
        width=64, height=48, fps=30, duration=0.5, seed=3, gravity=(0.0, 100.0), max_speed=1500
    )
    scene.add_circle(center=(32, 24), radius=20, segments=32)
    scene.add_ball(pos=(32, 24), radius=4, velocity=(30.0, 10.0))
    return scene


def key(k: int) -> "pygame.event.Event":
    return pygame.event.Event(pygame.KEYDOWN, key=k)


@pytest.fixture
def preview() -> "Preview":
    return Preview(make_scene, scale=1.0)


def test_runs_n_frames_headless() -> None:
    scene = run_preview(make_scene, scale=1.0, max_frames=5)
    assert scene.frame == 5  # each loop iteration draws, then steps once


def test_holds_last_frame_when_finished() -> None:
    scene = run_preview(make_scene, scale=1.0, max_frames=60)
    assert scene.frame == scene.total_frames == 15


def test_space_toggles_pause(preview: "Preview") -> None:
    assert not preview.paused
    preview.handle_event(key(pygame.K_SPACE))
    assert preview.paused
    preview.tick()
    preview.tick()
    assert preview.scene.frame == 0
    preview.handle_event(key(pygame.K_SPACE))
    assert not preview.paused


def test_right_steps_one_frame_only_when_paused(preview: "Preview") -> None:
    preview.handle_event(key(pygame.K_RIGHT))
    assert preview.scene.frame == 0  # ignored while playing
    preview.handle_event(key(pygame.K_SPACE))
    preview.handle_event(key(pygame.K_RIGHT))
    assert preview.scene.frame == 1
    preview.handle_event(key(pygame.K_RIGHT))
    assert preview.scene.frame == 2


def test_step_does_not_pass_the_end(preview: "Preview") -> None:
    preview.handle_event(key(pygame.K_SPACE))
    for _ in range(100):
        preview.handle_event(key(pygame.K_RIGHT))
    assert preview.scene.frame == preview.scene.total_frames


def test_restart_rebuilds_scene_and_unpauses(preview: "Preview") -> None:
    for _ in range(5):
        preview.tick()
    old = preview.scene
    assert old.frame == 5
    preview.handle_event(key(pygame.K_SPACE))
    preview.handle_event(key(pygame.K_r))
    assert preview.scene is not old
    assert preview.scene.frame == 0
    assert not preview.paused
    assert preview.scene.objects[1].position == make_scene().objects[1].position


@pytest.mark.parametrize("k", [pygame.K_ESCAPE, pygame.K_q])
def test_quit_keys(preview: "Preview", k: int) -> None:
    assert not preview.quit
    preview.handle_event(key(k))
    assert preview.quit


def test_window_close_quits(preview: "Preview") -> None:
    preview.handle_event(pygame.event.Event(pygame.QUIT))
    assert preview.quit


def test_window_size_and_title() -> None:
    p = Preview(make_scene, scale=0.5)
    assert p.screen.get_size() == (32, 24)
    p.tick()
    assert "1/15" in pygame.display.get_caption()[0]
    p.handle_event(key(pygame.K_SPACE))
    p.tick()
    assert "paused" in pygame.display.get_caption()[0]


def test_preview_frames_match_offline_render() -> None:
    p = Preview(make_scene, scale=1.0)
    p.tick()
    p.tick()
    # The displayed surface is the renderer output for the state before the last step.
    ref = make_scene()
    it = ref.frames()
    next(it)
    assert p.renderer.to_rgb_bytes() == next(it)


def test_invalid_scale_rejected() -> None:
    from bouncekit.errors import ConfigError

    with pytest.raises(ConfigError):
        Preview(make_scene, scale=0.0)


def test_scene_preview_runs_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Scene] = []

    def fake_run(
        make: "object", scale: float = 0.45, max_frames: int | None = None, **_kw: object
    ) -> Scene:
        scene = make()  # type: ignore[operator]
        seen.append(scene)
        return scene  # type: ignore[no-any-return]

    monkeypatch.setattr("bouncekit.render.preview.run_preview", fake_run)
    s = make_scene()
    s.preview(scale=0.5)
    assert seen == [s]


class _SlowClock:
    """Fake clock that records pacing calls and pretends every frame ran late."""

    def __init__(self) -> None:
        self.ticks: list[int] = []

    def tick(self, fps: int = 0) -> int:
        self.ticks.append(fps)
        return 1000  # 1 s per frame: far behind real time


def test_paced_at_scene_fps_and_never_skips_steps(preview: "Preview") -> None:
    clock = _SlowClock()
    preview.clock = clock  # type: ignore[assignment]
    preview.run(max_frames=5)
    assert clock.ticks == [preview.scene.config.fps] * 5
    assert preview.scene.frame == 5  # one step per displayed frame despite lag


# --- T-305: hot-reload (FR-310) ---

SCRIPT = (
    "from bouncekit import Scene\n"
    "scene = Scene(width=64, height=48, fps=30, duration=0.5, seed=3, background={bg!r})\n"
)


def write_script(path: Path, text: str, bump: int) -> None:
    path.write_text(text)
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + bump * 1_000_000_000))


@pytest.fixture
def watched(tmp_path: Path) -> "tuple[Path, Preview]":
    file = tmp_path / "scene.py"
    write_script(file, SCRIPT.format(bg="#101010"), 0)
    pv = Preview(lambda: load_scene(file), scale=1.0, watch=file)
    return file, pv


def test_reload_replaces_scene_and_prints_reloaded(
    watched: "tuple[Path, Preview]", capsys: pytest.CaptureFixture[str]
) -> None:
    file, pv = watched
    old = pv.scene
    pv.scene.step_frame()
    write_script(file, SCRIPT.format(bg="#ff0000"), 1)
    pv.poll_reload(now=pv._last_check + 1.0)
    assert pv.scene is not old
    assert pv.scene.frame == 0
    assert pv.scene.config.background != old.config.background
    captured = capsys.readouterr()
    assert f"reloaded {file}" in captured.err  # FR-310: path, on stderr
    assert "reloaded" not in captured.out
    assert "reloaded" in pv._title()


def test_poll_within_throttle_does_nothing(watched: "tuple[Path, Preview]") -> None:
    file, pv = watched
    old = pv.scene
    pv.poll_reload(now=pv._last_check + 1.0)
    write_script(file, SCRIPT.format(bg="#ff0000"), 1)
    pv.poll_reload(now=pv._last_check + 0.1)
    assert pv.scene is old


def test_unchanged_file_never_reloads(watched: "tuple[Path, Preview]") -> None:
    _, pv = watched
    old = pv.scene
    for i in range(1, 4):
        pv.poll_reload(now=pv._last_check + 1.0 * i)
    assert pv.scene is old


def test_errors_keep_scene_print_once_and_fix_clears(
    watched: "tuple[Path, Preview]", capsys: pytest.CaptureFixture[str]
) -> None:
    file, pv = watched
    old = pv.scene
    write_script(file, "def (:\n", 1)
    pv.poll_reload(now=pv._last_check + 1.0)
    pv.poll_reload(now=pv._last_check + 1.0)  # same version: no second message
    assert pv.scene is old
    err = capsys.readouterr().err
    assert err.count("error: SyntaxError") == 1
    assert "load error" in pv._title()

    write_script(file, SCRIPT.format(bg="#101010").replace("duration=0.5", "duration=-1"), 2)
    pv.poll_reload(now=pv._last_check + 1.0)
    assert pv.scene is old
    assert "error: ConfigError" in capsys.readouterr().err

    write_script(file, SCRIPT.format(bg="#00ff00"), 3)
    pv.poll_reload(now=pv._last_check + 1.0)
    assert pv.scene is not old
    assert pv.error is None
    assert "load error" not in pv._title()


def test_restart_with_broken_file_keeps_scene(watched: "tuple[Path, Preview]") -> None:
    file, pv = watched
    old = pv.scene
    write_script(file, "def (:\n", 1)
    pv.handle_event(key(pygame.K_r))
    assert pv.scene is old
    assert pv.error is not None


def test_reload_with_new_canvas_size_rebuilds_window(watched: "tuple[Path, Preview]") -> None:
    file, pv = watched
    write_script(file, SCRIPT.format(bg="#101010").replace("width=64", "width=80"), 1)
    pv.poll_reload(now=pv._last_check + 1.0)
    assert pv.renderer.surface.get_size()[0] == 80
    assert pv.screen.get_size()[0] == 80
    pv.tick()
