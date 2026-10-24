"""Renderer protocol: the drawing primitives every backend implements (FR-008)."""

from typing import Protocol, runtime_checkable

from bouncekit.colors import Color
from bouncekit.config import Vec


@runtime_checkable
class Renderer(Protocol):
    """A drawing target of ``width`` x ``height`` pixels (origin top-left, +y down).

    World objects draw themselves through these primitives and must only read
    simulation state while doing so.
    """

    width: int
    height: int

    def clear(self, color: Color) -> None:
        """Fill the whole frame with ``color``."""
        ...

    def circle(self, center: Vec, radius: float, color: Color) -> None:
        """Draw a filled circle with an anti-aliased edge."""
        ...

    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None:
        """Draw a line ``width`` pixels thick from ``a`` to ``b`` with round caps."""
        ...

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        ...
