"""Rule engine: events, registration, dispatch, cooldowns (FR-201..FR-204, FR-211, NFR-203)."""

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from bouncekit import Ball, CircleBoundary, ConfigError, Scene  # noqa: E402
from bouncekit import actions as A  # noqa: E402
from bouncekit import sound as S  # noqa: E402
from bouncekit.config import AudioConfig  # noqa: E402
from bouncekit.events import CollisionEvent, Event  # noqa: E402
from bouncekit.rules import ActionContext  # noqa: E402

RATE = 480  # 60 fps x 8 substeps


def _scene(**kw: Any) -> tuple[Scene, CircleBoundary, Ball]:
    """A ball dropped from the centre of a ring; it first hits the bottom after ~0.55 s."""
    options: dict[str, Any] = {"width": 400, "height": 400, "duration": 3.0, "max_speed": 2000}
    options.update(kw)
    s = Scene(**options)
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    ball = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    return s, ring, ball


def _run_until(s: Scene, done: Any, max_frames: int = 120) -> None:
    for _ in range(max_frames):
        s.step_frame()
        if done():
            return
    raise AssertionError("condition never met")


def _ev(step: int, a: Ball, b: Ball | CircleBoundary, speed: float = 1500.0) -> Event:
    return Event(
        kind="collision", step=step, frame=(step - 1) // 8, time=step / RATE,
        objects=(a, b), speed=speed, position=(0.0, 0.0),
    )  # fmt: skip


def _kinds(s: Scene) -> list[str]:
    return [e.kind for e in s.events]


# --- Event model (FR-201) ------------------------------------------------------------


def test_collision_event_is_event_alias() -> None:
    assert CollisionEvent is Event
    s, ring, ball = _scene()
    ev = CollisionEvent(
        kind="collision", step=1, frame=0, time=1 / RATE, objects=(ball, ring), speed=1.0,
        position=(0.0, 0.0),
    )  # fmt: skip
    assert isinstance(ev, Event) and ev.kind == "collision"
    timer = Event(
        kind="timer", step=2, frame=0, time=2 / RATE, objects=(), speed=None, position=None
    )
    with pytest.raises(AttributeError):
        timer.step = 3  # type: ignore[misc]


def test_collision_events_are_logged_per_step() -> None:
    s, ring, ball = _scene()
    _run_until(s, lambda: bool(s.events))
    ev = s.events[0]
    assert ev.kind == "collision" and set(ev.objects) == {ring, ball}
    assert ev.time == ev.step / RATE and ev.frame == s.frame - 1


# --- Deferred mutation (FR-203, NFR-203) ---------------------------------------------


def test_dispatch_never_mutates_the_space_and_destroy_applies_after_the_step() -> None:
    s, ring, ball = _scene()
    seen: list[tuple[object, ...]] = []

    def snapshot(ctx: ActionContext, a: Any, b: Any, event: Event) -> None:
        bodies = list(s.space.bodies)
        shapes = list(s.space.shapes)
        seen.append((tuple(bodies), tuple(shapes), ball.alive, ball in s.objects, s.count("ball")))

    before_bodies, before_shapes = tuple(s.space.bodies), tuple(s.space.shapes)
    # A built-in destroy, a callback destroy, then a callback that inspects the space.
    s.on_collision("ball", "wall", [A.destroy(), lambda ctx, a, b, ev: ctx.destroy(a), snapshot])
    _run_until(s, lambda: bool(seen))
    assert seen == [(before_bodies, before_shapes, True, True, 1)]
    # Visible after the step: removed from space and scene; one destroy event, same step.
    assert ball.body not in s.space.bodies and ball.shape not in s.space.shapes
    assert not ball.alive and ball not in s.objects and s.count("ball") == 0
    collision, destroy = s.events
    assert destroy.kind == "destroy" and destroy.step == collision.step
    assert destroy.objects == (ball,)


def test_handlers_run_in_list_order_and_rules_in_registration_order() -> None:
    s, _, _ = _scene(audio=AudioConfig(min_retrigger_interval=0.0))
    calls: list[tuple[str, int]] = []
    s.on_collision(
        "ball", "wall",
        [
            lambda ctx, a, b, ev: calls.append(("first", len(s.triggers))),
            A.play(S.note("C4")),
            lambda ctx, a, b, ev: calls.append(("second", len(s.triggers))),
        ],
    )  # fmt: skip
    s.on_collision("wall", "ball", [lambda ctx, a, b, ev: calls.append(("rule2", len(s.triggers)))])
    _run_until(s, lambda: bool(calls))
    assert calls == [("first", 0), ("second", 1), ("rule2", 1)]


def test_decorator_registers_and_returns_the_function() -> None:
    s, ring, ball = _scene()
    got: list[tuple[Any, ...]] = []

    def handler(ctx: ActionContext, a: Any, b: Any, event: Event) -> str:
        got.append((ctx, a, b, event))
        return "ignored"

    returned = s.on_collision("wall", "ball")(handler)
    assert returned is handler
    _run_until(s, lambda: bool(got))
    ctx, a, b, event = got[0]
    assert a is ring and b is ball  # a carries tag_a
    assert event is s.events[0]
    assert (ctx.a, ctx.b, ctx.event, ctx.scene, ctx.rng) == (ring, ball, event, s, s.rng)
    assert ctx.time == event.time


