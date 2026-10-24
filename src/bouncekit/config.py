"""Scene configuration with validation."""

import math
from dataclasses import dataclass, field

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.errors import ConfigError

Vec = tuple[float, float]


def _positive_int(name: str, value: object) -> None:
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{name} must be a positive integer; got {value!r}")


def _positive_even_int(name: str, value: object) -> None:
    if type(value) is not int or value <= 0 or value % 2:
        raise ConfigError(f"{name} must be a positive even integer; got {value!r}")


def _positive_number(name: str, value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ConfigError(f"{name} must be a positive finite number; got {value!r}")
    return float(value)


@dataclass(frozen=True)
class SceneConfig:
    """Immutable, validated scene settings (pixels, origin top-left, +y down).

    ``background`` accepts a colour string or tuple and is stored as an RGB tuple.
    """

    width: int = 1080
    height: int = 1920
    fps: int = 60
    duration: float = 60.0
    seed: int = 0
    background: Color = field(default=(0, 0, 0))
    gravity: Vec = (0.0, 900.0)
    substeps: int = 8
    max_speed: float = 4000.0

    def __post_init__(self) -> None:
        _positive_even_int("width", self.width)
        _positive_even_int("height", self.height)
        _positive_int("fps", self.fps)
        _positive_int("substeps", self.substeps)
        if type(self.seed) is not int:
            raise ConfigError(f"seed must be an integer; got {self.seed!r}")
        duration = _positive_number("duration", self.duration)
        max_speed = _positive_number("max_speed", self.max_speed)
        bg_input: ColorLike = self.background
        background = parse_color(bg_input)
        g = self.gravity
        try:
            ok = len(g) == 2 and all(
                isinstance(c, int | float) and not isinstance(c, bool) and math.isfinite(c)
                for c in g
            )
        except TypeError:
            ok = False
        if not ok:
            raise ConfigError(f"gravity must be two finite numbers (x, y); got {g!r}")
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "max_speed", max_speed)
        object.__setattr__(self, "background", background)
        object.__setattr__(self, "gravity", (float(g[0]), float(g[1])))
