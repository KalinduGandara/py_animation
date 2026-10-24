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
