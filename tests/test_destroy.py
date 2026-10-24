"""Destroy action, destroy events, on_destroy, count and live objects (FR-202, FR-203, FR-207)."""

import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, CircleBoundary, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480


def _scene(**kw: Any) -> tuple[Scene, CircleBoundary, Ball]:
    s = Scene(width=400, height=400, duration=3.0, max_speed=2000, **kw)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    ball = s.add_ball(pos=(200, 200), radius=10, color="#ff0000", tags={"ball"})
    return s, ring, ball


def _run_until(s: Scene, done: Any, max_frames: int = 120) -> None:
    for _ in range(max_frames):
        s.step_frame()
        if done():
            return
    raise AssertionError("condition never met")


def _pixel(s: Scene, pos: tuple[float, float]) -> tuple[int, int, int]:
    r = PygameRenderer(s.config.width, s.config.height)
    s.draw(r)
    data = r.to_rgb_bytes()
    i = (round(pos[1]) * s.config.width + round(pos[0])) * 3
    return (data[i], data[i + 1], data[i + 2])


def test_destroy_ball_removes_it_everywhere_and_logs_one_event() -> None:
    s, ring, ball = _scene()
    speeds: list[float] = []
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: speeds.append(math.hypot(*a.velocity))])
    s.on_collision("ball", "wall", [A.destroy()])
    _run_until(s, lambda: not ball.alive)
    pos = ball.position
    assert ball not in s.objects and s.objects == (ring,)
    assert ball.body not in s.space.bodies and ball.shape not in s.space.shapes
    destroys = [e for e in s.events if e.kind == "destroy"]
    assert len(destroys) == 1
    ev = destroys[0]
    assert ev.objects == (ball,) and ev.position == pos
    assert ev.speed == pytest.approx(math.hypot(*ball.velocity))
    assert ev.time == ev.step / RATE and ev.frame == s.frame - 1
    assert _pixel(s, pos) == (0, 0, 0)  # no longer drawn
    for _ in range(10):
        s.step_frame()  # simulation continues without it
    assert [e.kind for e in s.events].count("destroy") == 1


def test_drawn_before_destroy() -> None:
    s, _, ball = _scene()
    assert _pixel(s, ball.position) == (255, 0, 0)


def test_destroy_ring_ends_its_contacts() -> None:
    s = Scene(width=400, height=400, duration=3.0, max_speed=2000)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, elasticity=0.0, tags={"wall"})
    ball = s.add_ball(pos=(200, 300), radius=10, elasticity=0.0, tags={"ball"})
    s.on_collision("ball", "wall", [A.destroy(target="b")])
    _run_until(s, lambda: not ring.alive)
    ev = s.events[-1]
    assert ev.kind == "destroy" and ev.objects == (ring,)
    assert ev.speed == 0.0 and ev.position == ring.center
    assert s.objects == (ball,) and s.count("wall") == 0
    assert all(sh not in s.space.shapes for sh in ring.shapes)
    assert s._recorder._contacts == {}
    for _ in range(60):
        s.step_frame()
    assert ball.position[1] > 400  # fell through where the ring was


def test_destroy_explicit_target_object() -> None:
    s, ring, ball = _scene()
    other = s.add_ball(pos=(100, 120), radius=10, velocity=(0, 0), tags={"other"})
    s.on_collision("ball", "wall", [A.destroy(target=other)])
    _run_until(s, lambda: not other.alive)
    assert ball.alive and other not in s.objects


def test_commands_on_dead_objects_are_skipped() -> None:
    s, ring, ball = _scene()
    s.on_collision("ball", "wall", [A.destroy(), A.destroy()])
    s.on_collision(
        "ball", "wall", [lambda ctx, a, b, ev: ctx.destroy(a), lambda ctx, a, b, ev: ctx.destroy(a)]
    )
    _run_until(s, lambda: not ball.alive)
    for _ in range(5):
        s.step_frame()
    assert [e.kind for e in s.events] == ["collision", "destroy"]


