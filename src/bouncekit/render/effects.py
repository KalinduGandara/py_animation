"""Effect state kept only for drawing (FR-301, FR-303).

Nothing here touches pymunk, ``scene.rng`` or ``scene.events``; the scene owns one
:class:`Effects` and updates it keyed on ``scene.frame``, never on how often
``draw`` is called.
"""

import math
from collections.abc import Sequence

from bouncekit.colors import Color
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


class Effects:
    """Per-scene effect state.

    Attributes:
        trail_pos: object index -> position at the last trail update (lookup only).
        trail_frame: frame of the last trail update, ``None`` before the first.
        trail_active: last frame that had a live trail ball, ``None`` before any.
    """

    def __init__(self) -> None:
        self.trail_pos: dict[int, Vec] = {}
        self.trail_frame: int | None = None
        self.trail_active: int | None = None

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
