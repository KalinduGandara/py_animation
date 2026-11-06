"""Export pack beside an MP4: climax thumbnail PNG and post text (FR-611)."""

from pathlib import Path
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["pack_paths", "write_pack"]


def pack_paths(video: Path) -> tuple[Path, Path]:
    """``(<stem>_thumb.png, <stem>_post.txt)`` beside ``video``."""
    video = Path(video)
    return (
        video.with_name(f"{video.stem}_thumb.png"),
        video.with_name(f"{video.stem}_post.txt"),
    )


def write_pack(scene: "Scene", video: Path) -> list[Path]:
    """Write the thumbnail (``scene.climax_image``) and, if set, the post text.

    Call after the scene has been rendered. Returns the paths written; the post file
    is skipped when the scene never called ``scene.post``.

    Raises:
        ConfigError: if the post's title/description callables return bad text.
        RuntimeError: if the scene has not been rendered.
    """
    image = scene.climax_image
    if image is None:
        raise RuntimeError("write_pack needs a rendered scene (no frames were drawn)")
    thumb, post = pack_paths(video)
    text = scene.post_text()
    size = (scene.config.width, scene.config.height)
    pygame.image.save(pygame.image.frombuffer(image, size, "RGB"), str(thumb))
    written = [thumb]
    if text is not None:
        post.write_text(text, encoding="utf-8")
        written.append(post)
    return written
