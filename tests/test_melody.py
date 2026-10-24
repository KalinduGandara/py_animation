"""MIDI melody source and chord playback (FR-307) and the MIDI asset (FR-311)."""

import subprocess
import sys
from pathlib import Path

import mido
import pytest

from bouncekit import ConfigError, Scene
from bouncekit import actions as A
from bouncekit import sound as S
from bouncekit.audio.midi import read_chords
from bouncekit.audio.voices import Pluck, Sine
from bouncekit.config import AudioConfig
from bouncekit.events import CollisionEvent
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "midi" / "ode_to_joy.mid"

C4, D4, E4, G4, C5 = 60, 62, 64, 67, 72


def _write_midi(path: Path) -> Path:
    """C4; then E4 + G4 + C5 at one tick across two tracks; then D4.

    Also a percussion note (channel 9) and a velocity-0 note_on (a note-off).
    """
    mid = mido.MidiFile(ticks_per_beat=480)
    t0 = mido.MidiTrack()
    t0.append(mido.Message("note_on", note=C4, velocity=127, time=0))
    t0.append(mido.Message("note_on", note=C4, velocity=0, time=480))  # note-off
    t0.append(mido.Message("note_on", note=E4, velocity=64, time=0))
    t0.append(mido.Message("note_on", note=C5, velocity=100, time=0))
    t0.append(mido.Message("note_on", note=D4, velocity=90, time=480))
    mid.tracks.append(t0)
    t1 = mido.MidiTrack()
    t1.append(mido.Message("note_on", channel=9, note=36, velocity=127, time=240))  # drum
    t1.append(mido.Message("note_on", note=G4, velocity=32, time=240))  # tick 480
    t1.append(mido.Message("note_on", note=E4, velocity=10, time=0))  # duplicate pitch
    mid.tracks.append(t1)
    mid.save(path)
    return path


@pytest.fixture
def midi_file(tmp_path: Path) -> Path:
    return _write_midi(tmp_path / "tune.mid")


def _hz(n: int) -> float:
    return S.pitch_to_hz(n)


# --- Parsing ------------------------------------------------------------------


def test_read_chords_groups_by_tick(midi_file: Path) -> None:
    assert read_chords(midi_file, track=None, transpose=0) == (
        ((C4, 127),),
        ((E4, 64), (G4, 32), (C5, 100)),
        ((D4, 90),),
    )


def test_melody_chords_in_hz_and_velocity(midi_file: Path) -> None:
    m = S.melody(midi_file)
    assert m.chords == (
        ((_hz(C4), 1.0),),
        ((_hz(E4), 64 / 127), (_hz(G4), 32 / 127), (_hz(C5), 100 / 127)),
        ((_hz(D4), 90 / 127),),
    )
    assert m.voice == Sine()
    assert S.melody(midi_file, voice="pluck").voice == Pluck()


def test_transpose_shifts_by_octave(midi_file: Path) -> None:
    base, up = S.melody(midi_file), S.melody(midi_file, transpose=12)
    for c0, c1 in zip(base.chords, up.chords, strict=True):
        for (h0, v0), (h1, v1) in zip(c0, c1, strict=True):
            assert h1 == pytest.approx(2 * h0)
            assert v1 == v0


def test_track_selects_one_track(midi_file: Path) -> None:
    m = S.melody(midi_file, track=1)
    assert m.chords == (((_hz(E4), 10 / 127), (_hz(G4), 32 / 127)),)
    assert read_chords(midi_file, track=0, transpose=0)[1] == ((E4, 64), (C5, 100))


@pytest.mark.parametrize("track", [2, -1, 1.0, True, "0"])
def test_bad_track_raises(midi_file: Path, track: object) -> None:
    with pytest.raises(ConfigError, match="track"):
        S.melody(midi_file, track=track)  # type: ignore[arg-type]


@pytest.mark.parametrize("transpose", [1.5, True, "12"])
def test_bad_transpose_raises(midi_file: Path, transpose: object) -> None:
    with pytest.raises(ConfigError, match="transpose"):
        S.melody(midi_file, transpose=transpose)  # type: ignore[arg-type]


def test_transpose_out_of_audible_range_raises(midi_file: Path) -> None:
    with pytest.raises(ConfigError, match="20 Hz"):
        S.melody(midi_file, transpose=-48)  # C4 - 48 = C0 = 16.35 Hz


def test_missing_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "nope.mid"
    with pytest.raises(ConfigError, match="nope.mid"):
        S.melody(path)


