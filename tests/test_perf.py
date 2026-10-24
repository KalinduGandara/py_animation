"""Render-cost benchmark (NFR-303): loose bound only, the median is printed."""

import os
import statistics
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Scene  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402


def _trail_glow_scene() -> Scene:
    s = Scene(duration=5.0, seed=1, background="#07070d", gravity=(0, 300))
    s.add_circle(center=(540, 960), radius=480, color="#e8e8ff", glow=0.6, tags={"wall"})
    for i in range(100):
        row, col = divmod(i, 10)
        s.add_ball(
            pos=(330 + 42 * col, 760 + 42 * row),
            radius=14,
            velocity=(s.rng.uniform(-400, 400), s.rng.uniform(-400, 400)),
            color=(80 + (i * 37) % 176, 80 + (i * 91) % 176, 255),
            trail=True,
            glow=1.0,
            tags={"ball"},
        )
    return s


def test_trail_glow_render_cost() -> None:
    s = _trail_glow_scene()
    r = PygameRenderer(s.config.width, s.config.height)
    for _ in range(3):  # warm up and let trails build
        s.draw(r)
        r.to_rgb_bytes()
        s.step_frame()
    times = []
    for _ in range(8):
        t0 = time.perf_counter()
        s.draw(r)
        r.to_rgb_bytes()
        times.append((time.perf_counter() - t0) * 1000)
        s.step_frame()
    median = statistics.median(times)
    print(f"\nNFR-303 trail+glow scene (100 balls, ring): median {median:.1f} ms/frame")
    assert median < 250


def test_full_effects_scene_render_cost() -> None:
    from bouncekit import actions as A

    s = _trail_glow_scene()
    s.every(1 / 60, [A.particles(pos=(540, 960), count=10, lifetime=0.5)])
    for _ in range(30):  # fill ~300 live particles
        s.step_frame()
    assert 250 <= len(s._fx.particles) <= 350
    r = PygameRenderer(s.config.width, s.config.height)
    for _ in range(3):
        s.draw(r)
        r.to_rgb_bytes()
        s.step_frame()
    times = []
    for _ in range(8):
        t0 = time.perf_counter()
        s.draw(r)
        r.to_rgb_bytes()
        times.append((time.perf_counter() - t0) * 1000)
        s.step_frame()
    median = statistics.median(times)
    n = len(s._fx.particles)
    print(
        f"\nNFR-303 full scene (100 trail+glow balls, ring, {n} particles): {median:.1f} ms/frame"
    )
    assert median < 250
