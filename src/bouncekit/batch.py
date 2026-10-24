"""Render jobs: one load + render + metadata per job (FR-402, FR-404, FR-405).

``bouncekit render`` runs one :class:`Job` through :func:`run_job`.
"""

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from bouncekit.errors import ConfigError
from bouncekit.export.metadata import build_metadata, write_metadata
from bouncekit.params import suffix

__all__ = ["Job", "JobResult", "parse_assignments", "run_job"]

_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)


def parse_assignments(items: Sequence[str], option: str) -> list[tuple[str, str]]:
    """Parse ``NAME=VALUE`` texts (``--set``) into ``(name, value)`` pairs, in order.

    ``NAME`` must be a valid param name; ``VALUE`` is any text, possibly empty.

    Raises:
        ConfigError: naming ``option`` for a malformed item or a repeated name.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in items:
        match = _ASSIGNMENT.fullmatch(item)
        if match is None:
            raise ConfigError(f"{option} expects NAME=VALUE with a valid param name; got {item!r}")
        name, value = match.group(1), match.group(2)
        if name in seen:
            raise ConfigError(f"{option}: param {name!r} given more than once")
        seen.add(name)
        pairs.append((name, value))
    return pairs


@dataclass(frozen=True)
class Job:
    """One render: a script with one seed, duration and set of overrides.

    ``seed``/``duration`` of ``None`` keep the script's values. ``out`` of
    ``None`` names the MP4 ``<out_dir>/<stem>_seed<seed><suffix>.mp4`` once the
    seed is known (after loading).
    """

    index: int
    script: Path
    seed: int | None
    duration: float | None
    overrides: tuple[tuple[str, str], ...]
    out_dir: Path
    out: Path | None


@dataclass(frozen=True)
class JobResult:
    """Outcome of :func:`run_job`; ``error`` is ``"<ExceptionType>: <message>"`` on failure.

    ``out`` is ``None`` when the job failed before its output name was known.
    """

    index: int
    out: Path | None
    ok: bool
    frames: int
    seconds: float
    error: str | None


def run_job(job: Job) -> JobResult:
    """Load the job's script, render the MP4 and write its metadata JSON beside it.

    Any ``Exception`` makes the job fail: its MP4 and JSON are deleted if they
    exist and the error is returned in the result. ``KeyboardInterrupt`` propagates.
    """
    from bouncekit.cli import load_scene  # local import: cli imports this module

    t0 = time.monotonic()
    out = job.out
    try:
        scene = load_scene(
            job.script, seed=job.seed, duration=job.duration, params=dict(job.overrides)
        )
        if out is None:
            name = f"{job.script.stem}_seed{scene.config.seed}{suffix(job.overrides)}.mp4"
            out = job.out_dir / name
        scene.render(out)
        seconds = round(time.monotonic() - t0, 3)
        data = build_metadata(scene, script=str(job.script), video=out, render_seconds=seconds)
        write_metadata(out, data)
    except Exception as exc:
        if out is not None:
            out.unlink(missing_ok=True)
            out.with_suffix(".json").unlink(missing_ok=True)
        seconds = round(time.monotonic() - t0, 3)
        return JobResult(job.index, out, False, 0, seconds, f"{type(exc).__name__}: {exc}")
    return JobResult(job.index, out, True, scene.frame, seconds, None)
