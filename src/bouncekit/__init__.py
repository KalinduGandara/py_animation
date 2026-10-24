"""bouncekit: deterministic 2D physics videos."""

from bouncekit import colors
from bouncekit.errors import ConfigError
from bouncekit.scene import Scene
from bouncekit.world.ball import Ball
from bouncekit.world.circle import CircleBoundary

__version__ = "0.1.0"

__all__ = ["Ball", "CircleBoundary", "ConfigError", "Scene", "__version__", "colors"]
