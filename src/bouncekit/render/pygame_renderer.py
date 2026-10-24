"""Off-screen pygame-ce renderer (FR-008)."""

import math

import pygame

from bouncekit.colors import Color
from bouncekit.config import Vec


class PygameRenderer:
    """Renderer that draws into an off-screen ``pygame.Surface``.

    Needs no display; pygame's software drawing is deterministic, so the same
    calls always produce the same bytes.
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
        pygame.draw.aacircle(self.surface, color, center, radius)

    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None:
        """Draw a line ``width`` pixels thick from ``a`` to ``b`` with round caps.

        The body is a filled quad with anti-aliased edges; each end gets a filled
        circle of radius ``width / 2``, so consecutive lines join seamlessly.
        """
        half = width / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length > 0:
            nx, ny = -dy / length * half, dx / length * half
            quad = [
                (a[0] + nx, a[1] + ny),
                (b[0] + nx, b[1] + ny),
                (b[0] - nx, b[1] - ny),
                (a[0] - nx, a[1] - ny),
            ]
            pygame.draw.polygon(self.surface, color, quad)
            pygame.draw.aalines(self.surface, color, True, quad)
        self.circle(a, half, color)
        self.circle(b, half, color)

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        return pygame.image.tobytes(self.surface, "RGB")
