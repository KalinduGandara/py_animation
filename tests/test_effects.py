"""Trails, glow and the effects pipeline (FR-301..FR-304, NFR-302, NFR-304)."""

import hashlib
import math
import os
import random
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, ConfigError, EffectsConfig, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit.events import Event  # noqa: E402
from bouncekit.render.base import GlowArc, GlowDisc, Renderer, TrailSegment  # noqa: E402
from bouncekit.render.pygame_renderer import PygameRenderer  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

BG = (10, 20, 30)
BLACK = (0, 0, 0)


def _pixel(data: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    i = (y * width + x) * 3
    return (data[i], data[i + 1], data[i + 2])


def _scene(**kw: Any) -> Scene:
    opts: dict[str, Any] = {
        "width": 200,
        "height": 200,
        "fps": 30,
        "duration": 2.0,
        "background": BG,
        "gravity": (0.0, 0.0),
        "max_speed": 2000.0,
    }
    opts.update(kw)
    return Scene(**opts)


def _ctx(s: Scene, a: Any = None) -> ActionContext:
    rate = s.config.fps * s.config.substeps
    ev = Event("timer", s._step, s.frame, s._step / rate, (), None, None)
    return ActionContext(s, ev, a, None)


class Spy:
    """Wraps a PygameRenderer and records every call (name, args, kwargs)."""

    def __init__(self, width: int, height: int) -> None:
        self.inner = PygameRenderer(width, height)
        self.width = width
        self.height = height
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.inner, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            return target(*args, **kwargs)

        return call

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


# --- circle(alpha=) -----------------------------------------------------------


def test_circle_alpha_half_blends_and_alpha_one_equals_m2_call() -> None:
    r = PygameRenderer(40, 40)
    r.clear(BLACK)
    r.circle((20, 20), 8, (200, 100, 50), alpha=0.5)
    assert _pixel(r.to_rgb_bytes(), 40, 20, 20) == (100, 50, 25)
    r.clear((0, 0, 200))
    r.circle((20, 20), 8, (200, 100, 50), alpha=0.5)
    assert _pixel(r.to_rgb_bytes(), 40, 20, 20) == (100, 50, 125)
    assert _pixel(r.to_rgb_bytes(), 40, 2, 2) == (0, 0, 200)

    m2, a1 = PygameRenderer(40, 40), PygameRenderer(40, 40)
    for rr in (m2, a1):
        rr.clear(BG)
    m2.circle((19.3, 20.7), 7.4, (250, 10, 90))
    a1.circle((19.3, 20.7), 7.4, (250, 10, 90), alpha=1.0)
    assert m2.to_rgb_bytes() == a1.to_rgb_bytes()


# --- trails -------------------------------------------------------------------

WHITE_BAR = TrailSegment((0.0, 20.0), (40.0, 20.0), 60.0, (255, 255, 255))


def test_trails_reset_clears_the_layer() -> None:
    r = PygameRenderer(40, 40)
    r.clear(BLACK)
    r.trails([WHITE_BAR], keep=0.85, reset=True)
    assert set(r.to_rgb_bytes()) == {255}
    r.clear(BLACK)
    r.trails([], keep=0.85, reset=True)
    assert set(r.to_rgb_bytes()) == {0}


def test_trail_layer_decays_to_exactly_zero_within_bound() -> None:
    keep = 0.85
    bound = math.ceil(math.log(1 / 255) / math.log(keep)) + 255
    r = PygameRenderer(40, 40)
    r.clear(BLACK)
    r.trails([WHITE_BAR], keep=keep, reset=True)
    previous = 255
    for _ in range(bound):
        r.clear(BLACK)
        r.trails([], keep=keep, reset=False)
        values = set(r.to_rgb_bytes())
        assert max(values) <= previous
        previous = max(values)
    assert previous == 0
    # keep = 1.0 leaves the layer unchanged.
    r.clear(BLACK)
    r.trails([WHITE_BAR], keep=1.0, reset=True)
    for _ in range(5):
        r.clear(BLACK)
        r.trails([], keep=1.0, reset=False)
    assert set(r.to_rgb_bytes()) == {255}


def test_trail_segment_decays_partially_after_one_frame() -> None:
    r = PygameRenderer(40, 40)
    r.clear(BLACK)
    r.trails([WHITE_BAR], keep=0.5, reset=True)
    r.clear(BLACK)
    r.trails([], keep=0.5, reset=False)
    assert 120 <= _pixel(r.to_rgb_bytes(), 40, 20, 20)[0] <= 130


def test_trail_max_composite_never_darkens_the_frame() -> None:
    r = PygameRenderer(40, 40)
    bright = (180, 90, 200)
    r.clear(bright)
    seg = TrailSegment((5.0, 5.0), (35.0, 30.0), 10.0, (100, 200, 50))
    r.trails([seg], keep=0.85, reset=True)
    data = r.to_rgb_bytes()
    for i in range(0, len(data), 3):
        px = data[i : i + 3]
        assert px[0] >= 180 and px[1] >= 90 and px[2] >= 200
    assert _pixel(data, 40, 20, 17) == (180, 200, 200)  # per-channel max


def test_moving_trail_ball_leaves_fading_pixels_behind() -> None:
    s = _scene()
    s.add_ball(pos=(40, 100), radius=8, velocity=(600, 0), color="#ff0000", trail=True)
    r = PygameRenderer(200, 200)
    reds = []
    for _ in range(6):
        s.draw(r)
        reds.append(_pixel(r.to_rgb_bytes(), 200, 40, 100)[0])
        s.step_frame()
    # frame 0 shows the ball itself; later frames show the fading trail behind it.
    assert reds[0] == 255
    assert all(v > BG[0] for v in reds[1:4])
    assert reds[1] > reds[2] > reds[3] > reds[4]


def test_paused_redraw_gives_identical_bytes() -> None:
    s = _scene()
    s.add_ball(pos=(40, 100), radius=8, velocity=(600, 0), trail=True, glow=1.0)
    r = PygameRenderer(200, 200)
    for _ in range(3):
        s.draw(r)
        s.step_frame()
    s.draw(r)
    first = r.to_rgb_bytes()
    s.draw(r)
    assert r.to_rgb_bytes() == first


def test_trail_keep_reset_and_segments_follow_frame_bookkeeping() -> None:
    s = _scene(effects=EffectsConfig(trail_seconds=0.5))
    ball = s.add_ball(pos=(40, 100), radius=8, velocity=(300, 0), trail=True)
    s.add_ball(pos=(100, 50), radius=4, velocity=(0, 0))  # no trail: no segment
    spy = Spy(200, 200)
    keep = 0.05 ** (1 / (0.5 * 30))
    assert s.config.effects.trail_keep(30) == pytest.approx(keep)

    s.draw(spy)  # first draw: reset, a dot
    s.step_frame()
    p0, p1 = (40.0, 100.0), ball.position
    s.draw(spy)  # next frame: fade + segment from previous position
    s.draw(spy)  # redraw: keep 1, no segments
    s.step_frame()
    s.step_frame()  # a skipped frame
    s.draw(spy)
    trails = [c for c in spy.calls if c[0] == "trails"]
    assert len(trails) == 4
    names = spy.names()
    assert names[:3] == ["clear", "trails", "circle"]
    (segs0,), kw0 = trails[0][1], trails[0][2]
    assert kw0["reset"] is True and segs0 == [TrailSegment(p0, p0, 16.0, (255, 255, 255))]
    (segs1,), kw1 = trails[1][1], trails[1][2]
    assert kw1 == {"keep": pytest.approx(keep), "reset": False}
    assert len(segs1) == 1 and segs1[0].a == p0 and segs1[0].b == p1
    (segs2,), kw2 = trails[2][1], trails[2][2]
    assert segs2 == [] and kw2 == {"keep": 1.0, "reset": False}
    (segs3,), kw3 = trails[3][1], trails[3][2]
    assert kw3["reset"] is True and segs3[0].a == segs3[0].b == ball.position


def test_destroyed_trail_ball_adds_no_segments() -> None:
    s = _scene()
    a = s.add_ball(pos=(40, 100), radius=8, velocity=(300, 0), trail=True)
    b = s.add_ball(pos=(40, 40), radius=8, velocity=(300, 0), trail=True)
    spy = Spy(200, 200)
    s.draw(spy)
    s.step_frame()
    A.destroy().run(_ctx(s, a))
    s._apply_commands()
    s.draw(spy)
    last = [c for c in spy.calls if c[0] == "trails"][-1]
    (segs,) = last[1]
    assert len(segs) == 1 and segs[0].b == b.position


# --- glow ---------------------------------------------------------------------


def test_glow_brightens_near_pixels_and_leaves_far_pixels() -> None:
    def frame(glow: float) -> bytes:
        s = _scene(background=BLACK)
        s.add_ball(pos=(100, 100), radius=10, color="#3060ff", glow=glow)
        r = PygameRenderer(200, 200)
        s.draw(r)
        return r.to_rgb_bytes()

    plain, glowing = frame(0.0), frame(1.0)
    near_plain = _pixel(plain, 200, 114, 100)
    near_glow = _pixel(glowing, 200, 114, 100)
    assert near_plain == BLACK and sum(near_glow) > 0
    assert _pixel(glowing, 200, 2, 2) == BLACK
    assert _pixel(glowing, 200, 190, 30) == BLACK


def test_glow_renderer_disc_and_arc() -> None:
    r = PygameRenderer(200, 200)
    r.clear((20, 20, 20))
    r.glow([GlowDisc((50.0, 50.0), 10.0, (255, 0, 0), 1.0)], blur=8.0)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 50, 50)[0] > 20 and _pixel(data, 200, 50, 50)[1] == 20
    assert _pixel(data, 200, 150, 150) == (20, 20, 20)

    r.clear(BLACK)
    arc = GlowArc((100.0, 100.0), 60.0, 6.0, 0.0, 360.0, (0, 255, 0), 2.0)
    r.glow([arc], blur=8.0)
    data = r.to_rgb_bytes()
    assert _pixel(data, 200, 160, 100)[1] > 0 and _pixel(data, 200, 100, 40)[1] > 0
    assert _pixel(data, 200, 100, 100) == BLACK


