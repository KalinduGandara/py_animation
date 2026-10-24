"""bouncekit: deterministic 2D physics videos."""

import os

# pygame prints a banner to stdout on import; keep CLI output clean.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from bouncekit import colors
from bouncekit.errors import ConfigError
from bouncekit.scene import Scene
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

__version__ = "0.1.0"

__all__ = [
    "Ball",
    "CircleBoundary",
    "ConfigError",
    "Scene",
    "__version__",
    "colors",
]
