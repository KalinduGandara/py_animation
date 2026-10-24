"""Render jobs and batches: planning, one load + render + metadata per job (FR-402..FR-405).

``bouncekit render`` runs one :class:`Job` through :func:`run_job`; ``bouncekit batch``
plans jobs with :func:`plan_jobs` and runs them with :func:`run_batch`.
"""

import itertools
import multiprocessing
import re
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from bouncekit.errors import ConfigError
from bouncekit.export.metadata import build_metadata, write_metadata
from bouncekit.params import suffix

__all__ = [
    "Job",
    "JobResult",
    "parse_assignments",
    "parse_grid",
    "parse_seeds",
    "plan_jobs",
    "run_batch",
    "run_job",
]

_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.DOTALL)
_SEED_ITEM = re.compile(r"(\d+)(?:-(\d+))?", re.ASCII)


def parse_seeds(spec: str) -> list[int]:
    """Parse a ``--seeds`` spec such as ``"3,1-2,2"`` into seeds, in written order.

    Items are non-negative integers ``N`` or inclusive ranges ``A-B`` with ``A <= B``.
    Duplicates are dropped, keeping the first occurrence.

    Raises:
        ConfigError: naming ``--seeds`` for an empty or malformed item or a reversed range.
    """
    seeds: dict[int, None] = {}
    for item in spec.split(","):
        match = _SEED_ITEM.fullmatch(item.strip())
        if match is None:
            raise ConfigError(
                f"--seeds expects comma-separated N or A-B (non-negative ints); got {spec!r}"
            )
        first = int(match.group(1))
        last = first if match.group(2) is None else int(match.group(2))
        if last < first:
            raise ConfigError(f"--seeds range {item.strip()!r} must have A <= B")
        for seed in range(first, last + 1):
            seeds.setdefault(seed, None)
    return list(seeds)


def parse_grid(items: Sequence[str]) -> list[tuple[str, list[str]]]:
    """Parse ``--grid NAME=V1,V2,...`` texts into ``(name, values)`` pairs, in order.

    Values are split on ``,`` and may be empty (``"gap="`` gives ``[""]``).

    Raises:
        ConfigError: naming ``--grid`` for a malformed item or a repeated name.
    """
    return [(name, value.split(",")) for name, value in parse_assignments(items, "--grid")]


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


def plan_jobs(
    script: str | Path,
    *,
    seeds: Sequence[int] | None,
    sets: Sequence[tuple[str, str]],
    grid: Sequence[tuple[str, Sequence[str]]],
    duration: float | None,
    out_dir: str | Path,
) -> list[Job]:
    """Plan the batch: seeds (outermost) x the grid product (last grid varies fastest).

    Every job carries all ``sets`` overrides followed by one value per grid param.
    Empty or ``None`` ``seeds`` runs the script's own seed, so the output name is
    resolved after loading. Indices are 1-based in planned order.

    Raises:
        ConfigError: if a name appears in both ``sets`` and ``grid``, or two jobs
            would write the same file name.
    """
    path = Path(script)
    folder = Path(out_dir)
    set_names = {name for name, _ in sets}
    for name, _ in grid:
        if name in set_names:
            raise ConfigError(f"--grid: param {name!r} is also given with --set")
    grid_names = [name for name, _ in grid]
    seed_list: list[int | None] = list(seeds) if seeds else [None]
    jobs: list[Job] = []
    seen: dict[tuple[int | None, str], int] = {}
    for seed in seed_list:
        for combo in itertools.product(*[values for _, values in grid]):
            overrides = (*sets, *zip(grid_names, combo, strict=True))
            tail = suffix(overrides)
            index = len(jobs) + 1
            if (seed, tail) in seen:
                shown = f"{path.stem}_seed{'<script seed>' if seed is None else seed}{tail}.mp4"
                raise ConfigError(
                    f"--grid/--set: jobs {seen[(seed, tail)]} and {index} would write "
                    f"the same file {shown!r}"
                )
            seen[(seed, tail)] = index
            out = None if seed is None else folder / f"{path.stem}_seed{seed}{tail}.mp4"
            jobs.append(Job(index, path, seed, duration, tuple(overrides), folder, out))
    return jobs


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


def _crashed(job: Job, exc: BaseException) -> JobResult:
    error = f"worker crashed: {type(exc).__name__}: {exc}"
    return JobResult(job.index, job.out, False, 0, 0.0, error)


def run_batch(
    jobs: Sequence[Job], *, workers: int, on_result: Callable[[JobResult], None]
) -> list[JobResult]:
    """Run ``jobs`` and return their results sorted by index.

    ``workers == 1`` runs them in this process in planned order; more runs up to
    ``workers`` at once in spawned worker processes. ``on_result`` is called in this
    process as each job finishes. A worker that dies (or a job that cannot be sent
    to one) gives a failed result instead of stopping the batch.
    """
    results: list[JobResult] = []
    if workers <= 1:
        for job in jobs:
            result = run_job(job)
            results.append(result)
            on_result(result)
        return results
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=context) as pool:
        futures: dict[Future[JobResult], Job] = {pool.submit(run_job, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                if job.out is not None:
                    job.out.unlink(missing_ok=True)
                    job.out.with_suffix(".json").unlink(missing_ok=True)
                result = _crashed(job, exc)
            results.append(result)
            on_result(result)
    return sorted(results, key=lambda r: r.index)
