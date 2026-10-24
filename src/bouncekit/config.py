"""Scene configuration with validation."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from bouncekit.colors import Color, ColorLike, parse_color
from bouncekit.errors import ConfigError

Vec = tuple[float, float]

MAX_GLOW = 4.0
"""Largest accepted glow intensity (FR-304)."""


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


def _glow(value: object) -> float:
    """Validate a glow intensity: a number in [0, 4] or a bool (True = 1.0)."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, int | float) or not math.isfinite(value) or not 0 <= value <= MAX_GLOW:
        raise ConfigError(f"glow must be a number in [0, {MAX_GLOW:g}] or a bool; got {value!r}")
    return float(value)


def _trail(value: object) -> bool:
    """Validate a trail flag (a bool)."""
    if type(value) is not bool:
        raise ConfigError(f"trail must be True or False; got {value!r}")
    return value


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
class AudioConfig:
    """Sound settings for a scene (sample rate is fixed at 48 000 Hz).

    Raises ``ConfigError`` naming the field for a negative speed or interval, a
    non-positive reference speed or count, or ``peak_dbfs > 0``.

    Attributes:
        min_impact_speed: px/s; slower impacts play nothing.
        reference_speed: px/s; impact speed that gives full gain. A note's gain is
            ``play.gain * min(1, speed / reference_speed) ** 0.5``.
        min_retrigger_interval: seconds between notes of one play action for one object.
        max_triggers_per_frame: notes started per video frame, all rules together.
        max_polyphony: notes sounding at once; a new note beyond this cuts the oldest
            with a 5 ms fade.
        peak_dbfs: peak level of the final mix in dBFS (<= 0).
    """

    min_impact_speed: float = 40.0
    reference_speed: float = 1500.0
    min_retrigger_interval: float = 0.05
    max_triggers_per_frame: int = 6
    max_polyphony: int = 24
    peak_dbfs: float = -1.0

    def __post_init__(self) -> None:
        values = {
            "min_impact_speed": _non_negative_number("min_impact_speed", self.min_impact_speed),
            "reference_speed": _positive_number("reference_speed", self.reference_speed),
            "min_retrigger_interval": _non_negative_number(
                "min_retrigger_interval", self.min_retrigger_interval
            ),
            "peak_dbfs": _finite_number("peak_dbfs", self.peak_dbfs),
        }
        _positive_int("max_triggers_per_frame", self.max_triggers_per_frame)
        _positive_int("max_polyphony", self.max_polyphony)
        if values["peak_dbfs"] > 0:
            raise ConfigError(f"peak_dbfs must be <= 0; got {self.peak_dbfs!r}")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class EffectsConfig:
    """Visual effect settings for a scene (FR-303..FR-305); effects never change physics.

    Raises ``ConfigError`` naming the field for a non-positive or non-finite
    ``trail_seconds``/``glow_blur`` or a ``max_particles`` that is not an int >= 0.

    Attributes:
        trail_seconds: seconds after which a trail has faded to 5 %.
        glow_blur: blur radius of glows in pixels (at full resolution).
        max_particles: cap on live impact particles; bursts beyond it are truncated.
    """

    trail_seconds: float = 0.3
    glow_blur: float = 18.0
    max_particles: int = 2000

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "trail_seconds", _positive_number("trail_seconds", self.trail_seconds)
        )
        object.__setattr__(self, "glow_blur", _positive_number("glow_blur", self.glow_blur))
        if type(self.max_particles) is not int or self.max_particles < 0:
            raise ConfigError(f"max_particles must be an integer >= 0; got {self.max_particles!r}")

    def trail_keep(self, fps: int) -> float:
        """Per-frame trail decay factor ``0.05 ** (1 / (trail_seconds * fps))``."""
        return float(0.05 ** (1 / (self.trail_seconds * fps)))


@dataclass(frozen=True)
class SceneConfig:
    """Immutable, validated scene settings (pixels, origin top-left, +y down).

    ``background`` accepts a colour string or tuple and is stored as an RGB tuple.
    ``audio`` holds the sound settings (:class:`AudioConfig`). ``rule_cooldown`` is
    the default per-pair cooldown of collision rules in seconds (FR-204).
    ``max_balls`` caps the number of live balls (FR-205). ``effects`` holds the
    visual effect settings (:class:`EffectsConfig`).
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
    audio: AudioConfig = field(default_factory=AudioConfig)
    rule_cooldown: float = 0.05
    max_balls: int = 1000
    effects: EffectsConfig = field(default_factory=EffectsConfig)

    def __post_init__(self) -> None:
        if not isinstance(self.effects, EffectsConfig):
            raise ConfigError(f"effects must be an EffectsConfig; got {self.effects!r}")
        if not isinstance(self.audio, AudioConfig):
            raise ConfigError(f"audio must be an AudioConfig; got {self.audio!r}")
        _positive_even_int("width", self.width)
        _positive_even_int("height", self.height)
        _positive_int("fps", self.fps)
        _positive_int("substeps", self.substeps)
        _positive_int("max_balls", self.max_balls)
        if type(self.seed) is not int:
            raise ConfigError(f"seed must be an integer; got {self.seed!r}")
        duration = _positive_number("duration", self.duration)
        if round(duration * self.fps) < 1:
            raise ConfigError(
                f"duration must last at least one frame (1/{self.fps} s); got {duration!r}"
            )
        max_speed = _positive_number("max_speed", self.max_speed)
        bg_input: ColorLike = self.background
        background = parse_color(bg_input)
        gravity = _vec("gravity", self.gravity)
        object.__setattr__(self, "duration", duration)
        object.__setattr__(self, "max_speed", max_speed)
        object.__setattr__(self, "background", background)
        object.__setattr__(self, "gravity", gravity)
        object.__setattr__(
            self, "rule_cooldown", _non_negative_number("rule_cooldown", self.rule_cooldown)
        )
