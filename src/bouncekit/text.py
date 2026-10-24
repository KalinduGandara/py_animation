"""Text overlay: a visual-only caption drawn after everything else (FR-406)."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.config import Vec, _finite_number, _non_negative_number, _positive_number, _vec
from bouncekit.errors import ConfigError

if TYPE_CHECKING:
    from bouncekit.scene import Scene

MAX_TEXT_SIZE = 1000.0


@dataclass(frozen=True, eq=False)
class Text:
    """A text overlay. ``start_frame`` is inclusive, ``end_frame`` exclusive (or ``None``)."""

    text: "str | Callable[[Scene], str]"
    pos: Vec
    size: float
    color: Color
    start_frame: int
    end_frame: int | None

    def visible(self, frame: int) -> bool:
        """Whether the text is shown at ``frame``."""
        return frame >= self.start_frame and (self.end_frame is None or frame < self.end_frame)


def make_text(
    text: "str | Callable[[Scene], str]",
    *,
    pos: Vec,
    size: float,
    color: ColorLike,
    start: float,
    end: float | None,
    fps: int,
) -> Text:
    """Validate the arguments of ``Scene.add_text`` and build a :class:`Text`."""
    if not isinstance(text, str) and not callable(text):
        raise ConfigError(f"text must be a str or a callable; got {text!r}")
    position = _vec("pos", pos)
    px = _positive_number("size", size)
    if px > MAX_TEXT_SIZE:
        raise ConfigError(f"size must be <= {MAX_TEXT_SIZE:g}; got {size!r}")
    try:
        rgb = parse_color(color)
    except ConfigError as err:
        raise ConfigError(f"color is invalid: {err}") from err
    first = round(_non_negative_number("start", start) * fps)
    last: int | None = None
    if end is not None:
        last = round(_finite_number("end", end) * fps)
        if last <= first:
            raise ConfigError(
                f"end must be after start by at least one frame; got end={end!r}, start={start!r}"
            )
    if not math.isfinite(first):  # pragma: no cover - guarded by _non_negative_number
        raise ConfigError(f"start must be finite; got {start!r}")
    return Text(text, position, px, rgb, first, last)
