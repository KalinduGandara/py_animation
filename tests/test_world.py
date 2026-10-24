"""World behaviour tests: gravity, rings, balls, stepping (FR-002..FR-006, NFR-003)."""

import math
import random

import pytest

import bouncekit.scene as scene_mod
from bouncekit import Ball, CircleBoundary, ConfigError, Scene


def _small(**kw: object) -> Scene:
    opts: dict[str, object] = {"width": 200, "height": 200, "fps": 60, "duration": 1.0}
    opts.update(kw)
    return Scene(**opts)  # type: ignore[arg-type]


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --- Scene core -------------------------------------------------------------


def test_scene_defaults_and_config() -> None:
    s = Scene()
    c = s.config
    assert (c.width, c.height, c.fps, c.substeps, c.seed) == (1080, 1920, 60, 8, 0)
    assert c.duration == 60.0
    assert c.gravity == (0.0, 900.0)
    assert s.total_frames == 3600
    assert s.frame == 0
    assert s.time == 0.0


def test_scene_custom_config() -> None:
    s = Scene(width=100, height=50, fps=30, duration=2.5, seed=4, background="#123",
              gravity=(1, 2), substeps=3, max_speed=50)
    assert s.config.background == (0x11, 0x22, 0x33)
    assert s.config.substeps == 3
    assert s.total_frames == 75


def test_rng_seeded_from_seed() -> None:
    a, b = Scene(seed=42).rng, random.Random(42)
    assert [a.random() for _ in range(5)] == [b.random() for _ in range(5)]
    assert Scene(seed=1).rng.random() != Scene(seed=2).rng.random()


def test_overrides_applied_before_rng() -> None:
    scene_mod._overrides.update(seed=9, duration=0.5)
    try:
        s = Scene(seed=1, duration=10.0, fps=30)
    finally:
        scene_mod._overrides.clear()
    assert s.config.seed == 9
    assert s.config.duration == 0.5
    assert s.total_frames == 15
    assert s.rng.random() == random.Random(9).random()
    assert Scene(seed=1).config.seed == 1


def test_step_and_frame_counting() -> None:
    s = _small(fps=30, duration=1.0)
    assert s.total_frames == 30
    for i in range(1, 8):
        s.step_frame()
        assert s.frame == i
        assert s.time == pytest.approx(i / 30)


def test_object_registry_in_insertion_order() -> None:
    s = _small()
    r = s.add_circle(center=(100, 100), radius=80)
    b = s.add_ball(pos=(100, 100), radius=5)
    assert isinstance(r, CircleBoundary)
    assert isinstance(b, Ball)
    assert s.objects == (r, b)


# --- Gravity / stepping (FR-002, FR-005) -------------------------------------


def test_gravity_pulls_down_screen() -> None:
    s = _small(gravity=(0, 900))
    b = s.add_ball(pos=(100, 50), radius=5)
    y0 = b.position[1]
    s.step_frame()
    assert b.velocity[1] == pytest.approx(900 / 60)
    assert b.velocity[0] == pytest.approx(0)
    for _ in range(5):
        s.step_frame()
    assert b.position[1] > y0


def test_one_frame_is_substeps_fixed_steps() -> None:
    # pymunk integrates position (with the old velocity) before velocity in each step, so
    # after n steps from rest: y = sum_{k=0..n-1} k*g*dt^2 = g*dt^2*n(n-1)/2, v = n*g*dt.
    s = _small(fps=50, substeps=4, gravity=(0, 1000))
    b = s.add_ball(pos=(0, 0), radius=5)
    s.step_frame()
    dt = 1 / (50 * 4)
    assert b.position[1] == pytest.approx(1000 * dt * dt * 4 * 3 / 2)
    assert b.velocity[1] == pytest.approx(1000 * dt * 4)


# --- Ball (FR-004, FR-005 clamp) ----------------------------------------------


