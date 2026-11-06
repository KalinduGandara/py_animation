"""WAV export of the mix (FR-109) and the loop-ending fade (FR-608)."""

from pathlib import Path

import numpy as np
import soundfile
from numpy.typing import NDArray

from bouncekit.audio.mixer import SAMPLE_RATE


def fade_out(buffer: NDArray[np.float32], start: int) -> NDArray[np.float32]:
    """Return a copy of ``buffer`` ramped linearly from 1 at ``start`` to 0 at the end (FR-608)."""
    out = buffer.copy()
    n = len(out) - start
    if n > 0:
        out[start:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)[:, None]
    return out


def write_wav(path: str | Path, buffer: NDArray[np.float32]) -> None:
    """Write ``buffer`` (shape ``(n, channels)``) as a 48 kHz 32-bit float WAV."""
    soundfile.write(str(path), buffer, SAMPLE_RATE, subtype="FLOAT", format="WAV")
