"""Determinism: same seed gives identical frames; different seed differs (NFR-001)."""

import hashlib
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402


def _make_scene(seed: int) -> Scene:
    s = Scene(
        width=270, height=480, fps=30, duration=2.0, seed=seed, background="#101018", max_speed=3000
    )
    s.add_circle(
        center=(135, 240),
        radius=120,
        thickness=6,
        color="#ffffff",
        gap_degrees=30,
        angular_velocity=60,
    )
    vx = s.rng.uniform(-600.0, 600.0)
    vy = s.rng.uniform(-600.0, 600.0)
    s.add_ball(pos=(135, 200), radius=10, velocity=(vx, vy), color="#ff4060")
    return s


def _hashes(seed: int) -> list[str]:
    return [hashlib.sha256(f).hexdigest() for f in _make_scene(seed).frames()]


def test_same_seed_gives_identical_frame_hashes() -> None:
    a = _hashes(1)
    b = _hashes(1)
    assert len(a) == 60
    assert a == b


def test_different_seed_gives_different_frame_hashes() -> None:
    a = _hashes(1)
    b = _hashes(2)
    assert a[-1] != b[-1]
    assert a != b


def _split_scene(seed: int) -> Scene:
    from bouncekit import actions as A
    from bouncekit import sound as S

    s = Scene(width=200, height=200, fps=30, duration=2.0, seed=seed, max_speed=2000, max_balls=24)
    s.add_circle(center=(100, 100), radius=90, thickness=6, tags={"wall"})
    vx = s.rng.uniform(-400.0, 400.0)
    s.add_ball(pos=(100, 80), radius=8, velocity=(vx, 200.0), tags={"ball"})
    s.on_collision(
        "ball",
        "wall",
        [A.split(into=2, spread_degrees=40, radius_scale=0.9), A.play(S.scale("C4"))],
    )
    return s


def _split_run(seed: int) -> tuple[list[str], bytes, list[tuple[object, ...]]]:
    s = _split_scene(seed)
    hashes = [hashlib.sha256(f).hexdigest() for f in s.frames()]
    index = s._indices
    keys = [
        (e.kind, e.step, tuple(index[o] for o in e.objects), e.speed, e.position) for e in s.events
    ]
    return hashes, s.audio_buffer().tobytes(), keys


def test_split_scene_is_deterministic_and_seed_dependent() -> None:
    a = _split_run(3)
    b = _split_run(3)
    assert any(k[0] == "spawn" for k in a[2])
    assert a == b
    c = _split_run(4)
    assert c[0] != a[0] and c[1] != a[1] and c[2] != a[2]
