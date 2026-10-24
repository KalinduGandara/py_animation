"""Rendering tests: renderer primitives, scene drawing, frames (FR-008, NFR-004)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402
from bouncekit.render.base import Renderer  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
BG = (10, 20, 30)


def _pixel(data: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    i = (y * width + x) * 3
    return (data[i], data[i + 1], data[i + 2])


def _scene(**kw: object) -> Scene:
    opts: dict[str, object] = {
        "width": 200,
        "height": 200,
        "fps": 30,
        "duration": 0.5,
        "background": BG,
        "gravity": (0.0, 0.0),
    }
    opts.update(kw)
    return Scene(**opts)  # type: ignore[arg-type]


# --- PygameRenderer primitives ---------------------------------------------


def test_renderer_satisfies_protocol() -> None:
    r: Renderer = PygameRenderer(40, 20)
    assert isinstance(r, Renderer)
    assert (r.width, r.height) == (40, 20)


def test_clear_fills_frame_and_size() -> None:
    r = PygameRenderer(40, 20)
    r.clear(BG)
    data = r.to_rgb_bytes()
    assert len(data) == 40 * 20 * 3
    assert data == bytes(BG) * (40 * 20)


def test_circle_fills_inside_only() -> None:
    r = PygameRenderer(100, 100)
    r.clear(BG)
    r.circle((50.0, 50.0), 20.0, RED)
    data = r.to_rgb_bytes()
    assert _pixel(data, 100, 50, 50) == RED
    assert _pixel(data, 100, 50 + 15, 50) == RED
    assert _pixel(data, 100, 50 + 25, 50) == BG
    assert _pixel(data, 100, 2, 2) == BG


def test_thick_line_has_width_and_round_caps() -> None:
    r = PygameRenderer(100, 100)
    r.clear(BG)
    r.thick_line((20.0, 50.0), (80.0, 50.0), 10.0, GREEN)
    data = r.to_rgb_bytes()
    assert _pixel(data, 100, 50, 50) == GREEN
    assert _pixel(data, 100, 50, 47) == GREEN  # within half width
    assert _pixel(data, 100, 50, 58) == BG  # outside half width
    assert _pixel(data, 100, 17, 50) == GREEN  # round cap beyond endpoint
    assert _pixel(data, 100, 10, 50) == BG


# --- Scene drawing ----------------------------------------------------------


def test_scene_draw_background_ball_and_ring() -> None:
    s = _scene()
    s.add_circle(center=(100, 100), radius=80, thickness=8, color=GREEN)
    s.add_ball(pos=(100, 100), radius=10, color=RED)
    r = PygameRenderer(200, 200)
    s.draw(r)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 2, 2) == BG
    assert _pixel(data, 200, 100, 100) == RED
    for x, y in [(180, 100), (20, 100), (100, 20), (100, 180)]:
        assert _pixel(data, 200, x, y) == GREEN, (x, y)
    assert _pixel(data, 200, 140, 100) == BG


def test_scene_draw_shows_gap() -> None:
    s = _scene()
    s.add_circle(center=(100, 100), radius=80, thickness=8, color=GREEN, gap_degrees=60)
    r = PygameRenderer(200, 200)
    s.draw(r)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 180, 100) == BG  # gap centred on +x
    assert _pixel(data, 200, 20, 100) == GREEN


def test_scene_draw_follows_rotation() -> None:
    # 90 deg/s clockwise for 1 s moves the gap from +x to +y (down on screen).
    s = _scene(duration=1.0)
    ring = s.add_circle(center=(100, 100), radius=80, thickness=8, color=GREEN,
                        gap_degrees=60, angular_velocity=90)
    for _ in range(30):
        s.step_frame()
    assert abs(ring.angle_degrees - 90) < 1e-6
    r = PygameRenderer(200, 200)
    s.draw(r)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 100, 180) == BG
    assert _pixel(data, 200, 180, 100) == GREEN


def test_draw_order_is_insertion_order() -> None:
    s = _scene()
    s.add_ball(pos=(100, 100), radius=20, color=RED)
    s.add_ball(pos=(100, 100), radius=10, color=BLUE)
    r = PygameRenderer(200, 200)
    s.draw(r)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 100, 100) == BLUE
    assert _pixel(data, 200, 115, 100) == RED


# --- frames() ---------------------------------------------------------------


def test_frames_yields_total_frames_of_right_size() -> None:
    s = _scene(width=60, height=40, fps=10, duration=0.5)
    frames = list(s.frames())
    assert len(frames) == s.total_frames == 5
    assert all(len(f) == 60 * 40 * 3 for f in frames)
    assert s.frame == 5


def test_frames_first_frame_is_initial_state_then_steps() -> None:
    s = _scene(gravity=(0.0, 900.0))
    ball = s.add_ball(pos=(100, 50), radius=10, color=RED)
    gen = s.frames()
    first = next(gen)
    assert s.frame == 0
    r = PygameRenderer(200, 200)
    s.draw(r)
    assert first == r.to_rgb_bytes()
    next(gen)
    assert s.frame == 1
    assert ball.position[1] > 50
    later = [next(gen) for _ in range(5)][-1]  # ball has fallen ~12 px by now
    assert later != first


# --- NFR-004: rendering does not change physics ----------------------------


def _physics_scene() -> Scene:
    s = _scene(duration=1.0, gravity=(0.0, 900.0))
    s.add_circle(center=(100, 100), radius=80, color=GREEN, gap_degrees=40,
                 angular_velocity=45)
    s.add_ball(pos=(100, 80), radius=8, velocity=(300.0, -100.0), color=RED)
    return s


def _state(s: Scene) -> list[tuple[float, ...]]:
    out: list[tuple[float, ...]] = []
    for obj in s.objects:
        b = obj.body
        out.append((*b.position, *b.velocity, b.angle, b.angular_velocity))
    return out


def test_rendering_does_not_mutate_physics() -> None:
    drawn = _physics_scene()
    plain = _physics_scene()
    for _ in drawn.frames():
        pass
    for _ in range(plain.total_frames):
        plain.step_frame()
    assert drawn.frame == plain.frame
    assert _state(drawn) == _state(plain)


def test_draw_alone_leaves_state_unchanged() -> None:
    s = _physics_scene()
    for _ in range(5):
        s.step_frame()
    before = _state(s)
    r = PygameRenderer(200, 200)
    s.draw(r)
    s.draw(r)
    assert _state(s) == before
    assert s.frame == 5
