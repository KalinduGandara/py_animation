"""Rule registry and dispatch: matching, cooldowns, escapes, timers, conditions.

FR-202..FR-204, FR-208, FR-209.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from bouncekit.actions import Destroy, EndAfter, Handler, Play, Spawn, Split
from bouncekit.events import Event, WorldObject
from bouncekit.rules.context import ActionContext
from bouncekit.sound import Source
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["Rule", "RuleEngine", "RuleKind"]

type RuleKind = Literal["collision", "escape", "spawn", "destroy", "timer", "condition"]

# Subjects each rule kind provides to its actions' ``target``.
SUBJECTS: dict[str, tuple[str, ...]] = {
    "collision": ("a", "b"),
    "escape": ("a", "b"),
    "spawn": ("a",),
    "destroy": ("a",),
    "timer": (),
    "condition": (),
}


@dataclass(eq=False)
class Rule:
    """One registration: when an event of ``kind`` matches, run ``handlers`` in order.

    ``tag_a``/``tag_b``: collision tags (``tag_a`` alone for escape/spawn/destroy
    rules, ``None`` for timer/condition rules).
    ``cooldown``/``object_cooldown``: seconds (collision rules only).
    ``ring``/``margin``: the watched ring and extra distance (escape rules).
    ``period``/``at_step``: timer schedule in steps (``every``: period; ``at``: step).
    ``predicate``/``fired``: condition rules; ``fired`` once the predicate held.
    ``index``: registration order, used as a lookup key for cooldown state.
    """

    kind: RuleKind
    handlers: tuple[Handler, ...]
    index: int
    tag_a: str | None = None
    tag_b: str | None = None
    cooldown: float = 0.0
    object_cooldown: float = 0.0
    ring: CircleBoundary | None = None
    margin: float = 0.0
    period: int = 0
    at_step: int = 0
    predicate: "Callable[[Scene], object] | None" = None
    fired: bool = False


class RuleEngine:
    """Holds a scene's rules and dispatches events to them.

    Events are processed in the given order; for each event, matching rules in
    registration order; for each rule, handlers in list order. Rule cooldowns gate
    only non-play handlers; ``A.play`` goes straight to the audio trigger policy.
    """

    def __init__(self, scene: "Scene") -> None:
        """Create an empty engine for ``scene``."""
        self.scene = scene
        self.rules: list[Rule] = []
        # Lookup-only cooldown state keyed by rule and object indices -> step.
        self._last_pair: dict[tuple[int, int, int], int] = {}
        self._last_object: dict[tuple[int, int], int] = {}
        # ctx.play(source, gain) shares one Play per (source, gain): lookup only.
        self._shared_play: dict[tuple[Source, float], Play] = {}
        # Per-kind views in registration order (iterated).
        self._escape_rules: list[Rule] = []
        self._timer_rules: list[Rule] = []
        self._condition_rules: list[Rule] = []
        # (ring index, ball index) pairs that already escaped: lookup only.
        self._escaped: set[tuple[int, int]] = set()

    def add(self, rule: Rule) -> None:
        """Register ``rule`` after the existing ones."""
        self.rules.append(rule)
        if rule.kind == "escape":
            self._escape_rules.append(rule)
        elif rule.kind == "timer":
            self._timer_rules.append(rule)
        elif rule.kind == "condition":
            self._condition_rules.append(rule)

    def inherit(self, parent: int, child: int) -> None:
        """Give object index ``child`` the cooldown timestamps of ``parent`` (split, C7)."""
        for (rule, i, j), step in list(self._last_pair.items()):
            if parent in (i, j):
                other = j if i == parent else i
                self._last_pair[(rule, min(child, other), max(child, other))] = step
        for (rule, i), step in list(self._last_object.items()):
            if i == parent:
                self._last_object[(rule, child)] = step

    def shared_play(self, action: Play) -> Play:
        """Return the play action shared by every ``ctx.play`` with the same source and gain."""
        return self._shared_play.setdefault((action.source, action.gain), action)

    @property
    def has_play(self) -> bool:
        """Whether any rule has an ``A.play`` handler."""
        return any(isinstance(h, Play) for rule in self.rules for h in rule.handlers)

    def escapes(self, step: int, frame: int) -> list[Event]:
        """Detect and return this step's escape events (FR-208), without dispatching.

        For each live ring with escape rules (insertion order) and each live ball
        carrying one of those rules' tags (insertion order), a pair escapes once, the
        first time the ball's centre is farther from the ring's centre than
        ``radius + thickness / 2 + ball.radius + margin``. With several matching rules
        on one ring the smallest margin applies.
        """
        if not self._escape_rules:
            return []
        scene = self.scene
        rate = scene._rate
        found: list[Event] = []
        for ring in scene._rings:
            rules = [r for r in self._escape_rules if r.ring is ring]
            if not rules:
                continue
            ring_index = scene._indices[ring]
            cx, cy = ring.center
            reach = ring.radius + ring.thickness / 2
            for ball in scene._balls:
                margins = [r.margin for r in rules if r.tag_a in ball.tags]
                if not margins:
                    continue
                key = (ring_index, scene._indices[ball])
                if key in self._escaped:
                    continue
                x, y = ball.position
                if math.hypot(x - cx, y - cy) > reach + ball.radius + min(margins):
                    self._escaped.add(key)
                    found.append(
                        Event(
                            "escape",
                            step,
                            frame,
                            step / rate,
                            (ring, ball),
                            math.hypot(*ball.velocity),
                            (x, y),
                        )
                    )
        return found

    def due_timers(self, step: int, frame: int) -> list[tuple[Rule, Event]]:
        """Timer rules due at ``step`` (registration order), each with its new event."""
        due: list[tuple[Rule, Event]] = []
        for rule in self._timer_rules:
            if (rule.period and step % rule.period == 0) or step == rule.at_step:
                ev = Event("timer", step, frame, step / self.scene._rate, (), None, None)
                due.append((rule, ev))
        return due

    def conditions(self, step: int, frame: int) -> None:
        """Fire each unfired condition rule whose predicate holds now (once, C9).

        Called after a frame's last step and command application. Each firing logs a
        ``"condition"`` event, runs that rule only and applies the queued commands.
        """
        scene = self.scene
        for rule in self._condition_rules:
            if rule.fired or rule.predicate is None or not rule.predicate(scene):
                continue
            rule.fired = True
            ev = Event("condition", step, frame, step / scene._rate, (), None, None)
            scene._events.append(ev)
            self.run(rule, ev)
            scene._apply_commands()

    def run(self, rule: Rule, ev: Event) -> None:
        """Run a subject-less (timer/condition) ``rule`` for its own event ``ev``."""
        self._run(rule, ev, None, None)

    def dispatch(self, events: list[Event] | tuple[Event, ...]) -> None:
        """Run every matching rule for each event, in order.

        Timer and condition events match no rule here: they are run directly on the
        rule that produced them (:meth:`run`).
        """
        for ev in events:
            for rule in self.rules:
                subjects = self._match(rule, ev)
                if subjects is not None:
                    self._run(rule, ev, *subjects)

    @staticmethod
    def _match(rule: Rule, ev: Event) -> tuple[WorldObject, WorldObject | None] | None:
        if rule.kind != ev.kind or rule.kind in ("timer", "condition"):
            return None
        if rule.kind == "escape":
            ring, ball = ev.objects
            return (ball, ring) if rule.ring is ring and rule.tag_a in ball.tags else None
        if rule.kind == "collision":
            first, second = ev.objects
            if rule.tag_a in first.tags and rule.tag_b in second.tags:
                return first, second
            if rule.tag_a in second.tags and rule.tag_b in first.tags:
                return second, first
            return None
        obj = ev.objects[0]
        return (obj, None) if rule.tag_a in obj.tags else None

    def _run(self, rule: Rule, ev: Event, a: WorldObject | None, b: WorldObject | None) -> None:
        scene = self.scene
        gated = False
        pair_key: tuple[int, int, int] | None = None
        object_key: tuple[int, int] | None = None
        if rule.kind == "collision" and a is not None and b is not None:
            rate = scene._rate
            i, j = scene._indices[a], scene._indices[b]
            pair_key = (rule.index, min(i, j), max(i, j))
            object_key = (rule.index, i)
            # Exact step gap, one correctly rounded division (as the M1 retrigger check).
            last = self._last_pair.get(pair_key)
            if last is not None and (ev.step - last) / rate < rule.cooldown:
                gated = True
            last = self._last_object.get(object_key)
            if last is not None and (ev.step - last) / rate < rule.object_cooldown:
                gated = True
        ctx = ActionContext(scene, ev, a, b)
        fired = False
        for handler in rule.handlers:
            if isinstance(handler, Play):
                handler.run(ctx)
                continue
            if gated:
                continue
            fired = True
            if isinstance(handler, Destroy | Split | Spawn | EndAfter):
                handler.run(ctx)
            elif rule.kind in ("collision", "escape"):
                handler(ctx, a, b, ev)
            elif rule.kind in ("spawn", "destroy"):
                handler(ctx, a, ev)
            else:
                handler(ctx, ev)
        if fired and pair_key is not None and object_key is not None:
            self._last_pair[pair_key] = ev.step
            self._last_object[object_key] = ev.step
