"""ActionContext: what a rule handler sees and can do (FR-203)."""

import random
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from bouncekit.actions import Play, Spawn, Split, Target, Value, play, spawn, split
from bouncekit.colors import ColorLike, parse_color
from bouncekit.config import Vec, _vec
from bouncekit.errors import ConfigError
from bouncekit.events import Event, WorldObject
from bouncekit.rules.commands import BallSpec, DestroyCmd, SpawnCmd, SplitCmd
from bouncekit.sound import Source
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["ActionContext"]


class ActionContext:
    """Passed to every handler as ``ctx``; one per (event, rule).

    Methods that change the world (``destroy``, ``split``, ``spawn``) only queue a
    command: the change is applied after the step's dispatch, never while handlers
    run. ``play`` produces a note trigger immediately (audio only). Bad arguments
    raise ``ConfigError`` at the call.

    Attributes:
        scene: the scene being simulated.
        event: the event being dispatched.
        a: the rule's first subject (collision: the object carrying ``tag_a``;
            destroy: the destroyed object), or ``None``.
        b: the rule's second subject (collision: the object carrying ``tag_b``), or
            ``None``.
        rng: ``scene.rng``; use it for any randomness so renders stay deterministic.
        time: ``event.time`` in seconds.
    """

    def __init__(
        self, scene: "Scene", event: Event, a: WorldObject | None, b: WorldObject | None
    ) -> None:
        """Create a context for dispatching ``event`` with subjects ``a`` and ``b``."""
        self.scene = scene
        self.event = event
        self.a = a
        self.b = b
        self.rng: random.Random = scene.rng
        self.time: float = event.time

    def _resolve(self, target: Target) -> WorldObject | None:
        if target == "a":
            return self.a
        if target == "b":
            return self.b
        return target

    def destroy(self, obj: WorldObject) -> None:
        """Queue removal of ``obj`` (a ball or ring) after dispatch.

        Raises:
            ConfigError: if ``obj`` is not a ball or ring handle.
        """
        if not isinstance(obj, Ball | CircleBoundary):
            raise ConfigError(f"obj must be a ball or ring handle; got {obj!r}")
        self.scene._queue.append(DestroyCmd(obj))

    def split(
        self,
        ball: Ball,
        *,
        into: int = 2,
        spread_degrees: float = 30.0,
        radius_scale: float = 1.0,
        max_total: int | None = None,
    ) -> None:
        """Queue a split of ``ball``; options and refusal rules as ``A.split`` (FR-206).

        A ring is accepted and ignored (no-op).

        Raises:
            ConfigError: for bad options, or if ``ball`` is not a ball or ring handle.
        """
        action = split(
            into=into, spread_degrees=spread_degrees, radius_scale=radius_scale, max_total=max_total
        )
        if not isinstance(ball, Ball | CircleBoundary):
            raise ConfigError(f"ball must be a ball handle; got {ball!r}")
        if isinstance(ball, Ball):
            self._split_action(ball, action)

    def _split_action(self, ball: Ball, action: Split) -> None:
        self.scene._queue.append(
            SplitCmd(
                ball, action.into, action.spread_degrees, action.radius_scale, action.max_total
            )
        )

    def spawn(
        self,
        *,
        pos: Value[Vec],
        radius: float,
        velocity: Value[Vec] = (0.0, 0.0),
        count: int = 1,
        color: Value[ColorLike] = "#ffffff",
        tags: Iterable[str] = ("ball",),
        elasticity: float = 1.0,
        max_total: int | None = None,
    ) -> None:
        """Queue ``count`` new balls; options and refusal rules as ``A.spawn`` (FR-207).

        Callable ``pos``/``velocity``/``color`` are evaluated now, per ball, in ball order.

        Raises:
            ConfigError: for bad options or a callable returning an invalid value.
        """
        self._spawn_action(
            spawn(
                pos=pos,
                radius=radius,
                velocity=velocity,
                count=count,
                color=color,
                tags=tags,
                elasticity=elasticity,
                max_total=max_total,
            )
        )

    def _spawn_action(self, action: Spawn) -> None:
        specs: list[BallSpec] = []
        step = 2 * action.radius + 1
        for i in range(action.count):
            x, y = _vec("pos", self._eval(action.pos))
            velocity = _vec("velocity", self._eval(action.velocity))
            color = parse_color(self._eval(action.color))  # type: ignore[arg-type]
            offset = (i - (action.count - 1) / 2) * step
            specs.append(
                BallSpec(
                    (x + offset, y), action.radius, velocity, color, action.tags, action.elasticity
                )
            )
        self.scene._queue.append(SpawnCmd(tuple(specs), action.max_total))

    def _eval(self, value: object) -> object:
        if callable(value):
            fn: Callable[[ActionContext], object] = value
            return fn(self)
        return value

    def play(self, source: Source, *, gain: float = 1.0) -> None:
        """Trigger ``source`` now, subject to the audio trigger policy (FR-106, FR-211).

        Calls with an equal ``(source, gain)`` share one retrigger timer per subject
        ``a``, like a single ``A.play`` action.

        Raises:
            ConfigError: if ``source`` is not a sound source or ``gain`` is negative.
        """
        action = play(source, gain=gain)
        self._play_action(self.scene._engine.shared_play(action))

    def _play_action(self, action: Play) -> None:
        self.scene._trigger(action, self.event, self.a)