@pytest.mark.parametrize("content", [b"", b"garbage, not a midi file at all", b"MThd\x00"])
def test_unreadable_file_raises(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.mid"
    path.write_bytes(content)
    with pytest.raises(ConfigError, match="bad.mid"):
        S.melody(path)


def test_file_without_notes_raises(tmp_path: Path) -> None:
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    track.append(mido.Message("note_on", channel=9, note=36, velocity=100))
    track.append(mido.Message("note_on", note=60, velocity=0, time=10))
    mid.tracks.append(track)
    path = tmp_path / "empty.mid"
    mid.save(path)
    with pytest.raises(ConfigError, match="empty.mid"):
        S.melody(path)


def test_melody_is_compared_by_identity(midi_file: Path) -> None:
    a, b = S.melody(midi_file), S.melody(midi_file)
    assert a != b
    assert len({a, b}) == 2
    assert A.play(a).source is a


# --- Playback -----------------------------------------------------------------


def _scene(**audio: float) -> tuple[Scene, Ball, Ball, CircleBoundary]:
    s = Scene(width=400, height=400, fps=60, substeps=8, duration=10.0,
              audio=AudioConfig(**audio))  # type: ignore[arg-type]  # fmt: skip
    ring = s.add_circle(center=(200, 200), radius=150, thickness=8, tags={"wall"})
    b1 = s.add_ball(pos=(200, 200), radius=10, tags={"ball"})
    b2 = s.add_ball(pos=(150, 200), radius=10, tags={"ball"})
    return s, b1, b2, ring


def _ev(step: int, a: Ball, b: Ball | CircleBoundary, speed: float = 1500.0) -> CollisionEvent:
    return CollisionEvent(
        kind="collision", step=step, frame=(step - 1) // 8, time=step / 480,
        objects=(a, b), speed=speed, position=(0.0, 0.0),
    )  # fmt: skip


def test_hits_play_chords_in_order_and_wrap(midi_file: Path) -> None:
    s, b1, _, ring = _scene(reference_speed=1500.0)
    m = S.melody(midi_file)
    s.on_collision("ball", "wall", [A.play(m, gain=0.5)])
    for i in range(4):
        s._dispatch([_ev(1 + 100 * i, b1, ring)])
    trig = s.triggers
    assert [t.hz for t in trig] == pytest.approx(
        [_hz(C4), _hz(E4), _hz(G4), _hz(C5), _hz(D4), _hz(C4)]
    )
    chord = trig[1:4]
    assert {t.step for t in chord} == {101}
    assert {t.offset for t in chord} == {trig[1].offset}
    assert [t.gain for t in chord] == pytest.approx(
        [0.5 * 64 / 127, 0.5 * 32 / 127, 0.5 * 100 / 127]
    )
    assert trig[0].gain == pytest.approx(0.5)
    assert all(t.voice == m.voice for t in trig)


def test_chord_counts_once_per_frame(midi_file: Path) -> None:
    s, b1, b2, ring = _scene(max_triggers_per_frame=2)
    m = S.melody(midi_file)
    s.on_collision("ball", "wall", [A.play(m)])
    s.on_collision("ball", "ball", [A.play(S.note("A4"))])
    # Same frame: C4 (1 hit), chord (1 hit, 3 notes) -> cap of 2 reached; note dropped.
    s._dispatch([_ev(1, b1, ring), _ev(2, b2, ring), _ev(3, b1, b2)])
    assert [t.hz for t in s.triggers] == pytest.approx([_hz(C4), _hz(E4), _hz(G4), _hz(C5)])


def test_dropped_hits_do_not_advance_cursor(midi_file: Path) -> None:
    s, b1, _, ring = _scene()
    m = S.melody(midi_file)
    s.on_collision("ball", "wall", [A.play(m)])
    s._dispatch([_ev(1, b1, ring)])
    s._dispatch([_ev(2, b1, ring)])  # within the retrigger interval: dropped
    s._dispatch([_ev(200, b1, ring, speed=10.0)])  # below min impact speed: dropped
    s._dispatch([_ev(400, b1, ring)])
    assert [t.hz for t in s.triggers] == pytest.approx([_hz(C4), _hz(E4), _hz(G4), _hz(C5)])


def test_ctx_play_accepts_melody(midi_file: Path) -> None:
    s, b1, _, ring = _scene()
    m = S.melody(midi_file)
    s.on_collision("ball", "wall", [lambda ctx, a, b, ev: ctx.play(m)])
    s._dispatch([_ev(1, b1, ring)])
    s._dispatch([_ev(100, b1, ring)])
    assert len(s.triggers) == 4


# --- Asset --------------------------------------------------------------------


def test_make_assets_reproduces_midi(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_assets.py"), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "midi" / "ode_to_joy.mid"
    assert out.read_bytes() == ASSET.read_bytes()


def test_ode_to_joy_asset() -> None:
    chords = read_chords(ASSET, track=None, transpose=0)
    melody_notes = sum(1 for c in chords for n, _ in c if n >= 60)
    assert melody_notes >= 30
    mid = mido.MidiFile(ASSET)
    bar = 4 * mid.ticks_per_beat
    starts: set[int] = set()
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and tick % bar == 0:
                starts.add(tick)
    assert len(starts) >= 8
    assert starts == set(range(0, max(starts) + 1, bar))  # every bar starts with notes
    # Exactly the bar starts are 2-note chords (melody + bass); the rest are single notes.
    assert sorted(len(c) for c in chords).count(2) == len(starts)
    assert {len(c) for c in chords} == {1, 2}
    assert len(S.melody(ASSET).chords) == len(chords)
