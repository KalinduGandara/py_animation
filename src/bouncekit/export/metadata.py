"""Render metadata JSON written beside each MP4 the CLI renders (FR-405)."""

import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

import pygame
import pymunk

if TYPE_CHECKING:
    from bouncekit.scene import Scene

__all__ = ["EVENT_KINDS", "build_metadata", "write_metadata"]

EVENT_KINDS = ("collision", "escape", "spawn", "destroy", "timer", "condition")
"""Event kinds counted in ``"events"``, in key order."""


def build_metadata(
    scene: "Scene", *, script: str, video: Path, render_seconds: float
) -> dict[str, object]:
    """Build the metadata dict for a finished render of ``scene`` to ``video``.

    Keys, in order: ``scene`` (``script`` as given), ``video`` (file name), ``seed``,
    ``params``, ``duration``, ``frames``, ``fps``, ``size``, ``events`` (count per
    kind of :data:`EVENT_KINDS`), ``sound_triggers``, ``versions`` and
    ``render_seconds`` (rounded to 3 decimals). Every value except
    ``render_seconds`` depends only on the script, seed, duration and overrides.
    """
    from bouncekit import __version__  # local import: the package imports scene

    cfg = scene.config
    counts: Counter[str] = Counter(event.kind for event in scene.events)
    return {
        "scene": script,
        "video": Path(video).name,
        "seed": cfg.seed,
        "params": scene.params,
        "duration": cfg.duration,
        "frames": scene.frame,
        "fps": cfg.fps,
        "size": [cfg.width, cfg.height],
        "events": {kind: counts.get(kind, 0) for kind in EVENT_KINDS},
        "sound_triggers": len(scene.triggers),
        "versions": {
            "bouncekit": __version__,
            "pymunk": pymunk.version,
            "pygame": pygame.version.ver,
        },
        "render_seconds": round(float(render_seconds), 3),
    }


def write_metadata(video: Path, data: Mapping[str, object]) -> Path:
    """Write ``data`` as indented UTF-8 JSON to ``video.with_suffix(".json")``.

    The file is written to a temporary file in the same directory and then
    renamed over the target, so a crash never leaves half a JSON. Returns the path.
    """
    path = Path(video).with_suffix(".json")
    text = json.dumps(data, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".bouncekit-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
