"""Colour parsing."""

import re
from collections.abc import Sequence

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
