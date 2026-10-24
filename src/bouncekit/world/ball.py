"""Ball: a dynamic circular body (FR-004, FR-005)."""

import math
from collections.abc import Iterable

import pymunk

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.config import Vec, _non_negative_number, _positive_number, _tags, _vec
from bouncekit.render.base import Renderer


class Ball:
    """Handle to a simulated ball.

    The ball is a dynamic pymunk body (density 1, so mass = pi * r^2) with a circle
    shape of zero friction. The owning scene clamps its speed to ``max_speed``
    after every physics step. ``body`` and ``shape`` are exposed as an escape
    hatch to pymunk.
    """

    def __init__(
        self,
        space: pymunk.Space,
        *,
        pos: Vec,
        radius: float,
        velocity: Vec = (0.0, 0.0),
        elasticity: float = 1.0,
        color: ColorLike = "#ffffff",
        tags: Iterable[str] = (),
    ) -> None:
        """Validate the options, create the body and shape, and add them to ``space``.

        Raises:
            ConfigError: if any option is invalid.
        """
        position = _vec("pos", pos)
        self._radius = _positive_number("radius", radius)
        initial_velocity = _vec("velocity", velocity)
        elasticity_value = _non_negative_number("elasticity", elasticity)
        self._color = parse_color(color)
        self._tags = _tags(tags)

        mass = math.pi * self._radius**2
        self.body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, self._radius))
        self.body.position = position
        self.body.velocity = initial_velocity
        self.shape = pymunk.Circle(self.body, self._radius)
        self.shape.elasticity = elasticity_value
        self.shape.friction = 0.0
        space.add(self.body, self.shape)

    def clamp_speed(self, max_speed: float) -> None:
        """Scale the velocity down to ``max_speed`` if it is faster, keeping direction."""
        vx, vy = self.body.velocity
        speed = math.hypot(vx, vy)
        if speed > max_speed:
            scale = max_speed / speed
            self.body.velocity = (vx * scale, vy * scale)

    @property
    def position(self) -> Vec:
        """Centre in screen pixels."""
        x, y = self.body.position
        return (x, y)

    @position.setter
    def position(self, value: Vec) -> None:
        self.body.position = _vec("position", value)

    @property
    def velocity(self) -> Vec:
        """Velocity in pixels per second."""
        vx, vy = self.body.velocity
        return (vx, vy)

    @velocity.setter
    def velocity(self, value: Vec) -> None:
        self.body.velocity = _vec("velocity", value)

    @property
    def radius(self) -> float:
        """Radius in pixels."""
        return self._radius

    @property
    def color(self) -> Color:
        """Fill colour as an RGB tuple."""
        return self._color

    @property
    def tags(self) -> frozenset[str]:
        """Tags given at creation."""
        return self._tags

    def draw(self, renderer: Renderer) -> None:
        """Draw the ball as a filled circle (reads state only)."""
        renderer.circle(self.position, self._radius, self._color)
