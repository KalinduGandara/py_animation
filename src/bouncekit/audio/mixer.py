"""Offline mixer, voice stealing and master bus (FR-106, FR-107).

All sample positions are derived from integer physics step counts with exact
integer arithmetic (rounding half up), so audio lines up with the simulation
regardless of floating-point time.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from bouncekit.audio.voices import SAMPLE_RATE, Voice
from bouncekit.config import AudioConfig

__all__ = ["NOTE_LEVEL", "SAMPLE_RATE", "NoteTrigger", "mix", "num_samples", "sample_offset"]

NOTE_LEVEL = 0.5
"""Level of a full-gain note before the master bus."""

_END_FADE = SAMPLE_RATE * 5 // 1000  # 5 ms
_STEAL_FADE = SAMPLE_RATE * 5 // 1000  # 5 ms


@dataclass(frozen=True)
class NoteTrigger:
    """A note to play: sample 0 of ``voice.render(hz, seed)`` lands at ``offset``."""

    step: int
    offset: int
    voice: Voice
    hz: float
    gain: float


def sample_offset(step: int, fps: int, substeps: int) -> int:
    """Sample index of physics step ``step``: ``round(step * 48000 / (fps * substeps))``.

    Exact integer arithmetic, halves round up.
    """
    rate = fps * substeps
    return (2 * step * SAMPLE_RATE + rate) // (2 * rate)


def num_samples(frames: int, fps: int) -> int:
    """Number of samples for ``frames`` video frames: ``round(frames * 48000 / fps)``, half up."""
    return (2 * frames * SAMPLE_RATE + fps) // (2 * fps)


def mix(
    triggers: Sequence[NoteTrigger], *, length: int, config: AudioConfig, seed: int
) -> NDArray[np.float32]:
    """Mix ``triggers`` into a centred stereo buffer of shape ``(length, 2)``.

    Triggers are taken in order of ``offset`` (ties keep their order). When a note
    starts while ``config.max_polyphony`` notes are still sounding, the oldest is
    cut with a linear 5 ms fade-out starting at the new note's offset (voice
    stealing). Each note is scaled by ``gain * NOTE_LEVEL`` and summed; samples
    past the end are dropped. The master bus applies ``tanh``, scales the result so
    its peak is ``config.peak_dbfs`` (silence stays silent) and fades out the last
    5 ms.
    """
    acc = np.zeros(length, dtype=np.float64)
    cache: dict[tuple[Voice, float, int], NDArray[np.float64]] = {}
    ordered = sorted((t for t in triggers if t.offset < length), key=lambda t: t.offset)
    notes: list[NDArray[np.float64]] = []
    ends: list[int] = []  # exclusive end sample of each note, shortened when stolen
    cut: dict[int, int] = {}  # note index -> sample where its steal fade starts
    sounding: list[int] = []  # note indices, oldest first
    for i, trig in enumerate(ordered):
        key = (trig.voice, trig.hz, seed)
        note = cache.get(key)
        if note is None:
            note = cache[key] = trig.voice.render(trig.hz, seed)
        start = trig.offset
        notes.append(note)
        ends.append(start + len(note))
        sounding = [j for j in sounding if ends[j] > start]
        if len(sounding) >= config.max_polyphony:
            oldest = sounding.pop(0)
            cut[oldest] = start
            ends[oldest] = min(ends[oldest], start + _STEAL_FADE)
        sounding.append(i)

    for i, trig in enumerate(ordered):
        start = trig.offset
        end = min(ends[i], length)
        seg = notes[i][: end - start] * (trig.gain * NOTE_LEVEL)
        if i in cut:
            k = cut[i] - start
            seg[k:] *= np.linspace(1.0, 0.0, _STEAL_FADE)[: len(seg) - k]
        acc[start:end] += seg

    out = np.tanh(acc)
    peak = float(np.abs(out).max()) if length else 0.0
    if peak > 0.0:
        out *= 10 ** (config.peak_dbfs / 20) / peak
    fade = min(_END_FADE, length)
    if fade:
        out[length - fade :] *= np.linspace(1.0, 0.0, fade)
    stereo = np.empty((length, 2), dtype=np.float32)
    stereo[:, 0] = out
    stereo[:, 1] = out
    return stereo
