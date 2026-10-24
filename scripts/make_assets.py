"""Generate the committed example assets deterministically (FR-311).

Usage: ``uv run python scripts/make_assets.py [OUT_DIR]`` (default: ``assets/`` next
to this script's parent). Writes ``OUT_DIR/midi/ode_to_joy.mid``. Every run produces
byte-identical files; nothing is downloaded.
"""

import sys
from pathlib import Path

import mido

TICKS_PER_BEAT = 480
BAR = 4 * TICKS_PER_BEAT
MELODY_VELOCITY = 96
BASS_VELOCITY = 72

# Beethoven's "Ode to Joy" theme (public domain), C major, 4/4: (note, beats) per bar.
_A = [("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1)]
_B = [("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1)]
_C = [("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1)]
_END_OPEN = [("E4", 1.5), ("D4", 0.5), ("D4", 2)]
_END_CLOSED = [("D4", 1.5), ("C4", 0.5), ("C4", 2)]
MELODY: list[list[tuple[str, float]]] = [
    _A, _B, _C, _END_OPEN,
    _A, _B, _C, _END_CLOSED,
    [("D4", 1), ("D4", 1), ("E4", 1), ("C4", 1)],
    [("D4", 1), ("E4", 0.5), ("F4", 0.5), ("E4", 1), ("C4", 1)],
    [("D4", 1), ("E4", 0.5), ("F4", 0.5), ("E4", 1), ("D4", 1)],
    [("C4", 1), ("D4", 1), ("G3", 2)],
    _A, _B, _C, _END_CLOSED,
]  # fmt: skip
# One whole-bar bass note per bar (tonic C3 / dominant G2).
BASS = ["C3", "G2", "C3", "G2", "C3", "G2", "C3", "C3",
        "G2", "C3", "G2", "G2", "C3", "G2", "C3", "C3"]  # fmt: skip

_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _midi(name: str) -> int:
    return (int(name[1:]) + 1) * 12 + _SEMITONE[name[0]]


def _track(
    name: str, channel: int, notes: list[tuple[str, float]], velocity: int
) -> mido.MidiTrack:
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    track.append(mido.Message("program_change", channel=channel, program=0, time=0))
    for note, beats in notes:
        n = _midi(note)
        track.append(mido.Message("note_on", channel=channel, note=n, velocity=velocity, time=0))
        ticks = round(beats * TICKS_PER_BEAT)
        track.append(mido.Message("note_off", channel=channel, note=n, velocity=0, time=ticks))
    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def make_midi(out_dir: Path) -> Path:
    """Write ``out_dir/midi/ode_to_joy.mid``: melody track plus a bass note per bar."""
    assert len(MELODY) == len(BASS)
    assert all(sum(b for _, b in bar) == 4 for bar in MELODY)
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name="Ode to Joy", time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta)
    melody = [note for bar in MELODY for note in bar]
    mid.tracks.append(_track("Melody", 0, melody, MELODY_VELOCITY))
    mid.tracks.append(_track("Bass", 1, [(n, 4) for n in BASS], BASS_VELOCITY))
    path = out_dir / "midi" / "ode_to_joy.mid"
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(path)
    return path


def main(argv: list[str]) -> None:
    """Generate every asset into ``argv[0]`` (default: the repository's ``assets/``)."""
    out = Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "assets"
    print(make_midi(out))


if __name__ == "__main__":
    main(sys.argv[1:])