def test_decorator_syntax() -> None:
    s, _, ball = _scene()
    seen: list[Any] = []

    @s.on_collision("ball", "wall")
    def on_hit(ctx: ActionContext, a: Any, b: Any, event: Event) -> None:
        seen.append(a)

    assert callable(on_hit)
    _run_until(s, lambda: bool(seen))
    assert seen == [ball]


def test_list_form_returns_none() -> None:
    s, _, _ = _scene()
    assert s.on_collision("ball", "wall", [A.destroy()]) is None


# --- Cooldowns (FR-204) --------------------------------------------------------------


def _counting_rule(s: Scene, **kw: Any) -> list[int]:
    fired: list[int] = []
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: fired.append(ev.step)], **kw)
    return fired


def test_rule_cooldown_default_and_config() -> None:
    s, _, _ = _scene()
    assert s.config.rule_cooldown == 0.05
    assert Scene(rule_cooldown=0.2).config.rule_cooldown == 0.2


def test_pair_cooldown_exact_step_gap() -> None:
    s, ring, ball = _scene()
    fired = _counting_rule(s)
    # 0.05 s = 24 steps: a gap of 23 is blocked, a gap of exactly 24 fires.
    for step in (1, 24, 25, 48, 49):
        s._dispatch([_ev(step, ball, ring)])
    assert fired == [1, 25, 49]


def test_pair_cooldown_is_per_pair() -> None:
    s, ring, ball = _scene()
    other = s.add_ball(pos=(150, 200), radius=10, tags={"ball"})
    fired = _counting_rule(s)
    s._dispatch([_ev(1, ball, ring), _ev(2, other, ring), _ev(3, ring, ball)])
    assert fired == [1, 2]


def test_cooldown_override() -> None:
    s, ring, ball = _scene()
    fired = _counting_rule(s, cooldown=0.1)  # 48 steps
    for step in (1, 48, 49):
        s._dispatch([_ev(step, ball, ring)])
    assert fired == [1, 49]
    s2, ring2, ball2 = _scene(rule_cooldown=0.0)
    fired2 = _counting_rule(s2)
    s2._dispatch([_ev(1, ball2, ring2), _ev(1, ring2, ball2)])
    assert fired2 == [1, 1]


def test_object_cooldown_across_partners() -> None:
    s, ring, ball = _scene()
    ring2 = s.add_circle(center=(200, 200), radius=100, thickness=8, tags={"wall"})
    other = s.add_ball(pos=(150, 200), radius=10, tags={"ball"})
    fired: list[tuple[int, Any, Any]] = []
    s.on_collision(
        "ball", "wall", [lambda ctx, a, b, ev: fired.append((ev.step, a, b))],
        cooldown=0.0, object_cooldown=0.1,
    )  # fmt: skip
    s._dispatch([_ev(1, ball, ring), _ev(10, ball, ring2), _ev(10, other, ring2)])
    s._dispatch([_ev(49, ball, ring2)])
    assert fired == [(1, ball, ring), (10, other, ring2), (49, ball, ring2)]


def test_cooldowns_are_per_rule() -> None:
    s, ring, ball = _scene()
    first = _counting_rule(s)
    second = _counting_rule(s, cooldown=0.0)
    s._dispatch([_ev(1, ball, ring), _ev(2, ball, ring)])
    assert first == [1] and second == [1, 2]


def test_play_ignores_rule_cooldown() -> None:
    s, ring, ball = _scene(rule_cooldown=1.0, audio=AudioConfig(min_retrigger_interval=0.0))
    calls: list[int] = []
    s.on_collision("ball", "wall", [A.play(S.note("C4")), lambda ctx, a, b, ev: calls.append(1)])
    s._dispatch([_ev(1, ball, ring)])
    s._dispatch([_ev(10, ball, ring)])
    assert len(s.triggers) == 2 and calls == [1]


def test_play_keeps_retrigger_policy() -> None:
    s, ring, ball = _scene(rule_cooldown=0.0)
    s.on_collision("ball", "wall", [A.play(S.note("C4"))])
    s._dispatch([_ev(1, ball, ring)])
    s._dispatch([_ev(10, ball, ring)])  # within min_retrigger_interval (0.05 s)
    assert len(s.triggers) == 1


# --- Play on any event, ctx.play (FR-211) --------------------------------------------


def test_ctx_play_produces_triggers_immediately() -> None:
    s, ring, ball = _scene()
    counts: list[int] = []

    def cb(ctx: ActionContext, a: Any, b: Any, event: Event) -> None:
        ctx.play(S.note("C5"), gain=0.5)
        counts.append(len(s.triggers))

    s.on_collision("ball", "wall", [cb])
    assert not s.has_sound
    _run_until(s, lambda: bool(counts))
    assert counts == [1]
    trig = s.triggers[0]
    assert trig.step == s.events[0].step
    assert trig.gain == pytest.approx(0.5 * min(1.0, s.events[0].speed / 1500.0) ** 0.5)


