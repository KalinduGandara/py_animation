"""Write a MIDI file from a list of notes, for ``S.melody``.

``S.melody`` plays one chord per hit, so only the ORDER of notes matters (the hits set
the rhythm). Write notes separated by spaces; join simultaneous notes with ``+``.

Usage (from the repo root):
    uv run python .claude/skills/bouncekit-video/scripts/notes_to_midi.py \
        assets/midi/twinkle.mid "C4 C4 G4 G4 A4 A4 G4 F4 F4 E4 E4 D4 D4 C4"
    # chords: "C4+E4+G4 F4+A4 G4+B4+D5"
"""

import math
import sys
from pathlib import Path

import mido

from bouncekit.sound import pitch_to_hz

TICKS = 480


def to_midi(name: str) -> int:
    hz = pitch_to_hz(name)  # validates the note name (e.g. "C#4", "Bb3")
    return round(69 + 12 * math.log2(hz / 440.0))


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    out, text = Path(sys.argv[1]), sys.argv[2]
    chords = [[to_midi(n) for n in token.split("+")] for token in text.split()]
    if not chords:
        print("error: no notes given", file=sys.stderr)
        return 2

    track = mido.MidiTrack()
    for chord in chords:
        for n in chord:
            track.append(mido.Message("note_on", note=n, velocity=96, time=0))
        for i, n in enumerate(chord):
            track.append(mido.Message("note_off", note=n, velocity=0, time=TICKS if i == 0 else 0))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid = mido.MidiFile(type=0, ticks_per_beat=TICKS)
    mid.tracks.append(track)
    out.parent.mkdir(parents=True, exist_ok=True)
    mid.save(out)
    print(f"wrote {out} ({len(chords)} chords)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
