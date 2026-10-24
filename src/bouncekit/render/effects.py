"""Effect state kept only for drawing (FR-301, FR-303, FR-305, FR-306).

Nothing here touches pymunk, ``scene.rng`` or ``scene.events``; the scene owns one
:class:`Effects` and updates it keyed on ``scene.frame``, never on how often
``draw`` is called.
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from bouncekit.colors import Color, HueCycle
from bouncekit.config import Vec
from bouncekit.render.base import TrailSegment

TrailBall = tuple[int, Vec, float, Color]
"""(object index, position, radius, base colour) of one live trail ball."""


def fade_frames(keep: float) -> int:
    """Calls after which a trail layer faded by ``keep`` is black (FR-302 bound)."""
    if keep <= 0:
        return 1
    if keep >= 1:
        return 255
    return math.ceil(math.log(1 / 255) / math.log(keep)) + 255


@dataclass(eq=False)
class Particle:
    """One impact particle (visual only).

    ``age`` counts frames since it was first drawn; it is removed at ``age >= life``.
    ``damp`` is the per-frame velocity factor ``exp(-drag / fps)``.
    """

    x: float
    y: float
    vx: float
    vy: float
    age: int
    life: int
    size: float
    color: Color
    damp: float


class Effects:
    """Per-scene effect state.

    Attributes:
        trail_pos: object index -> position at the last trail update (lookup only).
        trail_frame: frame of the last trail update, ``None`` before the first.
        trail_active: last frame that had a live trail ball, ``None`` before any.
        particles: live particles in creation order.
        pending: particles created during the current frame (appended by ``advance``).
        hue_index: hue-cycle mode -> balls coloured with it so far (lookup only).
        burst_hue: hue-cycle mode -> particle bursts coloured with it (lookup only).
    """

    def __init__(self) -> None:
        self.trail_pos: dict[int, Vec] = {}
        self.trail_frame: int | None = None
        self.trail_active: int | None = None
        self.particles: list[Particle] = []
        self.pending: list[Particle] = []
        self.hue_index: dict[HueCycle, int] = {}
        self.burst_hue: dict[HueCycle, int] = {}

    def next_hue(self, mode: HueCycle, *, burst: bool = False) -> Color:
        """The next colour of ``mode`` for a ball (or, with ``burst``, a particle burst)."""
        counters = self.burst_hue if burst else self.hue_index
        k = counters.get(mode, 0)
        counters[mode] = k + 1
        return mode.color_at(k)

    def burst(
        self,
        rng: random.Random,
        *,
        pos: Vec,
        count: int,
        speed: float,
        lifetime: float,
        size: float,
        color: Color,
        drag: float,
        fps: int,
        capacity: int,
    ) -> None:
        """Queue up to ``count`` particles at ``pos`` (FR-305).

        Kept: ``min(count, capacity - live - pending)``. Per kept particle in order,
        draws ``angle = uniform(0, 2 pi)`` then ``speed * uniform(0.4, 1.0)`` from ``rng``.
        """
        n = min(count, capacity - len(self.particles) - len(self.pending))
        if n <= 0:
            return
        life = max(1, round(lifetime * fps))
        damp = math.exp(-drag / fps)
        x, y = pos
        for _ in range(n):
            phi = rng.uniform(0, 2 * math.pi)
            sp = speed * rng.uniform(0.4, 1.0)
            self.pending.append(
                Particle(x, y, sp * math.cos(phi), sp * math.sin(phi), 0, life, size, color, damp)
            )

    def advance(self, fps: int) -> None:
        """Advance live particles one frame, drop expired ones, then add the pending ones."""
        live: list[Particle] = []
        for p in self.particles:
            p.vx *= p.damp
            p.vy *= p.damp
            p.x += p.vx / fps
            p.y += p.vy / fps
            p.age += 1
            if p.age < p.life:
                live.append(p)
        live.extend(self.pending)
        self.particles = live
        self.pending = []

    def trail_update(
        self, balls: Sequence[TrailBall], frame: int, keep: float
    ) -> tuple[list[TrailSegment], float, bool] | None:
        """Decide this draw's ``renderer.trails`` arguments and update the bookkeeping.

        Returns ``(segments, keep, reset)`` or ``None`` when no trail call is needed:
        no live trail ball and the layer has fully faded since the last one (or
        trails were never used). A redraw of ``trail_frame`` passes ``keep=1.0`` and
        no segments; the frame after it fades by ``keep`` and draws one segment per
        ball from its previous position; any other frame resets the layer and draws
        dots (FR-303).
        """
        if not balls and (
            self.trail_active is None or frame - self.trail_active > fade_frames(keep)
        ):
            return None
        if self.trail_frame == frame:
            return [], 1.0, False
        reset = self.trail_frame is None or self.trail_frame != frame - 1
        previous = {} if reset else self.trail_pos
        segments = [
            TrailSegment(previous.get(index, pos), pos, 2 * radius, color)
            for index, pos, radius, color in balls
        ]
        self.trail_pos = {index: pos for index, pos, _, _ in balls}
        self.trail_frame = frame
        if balls:
            self.trail_active = frame
        return segments, keep, reset