def test_destroy_event_dispatches_to_on_destroy_at_next_step() -> None:
    s, ring, ball = _scene()
    s.on_collision("ball", "wall", [A.destroy()])
    got: list[tuple[Any, ...]] = []

    @s.on_destroy("ball")
    def gone(ctx: ActionContext, obj: Any, event: Event) -> None:
        got.append((obj, event, s._step, ctx.a, ctx.b))

    s.on_destroy("wall", [lambda ctx, obj, ev: got.append(("wall",))])
    _run_until(s, lambda: bool(got), max_frames=120)
    obj, event, step_at_call, a, b = got[0]
    assert obj is ball and a is ball and b is None
    assert event.kind == "destroy" and step_at_call == event.step + 1
    assert len(got) == 1


def test_destroy_event_cascade_crosses_frame_boundary() -> None:
    # A destroy applied in a frame's last step is dispatched in the next frame's first step.
    s, ring, ball = _scene()
    seen: list[int] = []
    s.on_destroy("ball", [lambda ctx, obj, ev: seen.append(s._step)])
    for _ in range(3):
        s.step_frame()
    ctx = ActionContext(s, _timer_event(s), None, None)
    ctx.destroy(ball)
    s._apply_commands()
    destroy = s.events[-1]
    assert destroy.kind == "destroy" and not seen
    s.step_frame()
    assert seen == [destroy.step + 1]


def _timer_event(s: Scene) -> Event:
    return Event(
        kind="timer", step=s._step, frame=s.frame, time=s._step / RATE, objects=(), speed=None,
        position=None,
    )  # fmt: skip


def test_play_on_destroy_event_uses_ball_speed() -> None:
    s, ring, ball = _scene()
    s.on_collision("ball", "wall", [A.destroy()])
    s.on_destroy("ball", [A.play(S.note("C5"))])
    _run_until(s, lambda: bool(s.triggers))
    destroy = next(e for e in s.events if e.kind == "destroy")
    assert s.triggers[0].step == destroy.step
    assert destroy.speed is not None
    assert s.triggers[0].gain == pytest.approx(min(1.0, destroy.speed / 1500.0) ** 0.5)


# --- count, live objects, indices ----------------------------------------------------


def test_count_and_live_objects_in_insertion_order() -> None:
    s, ring, ball = _scene()
    b2 = s.add_ball(pos=(150, 200), radius=10, tags={"ball", "red"})
    b3 = s.add_ball(pos=(250, 200), radius=10, tags={"red"})
    assert s.count() == 4 and s.count("ball") == 2 and s.count("red") == 2
    assert s.count("nothing") == 0
    s.on_collision("red", "wall", [A.destroy()])
    _run_until(s, lambda: not b2.alive)
    assert not b3.alive  # falls in the same step as b2
    assert s.objects == (ring, ball) and s.count() == 2 and s.count("red") == 0
    assert ball.alive and ring.alive


def test_object_indices_are_monotonic() -> None:
    s, ring, ball = _scene()
    s.on_collision("ball", "wall", [A.destroy()])
    _run_until(s, lambda: not ball.alive)
    new = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    assert s._recorder.owners[new.shape][0] == 2
    _run_until(s, lambda: not new.alive)
    assert [e.kind for e in s.events].count("destroy") == 2


# --- Validation -------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["c", "", 3, None, ("a",)])
def test_destroy_bad_target(target: object) -> None:
    with pytest.raises(ConfigError, match="target"):
        A.destroy(target=target)  # type: ignore[arg-type]


def test_b_target_on_destroy_rule_is_rejected() -> None:
    s, _, _ = _scene()
    with pytest.raises(ConfigError, match="on_destroy"):
        s.on_destroy("ball", [A.destroy(target="b")])
    s.on_destroy("ball", [A.destroy(target="a")])
    s.on_collision("ball", "wall", [A.destroy(target="b")])


@pytest.mark.parametrize(
    ("tag", "handlers"),
    [("", []), (None, []), ("ball", "x"), ("ball", [object()]), ("ball", A.destroy())],
)
def test_on_destroy_validation(tag: object, handlers: object) -> None:
    s, _, _ = _scene()
    with pytest.raises(ConfigError):
        s.on_destroy(tag, handlers)  # type: ignore[arg-type]


def test_ctx_destroy_rejects_non_objects() -> None:
    s, ring, ball = _scene()
    ctx = ActionContext(s, _timer_event(s), None, None)
    with pytest.raises(ConfigError):
        ctx.destroy(42)  # type: ignore[arg-type]
