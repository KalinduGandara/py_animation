"""Exception types raised by bouncekit."""


class BouncekitError(Exception):
    """Base class for all bouncekit errors."""


class ConfigError(BouncekitError):
    """Invalid scene or object configuration."""


class FfmpegError(BouncekitError):
    """ffmpeg is missing or failed while encoding."""


class TunnellingWarning(UserWarning):
    """A ball moving at ``max_speed`` could pass straight through a ring."""


class SceneLoadError(BouncekitError):
    """A scene file is missing or does not define exactly one ``Scene``."""
