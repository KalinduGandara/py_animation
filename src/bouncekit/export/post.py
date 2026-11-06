"""Post text for uploads: title, description and hashtags (FR-610)."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bouncekit.errors import ConfigError

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["MAX_DESCRIPTION", "MAX_TITLE", "Post", "format_post", "make_post"]

MAX_TITLE = 100
"""YouTube's title limit, in characters."""
MAX_DESCRIPTION = 5000
"""YouTube's description limit, in characters."""


@dataclass(frozen=True)
class Post:
    """Validated post text; ``title``/``description`` may be callables ``f(scene) -> str``."""

    title: "str | Callable[[Scene], str]"
    description: "str | Callable[[Scene], str]"
    hashtags: tuple[str, ...]


def _check_text(name: str, value: object, *, required: bool, limit: int) -> None:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a str or a callable; got {value!r}")
    if required and not value.strip():
        raise ConfigError(f"{name} must not be empty")
    if len(value) > limit:
        raise ConfigError(f"{name} must be at most {limit} characters; got {len(value)}")


def _hashtags(values: object) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, Iterable):
        raise ConfigError(f"hashtags must be a list of words; got {values!r}")
    tags: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ConfigError(f"hashtags must be strings; got {value!r}")
        word = value.removeprefix("#")
        if not word or any(ch.isspace() or ch == "#" for ch in word):
            raise ConfigError(f"hashtags must be single words without spaces; got {value!r}")
        tags.append(f"#{word}")
    return tuple(tags)


def make_post(
    *,
    title: "str | Callable[[Scene], str]",
    description: "str | Callable[[Scene], str]",
    hashtags: Iterable[str],
) -> Post:
    """Validate the arguments of ``Scene.post`` (callables are checked when evaluated).

    Raises:
        ConfigError: naming ``title``, ``description`` or ``hashtags``.
    """
    if not callable(title):
        _check_text("title", title, required=True, limit=MAX_TITLE)
    if not callable(description):
        _check_text("description", description, required=False, limit=MAX_DESCRIPTION)
    return Post(title, description, _hashtags(hashtags))


def format_post(post: Post, scene: "Scene") -> str:
    """The post file text, with callables evaluated now::

        TITLE
        <title>

        DESCRIPTION
        <description>

        HASHTAGS
        #a #b

    Raises:
        ConfigError: if a callable returns an invalid title or description.
    """
    title = post.title(scene) if callable(post.title) else post.title
    _check_text("title", title, required=True, limit=MAX_TITLE)
    description = post.description(scene) if callable(post.description) else post.description
    _check_text("description", description, required=False, limit=MAX_DESCRIPTION)
    return f"TITLE\n{title}\n\nDESCRIPTION\n{description}\n\nHASHTAGS\n{' '.join(post.hashtags)}\n"
