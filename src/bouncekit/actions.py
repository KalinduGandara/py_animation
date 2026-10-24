"""Rule actions (FR-104): ``A.play(source, gain=...)``.

The trigger's final gain also depends on impact speed (FR-106, see ``AudioConfig``).
"""

from dataclasses import dataclass

from bouncekit.config import _non_negative_number
from bouncekit.errors import ConfigError
from bouncekit.sound import Note, Scale, Source

__all__ = ["Play", "play"]


@dataclass(frozen=True, eq=False)
class Play:
    """Play a note from ``source`` at ``gain`` when the rule fires.

    Compared by identity: each ``play(...)`` call is a distinct action.
    """

    source: Source
    gain: float = 1.0


def play(source: Source, *, gain: float = 1.0) -> Play:
    """Return an action that plays ``source`` (``S.note(...)``/``S.scale(...)``) at ``gain`` (>= 0).

    Raises:
        ConfigError: if ``source`` is not a sound source or ``gain`` is negative.
    """
    if not isinstance(source, Note | Scale):
        raise ConfigError(
            f"source must be a sound source such as S.note(...) or S.scale(...); got {source!r}"
        )
    return Play(source=source, gain=_non_negative_number("gain", gain))
