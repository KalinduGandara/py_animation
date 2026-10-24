"""Scene parameters: name checks, override parsing and output-name suffixes (FR-401, FR-402)."""

import math
import re
from collections.abc import Sequence

from bouncekit.errors import ConfigError

__all__ = ["ParamValue", "check_default", "check_name", "parse_value", "suffix"]

ParamValue = bool | int | float | str
"""Type of a param's default and value."""

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_UNSAFE = re.compile(r"[^A-Za-z0-9.+-]")
_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})


def check_name(name: object) -> str:
    """Return ``name`` if it is a valid param name (``[A-Za-z_][A-Za-z0-9_]*``).

    Raises:
        ConfigError: naming ``name`` otherwise.
    """
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise ConfigError(f"param name must match [A-Za-z_][A-Za-z0-9_]*; got name={name!r}")
    return name


def check_default(name: str, default: object) -> ParamValue:
    """Return ``default`` if it is a ``bool``, ``int``, finite ``float`` or ``str``.

    Raises:
        ConfigError: naming the param otherwise.
    """
    if isinstance(default, bool | int | str):
        return default
    if isinstance(default, float) and math.isfinite(default):
        return default
    raise ConfigError(
        f"param {name!r}: default must be a bool, int, finite float or str; got {default!r}"
    )


def parse_value(name: str, default: ParamValue, text: str) -> ParamValue:
    """Parse override ``text`` to the type of ``default``.

    ``bool`` accepts ``true/false/1/0/yes/no/on/off`` (any case); ``int`` accepts
    what ``int(text)`` accepts; ``float`` accepts finite ``float(text)`` values;
    ``str`` returns ``text`` unchanged.

    Raises:
        ConfigError: naming the param, its type and the text when parsing fails.
    """
    if isinstance(default, str):
        return text
    kind = type(default).__name__
    error = ConfigError(f"param {name!r} ({kind}): cannot parse override {text!r}")
    if isinstance(default, bool):
        word = text.strip().lower()
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
        raise error
    if isinstance(default, int):
        try:
            return int(text)
        except ValueError:
            raise error from None
    try:
        value = float(text)
    except ValueError:
        raise error from None
    if not math.isfinite(value):
        raise error
    return value


def suffix(overrides: Sequence[tuple[str, str]]) -> str:
    """Output-name suffix for overrides: ``""`` or ``"_<name>-<value>"`` per override.

    Characters of a value outside ``[A-Za-z0-9.+-]`` become ``_``; an empty value
    is written as ``_``.
    """
    return "".join(f"_{name}-{_UNSAFE.sub('_', value) or '_'}" for name, value in overrides)
