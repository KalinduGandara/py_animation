"""Timers, conditions, end_after, decorators, subject checks (FR-202, FR-209, FR-211)."""

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import AudioConfig, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.audio.mixer import num_samples  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.preview import run_preview  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480  # 60 fps x 8 substeps


def _scene(duration: float = 2.0, **kw: Any) -> Scene:
    s = Scene(width=64, height=64, duration=duration, max_speed=1000, **kw)
    s.add_circle(center=(32, 32), radius=24, thickness=6, segments=32, tags={"wall"})
    s.add_ball(pos=(32, 32), radius=4, tags={"ball"})
    return s


def _run(s: Scene, frames: int | None = None) -> None:
    """Step ``frames`` frames, or until ``total_frames`` (which end_after may lower)."""
    if frames is None:
        while s.frame < s.total_frames:
            s.step_frame()
        return
    for _ in range(frames):
        s.step_frame()


def _kind(s: Scene, kind: str) -> list[Event]:
    return [e for e in s.events if e.kind == kind]


# --- timers ---------------------------------------------------------------------------


def test_every_fires_at_multiples_of_its_period() -> None:
    s = _scene()
    seen: list[Event] = []
    s.every(0.5, [lambda ctx, ev: seen.append(ev)])
    _run(s)
    assert [e.step for e in seen] == [240, 480, 720, 960]
    assert seen == _kind(s, "timer")
    for ev in seen:
        assert ev.objects == () and ev.speed is None and ev.position is None
        assert ev.time == ev.step / RATE and ev.frame == (ev.step - 1) // 8


def test_at_fires_once() -> None:
    s = _scene()
    seen: list[int] = []
    s.at(1.0, [lambda ctx, ev: seen.append(ev.step)])
    _run(s)
    assert seen == [480]
    assert [e.step for e in _kind(s, "timer")] == [480]


def test_due_timers_dispatch_in_registration_order() -> None:
    s = _scene()
    order: list[str] = []
    s.at(1.0, [lambda ctx, ev: order.append("at")])
    s.every(0.5, [lambda ctx, ev: order.append("every")])
    _run(s)
    assert order == ["every", "at", "every", "every", "every"]
    assert [e.step for e in _kind(s, "timer")] == [240, 480, 480, 720, 960]


def test_timer_handler_sees_no_subjects() -> None:
    s = _scene()
    seen: list[tuple[Any, ...]] = []

    @s.every(0.5)
    def tick(ctx: ActionContext, ev: Event) -> None:
        seen.append((ctx.a, ctx.b, ctx.event is ev, ctx.time))

    assert tick.__name__ == "tick"
    _run(s, 30)
    assert seen == [(None, None, True, 0.5)]


def test_timer_seconds_validation() -> None:
    s = _scene()
    for bad in (0, -1.0, math.nan, math.inf, "1", True):
        with pytest.raises(ConfigError, match="seconds"):
            s.every(bad, [A.destroy(target=s.objects[1])])  # type: ignore[arg-type]
        with pytest.raises(ConfigError, match="seconds"):
            s.at(bad, [A.destroy(target=s.objects[1])])  # type: ignore[arg-type]
    # Positive, but rounds to 0 steps at 480 steps per second.
    with pytest.raises(ConfigError, match="seconds"):
        s.every(0.0001, [lambda ctx, ev: None])
    with pytest.raises(ConfigError, match="seconds"):
        s.at(0.0001, [lambda ctx, ev: None])


def test_timer_play_uses_play_gain_and_ignores_min_impact_speed() -> None:
    s = _scene(audio=AudioConfig(min_impact_speed=1e9))
    s.every(0.25, [A.play(S.note("C5"), gain=0.5)])
    _run(s)
    assert [t.step for t in s.triggers] == [120, 240, 360, 480, 600, 720, 840, 960]
    assert all(t.gain == 0.5 for t in s.triggers)


def test_timer_ctx_play_and_retrigger_key_without_subject() -> None:
    s = _scene(audio=AudioConfig(min_retrigger_interval=0.3))
    s.every(0.25, [lambda ctx, ev: ctx.play(S.note("C5"), gain=0.7)])
    _run(s)
    # Retrigger key (play, None): 0.25 s gaps are blocked, 0.5 s gaps are not.
    assert [t.step for t in s.triggers] == [120, 360, 600, 840]
    assert all(t.gain == 0.7 for t in s.triggers)


# --- when -----------------------------------------------------------------------------


def test_when_fires_once_on_the_first_true_frame() -> None:
    s = _scene()
    calls: list[int] = []
    fired: list[tuple[Any, ...]] = []

    def predicate(scene: Scene) -> bool:
        calls.append(scene.frame)
        return scene.frame >= 3

    s.when(predicate, [lambda ctx, ev: fired.append((ctx.a, ctx.b, ev))])
    _run(s, 10)
    assert calls == [1, 2, 3]  # evaluated after each frame until it fires, then never
    assert len(fired) == 1
    _, _, ev = fired[0]
    assert (fired[0][0], fired[0][1]) == (None, None)
    assert ev.kind == "condition" and ev.frame == 2 and ev.step == 24
    assert ev.objects == () and ev.speed is None and ev.position is None
    assert _kind(s, "condition") == [ev]


