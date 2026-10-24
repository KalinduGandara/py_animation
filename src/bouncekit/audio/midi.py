"""Standard MIDI File reading for melody sources (FR-307)."""

import os

import mido

from bouncekit.errors import ConfigError

__all__ = ["PERCUSSION_CHANNEL", "read_chords"]

PERCUSSION_CHANNEL = 9
"""MIDI channel 10 (index 9): percussion, never part of a melody."""

Chord = tuple[tuple[int, int], ...]


def read_chords(
    path: str | os.PathLike[str], *, track: int | None = None, transpose: int = 0
) -> tuple[Chord, ...]:
    """Read the chords of a Standard MIDI File as ``((midi_number, velocity), ...)`` tuples.

    Notes are the ``note_on`` messages with velocity > 0 of ``track`` (``None``: all
    tracks), excluding the percussion channel, shifted by ``transpose`` semitones.
    Notes with the same absolute start tick form one chord, ordered by ascending
    note number; a pitch repeated within a chord is kept once with its highest
    velocity. Chords are ordered by start tick. Tempo, durations and every other
    message are ignored.

    Raises:
        ConfigError: if ``track``/``transpose`` are not ints, ``track`` is out of
            range, or the file is missing, unreadable or has no usable notes.
    """
    if track is not None and type(track) is not int:
        raise ConfigError(f"melody: track must be None or an int; got {track!r}")
    if type(transpose) is not int:
        raise ConfigError(f"melody: transpose must be an int; got {transpose!r}")
    try:
        mid = mido.MidiFile(path)
    except (OSError, EOFError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ConfigError(f"melody: cannot read {os.fspath(path)}: {exc}") from exc
    if track is not None and not 0 <= track < len(mid.tracks):
        raise ConfigError(
            f"melody: track must be in 0..{len(mid.tracks) - 1} for {os.fspath(path)}; "
            f"got {track!r}"
        )
    tracks = mid.tracks if track is None else [mid.tracks[track]]
    chords: dict[int, dict[int, int]] = {}
    for trk in tracks:
        tick = 0
        for msg in trk:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and msg.channel != PERCUSSION_CHANNEL:
                notes = chords.setdefault(tick, {})
                notes[msg.note] = max(notes.get(msg.note, 0), msg.velocity)
    if not chords:
        raise ConfigError(f"melody: no usable notes in {os.fspath(path)}")
    return tuple(
        tuple((note + transpose, vel) for note, vel in sorted(chords[tick].items()))
        for tick in sorted(chords)
    )