def test_flashing_glowing_ring_glows_in_flash_colour() -> None:
    s = _scene(background=BLACK)
    ring = s.add_circle(center=(100, 100), radius=60, color="#0000ff", glow=1.0)
    A.flash(ring, seconds=1.0, color="#ff0000").run(_ctx(s))
    s._apply_commands()
    spy = Spy(200, 200)
    s.draw(spy)
    glows = [c for c in spy.calls if c[0] == "glow"]
    assert len(glows) == 1
    (lights,) = glows[0][1]
    assert lights == [ring.glow_light((255, 0, 0))]
    assert isinstance(lights[0], GlowArc) and lights[0].color == (255, 0, 0)
    data = spy.inner.to_rgb_bytes()
    inside = _pixel(data, 200, 100, 46)  # just inside the band
    assert inside[0] > 0 and inside[2] == 0


def test_glow_lights_in_insertion_order_with_drawn_colours() -> None:
    s = _scene(effects=EffectsConfig(glow_blur=12.0))
    ring = s.add_circle(center=(100, 100), radius=80, glow=True, gap_degrees=40)
    b1 = s.add_ball(pos=(80, 100), radius=6, color="#00ff00", glow=0.5)
    s.add_ball(pos=(120, 100), radius=6)  # no glow
    b3 = s.add_ball(pos=(100, 80), radius=5, color="#0000ff", glow=4)
    spy = Spy(200, 200)
    s.draw(spy)
    assert spy.names()[-1] == "glow"
    (lights,), kw = spy.calls[-1][1], spy.calls[-1][2]
    assert kw == {"blur": 12.0}
    assert lights == [
        ring.glow_light((255, 255, 255)),
        GlowDisc(b1.position, 6.0, (0, 255, 0), 0.5),
        GlowDisc(b3.position, 5.0, (0, 0, 255), 4.0),
    ]
    arc = ring.glow_light((1, 2, 3))
    assert arc is not None
    assert (arc.center, arc.radius, arc.width, arc.intensity) == ((100.0, 100.0), 80.0, 8.0, 1.0)
    assert arc.end_degrees - arc.start_degrees == pytest.approx(320, abs=3)


