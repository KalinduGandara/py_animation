"""Escape detection and on_escape rules (FR-201, FR-202, FR-208)."""

import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, CircleBoundary, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480
SPEED = 300.0  # px/s along +x, straight out through the gap (centred on +x)


def _scene(gap: float = 60.0, **ball: Any) -> tuple[Scene, CircleBoundary, Ball]:
    s = Scene(width=400, height=400, duration=2.0, gravity=(0.0, 0.0), max_speed=2000)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, gap_degrees=gap, tags={"wall"})
    opts: dict[str, Any] = {"pos": (200, 200), "radius": 10, "velocity": (SPEED, 0.0)}
    opts.update(ball)
    ball_obj = s.add_ball(tags={"ball"}, **opts)
    return s, ring, ball_obj


def _first_escape_step(margin: float) -> int:
    """First step whose post-step centre distance exceeds the escape threshold (no forces)."""
    threshold = 150 + 8 / 2 + 10 + margin
    k = 0
    while True:
        k += 1
        if SPEED * k / RATE > threshold:
            return k


def _escapes(s: Scene) -> list[Event]:
    return [e for e in s.events if e.kind == "escape"]


@pytest.mark.parametrize("margin", [0.0, 5.0])
def test_one_escape_event_at_first_step_past_threshold(margin: float) -> None:
    s, ring, ball = _scene()
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: None], margin=margin)
    for _ in range(s.total_frames):
        s.step_frame()
    escapes = _escapes(s)
    assert len(escapes) == 1
    ev = escapes[0]
    k = _first_escape_step(margin)
    assert ev.step == k
    assert ev.frame == (k - 1) // 8
    assert ev.time == k / RATE
    assert ev.objects == (ring, ball)
    assert ev.speed == pytest.approx(SPEED)
    assert ev.position is not None
    assert ev.position[0] == pytest.approx(200 + SPEED * k / RATE)
    assert ev.position[1] == pytest.approx(200)


def test_closed_ring_never_escapes() -> None:
    s, ring, _ = _scene(gap=0.0)
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: None])
    for _ in range(s.total_frames):
        s.step_frame()
    assert _escapes(s) == []


def test_untagged_ball_and_ring_without_rules_are_not_checked() -> None:
    s, ring, _ = _scene()
    s.add_ball(pos=(200, 200), radius=10, velocity=(-SPEED, 0.0), tags={"other"})
    other = s.add_circle(center=(200, 200), radius=170, thickness=8, gap_degrees=90)
    s.on_escape(ring, "nobody", [lambda ctx, b, r, ev: None])
    for _ in range(s.total_frames):
        s.step_frame()
    assert other.alive and _escapes(s) == []


def test_escape_rule_receives_ball_then_ring() -> None:
    s, ring, ball = _scene()
    seen: list[tuple[Any, ...]] = []

    @s.on_escape(ring, "ball")
    def on_out(ctx: ActionContext, b: Ball, r: CircleBoundary, ev: Event) -> None:
        seen.append((ctx.a, ctx.b, b, r, ev, ctx.event))

    assert on_out.__name__ == "on_out"  # decorator returns the function
    for _ in range(s.total_frames):
        s.step_frame()
    assert len(seen) == 1
    a, bsub, b, r, ev, ctx_ev = seen[0]
    assert (a, bsub, b, r) == (ball, ring, ball, ring)
    assert ev is ctx_ev and ev.kind == "escape"


def test_escape_destroy_removes_the_ball_in_the_same_step() -> None:
    s, ring, ball = _scene()
    s.on_escape(ring, "ball", [A.destroy()])
    for _ in range(s.total_frames):
        s.step_frame()
    destroys = [e for e in s.events if e.kind == "destroy"]
    assert not ball.alive and len(destroys) == 1
    assert destroys[0].step == _escapes(s)[0].step


def test_escape_rules_match_their_ring() -> None:
    s, ring, ball = _scene()
    outer = s.add_circle(center=(200, 200), radius=190, thickness=8, gap_degrees=0)
    hits: list[CircleBoundary] = []
    s.on_escape(outer, "ball", [lambda ctx, b, r, ev: hits.append(r)])
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: hits.append(r)])
    for _ in range(s.total_frames):
        s.step_frame()
    assert hits == [ring]  # the closed outer ring keeps the ball in
    assert [e.objects for e in _escapes(s)] == [(ring, ball)]


def test_escape_rules_run_in_registration_order() -> None:
    s, ring, _ = _scene()
    hits: list[str] = []
    s.on_escape(ring, "other", [lambda ctx, b, r, ev: hits.append("other")])
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: hits.append("first")])
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: hits.append("second")])
    for _ in range(s.total_frames):
        s.step_frame()
    assert hits == ["first", "second"]
    assert len(_escapes(s)) == 1


def test_a_ball_spawned_outside_escapes_once_at_the_next_step() -> None:
    s, ring, _ = _scene(gap=0.0, velocity=(0.0, 0.0))
    s.on_escape(ring, "ball", [lambda ctx, b, r, ev: None])
    far = s.add_ball(pos=(380, 380), radius=5, tags={"ball"})
    s.step_frame()
    s.step_frame()
    escapes = _escapes(s)
    assert len(escapes) == 1 and escapes[0].objects == (ring, far) and escapes[0].step == 1


def test_on_escape_validation() -> None:
    s, ring, _ = _scene()
    with pytest.raises(ConfigError, match="ring"):
        s.on_escape("ring", "ball", [A.destroy()])  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="tag"):
        s.on_escape(ring, "", [A.destroy()])
    with pytest.raises(ConfigError, match="margin"):
        s.on_escape(ring, "ball", [A.destroy()], margin=-1.0)
    with pytest.raises(ConfigError, match="margin"):
        s.on_escape(ring, "ball", [A.destroy()], margin=math.inf)
    with pytest.raises(ConfigError, match="handlers"):
        s.on_escape(ring, "ball", A.destroy())  # type: ignore[arg-type]
    # Both subjects exist on an escape rule.
    s.on_escape(ring, "ball", [A.destroy(target="b")])
