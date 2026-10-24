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


@dataclass(frozen=True)
class Triangle:
    """Triangle oscillator from phase 0 shaped by an :class:`ADSR` envelope."""

    duration: float = 0.8
    envelope: ADSR = field(default_factory=ADSR)

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_number("duration", self.duration))
        if not isinstance(self.envelope, ADSR):
            raise ConfigError(f"envelope must be an ADSR; got {self.envelope!r}")

    def render(self, hz: float, seed: int) -> NDArray[np.float64]:
        """Render one note at ``hz`` (``seed`` is unused: the triangle is deterministic)."""
        n = round(self.duration * SAMPLE_RATE)
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        # Same shape as 2/pi * arcsin(sin(2 pi f t)), computed exactly: 0 at t=0, rising.
        x = hz * t + 0.25
        wave = 1.0 - 4.0 * np.abs(x - np.floor(x) - 0.5)
        out: NDArray[np.float64] = wave * self.envelope.curve(n, self.duration)
        return out


_PLUCK_ATTACK = SAMPLE_RATE * 2 // 1000  # 2 ms
_RELEASE = SAMPLE_RATE * 50 // 1000  # 50 ms linear fade to 0 at the end of a decaying note
_MARIMBA_ATTACK = SAMPLE_RATE // 1000  # 1 ms
_MARIMBA_PARTIALS = ((1.0, 1.0, 1.0), (3.93, 0.35, 3.0), (9.3, 0.1, 8.0))
"""(frequency ratio, amplitude, decay divisor) per partial."""
_NYQUIST_LIMIT = 20_000.0


@dataclass(frozen=True)
class Pluck:
    """Karplus-Strong plucked string, tuned exactly by resampling the delay-line output.

    ``damping`` in (0, 1) is the per-period loss of the feedback loop: closer to 1
    rings longer. The last 50 ms fade linearly to 0. The excitation noise is seeded
    from ``(seed, hz, damping)`` only, so equal inputs give bit-identical notes.
    """

    duration: float = 1.5
    damping: float = 0.996

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_number("duration", self.duration))
        damping = self.damping
        if (
            isinstance(damping, bool)
            or not isinstance(damping, int | float)
            or not math.isfinite(damping)
            or not 0.0 < damping < 1.0
        ):
            raise ConfigError(f"damping must be a number in (0, 1); got {damping!r}")
        object.__setattr__(self, "damping", float(damping))

    def render(self, hz: float, seed: int) -> NDArray[np.float64]:
        """Render one plucked note at ``hz`` with noise seeded from ``seed``."""
        n = round(self.duration * SAMPLE_RATE)
        # The two-tap average adds half a sample of delay: loop period = period + 0.5.
        # An integer delay line alone is up to ~1/(2 * period) off (+33 cents at C7),
        # so the string is rendered at 48000 / (period + 0.5) Hz and read back at
        # ``ratio`` source samples per output sample, which lands exactly on ``hz``.
        period = max(2, round(SAMPLE_RATE / hz - 0.5))
        ratio = hz * (period + 0.5) / SAMPLE_RATE
        m = math.ceil((n - 1) * ratio) + 2 if n else 0
        rng = np.random.default_rng(
            [seed % 2**32, round(hz * 1000), round(self.damping * 1_000_000)]
        )
        y = np.zeros(max(m, period + 1), dtype=np.float64)
        noise = rng.uniform(-1.0, 1.0, period)
        # One circular [1, 2, 1] / 4 smoothing pass: full-band noise has inter-sample
        # peaks ~1.4x its sample peak, which lossy (AAC) encoding turns into clipping.
        noise = 0.25 * np.roll(noise, 1) + 0.5 * noise + 0.25 * np.roll(noise, -1)
        y[:period] = noise - noise.mean()
        y[period] = self.damping * 0.5 * y[0]
        k = self.damping * 0.5
        i = period + 1
        while i < len(y):
            j = min(i + period, len(y))
            y[i:j] = k * (y[i - period : j - period] + y[i - period - 1 : j - period - 1])
            i = j
        if n == 0:
            return np.zeros(0, dtype=np.float64)
        out = np.interp(np.arange(n, dtype=np.float64) * ratio, np.arange(len(y)), y)
        ramp = min(_PLUCK_ATTACK, n)
        out[:ramp] *= np.arange(ramp, dtype=np.float64) / _PLUCK_ATTACK
        out[0] = 0.0
        return _normalise(_release(out))


