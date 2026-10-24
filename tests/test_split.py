"""Split action, ball caps and runtime refusal (FR-205, FR-206, NFR-202)."""

import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480


def _ctx(s: Scene, a: Any = None) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / RATE, (), None, None)
    return ActionContext(s, ev, a, None)


def _free_scene(**kw: Any) -> tuple[Scene, Ball]:
    s = Scene(width=400, height=400, duration=3.0, gravity=(0, 0), max_speed=2000, **kw)
    ball = s.add_ball(
        pos=(200, 200), radius=10, velocity=(300, 0), color="#ff0000", tags={"ball", "x"}
    )
    return s, ball


def _spawns(s: Scene) -> list[Event]:
    return [e for e in s.events if e.kind == "spawn"]


def test_split_geometry_velocities_generation_and_handle() -> None:
    s, ball = _free_scene()
    A.split(into=3, spread_degrees=60, radius_scale=0.5).run(_ctx(s, ball))
    assert s.count() == 1  # queued, not applied during dispatch
    s._apply_commands()
    balls = s.objects
    assert len(balls) == 3 and balls[0] is ball  # parent is child 0
    r2 = 5.0
    for i, child in enumerate(balls):
        assert isinstance(child, Ball)
        phi = math.radians(-30 + 30 * i)
        vx, vy = child.velocity
        assert vx == pytest.approx(300 * math.cos(phi)) and vy == pytest.approx(300 * math.sin(phi))
        assert math.hypot(vx, vy) == pytest.approx(300)
        # theta = 0: children side by side along (-sin 0, cos 0) = (0, 1)
        assert child.position == pytest.approx((200, 200 + (i - 1) * (2 * r2 + 1)))
        assert child.radius == r2 and child.shape.radius == r2
        assert child.body.mass == pytest.approx(math.pi * r2**2)
        assert child.generation == 1
        assert child.color == (255, 0, 0) and child.tags == frozenset({"ball", "x"})
    spawns = _spawns(s)
    assert [e.objects for e in spawns] == [(balls[1],), (balls[2],)]  # parent emits none
    assert spawns[0].speed == pytest.approx(300) and spawns[0].position == balls[1].position


def test_add_ball_generation_zero_and_split_generations_accumulate() -> None:
    s, ball = _free_scene()
    assert ball.generation == 0
    _ctx(s).split(ball)
    s._apply_commands()
    _ctx(s).split(ball, into=2)
    s._apply_commands()
    assert ball.generation == 2
    assert [b.generation for b in s.objects] == [2, 1, 2]


def test_split_of_resting_ball_uses_theta_zero() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0))
    ball = s.add_ball(pos=(200, 200), radius=10)
    _ctx(s).split(ball, into=2)
    s._apply_commands()
    assert [b.velocity for b in s.objects] == [(0.0, 0.0), (0.0, 0.0)]
    assert [b.position for b in s.objects] == [(200, 189.5), (200, 210.5)]


def test_split_ring_target_is_noop() -> None:
    s = Scene(width=400, height=400)
    ring = s.add_circle(center=(200, 200), radius=150)
    A.split().run(_ctx(s, ring))
    _ctx(s).split(ring)  # type: ignore[arg-type]
    s._apply_commands()
    assert s.objects == (ring,) and s.events == ()


def test_split_bad_arguments_raise_at_construction() -> None:
    for kw in (
        {"into": 1},
        {"into": 2.0},
        {"into": True},
        {"spread_degrees": -1},
        {"spread_degrees": 361},
        {"spread_degrees": math.nan},
        {"radius_scale": 0},
        {"radius_scale": math.inf},
        {"max_total": 0},
        {"max_total": 1.5},
        {"target": "c"},
    ):
        with pytest.raises(ConfigError):
            A.split(**kw)
    s, ball = _free_scene()
    with pytest.raises(ConfigError, match="into"):
        _ctx(s).split(ball, into=0)
    with pytest.raises(ConfigError):
        _ctx(s).split("ball")  # type: ignore[arg-type]


def test_max_balls_config_and_add_ball_cap() -> None:
    assert Scene().config.max_balls == 1000
    for bad in (0, -1, 2.5, True):
        with pytest.raises(ConfigError, match="max_balls"):
            Scene(max_balls=bad)  # type: ignore[arg-type]
    s = Scene(width=400, height=400, max_balls=2)
    s.add_circle(center=(200, 200), radius=150)  # rings do not count
    s.add_ball(pos=(100, 200), radius=10)
    s.add_ball(pos=(300, 200), radius=10)
    with pytest.raises(ConfigError, match="max_balls"):
        s.add_ball(pos=(200, 200), radius=10)
    assert s.count() == 3 and len(s.space.bodies) == 3


