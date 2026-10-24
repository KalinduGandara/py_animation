"""Sound sources for collision rules (FR-102): ``S.note(...)``.

Pitches are note names (``"C5"``, ``"F#4"``, ``"Bb3"``; octave -1..9, A4 = 440 Hz,
12-tone equal temperament), MIDI numbers (``int`` 0..127) or frequencies in Hz
(``float``). The resulting frequency must lie in 20 Hz..20 kHz.
"""

import math
import re
from dataclasses import dataclass

from bouncekit.audio.voices import ADSR, VOICES, Sine, Voice, resolve_voice
from bouncekit.errors import ConfigError

__all__ = [
    "ADSR",
    "VOICES",
    "Note",
    "Pitch",
    "Sine",
    "Source",
    "Voice",
    "VoiceLike",
    "note",
    "pitch_to_hz",
]

Pitch = str | int | float
VoiceLike = str | Voice

_NAME = re.compile(r"([A-G])([#b]?)(-1|[0-9])")
_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MIN_HZ, _MAX_HZ = 20.0, 20_000.0


def _midi_to_hz(midi: float) -> float:
    return float(440.0 * 2.0 ** ((midi - 69) / 12))


def pitch_to_hz(pitch: Pitch) -> float:
    """Convert a note name, MIDI number or frequency to Hz.

    Raises:
        ConfigError: for an unknown name, an int outside 0..127, a non-positive or
            non-finite float, or a frequency outside 20 Hz..20 kHz.
    """
    if isinstance(pitch, str):
        m = _NAME.fullmatch(pitch)
        if m is None:
            raise ConfigError(
                f"pitch must be a note name like 'C5', 'F#4' or 'Bb3' (octave -1..9); got {pitch!r}"
            )
        letter, accidental, octave = m.groups()
        shift = {"#": 1, "b": -1, "": 0}[accidental]
        hz = _midi_to_hz((int(octave) + 1) * 12 + _SEMITONE[letter] + shift)
    elif isinstance(pitch, bool):
        raise ConfigError(f"pitch must be a note name, MIDI int or Hz float; got {pitch!r}")
    elif isinstance(pitch, int):
        if not 0 <= pitch <= 127:
            raise ConfigError(f"pitch as MIDI number must be in 0..127; got {pitch!r}")
        hz = _midi_to_hz(pitch)
    elif isinstance(pitch, float):
        if not math.isfinite(pitch) or pitch <= 0:
            raise ConfigError(f"pitch in Hz must be positive and finite; got {pitch!r}")
        hz = pitch
    else:
        raise ConfigError(f"pitch must be a note name, MIDI int or Hz float; got {pitch!r}")
    if not _MIN_HZ <= hz <= _MAX_HZ:
        raise ConfigError(f"pitch must be within 20 Hz..20 kHz; got {pitch!r} ({hz:.2f} Hz)")
    return hz


@dataclass(frozen=True)
class Note:
    """A fixed-pitch source: every trigger plays ``voice`` at ``hz``."""

    hz: float
    voice: Voice


Source = Note


def note(pitch: Pitch, *, voice: VoiceLike = "sine") -> Note:
    """Return a source that always plays ``pitch`` with ``voice``.

    ``voice`` is a voice name (``"sine"``) or a voice instance such as
    ``Sine(duration=0.3)``.

    Raises:
        ConfigError: for a bad pitch or an unknown voice.
    """
    return Note(hz=pitch_to_hz(pitch), voice=resolve_voice(voice))
