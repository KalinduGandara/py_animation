"""Object actions: recolor, resize, set_velocity, flash (FR-210)."""

import math
import os
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480


def _ctx(s: Scene, a: Any = None, b: Any = None) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / RATE, (), None, None)
    return ActionContext(s, ev, a, b)


def _scene(**kw: Any) -> tuple[Scene, Ball]:
    opts: dict[str, Any] = {
        "width": 200,
        "height": 200,
        "duration": 2.0,
        "gravity": (0, 0),
        "max_speed": 2000,
        "background": "#000000",
    }
    opts.update(kw)
    s = Scene(**opts)
    ball = s.add_ball(
        pos=(100, 100), radius=10, velocity=(300, 400), color="#ff0000", tags={"ball"}
    )
    return s, ball


def _pixel(s: Scene, x: int, y: int) -> tuple[int, int, int]:
    r = PygameRenderer(s.config.width, s.config.height)
    s.draw(r)
    data = r.to_rgb_bytes()
    i = (y * s.config.width + x) * 3
    return (data[i], data[i + 1], data[i + 2])


# --- recolor ----------------------------------------------------------------


def test_recolor_changes_drawn_colour() -> None:
    s, ball = _scene()
    assert _pixel(s, 100, 100) == (255, 0, 0)
    A.recolor("#00ff00").run(_ctx(s, ball))
    assert ball.color == (255, 0, 0)  # queued only
    s._apply_commands()
    assert ball.color == (0, 255, 0)
    assert _pixel(s, 100, 100) == (0, 255, 0)


def test_recolor_callable_target_b_and_ring() -> None:
    s, ball = _scene()
    ring = s.add_circle(center=(100, 100), radius=80, thickness=8, color="#ffffff")
    A.recolor(lambda ctx: "#0000ff", target="b").run(_ctx(s, ball, ring))
    s._apply_commands()
    assert ring.color == (0, 0, 255)
    assert _pixel(s, 180, 100) == (0, 0, 255)


def test_ctx_recolor() -> None:
    s, ball = _scene()
    _ctx(s).recolor(ball, (1, 2, 3))
    s._apply_commands()
    assert ball.color == (1, 2, 3)
    with pytest.raises(ConfigError):
        _ctx(s).recolor(ball, "not-a-colour")
    with pytest.raises(ConfigError):
        _ctx(s).recolor("ball", "#ffffff")  # type: ignore[arg-type]


def test_recolor_validation() -> None:
    with pytest.raises(ConfigError):
        A.recolor("nope")
    with pytest.raises(ConfigError):
        A.recolor("#fff", target="c")  # type: ignore[arg-type]


# --- resize -----------------------------------------------------------------


def test_resize_radius_and_scale_update_mass_and_moment() -> None:
    s, ball = _scene()
    A.resize(radius=15).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.radius == 15 and ball.shape.radius == 15
    assert ball.body.mass == pytest.approx(math.pi * 225)
    assert ball.body.moment == pytest.approx(math.pi * 225 * 225 / 2)
    A.resize(scale=0.5).run(_ctx(s, ball))
    A.resize(scale=0.5).run(_ctx(s, ball))  # scale applies to the radius at apply time
    s._apply_commands()
    assert ball.radius == pytest.approx(3.75)
    _ctx(s).resize(ball, 8)
    s._apply_commands()
    assert ball.radius == 8 and ball.body.mass == pytest.approx(math.pi * 64)


def test_resize_refused_below_tunnelling_limit() -> None:
    s = Scene(width=1080, height=1920, duration=1.0)  # 4000 px/s at 480 Hz -> 8.33 px/step
    ring = s.add_circle(center=(540, 960), radius=400, thickness=8)
    ball = s.add_ball(pos=(540, 960), radius=10, tags={"ball"})
    A.resize(radius=4).run(_ctx(s, ball))  # 4 + 4 = 8 <= 8.33 -> could tunnel
    s._apply_commands()
    assert ball.radius == 10 and ball.shape.radius == 10
    A.resize(radius=5).run(_ctx(s, ball))  # 9 > 8.33 -> fine
    s._apply_commands()
    assert ball.radius == 5
    _ctx(s).resize(ring, 50)  # type: ignore[arg-type]  # ring: no-op
    A.resize(scale=2).run(_ctx(s, ring))
    s._apply_commands()
    assert ring.radius == 400


def test_resize_validation() -> None:
    with pytest.raises(ConfigError):
        A.resize()
    with pytest.raises(ConfigError):
        A.resize(radius=5, scale=2)
    with pytest.raises(ConfigError):
        A.resize(radius=-1)
    with pytest.raises(ConfigError):
        A.resize(scale=math.inf)
    s, ball = _scene()
    with pytest.raises(ConfigError):
        _ctx(s).resize(ball, 0)


# --- set_velocity -------------------------------------------------------------


