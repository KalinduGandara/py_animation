"""Synth voices (FR-105). Each ``render(hz, seed)`` returns mono float64 at 48 kHz.

Every voice is a frozen, hashable dataclass, so it can key the mixer's note cache.
Rendered notes start at exactly 0.0 and have a peak of at most 1.0.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from bouncekit.config import _non_negative_number, _positive_number
from bouncekit.errors import ConfigError

SAMPLE_RATE = 48_000


@dataclass(frozen=True)
class ADSR:
    """Amplitude envelope: times in seconds, ``sustain`` a level in [0, 1].

    The envelope rises linearly from 0 to 1 over ``attack``, falls to ``sustain``
    over ``decay``, holds, and falls to 0 over ``release``, ending at the voice's
    duration. If the three times exceed the duration they are scaled to fit.
    """

    attack: float = 0.005
    decay: float = 0.15
    sustain: float = 0.5
    release: float = 0.4

    def __post_init__(self) -> None:
        for name in ("attack", "decay", "release"):
            object.__setattr__(self, name, _non_negative_number(name, getattr(self, name)))
        sustain = _non_negative_number("sustain", self.sustain)
        if sustain > 1.0:
            raise ConfigError(f"sustain must be in [0, 1]; got {self.sustain!r}")
        object.__setattr__(self, "sustain", sustain)

    def curve(self, n: int, duration: float) -> NDArray[np.float64]:
        """Return the envelope sampled at ``arange(n) / SAMPLE_RATE``."""
        a, d, r = self.attack, self.decay, self.release
        total = a + d + r
        if total > duration:
            k = duration / total
            a, d, r = a * k, d * k, r * k
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        xp = [0.0, a, a + d, duration - r, duration]
        fp = [0.0, 1.0, self.sustain, self.sustain, 0.0]
        return np.interp(t, xp, fp)


@dataclass(frozen=True)
class Sine:
    """Sine oscillator from phase 0 shaped by an :class:`ADSR` envelope."""

    duration: float = 0.8
    envelope: ADSR = field(default_factory=ADSR)

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_number("duration", self.duration))
        if not isinstance(self.envelope, ADSR):
            raise ConfigError(f"envelope must be an ADSR; got {self.envelope!r}")

    def render(self, hz: float, seed: int) -> NDArray[np.float64]:
        """Render one note at ``hz`` (``seed`` is unused: the sine is deterministic)."""
        n = round(self.duration * SAMPLE_RATE)
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        out: NDArray[np.float64] = np.sin(2.0 * math.pi * hz * t) * self.envelope.curve(
            n, self.duration
        )
        return out


Voice = Sine

VOICES: dict[str, Voice] = {"sine": Sine()}


def resolve_voice(voice: object) -> Voice:
    """Return a voice instance for a name or instance.

    Raises:
        ConfigError: for an unknown name or a value that is not a voice.
    """
    if isinstance(voice, str):
        try:
            return VOICES[voice]
        except KeyError:
            raise ConfigError(
                f"voice must be one of {', '.join(sorted(VOICES))}; got {voice!r}"
            ) from None
    if isinstance(voice, Sine):
        return voice
    raise ConfigError(f"voice must be a voice name or voice instance; got {voice!r}")
