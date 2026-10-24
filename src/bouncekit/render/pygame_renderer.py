"""Off-screen pygame-ce renderer (FR-008)."""

import math
from collections.abc import Callable

import numpy as np
import pygame
from numpy.typing import NDArray

from bouncekit.colors import Color
from bouncekit.config import Vec

Floats = NDArray[np.float64]
Mask = NDArray[np.bool_]
Distance = Callable[[Floats, Floats], Floats]


class PygameRenderer:
    """Renderer that draws into an off-screen ``pygame.Surface``.

    Needs no display; pygame's software drawing and the numpy coverage maths are
    deterministic, so the same calls always produce the same bytes.
    """

    def __init__(self, width: int, height: int) -> None:
        """Create a ``width`` x ``height`` RGB surface."""
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))

    def clear(self, color: Color) -> None:
        """Fill the whole frame with ``color``."""
        self.surface.fill(color)

    def circle(self, center: Vec, radius: float, color: Color) -> None:
        """Draw a filled circle with an anti-aliased edge."""
        cx, cy = center

        def distance(px: Floats, py: Floats) -> Floats:
            return np.hypot(px - cx, py - cy) - radius

        self._fill_distance((cx - radius, cy - radius, cx + radius, cy + radius), distance, color)

    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None:
        """Draw a line ``width`` pixels thick from ``a`` to ``b`` with round caps.

        Anti-aliased: each pixel's coverage comes from its distance to the segment.
        """
        half = width / 2
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        length_sq = dx * dx + dy * dy
        bbox = (
            min(ax, b[0]) - half,
            min(ay, b[1]) - half,
            max(ax, b[0]) + half,
            max(ay, b[1]) + half,
        )

        def distance(px: Floats, py: Floats) -> Floats:
            if length_sq == 0:
                return np.hypot(px - ax, py - ay) - half
            t = np.clip(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
            return np.hypot(px - (ax + t * dx), py - (ay + t * dy)) - half

        self._fill_distance(bbox, distance, color)

    def arc(
        self,
        center: Vec,
        radius: float,
        width: float,
        start_degrees: float,
        end_degrees: float,
        color: Color,
    ) -> None:
        """Draw an anti-aliased band along a circle; see :class:`Renderer`."""
        half = width / 2
        cx, cy = center
        reach = radius + half
        bbox = (cx - reach, cy - reach, cx + reach, cy + reach)
        full = end_degrees - start_degrees >= 360
        start = math.radians(start_degrees)
        span = math.radians(end_degrees - start_degrees)
        caps = [
            (cx + radius * math.cos(t), cy + radius * math.sin(t)) for t in (start, start + span)
        ]

        def near_band(px: Floats, py: Floats) -> Mask:
            # Every covered pixel, caps included, lies within half + 1 of the circle.
            result: Mask = np.abs(np.hypot(px - cx, py - cy) - radius) <= half + 1
            return result

        def distance(px: Floats, py: Floats) -> Floats:
            band = np.abs(np.hypot(px - cx, py - cy) - radius) - half
            if full:
                return band
            # Inside the swept angle the band distance applies; outside it the
            # nearest point is one of the two round caps.
            rel = np.mod(np.arctan2(py - cy, px - cx) - start, 2 * math.pi)
            to_caps = (
                np.minimum(
                    np.hypot(px - caps[0][0], py - caps[0][1]),
                    np.hypot(px - caps[1][0], py - caps[1][1]),
                )
                - half
            )
            result: Floats = np.where(rel <= span, band, to_caps)
            return result

        self._fill_distance(bbox, distance, color, near_band)

    def _fill_distance(
        self,
        bbox: tuple[float, float, float, float],
        distance: Distance,
        color: Color,
        candidates: Callable[[Floats, Floats], Mask] | None = None,
    ) -> None:
        """Blend ``color`` into the pixels in ``bbox`` by their coverage.

        ``distance`` maps pixel-centre coordinates to signed distance from the
        shape's edge (negative inside); coverage is ``clip(0.5 - d, 0, 1)``, a
        one-pixel anti-aliased edge. ``candidates`` optionally limits the exact
        distance evaluation to pixels that can be covered (a cheap pre-filter).
        """
        x0 = max(math.floor(bbox[0]) - 1, 0)
        y0 = max(math.floor(bbox[1]) - 1, 0)
        x1 = min(math.ceil(bbox[2]) + 2, self.width)
        y1 = min(math.ceil(bbox[3]) + 2, self.height)
        if x0 >= x1 or y0 >= y1:
            return
        px, py = np.meshgrid(
            np.arange(x0, x1, dtype=np.float64) + 0.5,
            np.arange(y0, y1, dtype=np.float64) + 0.5,
            indexing="ij",
        )
        mask = np.ones(px.shape, dtype=bool) if candidates is None else candidates(px, py)
        coverage = np.clip(0.5 - distance(px[mask], py[mask]), 0.0, 1.0)
        covered = coverage > 0
        if not covered.any():
            return
        mask[mask] = covered
        alpha = coverage[covered][:, None]
        pixels = pygame.surfarray.pixels3d(self.surface)
        region = pixels[x0:x1, y0:y1]
        blended = region[mask] * (1.0 - alpha) + np.asarray(color, dtype=np.float64) * alpha
        region[mask] = np.rint(blended).astype(np.uint8)
        del region, pixels  # release the surface lock

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        return pygame.image.tobytes(self.surface, "RGB")
