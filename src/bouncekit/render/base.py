"""Renderer protocol: the drawing primitives every backend implements (FR-008, FR-302)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from bouncekit.colors import Color
from bouncekit.config import Vec


@dataclass(frozen=True)
class TrailSegment:
    """One stroke on the trail layer: ``a`` to ``b``, ``width`` px, round caps."""

    a: Vec
    b: Vec
    width: float
    color: Color


@dataclass(frozen=True)
class GlowDisc:
    """A filled disc of light (colour x ``intensity``, clamped to 255)."""

    center: Vec
    radius: float
    color: Color
    intensity: float


@dataclass(frozen=True)
class GlowArc:
    """A band of light along a circle; geometry as :meth:`Renderer.arc`."""

    center: Vec
    radius: float
    width: float
    start_degrees: float
    end_degrees: float
    color: Color
    intensity: float


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

    def circle(self, center: Vec, radius: float, color: Color, *, alpha: float = 1.0) -> None:
        """Draw a filled circle with an anti-aliased edge.

        Each pixel blends ``color`` over the frame by coverage x ``alpha`` (in [0, 1]).
        """
        ...

    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None:
        """Draw a line ``width`` pixels thick from ``a`` to ``b`` with round caps."""
        ...

    def arc(
        self,
        center: Vec,
        radius: float,
        width: float,
        start_degrees: float,
        end_degrees: float,
        color: Color,
    ) -> None:
        """Draw a band ``width`` thick along a circle of ``radius``, anti-aliased.

        The arc runs clockwise on screen (increasing angle, +y down) from
        ``start_degrees`` to ``end_degrees`` with round caps; a sweep of 360 degrees
        or more draws a full ring.
        """
        ...

    def trails(self, segments: Sequence[TrailSegment], *, keep: float, reset: bool) -> None:
        """Update the persistent trail layer and composite it onto the frame.

        ``reset`` clears the layer to black; otherwise every layer channel is scaled
        by ``keep`` (decaying to exactly 0 within ``ceil(log(1/255) / log(keep)) + 255``
        calls for ``keep < 1``). Then ``segments`` are drawn onto the layer and the
        layer is composited with a per-channel maximum, ``max(frame, layer)``.
        """
        ...

    def glow(self, lights: Sequence[GlowDisc | GlowArc], *, blur: float) -> None:
        """Draw ``lights`` on a cleared layer, blur it by about ``blur`` px, add it to the frame.

        The addition saturates per channel at 255.
        """
        ...

    def text(self, text: str, center: Vec, size: float, color: Color) -> None:
        """Draw one line of ``text``, anti-aliased and alpha-blended over the frame.

        The line's advance box is centred horizontally on ``center.x`` and its line box
        (ascender to descender, the font's sized height) vertically on ``center.y``.
        Empty or whitespace-only text draws nothing.
        """
        ...

    def to_rgb_bytes(self) -> bytes:
        """Return the frame as packed RGB24 bytes (``width * height * 3``)."""
        ...
