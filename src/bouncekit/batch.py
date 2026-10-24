"""Render jobs and batches: planning, one load + render + metadata per job (FR-402..FR-405).

``bouncekit render`` runs one :class:`Job` through :func:`run_job`; ``bouncekit batch``
plans jobs with :func:`plan_jobs` and runs them with :func:`run_batch`.
"""

import contextlib
import itertools
import multiprocessing
import os
import re
import signal
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from multiprocessing.connection import Connection, wait
from multiprocessing.process import BaseProcess
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
    seed is known (after loading). ``script`` is the path as given on the CLI; it is
    recorded verbatim in the metadata (FR-405).
    """

    index: int
    script: str | Path
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
    path = Path(script)  # for the stem; jobs keep ``script`` as given
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
            jobs.append(Job(index, script, seed, duration, tuple(overrides), folder, out))
    return jobs


def _default_out(job: Job, seed: int) -> Path:
    return job.out_dir / f"{Path(job.script).stem}_seed{seed}{suffix(job.overrides)}.mp4"


def run_job(
    job: Job,
    *,
    progress: Callable[[int, int], None] | None = None,
    on_out: Callable[[Path], None] | None = None,
) -> JobResult:
    """Load the job's script, render the MP4 and write its metadata JSON beside it.

    Any ``Exception`` makes the job fail: its MP4 and JSON are deleted if they
    exist and the error is returned in the result. ``KeyboardInterrupt`` propagates.
    ``progress`` is passed to :meth:`Scene.render` (frames written, total frames).
    ``on_out`` is called once with the MP4 path as soon as it is known: at the start
    when ``job.out`` is set, else when the script creates its Scene (so a batch
    parent can clean up after a worker that dies, FR-404). The result's ``out``
    stays ``None`` when the script fails to load with ``job.out`` unset.
    """
    from bouncekit.cli import load_scene  # local import: cli imports this module

    t0 = time.monotonic()
    out = job.out
    announced: list[Path] = []

    def announce(path: Path) -> None:
        if not announced:
            announced.append(path)
            if on_out is not None:
                on_out(path)

    if out is not None:
        announce(out)
    try:
        scene = load_scene(
            job.script,
            seed=job.seed,
            duration=job.duration,
            params=dict(job.overrides),
            on_seed=lambda seed: announce(_default_out(job, seed)),
        )
        if out is None:
            out = _default_out(job, scene.config.seed)
        scene.render(out, progress=progress)
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


@dataclass
class _Worker:
    """A running job in its own spawned process; ``out`` is filled when announced."""

    job: Job
    process: BaseProcess
    reader: Connection
    out: Path | None
    result: JobResult | None = None
    closed: bool = field(default=False)


def _work(job: Job, conn: Connection) -> None:
    """Worker process body: run ``job``, sending ``("out", path)`` then ``("result", r)``."""
    if hasattr(os, "setpgid"):
        os.setpgid(0, 0)  # own process group, so the parent can also stop its ffmpeg
    try:
        result = run_job(job, on_out=lambda path: conn.send(("out", path)))
        conn.send(("result", result))
    finally:
        conn.close()


def _drain(worker: _Worker) -> None:
    """Read every message the worker has sent so far."""
    try:
        while not worker.closed and worker.reader.poll():
            kind, value = worker.reader.recv()
            if kind == "out":
                worker.out = value
            else:
                worker.result = value
    except (EOFError, OSError):
        worker.closed = True


def _kill(process: BaseProcess) -> None:
    """Kill ``process`` and everything in its process group (its ffmpeg)."""
    pid = process.pid
    if pid is not None and hasattr(os, "killpg"):
        with contextlib.suppress(OSError):  # the group may already be gone
            os.killpg(pid, signal.SIGKILL)
    if process.is_alive():
        process.kill()
    process.join()


def _crashed(job: Job, out: Path | None, reason: str) -> JobResult:
    if out is not None:
        out.unlink(missing_ok=True)
        out.with_suffix(".json").unlink(missing_ok=True)
    return JobResult(job.index, out, False, 0, 0.0, f"worker crashed: {reason}")


def run_batch(
    jobs: Sequence[Job], *, workers: int, on_result: Callable[[JobResult], None]
) -> list[JobResult]:
    """Run ``jobs`` and return their results sorted by index.

    ``workers == 1`` runs them in this process in planned order; more runs up to
    ``workers`` at once, each job in its own spawned process (started in planned
    order). ``on_result`` is called in this process as each job finishes. A worker
    that dies (or a job that cannot be sent to one) fails only that job: its
    process group (its ffmpeg) is killed and its MP4/JSON deleted, and the other
    jobs carry on.
    """
    results: list[JobResult] = []
    if workers <= 1:
        for job in jobs:
            result = run_job(job)
            results.append(result)
            on_result(result)
        return results
    context = multiprocessing.get_context("spawn")
    pending = list(reversed(jobs))
    running: list[_Worker] = []

    def finish(result: JobResult) -> None:
        results.append(result)
        on_result(result)

    try:
        while pending or running:
            while pending and len(running) < workers:
                job = pending.pop()
                reader, writer = context.Pipe(duplex=False)
                process = context.Process(target=_work, args=(job, writer), daemon=True)
                try:
                    process.start()
                except Exception as exc:
                    reader.close()
                    finish(_crashed(job, job.out, f"{type(exc).__name__}: {exc}"))
                    continue
                finally:
                    writer.close()  # the child holds its own copy
                running.append(_Worker(job, process, reader, job.out))
            if not running:
                continue
            wait(
                [w.process.sentinel for w in running] + [w.reader for w in running if not w.closed]
            )
            for worker in list(running):
                _drain(worker)
                if worker.process.is_alive():
                    continue
                worker.process.join()
                _drain(worker)
                running.remove(worker)
                worker.reader.close()
                if worker.result is not None:
                    finish(worker.result)
                    continue
                _kill(worker.process)
                code = worker.process.exitcode
                finish(_crashed(worker.job, worker.out, f"worker process exited with code {code}"))
    finally:
        for worker in running:
            _kill(worker.process)
            worker.reader.close()
    return sorted(results, key=lambda r: r.index)
