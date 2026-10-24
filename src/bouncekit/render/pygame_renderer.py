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
Layer = NDArray[np.float32]
Box = tuple[int, int, int, int]  # x0, x1, y0, y1 (half-open pixel ranges)
Mask = NDArray[np.bool_]
Distance = Callable[[Floats, Floats], Floats]

GLOW_SCALE = 4
"""The glow layer is drawn and blurred at 1/GLOW_SCALE resolution (NFR-303)."""

TRAIL_FLOOR = 1 / 4096
"""Subtracted from the float trail layer after each fade so values reach exactly 0.

It lowers a fading value by at most ``TRAIL_FLOOR / (1 - keep)``, which stays below
one output level for trails up to ~200 s at 60 fps, and keeps the layer free of
denormals.
"""


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
        # Persistent trail layer (lazy): float32 (H, W, 3) values in 0..255, plus a
        # uint8 buffer and a surface that aliases it for the max-composite.
        self._trail: tuple[Layer, NDArray[np.uint8], pygame.Surface] | None = None
        self._trail_box: Box | None = None  # every non-zero layer pixel is inside
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
        self._fill_distance(_line_bbox(a, b, width), _line_distance(a, b, width), color)

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

        The layer is kept in float32 so the fade is exactly ``value * keep`` per call
        (an 8-bit layer cannot fade slowly: it either stalls or loses at least one
        level per frame). ``TRAIL_FLOOR`` is then subtracted (clamped at 0), and the
        composite truncates to 8 bits, so a value is 0 on screen once it is below 1,
        i.e. after at most ``ceil(log(1/255) / log(keep))`` calls. Only the box that
        holds every pixel drawn since the last reset is touched (the rest is 0).
        """
        if self._trail is None:
            pixels = np.empty((self.height, self.width, 3), dtype=np.uint8)
            image = pygame.image.frombuffer(pixels, (self.width, self.height), "RGB")
            self._trail = (np.zeros((self.height, self.width, 3), np.float32), pixels, image)
            self._trail_box = None
            reset = False
        layer, pixels, image = self._trail
        box = self._trail_box
        if reset and box is not None:
            layer[box[2] : box[3], box[0] : box[1]] = 0.0
            box = None
        elif box is not None and keep < 1:
            area = layer[box[2] : box[3], box[0] : box[1]]
            np.multiply(area, np.float32(keep), out=area)
            np.subtract(area, np.float32(TRAIL_FLOOR), out=area)
            np.maximum(area, np.float32(0.0), out=area)
        for seg in segments:
            drawn = self._trail_line(seg, layer)
            if drawn is not None:
                box = drawn if box is None else _union(box, drawn)
        self._trail_box = box
        if box is None:
            return
        x0, x1, y0, y1 = box
        # Truncation to 8 bits: layer values are always in 0..255.
        np.copyto(pixels[y0:y1, x0:x1], layer[y0:y1, x0:x1], casting="unsafe")
        rect = pygame.Rect(x0, y0, x1 - x0, y1 - y0)
        self.surface.blit(image, rect, area=rect, special_flags=pygame.BLEND_RGB_MAX)

    def _trail_line(self, seg: TrailSegment, layer: Layer) -> Box | None:
        """Blend one round-capped segment into the float trail ``layer`` by coverage.

        Returns the ``(x0, x1, y0, y1)`` box it touched, or ``None``.
        """
        bbox = _line_bbox(seg.a, seg.b, seg.width)
        distance = _line_distance(seg.a, seg.b, seg.width)
        found = self._coverage(bbox, distance, None, 1.0, self.width, self.height)
        if found is None:
            return None
        x0, x1, y0, y1, mask, weight = found
        region = layer[y0:y1, x0:x1].transpose(1, 0, 2)  # (x, y, 3) view, like pixels3d
        color = np.asarray(seg.color, dtype=np.float32)
        w = weight.astype(np.float32)
        region[mask] = region[mask] * (np.float32(1.0) - w) + color * w
        return (x0, x1, y0, y1)

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
        found = self._coverage(bbox, distance, candidates, alpha, *surface.get_size())
        if found is None:
            return
        x0, x1, y0, y1, mask, weight = found
        pixels = pygame.surfarray.pixels3d(surface)
        region = pixels[x0:x1, y0:y1]
        blended = region[mask] * (1.0 - weight) + np.asarray(color, dtype=np.float64) * weight
        region[mask] = np.rint(blended).astype(np.uint8)
        del region, pixels  # release the surface lock

    @staticmethod
    def _coverage(
        bbox: tuple[float, float, float, float],
        distance: Distance,
        candidates: Callable[[Floats, Floats], Mask] | None,
        alpha: float,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int, Mask, Floats] | None:
        """Covered pixels of a shape: ``(x0, x1, y0, y1, mask, weight)`` or ``None``.

        ``mask`` is indexed ``[x - x0, y - y0]``; ``weight`` is the (n, 1) coverage of
        the masked pixels, in mask order.
        """
        x0 = max(math.floor(bbox[0]) - 1, 0)
        y0 = max(math.floor(bbox[1]) - 1, 0)
        x1 = min(math.ceil(bbox[2]) + 2, width)
        y1 = min(math.ceil(bbox[3]) + 2, height)
        if x0 >= x1 or y0 >= y1:
            return None
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
            return None
        mask[mask] = covered
        weight: Floats = coverage[covered][:, None]
        return x0, x1, y0, y1, mask, weight

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        return pygame.image.tobytes(self.surface, "RGB")


def _union(a: Box, b: Box) -> Box:
    """Smallest box containing both ``a`` and ``b``."""
    return (min(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3]))


def _line_bbox(a: Vec, b: Vec, width: float) -> tuple[float, float, float, float]:
    """Bounding box of a round-capped segment ``width`` px thick."""
    half = width / 2
    return (
        min(a[0], b[0]) - half,
        min(a[1], b[1]) - half,
        max(a[0], b[0]) + half,
        max(a[1], b[1]) + half,
    )


def _line_distance(a: Vec, b: Vec, width: float) -> Distance:
    """Signed distance to a round-capped segment ``width`` px thick."""
    half = width / 2
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length_sq = dx * dx + dy * dy

    def distance(px: Floats, py: Floats) -> Floats:
        if length_sq == 0:
            return np.hypot(px - ax, py - ay) - half
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / length_sq, 0.0, 1.0)
        return np.hypot(px - (ax + t * dx), py - (ay + t * dy)) - half

    return distance


def _scaled(color: Color, intensity: float) -> Color:
    """``color`` x ``intensity`` per channel, rounded and clamped to 0..255."""
    r, g, b = (max(0, min(255, round(c * intensity))) for c in color)
    return (r, g, b)
