"""Ball: a dynamic circular body (FR-004, FR-005)."""

import math
from collections.abc import Iterable

import pymunk

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.config import (
    Vec,
    _glow,
    _non_negative_number,
    _positive_number,
    _tags,
    _trail,
    _vec,
)
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
        trail: bool = False,
        glow: float | bool = 0.0,
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
        trail_value = _trail(trail)
        glow_value = _glow(glow)

        mass = math.pi * self._radius**2
        self.body = pymunk.Body(mass, pymunk.moment_for_circle(mass, 0, self._radius))
        self.body.position = position
        self.body.velocity = initial_velocity
        self.shape = pymunk.Circle(self.body, self._radius)
        self.shape.elasticity = elasticity_value
        self.shape.friction = 0.0
        space.add(self.body, self.shape)
        self.alive: bool = True
        """``False`` once the ball has been destroyed (removed from its scene)."""
        self.generation: int = 0
        """How many splits produced this ball: 0 for ``add_ball``/spawn, parent + 1 for a split."""
        self.constant_speed: bool = False
        """Whether the scene rescales the velocity to ``target_speed`` after every step (FR-212)."""
        self.target_speed: float = 0.0
        """Speed held in constant-speed mode (initial ``|velocity|``, updated by set_velocity)."""
        self.trail: bool = trail_value
        """Whether the ball leaves a fading trail (FR-303); visual only."""
        self.glow: float = glow_value
        """Glow intensity in [0, 4], 0 = no glow (FR-304); visual only."""

    def set_radius(self, radius: float) -> None:
        """Change the radius, keeping density 1 (mass = pi * r^2, moment updated).

        Meant to be called between physics steps (the scene applies it after dispatch).

        Raises:
            ConfigError: if ``radius`` is not a positive finite number.
        """
        self._radius = _positive_number("radius", radius)
        self.shape.unsafe_set_radius(self._radius)
        mass = math.pi * self._radius**2
        self.body.mass = mass
        self.body.moment = pymunk.moment_for_circle(mass, 0, self._radius)

    def clamp_speed(self, max_speed: float) -> None:
        """Scale the velocity down to ``max_speed`` if it is faster, keeping direction."""
        vx, vy = self.body.velocity
        speed = math.hypot(vx, vy)
        if speed > max_speed:
            scale = max_speed / speed
            self.body.velocity = (vx * scale, vy * scale)

    def renormalize(self) -> None:
        """Rescale the velocity to ``target_speed`` keeping direction; zero stays zero."""
        vx, vy = self.body.velocity
        speed = math.hypot(vx, vy)
        if speed > 0:
            scale = self.target_speed / speed
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
        """Fill colour as an RGB tuple (settable; accepts any colour value)."""
        return self._color

    @color.setter
    def color(self, value: ColorLike) -> None:
        self._color = parse_color(value)

    @property
    def tags(self) -> frozenset[str]:
        """Tags given at creation."""
        return self._tags

    def draw(self, renderer: Renderer, color: Color | None = None) -> None:
        """Draw the ball as a filled circle in ``color`` (default: its colour); reads state only."""
        renderer.circle(self.position, self._radius, self._color if color is None else color)