# --- pipeline compatibility (NFR-304) and physics independence (NFR-302) ------


def _m2_scene(**kw: Any) -> Scene:
    s = _scene(gravity=(0.0, 900.0), **kw)
    s.add_circle(center=(100, 100), radius=80, gap_degrees=30, angular_velocity=40)
    s.add_ball(pos=(90, 80), radius=8, velocity=(200, 50), color="#ff8800", tags={"ball"})
    s.add_ball(pos=(110, 120), radius=6, velocity=(-150, 30), color="#00ffcc", tags={"ball"})
    return s


def test_effect_free_scene_makes_m2_calls_and_bytes() -> None:
    s = _m2_scene()
    spy = Spy(200, 200)
    ref = PygameRenderer(200, 200)
    for _ in range(10):
        spy.calls.clear()
        s.draw(spy)
        assert set(spy.names()) <= {"clear", "circle", "arc"}
        assert all(not c[2] for c in spy.calls)  # no alpha keyword
        ref.clear(s.config.background)
        for obj in s.objects:
            obj.draw(ref)
        assert (
            hashlib.sha256(spy.inner.to_rgb_bytes()).digest()
            == hashlib.sha256(ref.to_rgb_bytes()).digest()
        )
        s.step_frame()


def test_trail_and_glow_do_not_change_physics() -> None:
    def build(effects: bool) -> Scene:
        s = _scene(gravity=(0.0, 900.0), duration=3.0)
        s.add_circle(center=(100, 100), radius=80, glow=1.0 if effects else 0.0, tags={"wall"})
        for i in range(4):
            s.add_ball(
                pos=(70 + 20 * i, 90),
                radius=6,
                velocity=(100 * (i - 1.5), -60),
                tags={"ball"},
                trail=effects,
                glow=2.0 if effects else 0.0,
            )
        s.on_collision("ball", "wall", [A.split(max_total=12), A.flash()])
        return s

    on, off = build(True), build(False)
    r = PygameRenderer(200, 200)
    for _ in range(60):
        on.draw(r)
        on.step_frame()
        off.step_frame()
        assert [(b.position, b.velocity) for b in on._balls] == [
            (b.position, b.velocity) for b in off._balls
        ]
    assert [(e.kind, e.step, e.speed) for e in on.events] == [
        (e.kind, e.step, e.speed) for e in off.events
    ]
    assert on.rng.getstate() == off.rng.getstate()
    assert len(on._balls) > 4  # splits happened


