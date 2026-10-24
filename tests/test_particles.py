"""Impact particles: A.particles / ctx.particles, fx_rng bursts, frame-keyed advance (FR-305)."""

import math
import os
import random
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import ConfigError, EffectsConfig, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import colors as C  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402


def _scene(**kw: Any) -> Scene:
    opts: dict[str, Any] = {
        "width": 200,
        "height": 200,
        "fps": 30,
        "duration": 3.0,
        "seed": 7,
        "gravity": (0.0, 0.0),
        "max_speed": 2000.0,
    }
    opts.update(kw)
    return Scene(**opts)


def _ctx(s: Scene, a: Any = None) -> ActionContext:
    rate = s.config.fps * s.config.substeps
    ev = Event("timer", s._step, s.frame, s._step / rate, (), None, None)
    return ActionContext(s, ev, a, None)


def _expected(seed: int, n: int, speed: float) -> list[tuple[float, float]]:
    ref = random.Random(f"bouncekit-fx:{seed}")
    out = []
    for _ in range(n):
        phi = ref.uniform(0, 2 * math.pi)
        sp = speed * ref.uniform(0.4, 1.0)
        out.append((sp * math.cos(phi), sp * math.sin(phi)))
    return out


class Spy:
    def __init__(self, width: int, height: int) -> None:
        self.inner = PygameRenderer(width, height)
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.inner, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            return target(*args, **kwargs)

        return call

    def particle_calls(self) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        return [(a, k) for n, a, k in self.calls if n == "circle" and "alpha" in k]


def _collision_scene(**kw: Any) -> Scene:
    s = _scene(**kw)
    s.add_circle(center=(100, 100), radius=80, tags={"wall"})
    s.add_ball(pos=(100, 100), radius=8, velocity=(400, 0), color="#ff8800", tags={"ball"})
    return s


def _run_to_first_collision(s: Scene) -> Event:
    for _ in range(200):
        s.step_frame()
        hits = [e for e in s.events if e.kind == "collision"]
        if hits:
            return hits[0]
    raise AssertionError("no collision")


def test_collision_burst_at_contact_point_with_fx_rng_values() -> None:
    s = _collision_scene()
    s.on_collision("ball", "wall", [A.particles(count=8, speed=300.0)])
    ev = _run_to_first_collision(s)
    assert ev.frame == s.frame - 1
    parts = s._fx.particles
    assert len(parts) == 8
    assert all((p.x, p.y) == ev.position and p.age == 0 for p in parts)
    assert [(p.vx, p.vy) for p in parts] == _expected(7, 8, 300.0)
    assert all(p.color == (255, 136, 0) for p in parts)  # subject a's colour


def test_particles_drawn_from_next_frame_fade_and_expire() -> None:
    s = _collision_scene()
    s.on_collision("ball", "wall", [A.particles(count=4, lifetime=0.2)], cooldown=10.0)
    _run_to_first_collision(s)
    life = round(0.2 * 30)
    for age in range(life):
        spy = Spy(200, 200)
        s.draw(spy)
        calls = spy.particle_calls()
        assert len(calls) == 4
        assert all(k["alpha"] == pytest.approx(1 - age / life) for _, k in calls)
        s.step_frame()
    assert s._fx.particles == []
    spy = Spy(200, 200)
    s.draw(spy)
    assert spy.particle_calls() == []


def test_particles_drawn_after_objects_and_before_glow() -> None:
    s = _collision_scene()
    s.add_ball(pos=(30, 30), radius=6, glow=1.0)
    s.on_collision("ball", "wall", [A.particles(count=2)])
    _run_to_first_collision(s)
    spy = Spy(200, 200)
    s.draw(spy)
    names = [n for n, _, k in spy.calls]
    first_particle = next(i for i, (n, _, k) in enumerate(spy.calls) if "alpha" in k)
    assert names.index("glow") > first_particle
    assert names[first_particle - 1] == "circle"  # last object before particles


def test_particle_advance_is_independent_of_draw_calls() -> None:
    def run(draws: int) -> list[tuple[float, float, float, float, int]]:
        s = _collision_scene()
        s.on_collision("ball", "wall", [A.particles(count=6, drag=3.0, lifetime=1.0)])
        r = PygameRenderer(200, 200)
        for _ in range(40):
            for _ in range(draws):
                s.draw(r)
            s.step_frame()
        return [(p.x, p.y, p.vx, p.vy, p.age) for p in s._fx.particles]

    base = run(0)
    assert base
    assert run(1) == base
    assert run(3) == base


