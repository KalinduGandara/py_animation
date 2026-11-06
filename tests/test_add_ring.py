"""Rings added at runtime by rules: ctx.add_circle (FR-501, NFR-202)."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import CircleBoundary, ConfigError, Scene  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480


def _ctx(s: Scene) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / RATE, (), None, None)
    return ActionContext(s, ev, None, None)


def _kinds(s: Scene, kind: str) -> list[Event]:
    return [e for e in s.events if e.kind == kind]


def test_add_circle_is_queued_then_added_with_spawn_event() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0))
    ring = _ctx(s).add_circle(center=(100, 100), radius=10, thickness=20, tags={"lump"})
    assert isinstance(ring, CircleBoundary)
    assert not ring.alive and s.count() == 0  # queued only
    s._apply_commands()
    assert ring.alive and s.objects == (ring,) and s.count("lump") == 1
    (ev,) = _kinds(s, "spawn")
    assert ev.objects == (ring,) and ev.speed == 0.0 and ev.position == (100, 100)


def test_runtime_ring_collides_and_fires_rules() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0))
    ball = s.add_ball(pos=(100, 200), radius=10, velocity=(400, 0), tags={"ball"})
    hits: list[object] = []
    s.on_collision("ball", "lump", [lambda ctx, a, b, ev: hits.append(b)])
    lump = _ctx(s).add_circle(center=(200, 200), radius=10, thickness=20, tags={"lump"})
    s._apply_commands()
    for _ in range(30):
        s.step_frame()
    assert hits and hits[0] is lump
    assert ball.velocity[0] < 0  # bounced back off the solid disc


def test_add_circle_refused_on_overlap_or_tunnelling_without_error() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0), max_speed=2000)
    s.add_ball(pos=(200, 200), radius=10)
    overlap = _ctx(s).add_circle(center=(215, 200), radius=5, thickness=10)
    thin = _ctx(s).add_circle(center=(200, 200), radius=150, thickness=2)  # 10 + 1 > 4.17 px/step
    tunnel = Scene(width=400, height=400, gravity=(0, 0), max_speed=2000)
    tunnel.add_ball(pos=(200, 200), radius=2)
    through = _ctx(tunnel).add_circle(center=(200, 200), radius=150, thickness=2)
    s._apply_commands()
    tunnel._apply_commands()
    assert not overlap.alive  # touches the ball
    assert thin.alive  # clear of the ball and thick enough for radius 10
    assert not through.alive and tunnel.count() == 1  # 2 + 1 < 4.17 px/step
    assert len(_kinds(s, "spawn")) == 1 and _kinds(tunnel, "spawn") == []
    _ctx(s).destroy(overlap)
    s._apply_commands()  # destroying a refused ring is a no-op
    assert s.count() == 2


def test_add_circle_bad_arguments_raise_at_call() -> None:
    ctx = _ctx(Scene())
    for kw in ({"radius": 0}, {"thickness": -1}, {"gap_degrees": 360}, {"center": (1,)}):
        with pytest.raises(ConfigError):
            ctx.add_circle(**{"center": (1, 2), "radius": 5, **kw})  # type: ignore[arg-type]


def test_scene_adding_rings_is_deterministic() -> None:
    def run() -> list[tuple[str, int]]:
        s = Scene(width=400, height=400, gravity=(0, 600), seed=3)
        s.add_circle(center=(200, 200), radius=180, thickness=10, tags={"wall"})
        s.add_ball(pos=(200, 120), radius=12, velocity=(170, 0), tags={"ball"})

        @s.on_collision("ball", "wall")
        def lump(ctx, ball, wall, ev):  # type: ignore[no-untyped-def]
            x, y = ev.position  # mirror the hit point: far from the ball, on the wall
            ctx.add_circle(center=(400 - x, 400 - y), radius=6, thickness=12, tags={"wall"})

        for _ in range(240):
            s.step_frame()
        assert s.count("wall") > 1
        return [(e.kind, e.step) for e in s.events]

    assert run() == run()
