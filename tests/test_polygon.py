"""Static convex polygons: scene.add_polygon, ctx.add_polygon, Renderer.polygon (FR-502, FR-503)."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import ConfigError, Polygon, Scene  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480
SQUARE = [(100.0, 100.0), (200.0, 100.0), (200.0, 200.0), (100.0, 200.0)]


def _ctx(s: Scene) -> ActionContext:
    ev = Event("timer", s._step, s.frame, s._step / RATE, (), None, None)
    return ActionContext(s, ev, None, None)


def _kinds(s: Scene, kind: str) -> list[Event]:
    return [e for e in s.events if e.kind == kind]


def test_add_polygon_handle_and_ball_bounces_off_it() -> None:
    s = Scene(width=400, height=400, gravity=(0, 900))
    floor = s.add_polygon(
        points=[(0, 300), (400, 300), (400, 340), (0, 340)], color="#ff0000", tags={"floor"}
    )
    assert isinstance(floor, Polygon) and floor.alive and s.objects == (floor,)
    assert floor.color == (255, 0, 0) and floor.tags == frozenset({"floor"})
    assert floor.center == pytest.approx((200, 320))
    ball = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    hits: list[object] = []
    s.on_collision("ball", "floor", [lambda ctx, a, b, ev: hits.append(b)])
    for _ in range(40):
        s.step_frame()
    assert hits and hits[0] is floor
    assert ball.position[1] < 290 + 1  # never sank into the polygon


def test_polygon_uses_convex_hull_and_bad_points_raise() -> None:
    s = Scene()
    poly = s.add_polygon(points=[*SQUARE, (150.0, 150.0)])  # interior point dropped
    assert len(poly.points) == 4
    for pts in (
        [(0, 0), (1, 1)],
        [(0, 0), (1, 1), (2, 2)],
        [(0, 0), (1, 0), (0, float("nan"))],
        "abc",
    ):
        with pytest.raises(ConfigError, match="points"):
            s.add_polygon(points=pts)  # type: ignore[arg-type]


def test_overlaps_matches_geometry() -> None:
    poly = Scene().add_polygon(points=SQUARE)
    assert poly.overlaps((150, 150), 1)  # inside
    assert poly.overlaps((205, 150), 6)  # 5 px outside the right edge, radius 6
    assert not poly.overlaps((205, 150), 4)
    assert not poly.overlaps((210, 210), 13)  # corner distance is 14.1


def test_ctx_add_polygon_queued_refused_on_overlap_and_destroyable() -> None:
    s = Scene(width=400, height=400, gravity=(0, 0))
    s.add_ball(pos=(50, 50), radius=10)
    poly = _ctx(s).add_polygon(points=SQUARE, tags={"lump"})
    bad = _ctx(s).add_polygon(points=[(40, 40), (60, 40), (60, 60)])
    assert not poly.alive and s.count("lump") == 0
    s._apply_commands()
    assert poly.alive and not bad.alive and s.count("lump") == 1
    assert [e.objects for e in _kinds(s, "spawn")] == [(poly,)]
    _ctx(s).recolor(poly, "#00ff00")
    _ctx(s).flash(poly, seconds=0.1)
    s._apply_commands()
    assert poly.color == (0, 255, 0)
    _ctx(s).destroy(poly)
    _ctx(s).destroy(bad)  # refused handle: no-op
    s._apply_commands()
    assert not poly.alive and s.count("lump") == 0
    assert [e.objects for e in _kinds(s, "destroy")] == [(poly,)]


def test_renderer_polygon_fills_without_seams() -> None:
    r = PygameRenderer(300, 300)
    r.clear((0, 0, 0))
    r.polygon([(100, 100), (150, 100), (150, 200), (100, 200)], (255, 255, 255))
    r.polygon([(150, 100), (200, 100), (200, 200), (150, 200)], (255, 255, 255))
    px = r.surface.get_at
    assert px((125, 150))[:3] == (255, 255, 255)
    assert px((150, 150))[:3] == (255, 255, 255)  # shared edge: no dark seam
    assert px((149, 150))[:3] == (255, 255, 255)
    assert px((90, 150))[:3] == (0, 0, 0) and px((150, 90))[:3] == (0, 0, 0)
    again = PygameRenderer(300, 300)
    again.clear((0, 0, 0))
    again.polygon([(100, 100), (150, 100), (150, 200), (100, 200)], (255, 255, 255))
    again.polygon([(150, 100), (200, 100), (200, 200), (150, 200)], (255, 255, 255))
    assert again.to_rgb_bytes() == r.to_rgb_bytes()  # same calls, same bytes


def test_scene_draws_polygon_in_flash_colour() -> None:
    s = Scene(width=300, height=300, background="#000000")
    poly = s.add_polygon(points=SQUARE, color="#0000ff")
    r = PygameRenderer(300, 300)
    s.draw(r)
    assert r.surface.get_at((150, 150))[:3] == (0, 0, 255)
    _ctx(s).flash(poly, seconds=1.0, color="#ff0000")
    s._apply_commands()
    s.draw(r)
    assert r.surface.get_at((150, 150))[:3] == (255, 0, 0)


def test_runtime_polygons_are_deterministic() -> None:
    def run() -> list[tuple[str, int]]:
        s = Scene(width=400, height=400, gravity=(0, 0), seed=5)
        s.add_circle(center=(200, 200), radius=180, thickness=10, tags={"wall"})
        s.add_ball(pos=(200, 200), radius=12, velocity=(500, 230), tags={"ball"})

        @s.on_collision("ball", "wall")
        def grow(ctx, ball, wall, ev):  # type: ignore[no-untyped-def]
            x, y = 400 - ev.position[0], 400 - ev.position[1]
            ctx.add_polygon(points=[(x - 5, y - 5), (x + 5, y - 5), (x, y + 5)], tags={"wall"})

        for _ in range(180):
            s.step_frame()
        assert s.count("wall") > 1
        return [(e.kind, e.step) for e in s.events]

    assert run() == run()