def test_ball_properties() -> None:
    s = _small()
    b = s.add_ball(pos=(10, 20), radius=7, velocity=(3, 4), color="#ff0000",
                   tags={"a", "b"}, elasticity=0.5)
    assert b.position == pytest.approx((10, 20))
    assert b.velocity == pytest.approx((3, 4))
    assert b.radius == 7
    assert b.color == (255, 0, 0)
    assert b.tags == frozenset({"a", "b"})
    assert b.shape.elasticity == 0.5
    assert b.shape.friction == 0
    assert b.body.mass == pytest.approx(math.pi * 49)
    b.position = (1, 2)
    b.velocity = (5, 6)
    assert b.position == pytest.approx((1, 2))
    assert b.velocity == pytest.approx((5, 6))


def test_speed_clamp_keeps_direction() -> None:
    s = _small(gravity=(0, 0))
    b = s.add_ball(pos=(100, 100), radius=5, velocity=(3000, 4000))  # |v| = 5000
    s.step_frame()
    vx, vy = b.velocity
    assert math.hypot(vx, vy) == pytest.approx(4000)
    assert vx / vy == pytest.approx(3 / 4)


def test_speed_clamp_under_gravity_uses_config() -> None:
    s = _small(gravity=(0, 900), max_speed=100)
    b = s.add_ball(pos=(100, 0), radius=5)
    for _ in range(60):
        s.step_frame()
        assert math.hypot(*b.velocity) <= 100 + 1e-9
    assert b.velocity[1] == pytest.approx(100)


# --- Ring (FR-003) ----------------------------------------------------------


def test_ring_properties_and_segments() -> None:
    s = _small()
    r = s.add_circle(center=(100, 100), radius=80, thickness=6, color="#0f0",
                     gap_degrees=0, segments=32, tags=["ring"])
    assert r.center == pytest.approx((100, 100))
    assert (r.radius, r.thickness, r.gap_degrees) == (80, 6, 0)
    assert r.color == (0, 255, 0)
    assert r.tags == frozenset({"ring"})
    assert r.angle_degrees == 0
    assert len(r.shapes) == 32
    assert all(seg.radius == pytest.approx(3) for seg in r.shapes)
    assert all(seg.friction == 0 for seg in r.shapes)
    assert r.body.body_type == r.body.KINEMATIC


def test_gap_removes_segments_around_zero_degrees() -> None:
    s = _small()
    r = s.add_circle(center=(0, 0), radius=100, gap_degrees=90, segments=8)
    # Midpoints at 22.5 + 45k degrees: 22.5 and -22.5 are within +-45.
    assert len(r.shapes) == 6
    for seg in r.shapes:
        mx, my = (seg.a + seg.b) / 2
        assert abs(math.degrees(math.atan2(my, mx))) > 45


def _bouncing_ball_scene(gap: float) -> tuple[Scene, Ball, CircleBoundary]:
    s = _small(gravity=(0, 0), duration=3.0)
    r = s.add_circle(center=(100, 100), radius=80, gap_degrees=gap)
    b = s.add_ball(pos=(100, 100), radius=8, velocity=(600, 0))
    return s, b, r


def test_closed_ring_contains_ball() -> None:
    s, b, r = _bouncing_ball_scene(0)
    bounced = False
    for _ in range(s.total_frames):
        s.step_frame()
        assert _dist(b.position, r.center) < r.radius
        bounced = bounced or b.velocity[0] < 0
    assert bounced
    # Elastic bounces keep the speed (Chipmunk adds a fraction of a percent at vertices).
    assert math.hypot(*b.velocity) == pytest.approx(600, rel=0.1)


def test_ball_escapes_through_gap() -> None:
    s, b, r = _bouncing_ball_scene(60)
    for _ in range(30):
        s.step_frame()
    assert _dist(b.position, r.center) > r.radius + r.thickness


def test_rotation_angle_after_n_frames() -> None:
    s = _small(fps=30)
    r = s.add_circle(center=(100, 100), radius=80, angular_velocity=90)
    for _ in range(15):
        s.step_frame()
    assert r.angle_degrees == pytest.approx(45)
    assert r.body.angle == pytest.approx(math.radians(45))  # positive = clockwise on screen


def test_rotating_gap_collisions_follow_rotation() -> None:
    # After 1 s at 90 deg/s the gap (initially +x) points down the screen (+y).
    s = _small(fps=30, gravity=(0, 900), duration=3.0, max_speed=2800)
    r = s.add_circle(center=(100, 100), radius=80, gap_degrees=60, angular_velocity=90)
    for _ in range(30):
        s.step_frame()
    r.body.angular_velocity = 0  # freeze the gap pointing down
    b = s.add_ball(pos=(100, 100), radius=8)
    for _ in range(30):
        s.step_frame()
    assert b.position[1] > r.center[1] + r.radius + r.thickness


