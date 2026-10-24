"""Constant speed and the automatic spatial hash (FR-212)."""

import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402


def _ctx(s: Scene, a: Any = None) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / 480, (), None, None)
    return ActionContext(s, ev, a, None)


def test_constant_speed_ball_keeps_speed_every_step_for_5s() -> None:
    s = Scene(width=1080, height=1920, duration=5.0, substeps=8)
    s.add_circle(center=(540, 960), radius=450, thickness=8, tags={"wall"})
    ball = s.add_ball(
        pos=(540, 700), radius=20, velocity=(300, 0), constant_speed=True, tags={"ball"}
    )
    assert ball.constant_speed and ball.target_speed == 300
    speeds: list[float] = []
    original = s.space.step

    def spy(dt: float) -> None:  # the speed left by the previous step's fix-up
        speeds.append(math.hypot(*ball.velocity))
        original(dt)

    s.space.step = spy  # type: ignore[method-assign]
    for _ in range(s.total_frames):
        s.step_frame()
    speeds.append(math.hypot(*ball.velocity))
    assert len(speeds) == 5 * 480 + 1
    assert any(e.kind == "collision" for e in s.events)  # it bounced
    for v in speeds:
        assert abs(v - 300) <= 1e-9


def test_plain_ball_speed_changes_under_gravity() -> None:
    s = Scene(width=400, height=400, duration=1.0)
    ball = s.add_ball(pos=(200, 100), radius=10, velocity=(300, 0))
    assert not ball.constant_speed
    s.step_frame()
    assert math.hypot(*ball.velocity) > 300


def test_constant_speed_zero_velocity_stays_zero() -> None:
    s = Scene(width=400, height=400, duration=1.0, gravity=(0, 0))
    ball = s.add_ball(pos=(200, 100), radius=10, velocity=(300, 0), constant_speed=True)
    ball.velocity = (0, 0)
    s.step_frame()
    assert ball.velocity == (0, 0)


def test_constant_speed_invalid_initial_speed_raises() -> None:
    s = Scene(width=400, height=400, duration=1.0, max_speed=1000)
    with pytest.raises(ConfigError, match="constant_speed"):
        s.add_ball(pos=(200, 100), radius=10, constant_speed=True)
    with pytest.raises(ConfigError, match="constant_speed"):
        s.add_ball(pos=(200, 100), radius=10, velocity=(1000, 1), constant_speed=True)
    s.add_ball(pos=(200, 100), radius=10, velocity=(1000, 0), constant_speed=True)  # = max: ok
    with pytest.raises(ConfigError):
        A.spawn(pos=(1, 1), radius=5, constant_speed=True)  # zero speed
    with pytest.raises(ConfigError):
        _ctx(s).spawn(pos=(1, 1), radius=5, velocity=(2000, 0), constant_speed=True)


def test_spawn_and_split_carry_constant_speed() -> None:
    s = Scene(width=400, height=400, duration=1.0, gravity=(0, 0), max_speed=2000)
    _ctx(s).spawn(pos=(100, 100), radius=5, velocity=lambda ctx: (0, 250), constant_speed=True)
    A.spawn(pos=(300, 100), radius=5, velocity=(30, 40)).run(_ctx(s))
    s._apply_commands()
    a, b = s.objects
    assert isinstance(a, Ball) and isinstance(b, Ball)
    assert a.constant_speed and a.target_speed == 250
    assert not b.constant_speed
    a.velocity = (0, 100)  # off target: split uses the target speed, not |v|
    A.split(into=2, spread_degrees=90).run(_ctx(s, a))
    s._apply_commands()
    child = s.objects[-1]
    assert isinstance(child, Ball)
    assert child.constant_speed and child.target_speed == 250
    assert math.hypot(*a.velocity) == pytest.approx(250)
    assert math.hypot(*child.velocity) == pytest.approx(250)


# --- spatial hash --------------------------------------------------------------


def test_spatial_hash_switches_once_at_100_balls(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Scene(width=1080, height=1920, duration=2.0, gravity=(0, 0), max_balls=300)
    calls: list[tuple[float, int]] = []
    monkeypatch.setattr(s.space, "use_spatial_hash", lambda dim, count: calls.append((dim, count)))
    for i in range(98):
        s.add_ball(pos=(40 + (i % 20) * 50, 100 + (i // 20) * 50), radius=10, tags={"ball"})
    s.add_ball(pos=(500, 1500), radius=12, tags={"ball"})  # 99 balls
    s.step_frame()
    assert calls == []
    A.spawn(pos=(500, 1700), radius=7).run(_ctx(s))  # the 100th, applied in a step
    s._apply_commands()
    assert calls == []  # switches after command application inside a step
    s.step_frame()
    assert calls == [(24.0, 10_000)]
    A.spawn(pos=(700, 1700), radius=30).run(_ctx(s))
    s._apply_commands()
    for _ in range(3):
        s.step_frame()
    assert calls == [(24.0, 10_000)]  # exactly once, never again


def test_spatial_hash_not_used_below_100(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Scene(width=400, height=400, duration=1.0, gravity=(0, 0))
    calls: list[object] = []
    monkeypatch.setattr(s.space, "use_spatial_hash", lambda *a: calls.append(a))
    for i in range(5):
        s.add_ball(pos=(50 + i * 60, 200), radius=10)
    for _ in range(3):
        s.step_frame()
    assert calls == []
