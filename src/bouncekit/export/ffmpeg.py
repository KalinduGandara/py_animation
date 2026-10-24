"""ffmpeg export: pipe raw RGB24 frames to an H.264 encoder (FR-007); mux audio (FR-109)."""

import shutil
import subprocess
from pathlib import Path
from types import TracebackType

from bouncekit.errors import FfmpegError

_STDERR_TAIL = 2000


def require_ffmpeg() -> str:
    """Return the path to the ``ffmpeg`` executable.

    Raises:
        FfmpegError: if ffmpeg is not on ``PATH``.
    """
    path = shutil.which("ffmpeg")
    if path is None:
        raise FfmpegError("ffmpeg not found on PATH; install it, e.g. `brew install ffmpeg`")
    return path


class FfmpegWriter:
    """Context manager that encodes RGB24 frames to an MP4 file.

    Encodes H.264, ``yuv420p``, CRF 18, ``+faststart``. Width and height must be
    even. Frames are written with :meth:`write` as ``width * height * 3`` bytes.
    """

    def __init__(self, path: str | Path, width: int, height: int, fps: int) -> None:
        """Remember the output settings; ffmpeg starts on ``__enter__``."""
        self.path = Path(path)
        self.width = width
        self.height = height
        self.fps = fps
        self._frame_size = width * height * 3
        self._proc: subprocess.Popen[bytes] | None = None
        self._returncode = 0

    def _command(self, exe: str) -> list[str]:
        return [
            exe, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}", "-r", str(self.fps), "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-fflags", "+bitexact", "-flags:v", "+bitexact",
            str(self.path),
        ]  # fmt: skip

    def __enter__(self) -> "FfmpegWriter":
        """Start ffmpeg.

        Raises:
            FfmpegError: if ffmpeg is missing.
        """
        exe = require_ffmpeg()
        self._proc = subprocess.Popen(
            self._command(exe),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return self

    def write(self, frame: bytes) -> None:
        """Send one RGB24 frame to ffmpeg.

        Raises:
            FfmpegError: if the frame has the wrong length or ffmpeg has died.
        """
        if self._proc is None or self._proc.stdin is None:
            raise FfmpegError("FfmpegWriter is not open; use it as a context manager")
        if len(frame) != self._frame_size:
            raise FfmpegError(
                f"bad frame length: got {len(frame)} bytes, "
                f"expected {self._frame_size} ({self.width}x{self.height} RGB24)"
            )
        try:
            self._proc.stdin.write(frame)
        except BrokenPipeError:
            raise FfmpegError(f"ffmpeg exited early:\n{self._finish()}") from None

    def _finish(self) -> str:
        """Close stdin, wait for ffmpeg and return the stderr tail."""
        proc = self._proc
        assert proc is not None
        try:
            if proc.stdin is not None and not proc.stdin.closed:
                proc.stdin.close()
        except BrokenPipeError:
            pass
        stderr = proc.stderr.read() if proc.stderr is not None else b""
        proc.wait()
        if proc.stderr is not None:
            proc.stderr.close()
        self._proc = None
        self._returncode = proc.returncode
        return stderr.decode(errors="replace")[-_STDERR_TAIL:].strip()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Finish encoding; raise :class:`FfmpegError` if ffmpeg failed."""
        if self._proc is None:
            return
        if exc_type is not None:
            # Abort: don't mask the original error.
            self._proc.kill()
            self._finish()
            return
        tail = self._finish()
        if self._returncode != 0:
            raise FfmpegError(f"ffmpeg failed (exit {self._returncode}):\n{tail}")


def _mux_command(exe: str, video: Path, wav: Path, out: Path) -> list[str]:
    return [
        exe, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-i", str(wav),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-fflags", "+bitexact",
        str(out),
    ]  # fmt: skip


def mux(video: str | Path, wav: str | Path, out: str | Path) -> None:
    """Combine an H.264 MP4 and a WAV into ``out``: video copied, audio AAC 192 kb/s.

    Audio is 48 kHz stereo; the file is ``+faststart``.

    Raises:
        FfmpegError: if ffmpeg is missing or fails (with its stderr tail).
    """
    exe = require_ffmpeg()
    proc = subprocess.run(
        _mux_command(exe, Path(video), Path(wav), Path(out)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace")[-_STDERR_TAIL:].strip()
        raise FfmpegError(f"ffmpeg mux failed (exit {proc.returncode}):\n{tail}")
