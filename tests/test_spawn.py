"""Spawn action, spawn events, on_spawn and cascades (FR-202, FR-205, FR-207, NFR-202)."""

import math
import os
import random
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480


def _ctx(s: Scene) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / RATE, (), None, None)
    return ActionContext(s, ev, None, None)


def _spawns(s: Scene) -> list[Event]:
    return [e for e in s.events if e.kind == "spawn"]


def test_spawn_values_offsets_and_events() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0))
    _ctx(s).spawn(
        pos=(200, 100), radius=10, velocity=(30, 40), count=3, color="#00ff00", tags=("p",)
    )
    assert s.count() == 0  # queued only
    s._apply_commands()
    balls = s.objects
    assert [b.position for b in balls] == [(179, 100), (200, 100), (221, 100)]
    for b in balls:
        assert isinstance(b, Ball)
        assert b.radius == 10 and b.velocity == (30, 40) and b.color == (0, 255, 0)
        assert b.tags == frozenset({"p"}) and b.generation == 0
    spawns = _spawns(s)
    assert [e.objects for e in spawns] == [(b,) for b in balls]
    assert all(e.speed == 50 and e.step == 0 for e in spawns)
    assert [e.position for e in spawns] == [b.position for b in balls]


def test_spawn_callables_consume_rng_in_ball_order_during_dispatch() -> None:
    s = Scene(width=400, height=400, seed=7, gravity=(0, 400), max_speed=2000)
    s.add_circle(center=(200, 200), radius=150, tags={"wall"})
    s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    counts: list[int] = []

    def vel(ctx: ActionContext) -> tuple[float, float]:
        counts.append(ctx.scene.count())  # evaluated during dispatch, before apply
        return (ctx.rng.uniform(-100, 100), ctx.rng.uniform(-100, 100))

    s.on_collision(
        "ball",
        "wall",
        [
            A.spawn(
                pos=lambda ctx: (200.0, 150.0),
                radius=5,
                velocity=vel,
                count=3,
                color=lambda ctx: "#123456",
                tags=("p",),
            )
        ],
    )
    while s.count("p") == 0:
        s.step_frame()
    assert counts == [2, 2, 2]
    ref = random.Random(7)
    expected = [(ref.uniform(-100, 100), ref.uniform(-100, 100)) for _ in range(3)]
    spawned = [e.objects[0] for e in _spawns(s)]
    assert [e.speed for e in _spawns(s)] == pytest.approx([math.hypot(*v) for v in expected])
    assert all(isinstance(b, Ball) and b.color == (0x12, 0x34, 0x56) for b in spawned)


def test_spawn_refused_on_cap_max_total_and_tunnelling() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0), max_balls=3, max_speed=2000)
    s.add_circle(center=(200, 200), radius=150, thickness=2)
    s.add_ball(pos=(200, 200), radius=10)
    _ctx(s).spawn(pos=(100, 200), radius=10, count=3)  # 4 > max_balls
    _ctx(s).spawn(pos=(100, 200), radius=10, count=2, max_total=2)  # 3 > max_total
    _ctx(s).spawn(pos=(100, 200), radius=2)  # 2 + 1 < 4.17 px/step: would tunnel
    s._apply_commands()  # all refused, no exception
    assert s.count() == 2 and _spawns(s) == []
    _ctx(s).spawn(pos=(100, 200), radius=10, count=2)  # exactly max_balls
    s._apply_commands()
    assert s.count() == 4 and len(_spawns(s)) == 2


def test_spawn_bad_arguments_raise_at_construction() -> None:
    good: dict[str, Any] = {"pos": (1, 2), "radius": 5}
    for kw in (
        {"radius": 0},
        {"radius": math.inf},
        {"pos": (1,)},
        {"pos": "x"},
        {"velocity": (1, math.nan)},
        {"count": 0},
        {"count": 1.0},
        {"color": "nope"},
        {"tags": "ball"},
        {"elasticity": -1},
        {"max_total": 0},
    ):
        with pytest.raises(ConfigError):
            A.spawn(**{**good, **kw})
    with pytest.raises(ConfigError, match="count"):
        _ctx(Scene()).spawn(pos=(1, 2), radius=5, count=-1)


def test_spawn_callable_bad_result_raises_at_dispatch() -> None:
    s = Scene()
    with pytest.raises(ConfigError, match="velocity"):
        _ctx(s).spawn(pos=(1, 2), radius=5, velocity=lambda ctx: "fast")


def test_on_spawn_chain_grows_one_level_per_step() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0), substeps=8)
    s.on_spawn(
        "ball",
        [A.spawn(pos=lambda ctx: (10.0 + 12 * ctx.scene.count(), 50.0), radius=5, max_total=30)],
    )
    _ctx(s).spawn(pos=(10, 50), radius=5)
    s._apply_commands()
    assert s.count() == 1
    s.step_frame()
    assert s.count() == 9  # one new ball per step, not an unbounded same-step loop
    assert [e.step for e in _spawns(s)] == list(range(9))
    for _ in range(5):
        s.step_frame()
    assert s.count() == 30  # max_total stops the chain without an error


def test_on_spawn_registration_and_subjects() -> None:
    s = Scene()
    with pytest.raises(ConfigError, match="tag"):
        s.on_spawn("", [A.destroy()])
    with pytest.raises(ConfigError, match="on_spawn"):
        s.on_spawn("ball", [A.destroy(target="b")])
    with pytest.raises(ConfigError, match="on_spawn"):
        s.on_spawn("ball", [A.split(target="b")])
    seen: list[Any] = []

    @s.on_spawn("ball")
    def f(ctx: ActionContext, obj: Any, ev: Event) -> None:
        seen.append((ctx.a is obj, ctx.b, ev.kind))

    _ctx(s).spawn(pos=(100, 100), radius=5)
    s._apply_commands()
    s.step_frame()
    assert seen == [(True, None, "spawn")]
