"""Off-screen pygame-ce renderer (FR-008, FR-302)."""

import math
from collections.abc import Callable, Sequence

import numpy as np
import pygame
from numpy.typing import NDArray

from bouncekit.colors import Color
from bouncekit.config import Vec
from bouncekit.render.base import GlowArc, GlowDisc, TrailSegment

Floats = NDArray[np.float64]
Mask = NDArray[np.bool_]
Distance = Callable[[Floats, Floats], Floats]

GLOW_SCALE = 4
"""The glow layer is drawn and blurred at 1/GLOW_SCALE resolution (NFR-303)."""


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
        self._trail: pygame.Surface | None = None  # persistent trail layer, lazy
        self._glow: tuple[pygame.Surface, pygame.Surface, pygame.Surface] | None = None

    def clear(self, color: Color) -> None:
        """Fill the whole frame with ``color``."""
        self.surface.fill(color)

    def circle(self, center: Vec, radius: float, color: Color, *, alpha: float = 1.0) -> None:
        """Draw a filled circle with an anti-aliased edge, blended by coverage x ``alpha``."""
        if alpha <= 0:
            return
        cx, cy = center

        def distance(px: Floats, py: Floats) -> Floats:
            return np.hypot(px - cx, py - cy) - radius

        self._fill_distance(
            (cx - radius, cy - radius, cx + radius, cy + radius), distance, color, alpha=alpha
        )

    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None:
        """Draw a line ``width`` pixels thick from ``a`` to ``b`` with round caps.

        Anti-aliased: each pixel's coverage comes from its distance to the segment.
        """
        self._line(a, b, width, color, self.surface)

    def _line(self, a: Vec, b: Vec, width: float, color: Color, target: pygame.Surface) -> None:
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

        self._fill_distance(bbox, distance, color, target=target)

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
        self._arc(center, radius, width, start_degrees, end_degrees, color, self.surface)

    def _arc(
        self,
        center: Vec,
        radius: float,
        width: float,
        start_degrees: float,
        end_degrees: float,
        color: Color,
        target: pygame.Surface,
    ) -> None:
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

        self._fill_distance(bbox, distance, color, near_band, target=target)

    def trails(self, segments: Sequence[TrailSegment], *, keep: float, reset: bool) -> None:
        """Fade the trail layer, draw ``segments`` onto it and max-composite it (FR-302).

        The fade multiplies by ``round(keep * 255) / 255`` and then subtracts 1, so
        every value reaches exactly 0 (multiplication alone stalls above 0).
        """
        layer = self._trail
        if layer is None:
            layer = self._trail = pygame.Surface((self.width, self.height))
            layer.fill((0, 0, 0))
        if reset:
            layer.fill((0, 0, 0))
        elif keep < 1:
            k = max(0, min(255, round(keep * 255)))
            layer.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
            layer.fill((1, 1, 1), special_flags=pygame.BLEND_RGB_SUB)
        for seg in segments:
            self._line(seg.a, seg.b, seg.width, seg.color, layer)
        self.surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_MAX)

    def glow(self, lights: Sequence[GlowDisc | GlowArc], *, blur: float) -> None:
        """Add blurred ``lights`` to the frame (FR-302).

        Lights are drawn at quarter resolution, box-blurred twice with radius
        ``blur / 4`` (close to a gaussian of about ``blur`` px at full size), scaled
        up smoothly and added with saturation.
        """
        if self._glow is None:
            small = (-(-self.width // GLOW_SCALE), -(-self.height // GLOW_SCALE))
            self._glow = (
                pygame.Surface(small),
                pygame.Surface(small),
                pygame.Surface((self.width, self.height)),
            )
        layer, tmp, full = self._glow
        layer.fill((0, 0, 0))
        q = 1 / GLOW_SCALE
        for light in lights:
            color = _scaled(light.color, light.intensity)
            if isinstance(light, GlowDisc):
                cx, cy = light.center
                pygame.draw.circle(layer, color, (cx * q, cy * q), max(1.0, light.radius * q))
            else:
                cx, cy = light.center
                self._arc(
                    (cx * q, cy * q),
                    light.radius * q,
                    max(1.0, light.width * q),
                    light.start_degrees,
                    light.end_degrees,
                    color,
                    layer,
                )
        radius = max(1, round(blur * q))
        pygame.transform.box_blur(layer, radius, dest_surface=tmp)
        pygame.transform.box_blur(tmp, radius, dest_surface=layer)
        pygame.transform.smoothscale(layer, (self.width, self.height), full)
        self.surface.blit(full, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def _fill_distance(
        self,
        bbox: tuple[float, float, float, float],
        distance: Distance,
        color: Color,
        candidates: Callable[[Floats, Floats], Mask] | None = None,
        *,
        alpha: float = 1.0,
        target: pygame.Surface | None = None,
    ) -> None:
        """Blend ``color`` into the pixels in ``bbox`` by their coverage.

        ``distance`` maps pixel-centre coordinates to signed distance from the
        shape's edge (negative inside); coverage is ``clip(0.5 - d, 0, 1)``, a
        one-pixel anti-aliased edge. ``candidates`` optionally limits the exact
        distance evaluation to pixels that can be covered (a cheap pre-filter).
        Coverage is scaled by ``alpha`` (``1.0`` keeps the exact M0 arithmetic);
        ``target`` defaults to the frame surface.
        """
        surface = self.surface if target is None else target
        width, height = surface.get_size()
        x0 = max(math.floor(bbox[0]) - 1, 0)
        y0 = max(math.floor(bbox[1]) - 1, 0)
        x1 = min(math.ceil(bbox[2]) + 2, width)
        y1 = min(math.ceil(bbox[3]) + 2, height)
        if x0 >= x1 or y0 >= y1:
            return
        px, py = np.meshgrid(
            np.arange(x0, x1, dtype=np.float64) + 0.5,
            np.arange(y0, y1, dtype=np.float64) + 0.5,
            indexing="ij",
        )
        mask = np.ones(px.shape, dtype=bool) if candidates is None else candidates(px, py)
        coverage = np.clip(0.5 - distance(px[mask], py[mask]), 0.0, 1.0)
        if alpha != 1.0:
            coverage *= alpha
        covered = coverage > 0
        if not covered.any():
            return
        mask[mask] = covered
        weight = coverage[covered][:, None]
        pixels = pygame.surfarray.pixels3d(surface)
        region = pixels[x0:x1, y0:y1]
        blended = region[mask] * (1.0 - weight) + np.asarray(color, dtype=np.float64) * weight
        region[mask] = np.rint(blended).astype(np.uint8)
        del region, pixels  # release the surface lock

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        return pygame.image.tobytes(self.surface, "RGB")


def _scaled(color: Color, intensity: float) -> Color:
    """``color`` x ``intensity`` per channel, rounded and clamped to 0..255."""
    r, g, b = (max(0, min(255, round(c * intensity))) for c in color)
    return (r, g, b)