def test_static_ring_with_gap_right_holds_falling_ball() -> None:
    s = _small(fps=30, gravity=(0, 900), duration=2.0, max_speed=2800)
    r = s.add_circle(center=(100, 100), radius=80, gap_degrees=60)
    b = s.add_ball(pos=(100, 100), radius=8)
    for _ in range(s.total_frames):
        s.step_frame()
        assert _dist(b.position, r.center) < r.radius


def test_seams_are_smooth() -> None:
    # A ball rolling along the inside of a ring (default 128 segments) under gravity, with
    # zero friction and elasticity 1, conserves energy and stays near the wall. Without
    # neighbour-joined seams it hops off the wall by ~10 px at the seams.
    s = _small(gravity=(0, 900), duration=4.0, fps=60)
    radius, thickness, ball_r = 80.0, 8.0, 8.0
    r = s.add_circle(center=(100, 100), radius=radius, thickness=thickness)
    contact = radius - thickness / 2 - ball_r
    b = s.add_ball(pos=(100, 100 + contact), radius=ball_r, velocity=(250, 0))

    def energy() -> float:
        return 0.5 * (b.velocity[0] ** 2 + b.velocity[1] ** 2) - 900 * b.position[1]

    e0 = energy()
    for _ in range(s.total_frames):
        s.step_frame()
        assert abs(_dist(b.position, r.center) - contact) < 4.0
        assert energy() == pytest.approx(e0, rel=0.01)


# --- No tunnelling (NFR-003) ------------------------------------------------


@pytest.mark.parametrize("angle", [0.0, 0.7, 2.1, 4.0])
def test_no_tunnelling_at_max_speed(angle: float) -> None:
    s = _small(width=400, height=400, gravity=(0, 900), duration=4.0)
    r = s.add_circle(center=(200, 200), radius=180, thickness=8)
    v = (4000 * math.cos(angle), 4000 * math.sin(angle))
    b = s.add_ball(pos=(200, 200), radius=5, velocity=v)
    for _ in range(s.total_frames):
        s.step_frame()
        assert _dist(b.position, r.center) < r.radius


@pytest.mark.parametrize("angle", [0.0, 0.7, 2.1, 4.0])
def test_speed_clamped_after_collisions_with_spinning_ring(angle: float) -> None:
    # Collision impulses are applied after velocity integration, so the clamp
    # must hold at every step boundary, not only in free flight (FR-005).
    s = _small(width=400, height=400, gravity=(0, 900), duration=2.0)
    s.add_circle(center=(200, 200), radius=180, thickness=8, angular_velocity=2000)
    v = (4000 * math.cos(angle), 4000 * math.sin(angle))
    b = s.add_ball(pos=(200, 200), radius=10, velocity=v)
    for _ in range(s.total_frames):
        s.step_frame()
        assert math.hypot(*b.velocity) <= s.config.max_speed * (1 + 1e-9)


@pytest.mark.parametrize("ring_first", [True, False])
def test_ball_too_thin_for_ring_at_max_speed_is_rejected(ring_first: bool) -> None:
    # Per-step travel at max_speed is 4000/480 = 8.33 px; ball radius 3 plus half
    # of an 8 px ring is only 7 px, so the ball could tunnel (NFR-003).
    s = _small(width=400, height=400)
    if ring_first:
        s.add_circle(center=(200, 200), radius=180, thickness=8)
        with pytest.raises(ConfigError, match="tunnel"):
            s.add_ball(pos=(200, 200), radius=3)
    else:
        s.add_ball(pos=(200, 200), radius=3)
        with pytest.raises(ConfigError, match="tunnel"):
            s.add_circle(center=(200, 200), radius=180, thickness=8)


def test_thin_ball_allowed_with_more_substeps() -> None:
    s = _small(width=400, height=400, substeps=16)
    s.add_circle(center=(200, 200), radius=180, thickness=8)
    s.add_ball(pos=(200, 200), radius=3)
