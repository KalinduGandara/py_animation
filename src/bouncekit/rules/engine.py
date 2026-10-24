"""Rule registry and dispatch: matching, cooldowns, handler calls (FR-202..FR-204)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from bouncekit.actions import Destroy, Handler, Play, Spawn, Split
from bouncekit.events import Event, WorldObject
from bouncekit.rules.context import ActionContext
from bouncekit.sound import Source

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["Rule", "RuleEngine", "RuleKind"]

type RuleKind = Literal["collision", "spawn", "destroy"]

# Registration method that creates each rule kind, for error messages.
METHOD: dict[str, str] = {
    "collision": "on_collision",
    "spawn": "on_spawn",
    "destroy": "on_destroy",
}
# Subjects each rule kind provides to its actions' ``target``.
SUBJECTS: dict[str, tuple[str, ...]] = {"collision": ("a", "b"), "spawn": ("a",), "destroy": ("a",)}


@dataclass(eq=False)
class Rule:
    """One registration: when an event of ``kind`` matches, run ``handlers`` in order.

    ``tag_a``/``tag_b``: collision tags (``tag_a`` alone for spawn/destroy rules).
    ``cooldown``/``object_cooldown``: seconds (collision rules only).
    ``index``: registration order, used as a lookup key for cooldown state.
    """

    kind: RuleKind
    handlers: tuple[Handler, ...]
    index: int
    tag_a: str
    tag_b: str | None = None
    cooldown: float = 0.0
    object_cooldown: float = 0.0


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

    def add(self, rule: Rule) -> None:
        """Register ``rule`` after the existing ones."""
        self.rules.append(rule)

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

    def dispatch(self, events: list[Event] | tuple[Event, ...]) -> None:
        """Run every matching rule for each event, in order."""
        for ev in events:
            for rule in self.rules:
                subjects = self._match(rule, ev)
                if subjects is not None:
                    self._run(rule, ev, *subjects)

    @staticmethod
    def _match(rule: Rule, ev: Event) -> tuple[WorldObject, WorldObject | None] | None:
        if rule.kind != ev.kind:
            return None
        if rule.kind == "collision":
            first, second = ev.objects
            if rule.tag_a in first.tags and rule.tag_b in second.tags:
                return first, second
            if rule.tag_a in second.tags and rule.tag_b in first.tags:
                return second, first
            return None
        obj = ev.objects[0]
        return (obj, None) if rule.tag_a in obj.tags else None

    def _run(self, rule: Rule, ev: Event, a: WorldObject, b: WorldObject | None) -> None:
        scene = self.scene
        gated = False
        pair_key: tuple[int, int, int] | None = None
        object_key: tuple[int, int] | None = None
        if rule.kind == "collision" and b is not None:
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
            if isinstance(handler, Destroy | Split | Spawn):
                handler.run(ctx)
            elif rule.kind == "collision":
                handler(ctx, a, b, ev)
            else:
                handler(ctx, a, ev)
        if fired and pair_key is not None and object_key is not None:
            self._last_pair[pair_key] = ev.step
            self._last_object[object_key] = ev.step
