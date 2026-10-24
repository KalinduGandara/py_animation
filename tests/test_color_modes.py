"""Colour modes: fixed, hue_cycle, by_speed, by_generation, hsv (FR-306)."""

import colorsys
import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import colors as C  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402


def _scene(**kw: Any) -> Scene:
    opts: dict[str, Any] = {
        "width": 400,
        "height": 400,
        "fps": 30,
        "duration": 2.0,
        "gravity": (0.0, 0.0),
        "max_speed": 3000.0,
    }
    opts.update(kw)
    return Scene(**opts)


def _ctx(s: Scene, a: Any = None) -> ActionContext:
    rate = s.config.fps * s.config.substeps
    ev = Event("timer", s._step, s.frame, s._step / rate, (), None, None)
    return ActionContext(s, ev, a, None)


def _balls(s: Scene) -> list[Ball]:
    return [o for o in s.objects if isinstance(o, Ball)]


# --- constructors -------------------------------------------------------------


def test_hsv_matches_colorsys() -> None:
    for h, sat, v in [(0, 0.75, 1.0), (120, 1, 1), (250, 0.3, 0.6), (400, 1, 0.5)]:
        expected = tuple(round(255 * x) for x in colorsys.hsv_to_rgb((h % 360) / 360, sat, v))
        assert C.hsv(h, sat, v) == expected
    assert C.hsv(-120, 1, 1) == C.hsv(240, 1, 1)


def test_mode_constructors_and_identity() -> None:
    assert C.fixed("#ff0000").color == (255, 0, 0)
    h = C.hue_cycle()
    assert (h.start, h.step, h.saturation, h.value) == (0.0, 20.0, 0.75, 1.0)
    b = C.by_speed()
    assert (b.slow, b.fast, b.max_speed) == (C.parse_color("#2a6cff"), (255, 59, 107), 2000.0)
    g = C.by_generation()
    assert len(g.colors) == 6
    assert C.by_generation("#f00", (0, 0, 255)).colors == ((255, 0, 0), (0, 0, 255))
    assert C.hue_cycle() != C.hue_cycle()  # identity-compared
    hash(h)


@pytest.mark.parametrize(
    ("call", "field"),
    [
        (lambda: C.hue_cycle(start=math.nan), "start"),
        (lambda: C.hue_cycle(step="x"), "step"),
        (lambda: C.hue_cycle(saturation=1.5), "saturation"),
        (lambda: C.hue_cycle(value=-0.1), "value"),
        (lambda: C.by_speed(max_speed=0), "max_speed"),
        (lambda: C.by_speed(slow="bad"), "slow"),
        (lambda: C.by_speed(fast=(1, 2)), "fast"),
        (lambda: C.by_generation("#f00", "bad"), "colors"),
        (lambda: C.fixed("bad"), "color"),
        (lambda: C.hsv(0, 2, 1), "s"),
    ],
)
def test_bad_mode_arguments_raise_naming_them(call: Any, field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        call()


# --- hue cycle ----------------------------------------------------------------


def test_hue_cycle_gives_red_green_blue_to_successive_balls() -> None:
    s = _scene()
    mode = C.hue_cycle(start=0, step=120)
    balls = [s.add_ball(pos=(50 + 60 * i, 50), radius=5, color=mode) for i in range(3)]
    colors = [b.color for b in balls]
    assert colors == [C.hsv(0, 0.75, 1), C.hsv(120, 0.75, 1), C.hsv(240, 0.75, 1)]
    assert [max(range(3), key=lambda k, c=c: c[k]) for c in colors] == [0, 1, 2]
    assert all(b.color_mode is None and b.hue_mode is mode for b in balls)


def test_fixed_behaves_like_the_colour() -> None:
    s = _scene()
    b = s.add_ball(pos=(50, 50), radius=5, color=C.fixed("#102030"))
    assert b.color == (16, 32, 48) and b.color_mode is None and b.hue_mode is None


def test_hue_cycle_continues_across_split_and_spawn_and_refusals() -> None:
    s = _scene(max_balls=5)
    mode = C.hue_cycle(start=0, step=30)
    parent = s.add_ball(pos=(200, 200), radius=8, velocity=(100, 0), color=mode)  # k0
    A.split(into=3).run(_ctx(s, parent))
    s._apply_commands()  # children k1, k2; parent keeps k0
    assert [b.color for b in _balls(s)] == [C.hsv(h, 0.75, 1) for h in (0, 30, 60)]
    _ctx(s).spawn(pos=(50, 50), radius=5, color=mode)  # k3
    s._apply_commands()
    assert _balls(s)[-1].color == C.hsv(90, 0.75, 1)
    A.split(into=3).run(_ctx(s, parent))  # 4 + 2 > 5: refused
    _ctx(s).spawn(pos=(50, 300), radius=5, count=2, color=mode)  # refused
    s._apply_commands()
    assert len(_balls(s)) == 4
    A.split(into=2).run(_ctx(s, _balls(s)[1]))  # child of a hue ball: k4
    s._apply_commands()
    assert _balls(s)[-1].color == C.hsv(120, 0.75, 1)


def test_hue_counter_is_per_mode_instance_per_scene() -> None:
    m1, m2 = C.hue_cycle(step=10), C.hue_cycle(step=10)
    s = _scene()
    s.add_ball(pos=(50, 50), radius=5, color=m1)
    b = s.add_ball(pos=(80, 50), radius=5, color=m2)
    assert b.color == C.hsv(0, 0.75, 1)
    other = _scene()
    assert other.add_ball(pos=(50, 50), radius=5, color=m1).color == C.hsv(0, 0.75, 1)


def test_spawn_with_callable_returning_mode() -> None:
    s = _scene()
    mode = C.hue_cycle(start=0, step=60)
    A.spawn(pos=(100, 100), radius=5, count=2, color=lambda ctx: mode).run(_ctx(s))
    s._apply_commands()
    assert [b.color for b in _balls(s)] == [C.hsv(0, 0.75, 1), C.hsv(60, 0.75, 1)]


# --- dynamic modes ------------------------------------------------------------


def test_by_speed_colour_at_zero_half_and_max() -> None:
    s = _scene()
    mode = C.by_speed(slow=(0, 100, 200), fast=(255, 0, 51), max_speed=1000.0)
    b = s.add_ball(pos=(200, 200), radius=5, color=mode)
    assert b.color_mode is mode
    assert b.color == (0, 100, 200)
    b.velocity = (300, 400)  # |v| = 500
    assert b.color == (round(127.5), 50, round(125.5))
    b.velocity = (1000, 0)
    assert b.color == (255, 0, 51)
    b.velocity = (0, 2500)
    assert b.color == (255, 0, 51)


def test_by_speed_is_drawn_with_the_current_velocity() -> None:
    s = _scene()
    mode = C.by_speed(slow="#000000", fast="#ffffff", max_speed=100.0)
    s.add_ball(pos=(200, 200), radius=10, velocity=(100, 0), color=mode)
    r = PygameRenderer(400, 400)
    s.draw(r)
    data = r.to_rgb_bytes()
    i = (200 * 400 + 200) * 3
    assert tuple(data[i : i + 3]) == (255, 255, 255)


def test_by_generation_cycles_with_generation() -> None:
    s = _scene()
    mode = C.by_generation("#ff0000", "#00ff00", "#0000ff")
    b = s.add_ball(pos=(200, 200), radius=5, velocity=(50, 0), color=mode)
    assert b.color == (255, 0, 0)
    seen = []
    for g in range(5):
        b.generation = g
        seen.append(b.color)
    assert seen == [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 0), (0, 255, 0)]
    b.generation = 0
    A.split(into=2).run(_ctx(s, b))
    s._apply_commands()
    assert all(x.color_mode is mode and x.color == (0, 255, 0) for x in _balls(s))


