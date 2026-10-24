"""Exception types raised by bouncekit."""


class BouncekitError(Exception):
    """Base class for all bouncekit errors."""


class ConfigError(BouncekitError):
    """Invalid scene or object configuration."""


class FfmpegError(BouncekitError):
    """ffmpeg is missing or failed while encoding."""