def test_advance_physics_of_one_particle() -> None:
    s = _scene()
    _ctx(s).particles(pos=(50, 60), count=1, speed=200.0, drag=2.0, lifetime=1.0)
    s.step_frame()
    (p,) = s._fx.particles
    vx0, vy0 = p.vx, p.vy
    s.step_frame()
    k = math.exp(-2.0 / 30)
    assert (p.vx, p.vy) == pytest.approx((vx0 * k, vy0 * k))
    assert (p.x, p.y) == pytest.approx((50 + vx0 * k / 30, 60 + vy0 * k / 30))
    assert p.age == 1


def test_capacity_truncates_burst_and_draws_rng_only_for_kept() -> None:
    s = _scene(effects=EffectsConfig(max_particles=5))
    _ctx(s).particles(pos=(10, 10), count=8, speed=100.0)
    assert len(s._fx.pending) == 5
    assert [(p.vx, p.vy) for p in s._fx.pending] == _expected(7, 5, 100.0)
    ref = random.Random("bouncekit-fx:7")
    for _ in range(10):
        ref.random()
    assert s.fx_rng.getstate() == ref.getstate()
    _ctx(s).particles(pos=(10, 10), count=3)
    assert len(s._fx.pending) == 5
    s.step_frame()
    assert len(s._fx.particles) == 5
    s2 = _scene(effects=EffectsConfig(max_particles=0))
    _ctx(s2).particles(pos=(10, 10))
    assert s2._fx.pending == []


def test_particles_respect_pair_cooldown() -> None:
    s = _collision_scene()
    s.on_collision("ball", "wall", [A.particles(count=3, lifetime=60.0)], cooldown=100.0)
    for _ in range(60):
        s.step_frame()
    assert sum(1 for e in s.events if e.kind == "collision") >= 2
    assert len(s._fx.particles) == 3


@pytest.mark.parametrize("method", ["every", "at", "when"])
def test_pos_none_on_timer_or_condition_rule_raises(method: str) -> None:
    s = _scene()
    arg: Any = (lambda sc: True) if method == "when" else 0.5
    with pytest.raises(ConfigError, match="pos") as info:
        getattr(s, method)(arg, [A.particles()])
    assert ("timer" if method != "when" else "condition") in str(info.value)
    getattr(s, method)(arg, [A.particles(pos=(10, 10))])  # explicit pos is fine


def test_timer_particles_with_pos_and_default_white() -> None:
    s = _scene()
    s.every(0.1, [A.particles(pos=(20, 30), count=2)])
    for _ in range(4):
        s.step_frame()
    assert len(s._fx.particles) == 2
    assert all(p.color == (255, 255, 255) for p in s._fx.particles)


def test_particle_colour_options() -> None:
    s = _scene()
    ball = s.add_ball(pos=(50, 50), radius=5, color="#123456")
    _ctx(s, ball).particles(pos=(0, 0), count=1)
    _ctx(s, ball).particles(pos=(0, 0), count=1, color="#ff0000")
    _ctx(s, ball).particles(pos=(0, 0), count=1, color=C.fixed("#00ff00"))
    _ctx(s, ball).particles(pos=(0, 0), count=1, color=C.by_speed(max_speed=100.0))
    assert [p.color for p in s._fx.pending] == [
        (0x12, 0x34, 0x56),
        (255, 0, 0),
        (0, 255, 0),
        C.parse_color("#2a6cff"),
    ]


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"count": 0}, "count"),
        ({"count": 501}, "count"),
        ({"count": 2.0}, "count"),
        ({"speed": 0}, "speed"),
        ({"lifetime": -1}, "lifetime"),
        ({"size": math.inf}, "size"),
        ({"drag": -0.1}, "drag"),
        ({"color": "nope"}, "colo"),
        ({"pos": (1, "x")}, "pos"),
    ],
)
def test_bad_particle_options_raise(kw: dict[str, Any], field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        A.particles(**kw)
    s = _scene()
    opts: dict[str, Any] = {"pos": (1, 1)}
    opts.update(kw)
    with pytest.raises(ConfigError, match=field):
        _ctx(s).particles(**opts)


def test_particles_never_touch_physics_rng_or_events() -> None:
    s = _collision_scene()
    s.on_collision("ball", "wall", [A.particles(count=20)])
    state = s.rng.getstate()
    for _ in range(40):
        s.step_frame()
    assert s._fx.particles
    assert s.rng.getstate() == state
    assert {e.kind for e in s.events} == {"collision"}
