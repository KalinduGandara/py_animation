"""Collision event log and collision sound rules (FR-101, FR-104, NFR-101)."""

import math

import pymunk
import pytest

from bouncekit import Ball, CircleBoundary, ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.events import CollisionEvent

FPS, SUBSTEPS, G = 60, 8, 900.0
DT = 1.0 / (FPS * SUBSTEPS)


def _drop_scene(
    x_offset: float = 0.0,
    *,
    elasticity: float = 1.0,
    velocity: tuple[float, float] = (0.0, 0.0),
    y: float = 200.0,
    duration: float = 3.0,
) -> tuple[Scene, CircleBoundary, Ball]:
    s = Scene(
        width=400, height=400, fps=FPS, substeps=SUBSTEPS, duration=duration,
        gravity=(0, G), max_speed=2000,
    )  # fmt: skip
    ring = s.add_circle(
        center=(200, 200), radius=150, thickness=8, elasticity=elasticity, tags={"wall"}
    )
    ball = s.add_ball(
        pos=(200 + x_offset, y), radius=10, elasticity=elasticity, velocity=velocity,
        tags={"ball"},
    )  # fmt: skip
    return s, ring, ball


def _run(s: Scene, frames: int | None = None) -> None:
    for _ in range(s.total_frames if frames is None else frames):
        s.step_frame()


def _closest(p: tuple[float, float], ring: CircleBoundary) -> tuple[float, tuple[float, float]]:
    """Distance from ``p`` to the nearest ring segment centre line, and that point."""
    cx, cy = ring.center
    best = (math.inf, (0.0, 0.0))
    for seg in ring.shapes:
        ax, ay = seg.a.x + cx, seg.a.y + cy
        bx, by = seg.b.x + cx, seg.b.y + cy
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        q = (ax + t * dx, ay + t * dy)
        d = math.hypot(p[0] - q[0], p[1] - q[1])
        if d < best[0]:
            best = (d, q)
    return best


# --- Event recording (FR-101) -----------------------------------------------


@pytest.mark.parametrize("x_offset", [0.0, 30.0])
def test_drop_event_step_time_and_speed_are_analytic(x_offset: float) -> None:
    s, ring, ball = _drop_scene(x_offset)
    x0, y0 = ball.position
    reach = ball.radius + ring.thickness / 2
    # Chipmunk moves positions with the previous step's velocity, then detects
    # contacts, then integrates gravity: y_k = y0 + g dt^2 k (k - 1) / 2.
    k = 1
    while True:
        y = y0 + G * DT * DT * k * (k - 1) / 2
        d, q = _closest((x0, y), ring)
        if d < reach:
            break
        k += 1
    assert reach - d > 1e-3  # not a borderline case
    _run(s, 60)
    ev = s.events[0]
    assert isinstance(ev, CollisionEvent)
    assert ev.kind == "collision"
    assert ev.step == k
    assert ev.time == k / (FPS * SUBSTEPS)
    assert ev.frame == (k - 1) // SUBSTEPS
    assert set(ev.objects) == {ball, ring}
    normal_y = abs(q[1] - y) / d
    assert ev.speed == pytest.approx(G * DT * (k - 1) * normal_y, rel=1e-3)
    assert ev.position[1] == pytest.approx(q[1] - ring.thickness / 2 * normal_y, abs=1.0)


def test_one_event_per_seam_hit() -> None:
    # 128 segments: a vertex sits exactly at the bottom, so the ball lands on a seam
    # and touches two segments in the same step.
    s, ring, ball = _drop_scene(0.0)
    _run(s)
    steps = [e.step for e in s.events]
    assert len(steps) >= 2  # bounced back up and landed again
    assert all(b - a > 100 for a, b in zip(steps, steps[1:], strict=False))
    assert all(set(e.objects) == {ball, ring} for e in s.events)


def test_no_events_while_resting_after_settling() -> None:
    s, _, _ = _drop_scene(0.0, elasticity=0.0)
    _run(s)
    late = [e for e in s.events if e.time > 1.0]
    assert late == []
    assert len(s.events) >= 1


def test_no_events_while_rolling_across_seams() -> None:
    contact = 150 - 4 - 10
    s, _, ball = _drop_scene(0.0, elasticity=0.0, y=200 + contact, velocity=(300.0, 0.0))
    xs = []
    for _ in range(s.total_frames):
        s.step_frame()
        xs.append(ball.position[0])
    assert max(xs) - min(xs) > 40  # crossed several segments (each ~7 px)
    assert len(s.events) <= 1


