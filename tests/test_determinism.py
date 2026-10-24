"""Determinism: same seed gives identical frames; different seed differs (NFR-001)."""

import hashlib
import os
from typing import Any

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


def _effects_scene(seed: int, effects: bool = True) -> Scene:
    from bouncekit import EffectsConfig
    from bouncekit import actions as A
    from bouncekit import colors as C

    s = Scene(
        width=200,
        height=200,
        fps=30,
        duration=2.0,
        seed=seed,
        max_speed=2000,
        max_balls=24,
        effects=EffectsConfig(max_particles=150),
    )
    glow = 0.8 if effects else 0.0
    s.add_circle(center=(100, 100), radius=90, thickness=6, glow=glow, tags={"wall"})
    hue = C.hue_cycle(step=40)
    speed = C.by_speed(max_speed=800.0)
    for i in range(3):
        vx = s.rng.uniform(-400.0, 400.0)
        s.add_ball(
            pos=(70 + 30 * i, 80),
            radius=7,
            velocity=(vx, 150.0),
            color=(hue if i % 2 == 0 else speed) if effects else "#ffffff",
            trail=effects,
            glow=1.0 if effects else 0.0,
            tags={"ball"},
        )
    handlers: list[Any] = [A.split(into=2, spread_degrees=40, radius_scale=0.9, max_total=12)]
    if effects:
        handlers += [A.particles(count=10), A.flash()]
    s.on_collision("ball", "wall", handlers)
    return s


def test_effects_never_change_physics() -> None:
    from bouncekit.render.pygame_renderer import PygameRenderer

    on, off = _effects_scene(5, True), _effects_scene(5, False)
    r = PygameRenderer(200, 200)
    for _ in range(60):
        on.draw(r)
        on.step_frame()
        off.step_frame()
        assert [(b.position, b.velocity) for b in on._balls] == [
            (b.position, b.velocity) for b in off._balls
        ]
    keys = [(e.kind, e.step, e.speed, e.position) for e in on.events]
    assert keys == [(e.kind, e.step, e.speed, e.position) for e in off.events]
    assert on.rng.getstate() == off.rng.getstate()
    assert len(on._balls) > 3 and on._fx.particles


def _effects_hashes(seed: int) -> list[str]:
    return [hashlib.sha256(f).hexdigest() for f in _effects_scene(seed).frames()]


def test_effects_scene_is_deterministic_and_seed_dependent() -> None:
    a = _effects_hashes(5)
    assert a == _effects_hashes(5)
    b = _effects_hashes(6)
    assert a != b and a[-1] != b[-1]
