"""Sound sources for collision rules (FR-102, FR-103, FR-307).

``S.note(...)``, ``S.scale(...)`` and ``S.melody(...)``.

Pitches are note names (``"C5"``, ``"F#4"``, ``"Bb3"``; octave -1..9, A4 = 440 Hz,
12-tone equal temperament), MIDI numbers (``int`` 0..127) or frequencies in Hz
(``float``). The resulting frequency must lie in 20 Hz..20 kHz.
"""

import math
import os
import re
from dataclasses import dataclass

from bouncekit.audio.midi import read_chords
from bouncekit.audio.voices import (
    ADSR,
    VOICES,
    Marimba,
    Pluck,
    Sine,
    Triangle,
    Voice,
    resolve_voice,
)
from bouncekit.errors import ConfigError

__all__ = [
    "ADSR",
    "VOICES",
    "Marimba",
    "Melody",
    "MODES",
    "Note",
    "Pitch",
    "Pluck",
    "Scale",
    "Sine",
    "Source",
    "Triangle",
    "Voice",
    "VoiceLike",
    "melody",
    "note",
    "pitch_to_hz",
    "scale",
]

Pitch = str | int | float
VoiceLike = str | Voice

_NAME = re.compile(r"([A-G])([#b]?)(-1|[0-9])")
_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MIN_HZ, _MAX_HZ = 20.0, 20_000.0

MODES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "chromatic": tuple(range(12)),
}
"""Scale modes: semitone offsets of one octave's degrees from the root."""


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


@dataclass(frozen=True, eq=False)
class Scale:
    """An ascending note sequence: each trigger plays the next of ``hz`` with ``voice``.

    Compared and hashed by identity: every ``scale(...)`` call is a distinct source
    with its own cursor (one per scene, starting at the first note).
    """

    hz: tuple[float, ...]
    voice: Voice


@dataclass(frozen=True, eq=False)
class Melody:
    """A chord sequence from a MIDI file: each trigger plays the next chord with ``voice``.

    ``chords`` holds ``(hz, velocity / 127)`` pairs per chord, in ascending pitch.
    Compared and hashed by identity: every ``melody(...)`` call is a distinct source
    with its own cursor (one per scene, starting at the first chord).
    """

    chords: tuple[tuple[tuple[float, float], ...], ...]
    voice: Voice


Source = Note | Scale | Melody


def note(pitch: Pitch, *, voice: VoiceLike = "sine") -> Note:
    """Return a source that always plays ``pitch`` with ``voice``.

    ``voice`` is a voice name (``"sine"``, ``"triangle"``, ``"pluck"``,
    ``"marimba"``) or a voice instance such as ``Pluck(duration=0.5)``.

    Raises:
        ConfigError: for a bad pitch or an unknown voice.
    """
    return Note(hz=pitch_to_hz(pitch), voice=resolve_voice(voice))


def scale(
    root: Pitch = "C4",
    *,
    mode: str = "major_pentatonic",
    octaves: int = 2,
    voice: VoiceLike = "sine",
) -> Scale:
    """Return a source that steps through a scale, one note per trigger.

    The notes are ``mode``'s degrees ascending from ``root`` for ``octaves``
    octaves, plus the root ``octaves`` octaves up; after the last note it wraps to
    the first. Modes: ``major``, ``minor``, ``major_pentatonic``,
    ``minor_pentatonic``, ``chromatic``. Example: ``scale("C4", octaves=1)`` plays
    C4 D4 E4 G4 A4 C5, then C4 again.

    Raises:
        ConfigError: for a bad root pitch, an unknown mode, ``octaves`` not an int in
            1..8, an unknown voice, or a top note above 20 kHz.
    """
    if not isinstance(mode, str) or mode not in MODES:
        raise ConfigError(f"mode must be one of {', '.join(MODES)}; got {mode!r}")
    if type(octaves) is not int or not 1 <= octaves <= 8:
        raise ConfigError(f"octaves must be an int in 1..8; got {octaves!r}")
    base = pitch_to_hz(root)
    semis = [12 * o + d for o in range(octaves) for d in MODES[mode]] + [12 * octaves]
    hz = tuple(base * 2.0 ** (k / 12) for k in semis)
    if hz[-1] > _MAX_HZ:
        raise ConfigError(
            f"scale notes must be within 20 Hz..20 kHz; root {root!r} with "
            f"octaves={octaves} reaches {hz[-1]:.2f} Hz"
        )
    return Scale(hz=hz, voice=resolve_voice(voice))


def melody(
    path: str | os.PathLike[str],
    *,
    voice: VoiceLike = "sine",
    track: int | None = None,
    transpose: int = 0,
) -> Melody:
    """Return a source that plays a MIDI file's notes, one chord per trigger (FR-307).

    The file is read now (relative paths resolve against the current directory).
    Notes are the ``note_on`` messages with velocity > 0 of ``track`` (``None``: all
    tracks merged), excluding percussion (MIDI channel 10), shifted by
    ``transpose`` semitones. Notes starting at the same tick form a chord; every
    note of a chord starts together at the trigger's gain times ``velocity / 127``.
    A chord counts as one trigger for the trigger policy; after the last chord the
    melody wraps to the first. MIDI tempo and note durations are ignored: the hits
    set the rhythm.

    Raises:
        ConfigError: if the file is missing, unreadable or has no usable notes,
            ``track`` is not ``None`` or a valid track index, ``transpose`` is not an
            int, a transposed note is outside 20 Hz..20 kHz, or ``voice`` is unknown.
    """
    chords = read_chords(path, track=track, transpose=transpose)
    out: list[tuple[tuple[float, float], ...]] = []
    for chord in chords:
        notes = []
        for number, velocity in chord:
            hz = _midi_to_hz(number)
            if not _MIN_HZ <= hz <= _MAX_HZ:
                raise ConfigError(
                    f"melody: notes must be within 20 Hz..20 kHz; MIDI note {number - transpose} "
                    f"with transpose={transpose} is {hz:.2f} Hz in {os.fspath(path)}"
                )
            notes.append((hz, velocity / 127))
        out.append(tuple(notes))
    return Melody(chords=tuple(out), voice=resolve_voice(voice))
