"""Tests for the live preview (FR-009), run headless with the dummy SDL driver."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from bouncekit import Scene
from bouncekit.render.preview import Preview, run_preview


def make_scene() -> Scene:
    scene = Scene(width=64, height=48, fps=30, duration=0.5, seed=3, gravity=(0.0, 100.0),
                  max_speed=1500)
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

    def fake_run(make: "object", scale: float = 0.45, max_frames: int | None = None) -> Scene:
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