def test_handler_never_mutates_the_space(monkeypatch: pytest.MonkeyPatch) -> None:
    s, _, ball = _drop_scene(0.0)

    def forbidden(_space: object, *args: object, **_k: object) -> None:
        # Space.step itself calls add()/remove() with no arguments to flush queues.
        if args:
            raise AssertionError("space mutated during simulation")

    for name in ("add", "remove", "add_post_step_callback", "reindex_shape", "reindex_static"):
        monkeypatch.setattr(pymunk.Space, name, forbidden)
    _run(s, 60)
    assert len(s.events) == 1
    assert ball.velocity[1] < 0  # the collision itself still happened (bounced)


def _rng_scene(seed: int) -> Scene:
    s = Scene(width=400, height=400, fps=30, duration=2.0, seed=seed, max_speed=2000)
    s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    for _ in range(3):
        v = (s.rng.uniform(-600, 600), s.rng.uniform(-600, 600))
        s.add_ball(pos=(200, 200), radius=10, velocity=v, tags={"ball"})
    s.on_collision("ball", "wall", [A.play(S.note("C5"))])
    s.on_collision("ball", "ball", [A.play(S.note(60), gain=0.5)])
    return s


def _event_key(s: Scene) -> list[tuple[object, ...]]:
    objs = s.objects
    return [
        (e.step, e.frame, e.time, e.speed, e.position, tuple(objs.index(o) for o in e.objects))
        for e in s.events
    ]


def test_same_seed_identical_events_and_audio() -> None:
    a, b = _rng_scene(3), _rng_scene(3)
    _run(a)
    _run(b)
    assert len(a.events) > 3
    assert _event_key(a) == _event_key(b)
    assert a.audio_buffer().tobytes() == b.audio_buffer().tobytes()


def test_different_seed_differs() -> None:
    a, b = _rng_scene(3), _rng_scene(4)
    _run(a)
    _run(b)
    assert _event_key(a) != _event_key(b)
    assert a.audio_buffer().tobytes() != b.audio_buffer().tobytes()


# --- Collision rules (FR-104) -----------------------------------------------


def test_rule_produces_trigger_per_matching_event() -> None:
    s, _, _ = _drop_scene(0.0)
    note = S.note("A4")
    s.on_collision("wall", "ball", [A.play(note, gain=0.7)])  # either order matches
    s.on_collision("ball", "nothing", [A.play(note)])
    assert s.has_sound
    _run(s)
    assert len(s.triggers) == len(s.events) >= 2
    for trig, ev in zip(s.triggers, s.events, strict=True):
        assert trig.step == ev.step
        assert trig.hz == pytest.approx(440.0)
        assert trig.voice == note.voice
        # FR-106 (T-103): play.gain scaled by the impact-speed curve.
        assert trig.gain == pytest.approx(0.7 * min(1.0, ev.speed / 1500.0) ** 0.5)
        assert trig.offset == round(ev.step * 48000 / (FPS * SUBSTEPS))


def test_rules_fire_in_registration_order() -> None:
    s, _, _ = _drop_scene(0.0)
    s.on_collision("ball", "wall", [A.play(S.note("C4")), A.play(S.note("E4"))])
    s.on_collision("ball", "wall", [A.play(S.note("G4"))])
    _run(s, 60)
    assert [round(t.hz) for t in s.triggers] == [262, 330, 392]


def test_scene_without_rules_has_no_sound() -> None:
    s, _, _ = _drop_scene(0.0)
    assert not s.has_sound
    _run(s, 60)
    assert s.triggers == ()
    assert len(s.events) == 1


@pytest.mark.parametrize(
    ("tag_a", "tag_b", "actions"),
    [
        ("ball", "wall", A.play(S.note("C4"))),  # not a list
        ("ball", "wall", ["play"]),
        ("ball", "wall", [A.play(S.note("C4")), object()]),
        ("ball", "wall", "abc"),
        ("", "wall", [A.play(S.note("C4"))]),
        ("ball", 3, [A.play(S.note("C4"))]),
        (None, "wall", [A.play(S.note("C4"))]),
    ],
)
def test_on_collision_rejects_bad_input(tag_a: object, tag_b: object, actions: object) -> None:
    s, _, _ = _drop_scene(0.0)
    with pytest.raises(ConfigError):
        s.on_collision(tag_a, tag_b, actions)  # type: ignore[arg-type]