def test_ctx_play_applies_trigger_policy() -> None:
    s, ring, ball = _scene(rule_cooldown=0.0)
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: ctx.play(S.note("C5"))])
    s._dispatch([_ev(1, ball, ring)])
    s._dispatch([_ev(2, ball, ring)])  # retrigger interval: same source, same object
    s._dispatch([_ev(100, ball, ring, speed=1.0)])  # below min_impact_speed
    assert len(s.triggers) == 1


def test_ctx_methods_validate_at_the_call() -> None:
    s, ring, ball = _scene()
    errors: list[str] = []

    def cb(ctx: ActionContext, a: Any, b: Any, event: Event) -> None:
        for call in (
            lambda: ctx.play("C5"),  # type: ignore[arg-type]
            lambda: ctx.play(S.note("C5"), gain=-1.0),
            lambda: ctx.destroy("ball"),  # type: ignore[arg-type]
        ):
            try:
                call()
            except ConfigError as exc:
                errors.append(str(exc))

    s.on_collision("ball", "wall", [cb])
    s._dispatch([_ev(1, ball, ring)])
    assert len(errors) == 3 and not s.triggers


def test_per_frame_cap_counts_by_event_frame_in_simulation() -> None:
    # Per-step dispatch must give exactly the M1 per-frame result.
    s, ring, ball = _scene(audio=AudioConfig(max_triggers_per_frame=1, min_retrigger_interval=0.0))
    s.on_collision("ball", "wall", [A.play(S.note("C4")), A.play(S.note("E4"))])
    s._dispatch([_ev(1, ball, ring)])
    s._dispatch([_ev(2, ball, ring)])  # same frame 0, next step
    s._dispatch([_ev(9, ball, ring)])  # frame 1
    assert [t.step for t in s.triggers] == [1, 9]


def test_has_sound_only_with_play_handlers() -> None:
    s, _, _ = _scene()
    s.on_collision("ball", "wall", [A.destroy()])
    assert not s.has_sound
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: None, A.play(S.note("C4"))])
    assert s.has_sound


# --- Validation (FR-202, FR-204) -----------------------------------------------------


@pytest.mark.parametrize(
    ("args", "kwargs", "needle"),
    [
        (("", "wall", []), {}, "tag_a"),
        (("ball", 3, []), {}, "tag_b"),
        (("ball", "wall", A.destroy()), {}, "handlers"),
        (("ball", "wall", "abc"), {}, "handlers"),
        (("ball", "wall", [object()]), {}, "handlers"),
        (("ball", "wall", [1]), {}, "handlers"),
        (("ball", "wall", []), {"cooldown": -1.0}, "cooldown"),
        (("ball", "wall", []), {"cooldown": math.nan}, "cooldown"),
        (("ball", "wall", []), {"cooldown": "1"}, "cooldown"),
        (("ball", "wall", []), {"object_cooldown": -0.1}, "object_cooldown"),
        (("ball", "wall", []), {"object_cooldown": math.inf}, "object_cooldown"),
    ],
)
def test_on_collision_validation(
    args: tuple[Any, ...], kwargs: dict[str, Any], needle: str
) -> None:
    s, _, _ = _scene()
    with pytest.raises(ConfigError, match=needle):
        s.on_collision(*args, **kwargs)


def test_decorator_rejects_non_callable() -> None:
    s, _, _ = _scene()
    with pytest.raises(ConfigError):
        s.on_collision("ball", "wall")(42)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-0.01, math.inf, math.nan, "0.05", True])
def test_bad_rule_cooldown(value: object) -> None:
    with pytest.raises(ConfigError, match="rule_cooldown"):
        Scene(rule_cooldown=value)  # type: ignore[arg-type]


# --- Render audio decision (FR-211) ---------------------------------------------------


def _streams(path: Path) -> list[str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return [st["codec_type"] for st in json.loads(out)["streams"]]


def _tiny(handlers: list[Any]) -> Scene:
    s = Scene(width=160, height=160, fps=30, duration=1.0, max_speed=1000)
    s.add_circle(center=(80, 80), radius=60, thickness=6, tags={"wall"})
    s.add_ball(pos=(80, 80), radius=6, tags={"ball"})
    s.on_collision("ball", "wall", handlers)
    return s


def test_render_rules_without_sound_is_video_only(tmp_path: Path) -> None:
    out = _tiny([lambda ctx, a, b, ev: None]).render(tmp_path / "v.mp4")
    assert _streams(out) == ["video"]
    assert [p.name for p in tmp_path.iterdir()] == ["v.mp4"]


def test_render_callback_play_muxes_audio(tmp_path: Path) -> None:
    s = _tiny([lambda ctx, a, b, ev: ctx.play(S.note("C5"))])
    assert not s.has_sound
    out = s.render(tmp_path / "a.mp4")
    assert sorted(_streams(out)) == ["audio", "video"]
    assert [p.name for p in tmp_path.iterdir()] == ["a.mp4"]
