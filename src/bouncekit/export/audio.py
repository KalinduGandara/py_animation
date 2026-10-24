"""WAV export of the mix (FR-109)."""

from pathlib import Path

import numpy as np
import soundfile
from numpy.typing import NDArray

from bouncekit.audio.mixer import SAMPLE_RATE


def write_wav(path: str | Path, buffer: NDArray[np.float32]) -> None:
    """Write ``buffer`` (shape ``(n, channels)``) as a 48 kHz 32-bit float WAV."""
    soundfile.write(str(path), buffer, SAMPLE_RATE, subtype="FLOAT", format="WAV")
