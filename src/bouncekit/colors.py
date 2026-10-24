"""Colour parsing and colour modes (FR-306)."""

import colorsys
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from bouncekit.errors import ConfigError

Color = tuple[int, int, int]
ColorLike = str | Sequence[int]

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def parse_color(value: ColorLike) -> Color:
    """Convert ``"#rgb"``, ``"#rrggbb"`` or an ``(r, g, b)`` sequence to a tuple.

    Raises:
        ConfigError: if the value is not a valid colour.
    """
    if isinstance(value, str):
        if not _HEX.fullmatch(value):
            raise ConfigError(f"colour must be '#rgb' or '#rrggbb'; got {value!r}")
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
    if (
        isinstance(value, Sequence)
        and len(value) == 3
        and all(type(c) is int and 0 <= c <= 255 for c in value)
    ):
        return (int(value[0]), int(value[1]), int(value[2]))
    raise ConfigError(f"colour must be 3 ints in 0-255; got {value!r}")


# --- colour modes (FR-306) ----------------------------------------------------


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ConfigError(f"{name} must be a finite number; got {value!r}")
    return float(value)


def _unit(name: str, value: object) -> float:
    number = _finite(name, value)
    if not 0 <= number <= 1:
        raise ConfigError(f"{name} must be in [0, 1]; got {value!r}")
    return number


def _named_color(name: str, value: object) -> Color:
    try:
        return parse_color(value)  # type: ignore[arg-type]
    except ConfigError as exc:
        raise ConfigError(f"{name}: {exc}") from None


def hsv(h_degrees: float, s: float, v: float) -> Color:
    """RGB colour of hue ``h_degrees`` (any finite value, taken mod 360), saturation and value.

    Uses ``colorsys.hsv_to_rgb``; each channel is ``round(255 * x)``.

    Raises:
        ConfigError: if ``h_degrees`` is not finite or ``s``/``v`` are not in [0, 1].
    """
    h = _finite("h_degrees", h_degrees) % 360.0
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, _unit("s", s), _unit("v", v))
    return (round(255 * r), round(255 * g), round(255 * b))


@dataclass(frozen=True, eq=False)
class Fixed:
    """A plain colour as a mode; behaves exactly like ``color``."""

    color: Color


@dataclass(frozen=True, eq=False)
class HueCycle:
    """A new hue per ball: the ``k``-th ball created with this mode in a scene gets
    ``hsv(start + k * step, saturation, value)`` as its fixed colour.
    """

    start: float
    step: float
    saturation: float
    value: float

    def color_at(self, k: int) -> Color:
        """The colour of the ``k``-th ball (0-based)."""
        return hsv((self.start + k * self.step) % 360.0, self.saturation, self.value)


@dataclass(frozen=True, eq=False)
class BySpeed:
    """Colour blended from ``slow`` to ``fast`` by the ball's speed at draw time."""

    slow: Color
    fast: Color
    max_speed: float

    def color_for(self, velocity: tuple[float, float]) -> Color:
        """``round(slow + (fast - slow) * min(1, |v| / max_speed))`` per channel."""
        t = min(1.0, math.hypot(*velocity) / self.max_speed)
        r, g, b = (round(s + (f - s) * t) for s, f in zip(self.slow, self.fast, strict=True))
        return (r, g, b)


@dataclass(frozen=True, eq=False)
class ByGeneration:
    """Colour ``colors[generation % len(colors)]``, evaluated at draw time."""

    colors: tuple[Color, ...]

    def color_for(self, generation: int) -> Color:
        """The colour of a ball of ``generation``."""
        return self.colors[generation % len(self.colors)]


type ColorMode = Fixed | HueCycle | BySpeed | ByGeneration
"""Any colour mode."""
type Dynamic = BySpeed | ByGeneration
"""Modes evaluated at draw time."""
type ColorSpec = ColorLike | ColorMode
"""What ``add_ball``/``spawn``/``recolor`` accept as ``color``."""
type ColorSource = Color | HueCycle | BySpeed | ByGeneration
"""A validated colour spec (``Fixed`` replaced by its colour)."""

DEFAULT_PALETTE: tuple[Color, ...] = (
    (255, 59, 107),
    (255, 176, 46),
    (255, 225, 77),
    (61, 220, 132),
    (42, 157, 255),
    (155, 92, 255),
)
"""The 6 colours of ``by_generation()`` with no arguments."""


def fixed(color: ColorLike) -> Fixed:
    """Return a mode that is exactly ``color``.

    Raises:
        ConfigError: if ``color`` is not a colour.
    """
    return Fixed(_named_color("color", color))


def hue_cycle(
    *, start: float = 0.0, step: float = 20.0, saturation: float = 0.75, value: float = 1.0
) -> HueCycle:
    """Return a mode giving each new ball the next hue (``step`` degrees apart, FR-306).

    Counted per mode instance per scene over ``add_ball``, spawned balls, new split
    children and recolors with this mode, in creation order; a refused split or
    spawn does not advance it. A split parent keeps its colour.

    Raises:
        ConfigError: if ``start``/``step`` are not finite or ``saturation``/``value``
            are not in [0, 1].
    """
    return HueCycle(
        _finite("start", start),
        _finite("step", step),
        _unit("saturation", saturation),
        _unit("value", value),
    )


def by_speed(
    *, slow: ColorLike = "#2a6cff", fast: ColorLike = "#ff3b6b", max_speed: float = 2000.0
) -> BySpeed:
    """Return a mode blending ``slow`` -> ``fast`` by speed up to ``max_speed`` px/s.

    Raises:
        ConfigError: for a bad colour or a ``max_speed`` that is not positive and finite.
    """
    limit = _finite("max_speed", max_speed)
    if limit <= 0:
        raise ConfigError(f"max_speed must be a positive finite number; got {max_speed!r}")
    return BySpeed(_named_color("slow", slow), _named_color("fast", fast), limit)


def by_generation(*colors: ColorLike) -> ByGeneration:
    """Return a mode colouring a ball by its split generation (cycles through ``colors``).

    With no arguments, uses :data:`DEFAULT_PALETTE`.

    Raises:
        ConfigError: if any colour is invalid.
    """
    if not colors:
        return ByGeneration(DEFAULT_PALETTE)
    return ByGeneration(tuple(_named_color("colors", c) for c in colors))


def color_source(value: object, name: str = "color") -> ColorSource:
    """Validate a colour value or mode; ``Fixed`` becomes its colour.

    Raises:
        ConfigError: if ``value`` is neither a colour nor a colour mode.
    """
    if isinstance(value, Fixed):
        return value.color
    if isinstance(value, HueCycle | BySpeed | ByGeneration):
        return value
    return _named_color(name, value)


def ring_color(value: object) -> Color:
    """Validate a ring colour: a colour value or ``fixed(...)`` only (FR-306).

    Raises:
        ConfigError: naming ``color`` for any other mode or an invalid colour.
    """
    if isinstance(value, HueCycle | BySpeed | ByGeneration):
        raise ConfigError(
            f"color of a ring must be a colour value or C.fixed(...); got {value!r} "
            "(rings have no speed, generation or hue cycle)"
        )
    source = color_source(value)
    assert not isinstance(source, HueCycle | BySpeed | ByGeneration)
    return source
