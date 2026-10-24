"""Live preview window (placeholder; implemented in T-007)."""

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bouncekit.scene import Scene


def run_preview(make_scene: "Callable[[], Scene]", scale: float = 0.45) -> None:
    """Open a window that plays scenes built by ``make_scene`` (not implemented yet)."""
    raise NotImplementedError("live preview is implemented in T-007")
