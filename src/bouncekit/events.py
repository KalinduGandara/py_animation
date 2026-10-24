"""Event model (FR-201) and collision event log (FR-101).

One wildcard pymunk handler records, per pair of world objects, the moment they
start touching. Callbacks only read the arbiter and append to Python containers;
they never add, remove or modify bodies or shapes.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

import pymunk

from bouncekit.config import Vec
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

WorldObject = CircleBoundary | Ball


EventKind = Literal["collision", "escape", "spawn", "destroy", "timer", "condition"]


@dataclass(frozen=True)
class Event:
    """Something happened in the simulation (FR-201); immutable.

    Attributes:
        kind: ``"collision"``, ``"escape"``, ``"spawn"``, ``"destroy"``, ``"timer"`` or
            ``"condition"``.
        step: 1-based global physics step in which the event happened (for a
            collision: at whose end contact had begun).
        frame: video frame being simulated (frame index before it advanced).
        time: ``step / (fps * substeps)`` seconds.
        objects: collision: the two objects, in pymunk shape order; escape:
            ``(ring, ball)``; spawn/destroy: ``(obj,)``; timer/condition: ``()``.
        speed: px/s. Collision: relative velocity along the contact normal before
            the impact; escape/spawn/destroy: the ball's speed (0.0 for a ring);
            timer/condition: ``None``.
        position: contact point or object centre in screen pixels; ``None`` for
            timer/condition events.
    """

    kind: EventKind
    step: int
    frame: int
    time: float
    objects: tuple[WorldObject, ...]
    speed: float | None
    position: Vec | None


CollisionEvent = Event
"""M1 name of :class:`Event`, kept so ``CollisionEvent(kind="collision", ...)`` works."""


class EventRecorder:
    """Records ``CollisionEvent``s from a wildcard ``begin``/``separate`` handler.

    A pair of objects is "in contact" while at least one of their shape pairs
    touches; only the transition from no contact to contact records an event.
    Several shape pairs of the same objects beginning in one step (a ball landing
    on a ring seam) merge into one event with the largest speed.
    """

    def __init__(self, rate: int) -> None:
        """``rate`` is physics steps per second (``fps * substeps``)."""
        self.rate = rate
        self.step = 0
        self.frame = 0
        self.owners: dict[pymunk.Shape, tuple[int, WorldObject]] = {}
        self._contacts: dict[tuple[int, int], int] = {}
        self._pending: dict[tuple[int, int], CollisionEvent] = {}

    def install(self, space: pymunk.Space) -> None:
        """Install the wildcard handler on ``space``."""
        space.on_collision(begin=self._begin, separate=self._separate)

    def register(self, index: int, obj: WorldObject, shapes: Iterable[pymunk.Shape]) -> None:
        """Map ``shapes`` to ``obj``, the scene's ``index``-th object."""
        for shape in shapes:
            self.owners[shape] = (index, obj)

    def _pair(self, arb: pymunk.Arbiter) -> tuple[tuple[int, int], WorldObject, WorldObject] | None:
        sa, sb = arb.shapes
        a = self.owners.get(sa)
        b = self.owners.get(sb)
        if a is None or b is None or a[0] == b[0]:
            return None
        key = (a[0], b[0]) if a[0] < b[0] else (b[0], a[0])
        return key, a[1], b[1]

    def _begin(self, arb: pymunk.Arbiter, space: pymunk.Space, data: Any) -> None:
        pair = self._pair(arb)
        if pair is None:
            return
        key, obj_a, obj_b = pair
        count = self._contacts.get(key, 0)
        self._contacts[key] = count + 1
        pending = self._pending.get(key)
        if count > 0 and pending is None:
            return  # already touching through another shape pair
        body_a, body_b = arb.bodies
        points = arb.contact_point_set.points
        if points:
            pa, pb = points[0].point_a, points[0].point_b
            point = pymunk.Vec2d((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)
        else:
            point = (body_a.position + body_b.position) / 2
        rel = body_a.velocity_at_world_point(point) - body_b.velocity_at_world_point(point)
        speed = abs(rel.dot(arb.normal))
        if pending is not None:
            if pending.speed is None or speed > pending.speed:
                self._pending[key] = CollisionEvent(
                    "collision", pending.step, pending.frame, pending.time,
                    pending.objects, speed, (point.x, point.y),
                )  # fmt: skip
            return
        self._pending[key] = CollisionEvent(
            "collision", self.step, self.frame, self.step / self.rate,
            (obj_a, obj_b), speed, (point.x, point.y),
        )  # fmt: skip

    def _separate(self, arb: pymunk.Arbiter, space: pymunk.Space, data: Any) -> None:
        pair = self._pair(arb)
        if pair is None:
            return
        key = pair[0]
        count = self._contacts.get(key, 0) - 1
        if count > 0:
            self._contacts[key] = count
        else:
            self._contacts.pop(key, None)

    def flush(self) -> list[CollisionEvent]:
        """Return and clear the events recorded during the last step, in order."""
        events = list(self._pending.values())
        self._pending.clear()
        return events