def test_set_velocity_value_callable_and_speed() -> None:
    s, ball = _scene()
    A.set_velocity(velocity=(10, 20)).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.velocity == (10, 20)
    A.set_velocity(velocity=lambda ctx: (ctx.time, -5)).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.velocity == (0, -5)
    A.set_velocity(speed=50).run(_ctx(s, ball))  # keep direction
    s._apply_commands()
    assert ball.velocity == pytest.approx((0, -50))
    _ctx(s).set_velocity(ball, (3, 4))
    s._apply_commands()
    assert ball.velocity == (3, 4)


def test_set_velocity_clamps_to_max_speed() -> None:
    s, ball = _scene()
    A.set_velocity(velocity=(3000, 4000)).run(_ctx(s, ball))
    s._apply_commands()
    assert math.hypot(*ball.velocity) == pytest.approx(2000)
    A.set_velocity(speed=1e6).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.velocity == pytest.approx((1200, 1600))


def test_set_velocity_updates_constant_speed_target() -> None:
    s = Scene(width=200, height=200, duration=1.0, gravity=(0, 0), max_speed=2000)
    ball = s.add_ball(pos=(100, 100), radius=10, velocity=(300, 0), constant_speed=True)
    assert ball.target_speed == 300
    A.set_velocity(speed=500).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.target_speed == pytest.approx(500)
    A.set_velocity(velocity=(0, 5000)).run(_ctx(s, ball))
    s._apply_commands()
    assert ball.target_speed == pytest.approx(2000)
    s.step_frame()
    assert math.hypot(*ball.velocity) == pytest.approx(2000)


def test_set_velocity_validation_and_ring_noop() -> None:
    with pytest.raises(ConfigError):
        A.set_velocity()
    with pytest.raises(ConfigError):
        A.set_velocity(velocity=(1, 2), speed=3)
    with pytest.raises(ConfigError):
        A.set_velocity(speed=-1)
    with pytest.raises(ConfigError):
        A.set_velocity(velocity=(math.nan, 0))
    s, ball = _scene()
    with pytest.raises(ConfigError):
        A.set_velocity(velocity=lambda ctx: "fast").run(_ctx(s, ball))
    ring = s.add_circle(center=(100, 100), radius=80, thickness=8)
    A.set_velocity(velocity=(5, 5)).run(_ctx(s, ring))
    _ctx(s).set_velocity(ring, (5, 5))  # type: ignore[arg-type]
    s._apply_commands()
    assert ring.body.velocity == (0, 0)


# --- flash -------------------------------------------------------------------


def test_flash_draws_flash_colour_then_fades_back() -> None:
    s, ball = _scene(fps=30)
    ball.velocity = (0, 0)
    s.step_frame()  # frame 0 done
    assert _pixel(s, 100, 100) == (255, 0, 0)
    # Queue during a frame: like a rule firing mid-frame.
    s._in_frame = True
    A.flash(seconds=0.1, color="#0000ff").run(_ctx(s, ball))  # round(0.1 * 30) = 3 frames
    s._apply_commands()
    s._in_frame = False
    s.frame += 1  # the frame completes
    seen = []
    for _ in range(4):
        seen.append(_pixel(s, 100, 100))
        s.frame += 1
    assert seen[0] == (0, 0, 255)
    # linear blend from flash to base over 3 frames
    assert seen[1] == (round(255 / 3), 0, round(255 * 2 / 3))
    assert seen[2] == (round(255 * 2 / 3), 0, round(255 / 3))
    assert seen[3] == (255, 0, 0)


def test_flash_frame_count_minimum_one_and_ring_target() -> None:
    s, ball = _scene(fps=30)
    ring = s.add_circle(center=(100, 100), radius=80, thickness=8, color="#00ff00")
    _ctx(s).flash(ring, seconds=0.0, color="#ff00ff")
    s._apply_commands()  # outside a frame: next drawn frame is the current one
    assert _pixel(s, 180, 100) == (255, 0, 255)
    s.frame += 1
    assert _pixel(s, 180, 100) == (0, 255, 0)


def test_flash_validation() -> None:
    with pytest.raises(ConfigError):
        A.flash(seconds=-1)
    with pytest.raises(ConfigError):
        A.flash(color="bad")
    with pytest.raises(ConfigError):
        A.flash(target=3)  # type: ignore[arg-type]


def _flash_run(flash: bool) -> list[tuple[float, ...]]:
    s = Scene(width=400, height=400, duration=1.0, seed=3)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    s.add_ball(pos=(200, 150), radius=10, velocity=(250, -100), tags={"ball"})
    s.add_ball(pos=(170, 220), radius=12, velocity=(-150, 80), tags={"ball"})
    handlers: list[Any] = [A.flash(ring, seconds=0.2), A.flash(seconds=0.1)] if flash else []
    handlers.append(A.recolor(lambda ctx: (ctx.rng.randrange(256), 0, 0)))
    s.on_collision("ball", "wall", handlers)
    states: list[tuple[float, ...]] = []
    renderer = PygameRenderer(400, 400)
    for _ in range(40):
        s.draw(renderer)
        s.step_frame()
        for b in s.objects:
            if isinstance(b, Ball):
                states.append((*b.position, *b.velocity, *b.color))
    assert any(e.kind == "collision" for e in s.events)
    return states


def test_flash_does_not_change_physics() -> None:
    assert _flash_run(True) == _flash_run(False)