def test_split_refused_when_cap_or_max_total_exceeded() -> None:
    s, ball = _free_scene(max_balls=4)
    _ctx(s).split(ball, into=3)
    s._apply_commands()
    assert s.count() == 3
    before = (ball.radius, ball.position, ball.velocity, ball.generation, len(s.events))
    _ctx(s).split(ball, into=3)  # 3 - 1 + 3 = 5 > 4
    s._apply_commands()
    assert s.count() == 3
    assert (ball.radius, ball.position, ball.velocity, ball.generation, len(s.events)) == before
    _ctx(s).split(ball, into=2, max_total=3)  # 4 > max_total
    s._apply_commands()
    assert s.count() == 3 and len(s.events) == before[-1]
    _ctx(s).split(ball, into=2, max_total=4)  # exactly at the limit: allowed
    s._apply_commands()
    assert s.count() == 4


def test_split_refused_on_tunnelling_and_render_continues() -> None:
    # max_speed 2000 at 480 steps/s moves 4.17 px/step; ring half-thickness 1.
    s = Scene(width=400, height=400, duration=1.0, max_speed=2000)
    s.add_circle(center=(200, 200), radius=150, thickness=2, tags={"wall"})
    ball = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    s.on_collision("ball", "wall", [A.split(into=2, radius_scale=0.25)])
    for _ in range(s.total_frames):
        s.step_frame()  # r' = 2.5: 2.5 + 1 < 4.17 -> refused, never raised
    assert any(e.kind == "collision" for e in s.events)
    assert s.objects[1:] == (ball,) and ball.radius == 10 and ball.generation == 0
    assert _spawns(s) == []


def test_split_on_wall_does_not_resplit_children_within_cooldown() -> None:
    # Children are placed clear of the wall (C16); after this grazing hit the
    # wall-side child (spread 60) heads back into the wall within the cooldown.
    s = Scene(width=400, height=400, duration=2.0, gravity=(0, 0), max_speed=2000)
    s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    s.add_ball(pos=(200, 320), radius=20, velocity=(150, 20), tags={"ball"})
    s.on_collision("ball", "wall", [A.split(into=2, spread_degrees=60), A.play(S.note("C5"))])
    while not _spawns(s):
        s.step_frame()
    first = _spawns(s)[0].step
    while s._step < first + round(0.05 * RATE):
        s.step_frame()
    walls = [e for e in s.events if e.kind == "collision" and e.step > first]
    assert walls  # the child touched the wall again right after the split ...
    assert s.count("ball") == 2  # ... but was not split again (inherited cooldown)
    assert len(s.triggers) == 1  # and played no extra note (inherited retrigger time)


def test_cascaded_split_events_reach_on_spawn_next_step() -> None:
    s, ball = _free_scene()
    seen: list[tuple[int, int, Any]] = []
    s.on_spawn("ball", [lambda ctx, obj, ev: seen.append((s._step, ev.step, obj))])
    _ctx(s).split(ball, into=2)
    s._apply_commands()
    s.step_frame()
    child = s.objects[1]
    assert seen == [(1, 0, child)]


def _ring_scene(ball_pos: tuple[float, float], velocity: tuple[float, float]) -> tuple[Scene, Ball]:
    s = Scene(duration=2.0, gravity=(0, 0), max_balls=4)
    s.add_circle(center=(540, 960), radius=450, thickness=8, tags={"wall"})
    ball = s.add_ball(pos=ball_pos, radius=18, velocity=velocity, tags={"ball"})
    return s, ball


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
def test_split_at_grazing_inner_wall_keeps_children_clear_of_the_wall(scale: float) -> None:
    # Ball touching the bottom of the ring from inside and moving along it: the
    # perpendicular offset points straight into the wall (C16 placement correction).
    s, ball = _ring_scene((540, 960 + 450 - 4 - 18 - 0.5), (500, 0))
    A.split(into=2, spread_degrees=10, radius_scale=scale).run(_ctx(s, ball))
    s._apply_commands()
    r2 = 18 * scale
    inner = 450 * math.cos(math.pi / 128) - 4  # chord midpoint of the inner surface
    balls = [b for b in s.objects if isinstance(b, Ball)]
    assert len(balls) == 2
    for b in balls:
        assert math.dist(b.position, (540, 960)) + r2 <= inner + 1e-6
    # the formation is only translated: spacing is unchanged
    assert math.dist(balls[0].position, balls[1].position) == pytest.approx(2 * r2 + 1)


def test_split_outside_ring_keeps_children_outside() -> None:
    s, ball = _ring_scene((540, 960 + 450 + 4 + 18 + 0.5), (500, 0))
    A.split(into=3, spread_degrees=10, radius_scale=1.25).run(_ctx(s, ball))
    s._apply_commands()
    for b in s.objects:
        if isinstance(b, Ball):
            assert math.dist(b.position, (540, 960)) - 22.5 >= 454 - 1e-6


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("deg", [5, 10, 20])
def test_grazing_split_children_stay_inside_closed_ring(scale: float, deg: int) -> None:
    rad = math.radians(deg)
    s, _ = _ring_scene((390, 1350), (500 * math.cos(rad), 500 * math.sin(rad)))
    s.on_collision("ball", "wall", [A.split(into=2, spread_degrees=10, radius_scale=scale)])
    while s.frame < s.total_frames:
        s.step_frame()
        for b in s.objects:
            if isinstance(b, Ball):
                assert math.dist(b.position, (540, 960)) + b.radius < 446 + 1.0
    assert any(e.kind == "spawn" for e in s.events)