@dataclass(frozen=True)
class Marimba:
    """Struck bar: decaying sine partials at 1, 3.93 and 9.3 times ``hz``.

    ``decay`` is the fundamental's exponential time constant in seconds; the upper
    partials decay 3 and 8 times faster. Partials above 20 kHz are omitted. The last
    50 ms fade linearly to 0.
    """

    duration: float = 1.2
    decay: float = 0.35

    def __post_init__(self) -> None:
        object.__setattr__(self, "duration", _positive_number("duration", self.duration))
        object.__setattr__(self, "decay", _positive_number("decay", self.decay))

    def render(self, hz: float, seed: int) -> NDArray[np.float64]:
        """Render one note at ``hz`` (``seed`` is unused: the marimba is deterministic)."""
        n = round(self.duration * SAMPLE_RATE)
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE
        y = np.zeros(n, dtype=np.float64)
        for ratio, amp, divisor in _MARIMBA_PARTIALS:
            f = hz * ratio
            if f > _NYQUIST_LIMIT:
                continue
            y += amp * np.exp(-t * divisor / self.decay) * np.sin(2.0 * math.pi * f * t)
        ramp = min(_MARIMBA_ATTACK, n)
        y[:ramp] *= np.arange(ramp, dtype=np.float64) / _MARIMBA_ATTACK
        return _normalise(_release(y))


def _release(y: NDArray[np.float64]) -> NDArray[np.float64]:
    """Fade the last 50 ms linearly to exactly 0 so a note cut at its duration doesn't click."""
    k = min(_RELEASE, len(y))
    if k:
        y[len(y) - k :] *= np.linspace(1.0, 0.0, k)
    return y


def _normalise(y: NDArray[np.float64]) -> NDArray[np.float64]:
    peak = float(np.abs(y).max()) if len(y) else 0.0
    if peak > 0.0:
        y /= peak
    return y


_SAMPLE_ATTACK = SAMPLE_RATE // 1000  # 1 ms
_SAMPLE_RELEASE = SAMPLE_RATE * 5 // 1000  # 5 ms


@dataclass(frozen=True, eq=False)
class Sample:
    """A recorded sound played at any pitch by linear-interpolation resampling (FR-308).

    Build it with :func:`bouncekit.sound.sample`. ``data`` is the file's mono
    (channel-averaged) signal at ``rate`` Hz, read-only; it sounds at ``root_hz``
    when played unchanged. Compared and hashed by identity.
    """

    path: str
    root_hz: float
    rate: int
    data: NDArray[np.float64]
    duration: float | None = None

    def render(self, hz: float, seed: int) -> NDArray[np.float64]:
        """Render the sample shifted to ``hz`` (``seed`` is unused).

        The source is read at index ``i * ratio`` for output sample ``i``, with
        ``ratio = (hz / root_hz) * (rate / 48000)``, for ``floor((len - 1) / ratio) + 1``
        samples (at most ``round(duration * 48000)``). A 1 ms linear attack from 0 and
        a 5 ms linear release to 0 are applied, then the peak is normalised to 1.
        """
        ratio = (hz / self.root_hz) * (self.rate / SAMPLE_RATE)
        n = math.floor((len(self.data) - 1) / ratio) + 1
        if self.duration is not None:
            n = min(n, round(self.duration * SAMPLE_RATE))
        y = np.interp(
            np.arange(n, dtype=np.float64) * ratio,
            np.arange(len(self.data), dtype=np.float64),
            self.data,
        )
        ramp = min(_SAMPLE_ATTACK, n)
        y[:ramp] *= np.arange(ramp, dtype=np.float64) / _SAMPLE_ATTACK
        k = min(_SAMPLE_RELEASE, n)
        if k:
            y[n - k :] *= np.linspace(1.0, 0.0, k)
        return _normalise(y)


Voice = Sine | Triangle | Pluck | Marimba | Sample

VOICES: dict[str, Voice] = {
    "sine": Sine(),
    "triangle": Triangle(),
    "pluck": Pluck(),
    "marimba": Marimba(),
}
_VOICE_TYPES = (Sine, Triangle, Pluck, Marimba, Sample)


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
    if isinstance(voice, _VOICE_TYPES):
        return voice
    raise ConfigError(f"voice must be a voice name or voice instance; got {voice!r}")