# --- inheritance -------------------------------------------------------------


def test_split_children_inherit_trail_and_glow() -> None:
    s = _scene()
    ball = s.add_ball(pos=(100, 100), radius=10, velocity=(300, 0), trail=True, glow=0.7)
    A.split(into=3).run(_ctx(s, ball))
    s._apply_commands()
    balls = [o for o in s.objects if isinstance(o, Ball)]
    assert len(balls) == 3
    assert all(b.trail is True and b.glow == 0.7 for b in balls)


def test_spawned_balls_get_trail_and_glow() -> None:
    s = _scene()
    A.spawn(pos=(100, 100), radius=5, count=2, trail=True, glow=True).run(_ctx(s))
    _ctx(s).spawn(pos=(50, 50), radius=5, glow=2.5)
    s._apply_commands()
    balls = [o for o in s.objects if isinstance(o, Ball)]
    assert [(b.trail, b.glow) for b in balls] == [(True, 1.0), (True, 1.0), (False, 2.5)]
    plain = s.add_ball(pos=(20, 20), radius=4)
    assert (plain.trail, plain.glow) == (False, 0.0)


# --- validation and fx_rng ----------------------------------------------------


@pytest.mark.parametrize("value", [1, "yes", None, 0.0])
def test_bad_trail_raises_naming_trail(value: Any) -> None:
    s = _scene()
    with pytest.raises(ConfigError, match="trail"):
        s.add_ball(pos=(10, 10), radius=4, trail=value)
    with pytest.raises(ConfigError, match="trail"):
        A.spawn(pos=(10, 10), radius=4, trail=value)
    with pytest.raises(ConfigError, match="trail"):
        _ctx(s).spawn(pos=(10, 10), radius=4, trail=value)


