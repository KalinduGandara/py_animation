"""Polygon: a static, solid convex polygon (FR-502)."""

import math
from collections.abc import Iterable, Sequence

import pymunk

from bouncekit.colors import Color, ColorLike, Fixed, ring_color
from bouncekit.config import Vec, _non_negative_number, _tags, _vec
from bouncekit.errors import ConfigError
from bouncekit.render.base import GlowArc, Renderer


def _hull(points: Sequence[Vec]) -> list[Vec]:
    """Convex hull (monotone chain), clockwise on screen (y down), no collinear points."""
    pts = sorted(set(points))

    def cross(o: Vec, a: Vec, b: Vec) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Vec] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Vec] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


class Polygon:
    """Handle to a static, solid convex polygon: the convex hull of ``points``.

    Coordinates are screen pixels. The polygon never moves; balls bounce off its
    edges. It is drawn filled in ``color``.
    """

    glow: float = 0.0
    """Polygons do not glow (kept for the shared draw loop)."""

    def __init__(
        self,
        space: pymunk.Space | None,
        *,
        points: Iterable[Vec],
        color: ColorLike | Fixed = "#ffffff",
        elasticity: float = 1.0,
        tags: Iterable[str] = (),
    ) -> None:
        """Validate the options, build the shape and add it to ``space``.

        With ``space=None`` the polygon is built but not added and stays not
        ``alive`` until its scene adds it (``ctx.add_polygon``).

        Raises:
            ConfigError: if ``points`` is not at least three finite points spanning a
                non-zero area, or another option is invalid.
        """
        try:
            raw = [_vec("points", p) for p in points]
        except (TypeError, ConfigError) as exc:
            message = f"points must be a sequence of (x, y) points; got {points!r}"
            raise ConfigError(message) from exc
        hull = _hull(raw)
        if len(hull) < 3:
            raise ConfigError(f"points must span a non-zero area (>= 3 non-collinear); got {raw!r}")
        self._points: tuple[Vec, ...] = tuple(hull)
        self._color = ring_color(color)
        self._tags = _tags(tags)
        elasticity_value = _non_negative_number("elasticity", elasticity)

        self.body = pymunk.Body(body_type=pymunk.Body.STATIC)
        shape = pymunk.Poly(self.body, list(self._points))
        shape.elasticity = elasticity_value
        shape.friction = 0.0
        self.shapes: list[pymunk.Shape] = [shape]
        if space is not None:
            space.add(self.body, *self.shapes)
        self.alive: bool = space is not None
        """``True`` while the polygon is in its scene."""

    @property
    def points(self) -> tuple[Vec, ...]:
        """Hull vertices in screen pixels, clockwise on screen (y down)."""
        return self._points

    @property
    def center(self) -> Vec:
        """Mean of the vertices in screen pixels."""
        n = len(self._points)
        return (sum(p[0] for p in self._points) / n, sum(p[1] for p in self._points) / n)

    @property
    def color(self) -> Color:
        """Fill colour as an RGB tuple (settable; accepts any colour value)."""
        return self._color

    @color.setter
    def color(self, value: ColorLike | Fixed) -> None:
        self._color = ring_color(value)

    @property
    def tags(self) -> frozenset[str]:
        """Tags given at creation."""
        return self._tags

    def distance(self, point: Vec) -> float:
        """Signed distance from ``point`` to the polygon (negative inside)."""
        x, y = point
        pts = self._points
        inside = -math.inf
        nearest = math.inf
        for k, (ax, ay) in enumerate(pts):
            bx, by = pts[(k + 1) % len(pts)]
            ex, ey = bx - ax, by - ay
            length = math.hypot(ex, ey)
            # Clockwise on screen (y down): the outward normal is (ey, -ex).
            inside = max(inside, ((x - ax) * ey - (y - ay) * ex) / length)
            t = min(max(((x - ax) * ex + (y - ay) * ey) / (length * length), 0.0), 1.0)
            nearest = min(nearest, math.hypot(x - (ax + t * ex), y - (ay + t * ey)))
        return inside if inside < 0 else nearest

    def overlaps(self, pos: Vec, radius: float) -> bool:
        """Whether a circle at ``pos`` of ``radius`` overlaps the polygon."""
        return self.distance(pos) < radius

    def draw(self, renderer: Renderer, color: Color | None = None) -> None:
        """Draw the filled polygon in ``color`` (default: its colour). Reads state only."""
        renderer.polygon(self._points, self._color if color is None else color)

    def glow_light(self, color: Color) -> GlowArc | None:
        """Polygons add no light to the glow layer."""
        return None
