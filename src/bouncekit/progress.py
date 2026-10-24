"""Single-line progress bar with ETA on stderr (FR-408).

Wall-clock time is read only here (through the injectable ``clock``), never by the simulation.
"""

import sys
import time
from collections.abc import Callable
from typing import TextIO

__all__ = ["Progress"]

_WIDTH = 20
_THROTTLE = 0.1


def _format_eta(seconds: float) -> str:
    whole = max(0, round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


class Progress:
    """A progress bar rewritten in place with ``\\r`` on a stream (default stderr).

    ``enabled=None`` shows the bar only when the stream is a TTY; ``False`` never
    writes the bar. Redraws are throttled to every 0.1 s of ``clock`` time, except
    that completion is always drawn.
    """

    def __init__(
        self,
        total: int,
        *,
        label: str,
        unit: str,
        stream: TextIO | None = None,
        enabled: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total = total
        self.label = label
        self.unit = unit
        self.stream: TextIO = sys.stderr if stream is None else stream
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self._clock = clock
        self._start = clock()
        self._last_draw: float | None = None
        self._done = 0
        self._width = 0  # length of the line currently on screen (0 if none)
        self._drawn = False

    def _line(self) -> str:
        done, total = self._done, self.total
        filled = _WIDTH if total <= 0 else min(_WIDTH, _WIDTH * done // total)
        pct = 100 if total <= 0 else min(100, 100 * done // total)
        if done <= 0:
            eta = "--:--"
        else:
            eta = _format_eta((self._clock() - self._start) / done * max(0, total - done))
        bar = "#" * filled + "-" * (_WIDTH - filled)
        return f"{self.label[:24]} [{bar}] {pct:3d}% {done}/{total} {self.unit} ETA {eta}"

    def _draw(self) -> None:
        line = self._line()
        pad = " " * max(0, self._width - len(line))
        self.stream.write("\r" + line + pad)
        self.stream.flush()
        self._width = len(line)
        self._drawn = True
        self._last_draw = self._clock()

    def update(self, done: int) -> None:
        """Record ``done`` items and redraw if 0.1 s passed since the last draw (or finished)."""
        self._done = done
        if not self.enabled:
            return
        if (
            done >= self.total
            or self._last_draw is None
            or self._clock() - self._last_draw >= _THROTTLE
        ):
            self._draw()

    def write(self, line: str, *, stream: TextIO) -> None:
        """Print ``line`` to ``stream``, clearing the bar line first and redrawing it after."""
        if self.enabled and self._drawn and self._width:
            self.stream.write("\r" + " " * self._width + "\r")
        print(line, file=stream, flush=True)
        if self.enabled and self._drawn:
            self._width = 0
            self._draw()

    def close(self) -> None:
        """End the bar line with a newline if anything was drawn."""
        if self.enabled and self._drawn:
            self.stream.write("\n")
            self.stream.flush()
            self._drawn = False