@pytest.mark.parametrize("value", [-0.1, 4.5, math.nan, math.inf, "1", None])
def test_bad_glow_raises_naming_glow(value: Any) -> None:
    s = _scene()
    with pytest.raises(ConfigError, match="glow"):
        s.add_ball(pos=(10, 10), radius=4, glow=value)
    with pytest.raises(ConfigError, match="glow"):
        s.add_circle(center=(100, 100), radius=50, glow=value)
    with pytest.raises(ConfigError, match="glow"):
        A.spawn(pos=(10, 10), radius=4, glow=value)
    with pytest.raises(ConfigError, match="glow"):
        _ctx(s).spawn(pos=(10, 10), radius=4, glow=value)


def test_glow_accepts_bounds_and_bools() -> None:
    s = _scene()
    assert s.add_ball(pos=(10, 10), radius=6, glow=4).glow == 4.0
    assert s.add_ball(pos=(30, 10), radius=6, glow=False).glow == 0.0
    assert s.add_circle(center=(100, 100), radius=50, glow=True).glow == 1.0


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"trail_seconds": 0}, "trail_seconds"),
        ({"trail_seconds": math.inf}, "trail_seconds"),
        ({"glow_blur": -1.0}, "glow_blur"),
        ({"glow_blur": "x"}, "glow_blur"),
        ({"max_particles": -1}, "max_particles"),
        ({"max_particles": 1.5}, "max_particles"),
        ({"max_particles": True}, "max_particles"),
    ],
)
def test_bad_effects_config_raises_naming_field(kw: dict[str, Any], field: str) -> None:
    with pytest.raises(ConfigError, match=field):
        EffectsConfig(**kw)


def test_effects_config_defaults_and_scene_option() -> None:
    cfg = EffectsConfig()
    assert (cfg.trail_seconds, cfg.glow_blur, cfg.max_particles) == (0.3, 18.0, 2000)
    assert EffectsConfig(max_particles=0).max_particles == 0
    assert _scene().config.effects == EffectsConfig()
    custom = EffectsConfig(trail_seconds=1.0)
    assert _scene(effects=custom).config.effects is custom
    with pytest.raises(ConfigError, match="effects"):
        _scene(effects="fast")


def test_fx_rng_is_seeded_from_the_scene_seed() -> None:
    s = _scene(seed=42)
    assert s.fx_rng.getstate() == random.Random("bouncekit-fx:42").getstate()
    assert s.fx_rng.getstate() != s.rng.getstate()


def test_renderer_protocol_has_the_m3_methods() -> None:
    r = PygameRenderer(10, 10)
    assert isinstance(r, Renderer)
    for name in ("trails", "glow"):
        assert callable(getattr(Renderer, name))


def test_trail_keeps_fading_after_the_last_trail_ball_is_destroyed() -> None:
    s = _scene()
    ball = s.add_ball(pos=(40, 100), radius=8, velocity=(300, 0), trail=True)
    spy = Spy(200, 200)
    s.draw(spy)
    s.step_frame()
    A.destroy().run(_ctx(s, ball))
    s._apply_commands()
    s.draw(spy)
    last = [c for c in spy.calls if c[0] == "trails"][-1]
    assert last[1] == ([],) and last[2]["reset"] is False and last[2]["keep"] < 1
    # once the layer must be black, trails are no longer drawn
    for _ in range(400):
        s.step_frame()
    spy.calls.clear()
    s.draw(spy)
    assert "trails" not in spy.names()
