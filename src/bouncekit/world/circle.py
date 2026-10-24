"""CircleBoundary: a ring of segments on a kinematic body (FR-003)."""

import math
from collections.abc import Iterable

import pymunk

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.config import (
    Vec,
    _finite_number,
    _non_negative_number,
    _positive_number,
    _tags,
    _vec,
)
from bouncekit.errors import ConfigError
from bouncekit.render.base import Renderer


class CircleBoundary:
    """Handle to a circular boundary ("ring").

    The ring is ``segments`` straight segments (radius ``thickness / 2``) on a
    kinematic body at ``center``. Segments whose angular midpoint lies within
    ``gap_degrees`` centred on local angle 0 (pointing +x) are omitted. The body
    rotates at ``angular_velocity`` degrees per second; positive is clockwise on
    screen because +y points down.
    """

    def __init__(
        self,
        space: pymunk.Space,
        *,
        center: Vec,
        radius: float,
        thickness: float = 8.0,
        color: ColorLike = "#ffffff",
        gap_degrees: float = 0.0,
        angular_velocity: float = 0.0,
        segments: int = 128,
        elasticity: float = 1.0,
        tags: Iterable[str] = (),
    ) -> None:
        """Validate the options, build the segments and add them to ``space``.

        Raises:
            ConfigError: if any option is invalid.
        """
        position = _vec("center", center)
        self._radius = _positive_number("radius", radius)
        self._thickness = _positive_number("thickness", thickness)
        gap = _non_negative_number("gap_degrees", gap_degrees)
        if gap >= 360:
            raise ConfigError(f"gap_degrees must be in [0, 360); got {gap_degrees!r}")
        self._gap_degrees = gap
        spin = _finite_number("angular_velocity", angular_velocity)
        if type(segments) is not int or segments < 8:
            raise ConfigError(f"segments must be an integer >= 8; got {segments!r}")
        elasticity_value = _non_negative_number("elasticity", elasticity)
        self._color = parse_color(color)
        self._tags = _tags(tags)

        self.body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.body.position = position
        self.body.angular_velocity = math.radians(spin)
        self._segment_count = segments
        self.shapes: list[pymunk.Segment] = self._build_segments(segments, elasticity_value)
        space.add(self.body, *self.shapes)

    def _build_segments(self, n: int, elasticity: float) -> list[pymunk.Segment]:
        angles = [2 * math.pi * k / n for k in range(n)]
        points = [(self._radius * math.cos(t), self._radius * math.sin(t)) for t in angles]

        def present(k: int) -> bool:
            mid = math.degrees(2 * math.pi * ((k % n) + 0.5) / n)
            mid = (mid + 180) % 360 - 180  # normalise to [-180, 180)
            return not abs(mid) < self._gap_degrees / 2

        shapes: list[pymunk.Segment] = []
        for k in range(n):
            if not present(k):
                continue
            a, b = points[k], points[(k + 1) % n]
            seg = pymunk.Segment(self.body, a, b, self._thickness / 2)
            seg.elasticity = elasticity
            seg.friction = 0.0
            prev = points[(k - 1) % n] if present(k - 1) else a
            nxt = points[(k + 2) % n] if present(k + 1) else b
            seg.set_neighbors(prev, nxt)
            shapes.append(seg)
        return shapes

    @property
    def center(self) -> Vec:
        """Centre in screen pixels."""
        x, y = self.body.position
        return (x, y)

    @property
    def radius(self) -> float:
        """Radius of the ring's centre line in pixels."""
        return self._radius

    @property
    def thickness(self) -> float:
        """Line thickness in pixels (segment radius is half of this)."""
        return self._thickness

    @property
    def gap_degrees(self) -> float:
        """Angular size of the opening in degrees."""
        return self._gap_degrees

    @property
    def angle_degrees(self) -> float:
        """Current rotation in degrees (positive = clockwise on screen)."""
        return math.degrees(self.body.angle)

    @property
    def color(self) -> Color:
        """Line colour as an RGB tuple."""
        return self._color

    @property
    def tags(self) -> frozenset[str]:
        """Tags given at creation."""
        return self._tags

    def draw(self, renderer: Renderer) -> None:
        """Draw the ring as a smooth arc at the current rotation (reads state only).

        The arc spans the present segments' end points, so the drawn gap matches the
        physics gap (the chord polygon is within a fraction of a pixel of the arc).
        """
        if not self.shapes:
            return
        rotation = math.degrees(self.body.angle)
        if len(self.shapes) == self._segment_count:
            start, end = rotation, rotation + 360.0
        else:
            first, last = self.shapes[0].a, self.shapes[-1].b
            start = rotation + math.degrees(math.atan2(first.y, first.x)) % 360
            end = rotation + math.degrees(math.atan2(last.y, last.x)) % 360
            if end <= start:
                end += 360.0
        renderer.arc(self.center, self._radius, self._thickness, start, end, self._color)
