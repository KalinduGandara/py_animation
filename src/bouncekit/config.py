"""Scene configuration with validation."""

import math
from collections.abc import Iterable, Sequence
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


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ConfigError(f"{name} must be a finite number; got {value!r}")
    return float(value)


def _non_negative_number(name: str, value: object) -> float:
    number = _finite_number(name, value)
    if number < 0:
        raise ConfigError(f"{name} must be a non-negative finite number; got {value!r}")
    return number


def _vec(name: str, value: object) -> Vec:
    """Validate a 2-vector of finite numbers and return it as floats."""
    if (
        isinstance(value, Sequence)
        and not isinstance(value, str)
        and len(value) == 2
        and all(
            isinstance(c, int | float) and not isinstance(c, bool) and math.isfinite(c)
            for c in value
        )
    ):
        return (float(value[0]), float(value[1]))
    raise ConfigError(f"{name} must be two finite numbers (x, y); got {value!r}")


def _tags(value: object) -> frozenset[str]:
    """Validate an iterable of tag strings (a bare string is rejected)."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ConfigError(f"tags must be an iterable of strings; got {value!r}")
    items = list(value)
    if not all(isinstance(t, str) for t in items):
        raise ConfigError(f"tags must be an iterable of strings; got {value!r}")
    return frozenset(items)


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
        gravity = _vec("gravity", self.gravity)
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "max_speed", max_speed)
        object.__setattr__(self, "background", background)
        object.__setattr__(self, "gravity", gravity)