def test_when_decorator_and_commands_apply_after_the_frame() -> None:
    s = _scene()
    ball = s.objects[1]
    counts: list[int] = []

    @s.when(lambda w: w.frame >= 2)
    def kill(ctx: ActionContext, ev: Event) -> None:
        ctx.destroy(ball)  # type: ignore[arg-type]

    s.every(1 / 60, [lambda ctx, ev: counts.append(ctx.scene.count("ball"))])
    assert kill.__name__ == "kill"
    _run(s, 4)
    assert not ball.alive
    destroy = _kind(s, "destroy")[0]
    assert destroy.step == 16  # applied right after frame 1's last step
    assert counts == [1, 1, 0, 0]


def test_when_validation() -> None:
    s = _scene()
    with pytest.raises(ConfigError, match="predicate"):
        s.when(True, [A.end_after(1.0)])  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="handlers"):
        s.when(lambda w: True, "nope")  # type: ignore[arg-type]


# --- subject validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("register", "name"),
    [
        (lambda s, h: s.every(1.0, h), "every"),
        (lambda s, h: s.at(1.0, h), "at"),
        (lambda s, h: s.when(lambda w: True, h), "when"),
    ],
)
def test_subject_targets_on_subjectless_rules_are_rejected(register: Any, name: str) -> None:
    s = _scene()
    for action in (A.destroy(), A.destroy(target="b"), A.split(), A.split(target="b")):
        with pytest.raises(ConfigError, match=name):
            register(s, [action])
    # Explicit handles are fine.
    register(s, [A.destroy(target=s.objects[1]), A.end_after(1.0)])


def test_b_target_on_escape_is_allowed_and_on_spawn_is_rejected() -> None:
    s = _scene()
    ring = s.objects[0]
    s.on_escape(ring, "ball", [A.destroy(target="b")])  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="on_spawn"):
        s.on_spawn("ball", [A.destroy(target="b")])


# --- end_after ------------------------------------------------------------------------


def _end_scene(duration: float = 5.0, **kw: Any) -> Scene:
    return _scene(duration=duration, **kw)


def test_end_after_shrinks_total_frames_frames_and_audio() -> None:
    s = _end_scene()
    assert s.total_frames == 300
    # Step 245 lies in frame 30 (steps 241..248).
    s.at(245 / RATE, [A.end_after(1.0)])
    frames = list(s.frames())
    assert s.total_frames == 91  # F = 31, + 60
    assert len(frames) == 91 and s.frame == 91
    assert s.audio_buffer().shape == (num_samples(91, 60), 2)


def test_earliest_end_wins() -> None:
    s = _end_scene()
    s.at(245 / RATE, [A.end_after(2.0), A.end_after(1.0)])
    s.at(250 / RATE, [lambda ctx, ev: ctx.end_after(3.0)])
    _run(s)
    assert s.total_frames == 91 and s.frame == 91
    t = _end_scene()
    t.at(245 / RATE, [A.end_after(1.0)])
    t.at(250 / RATE, [lambda ctx, ev: ctx.end_after(0.0)])  # frame 31 -> F = 32
    _run(t)
    assert t.total_frames == 32


def test_end_after_from_when_counts_from_the_completed_frame() -> None:
    s = _end_scene()
    s.when(lambda w: w.frame >= 10, [A.end_after(0.5)])
    list(s.frames())
    assert s.total_frames == 40 and s.frame == 40


def test_end_after_validation() -> None:
    for bad in (-0.1, math.nan, math.inf, "1", None):
        with pytest.raises(ConfigError, match="seconds"):
            A.end_after(bad)  # type: ignore[arg-type]
    s = _end_scene()
    hit: list[str] = []

    def cb(ctx: ActionContext, ev: Event) -> None:
        with pytest.raises(ConfigError, match="seconds"):
            ctx.end_after(-1.0)
        hit.append("ok")

    s.at(0.1, [cb])
    _run(s, 10)
    assert hit == ["ok"] and s.total_frames == 300


def test_preview_stops_at_the_new_end() -> None:
    def make() -> Scene:
        s = Scene(width=64, height=48, fps=30, duration=2.0, max_speed=1500)
        s.at(0.1, [A.end_after(0.2)])
        return s

    scene = run_preview(make, scale=1.0, max_frames=15)
    # 240 steps/s: step 24 lies in frame 2, so F = 3, plus round(0.2 * 30) = 6.
    assert scene.total_frames == scene.frame == 9


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def test_render_is_shortened_by_end_after(tmp_path: Path) -> None:
    s = Scene(width=64, height=64, fps=30, duration=3.0, max_speed=1000)
    s.at(0.5, [A.end_after(0.5), A.play(S.note("C5"))])
    out = s.render(tmp_path / "short.mp4")
    # 240 steps/s: step 120 lies in frame 14, so F = 15, plus round(0.5 * 30) = 15.
    assert s.total_frames == s.frame == 30
    assert abs(_duration(out) - s.total_frames / 30) < 0.08