def test_spawn_inherits_dynamic_mode() -> None:
    s = _scene()
    mode = C.by_speed(max_speed=100.0)
    _ctx(s).spawn(pos=(100, 100), radius=5, velocity=(500, 0), color=mode)
    s._apply_commands()
    (b,) = _balls(s)
    assert b.color_mode is mode and b.color == (255, 59, 107)


# --- recolor ------------------------------------------------------------------


def test_recolor_with_modes() -> None:
    s = _scene()
    b = s.add_ball(pos=(200, 200), radius=5, color="#ffffff")
    speed = C.by_speed(max_speed=100.0)
    A.recolor(speed).run(_ctx(s, b))
    s._apply_commands()
    assert b.color_mode is speed and b.color == C.parse_color("#2a6cff")
    hue = C.hue_cycle(start=0, step=90)
    s.add_ball(pos=(50, 50), radius=5, color=hue)  # k0
    A.recolor(hue).run(_ctx(s, b))  # k1
    s._apply_commands()
    assert b.color_mode is None and b.hue_mode is hue and b.color == C.hsv(90, 0.75, 1)
    _ctx(s).recolor(b, "#010203")
    s._apply_commands()
    assert b.color == (1, 2, 3) and b.color_mode is None and b.hue_mode is None
    _ctx(s).recolor(b, C.fixed("#040506"))
    s._apply_commands()
    assert b.color == (4, 5, 6)
    b.color = "#070809"
    assert b.color == (7, 8, 9)


def test_ring_accepts_only_plain_or_fixed_colours() -> None:
    s = _scene()
    ring = s.add_circle(center=(200, 200), radius=100, color=C.fixed("#ff0000"))
    assert ring.color == (255, 0, 0)
    for mode in (C.hue_cycle(), C.by_speed(), C.by_generation()):
        with pytest.raises(ConfigError, match="color"):
            s.add_circle(center=(200, 200), radius=150, color=mode)  # type: ignore[arg-type]
        with pytest.raises(ConfigError, match="color"):
            _ctx(s).recolor(ring, mode)
    _ctx(s).recolor(ring, C.fixed("#00ff00"))
    s._apply_commands()
    assert ring.color == (0, 255, 0)


def test_add_ball_rejects_non_colours() -> None:
    s = _scene()
    with pytest.raises(ConfigError):
        s.add_ball(pos=(50, 50), radius=5, color=42)  # type: ignore[arg-type]


def test_colour_modes_never_touch_scene_rng() -> None:
    s = _scene(max_balls=40, max_speed=1500.0)
    s.add_circle(center=(200, 200), radius=150, tags={"wall"})
    hue = C.hue_cycle()
    s.add_ball(pos=(200, 150), radius=6, velocity=(300, 200), color=hue, tags={"ball"})
    s.add_ball(pos=(200, 250), radius=6, velocity=(-200, 300), color=C.by_speed(), tags={"ball"})
    s.on_collision("ball", "wall", [A.split(max_total=20), A.recolor(C.by_generation())])
    state = s.rng.getstate()
    r = PygameRenderer(400, 400)
    for _ in range(40):
        s.draw(r)
        s.step_frame()
    assert len(_balls(s)) > 2
    assert s.rng.getstate() == state
