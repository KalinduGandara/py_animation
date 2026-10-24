"""Scene: configuration, seeded RNG, object registry, fixed-step loop and frames."""

import random
from collections.abc import Iterable, Iterator

import pymunk

from bouncekit.colors import ColorLike
from bouncekit.config import SceneConfig, Vec
from bouncekit.render.base import Renderer
from bouncekit.render.pygame_renderer import PygameRenderer
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

WorldObject = CircleBoundary | Ball

# Overrides (``seed``, ``duration``) set by the CLI while it executes a scene script.
# ``Scene.__init__`` applies them before creating ``rng``.
_overrides: dict[str, object] = {}


class Scene:
    """One video: settings, a pymunk space and the objects in it.

    Coordinates are screen pixels, origin top-left, +y down. The simulation
    advances only through :meth:`step_frame`, by ``substeps`` fixed steps of
    ``1 / (fps * substeps)`` seconds; it never reads wall-clock time.
    """

    def __init__(
        self,
        *,
        width: int = 1080,
        height: int = 1920,
        fps: int = 60,
        duration: float = 60.0,
        seed: int = 0,
        background: ColorLike = "#000000",
        gravity: Vec = (0.0, 900.0),
        substeps: int = 8,
        max_speed: float = 4000.0,
    ) -> None:
        """Validate the settings and create an empty world.

        Raises:
            ConfigError: if any setting is invalid.
        """
        options: dict[str, object] = {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "seed": seed,
            "background": background,
            "gravity": gravity,
            "substeps": substeps,
            "max_speed": max_speed,
        }
        options.update(_overrides)
        self.config: SceneConfig = SceneConfig(**options)  # type: ignore[arg-type]
        self.rng: random.Random = random.Random(self.config.seed)
        self.frame: int = 0
        self.total_frames: int = round(self.config.duration * self.config.fps)
        self.space = pymunk.Space()
        self.space.gravity = self.config.gravity
        self.space.iterations = 10
        self.space.damping = 1.0
        self._dt = 1.0 / (self.config.fps * self.config.substeps)
        self._objects: list[WorldObject] = []

    @property
    def time(self) -> float:
        """Simulated time in seconds (``frame / fps``)."""
        return self.frame / self.config.fps

    @property
    def objects(self) -> tuple[WorldObject, ...]:
        """All world objects in insertion order."""
        return tuple(self._objects)

    def add_circle(
        self,
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
    ) -> CircleBoundary:
        """Add a ring boundary; see :class:`CircleBoundary`.

        ``angular_velocity`` is in degrees per second, positive = clockwise.

        Raises:
            ConfigError: if any option is invalid.
        """
        ring = CircleBoundary(
            self.space,
            center=center,
            radius=radius,
            thickness=thickness,
            color=color,
            gap_degrees=gap_degrees,
            angular_velocity=angular_velocity,
            segments=segments,
            elasticity=elasticity,
            tags=tags,
        )
        self._objects.append(ring)
        return ring

    def add_ball(
        self,
        *,
        pos: Vec,
        radius: float,
        velocity: Vec = (0.0, 0.0),
        elasticity: float = 1.0,
        color: ColorLike = "#ffffff",
        tags: Iterable[str] = (),
    ) -> Ball:
        """Add a dynamic ball; its speed is clamped to ``config.max_speed``.

        Raises:
            ConfigError: if any option is invalid.
        """
        ball = Ball(
            self.space,
            pos=pos,
            radius=radius,
            velocity=velocity,
            elasticity=elasticity,
            color=color,
            tags=tags,
            max_speed=self.config.max_speed,
        )
        self._objects.append(ball)
        return ball

    def step_frame(self) -> None:
        """Advance the simulation by one frame (``substeps`` fixed physics steps)."""
        for _ in range(self.config.substeps):
            self.space.step(self._dt)
        self.frame += 1

    def draw(self, renderer: Renderer) -> None:
        """Draw the background and every object, in insertion order.

        Drawing only reads world state; it never changes the simulation.
        """
        renderer.clear(self.config.background)
        for obj in self._objects:
            obj.draw(renderer)

    def frames(self) -> Iterator[bytes]:
        """Yield each remaining frame as RGB24 bytes, then advance one frame.

        The first frame yielded shows the current state (frame 0 for a new scene);
        frames are produced until ``frame`` reaches ``total_frames``. Nothing is
        reset, so a scene is meant to be simulated once.
        """
        renderer = PygameRenderer(self.config.width, self.config.height)
        while self.frame < self.total_frames:
            self.draw(renderer)
            yield renderer.to_rgb_bytes()
            self.step_frame()
