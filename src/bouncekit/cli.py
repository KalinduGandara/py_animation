"""Command-line interface: ``bouncekit render``, ``bouncekit preview`` and ``bouncekit batch``."""

import argparse
import math
import runpy
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from bouncekit import scene as scene_module
from bouncekit.batch import (
    Job,
    JobResult,
    parse_assignments,
    parse_grid,
    parse_seeds,
    plan_jobs,
    run_batch,
    run_job,
)
from bouncekit.errors import BouncekitError, ConfigError, SceneLoadError
from bouncekit.export.ffmpeg import require_ffmpeg
from bouncekit.render.preview import run_preview
from bouncekit.scene import Scene

DEFAULT_SCALE = 0.45
ERROR_EXIT = 2


def load_scene(
    path: str | Path,
    seed: int | None = None,
    duration: float | None = None,
    params: Mapping[str, str] | None = None,
) -> Scene:
    """Execute a scene script and return its single module-level ``Scene``.

    ``seed`` and ``duration`` (when not ``None``) override the script's own
    values, and ``params`` maps param names to override text for
    ``scene.param``; all are active while the script runs, so anything it derives
    from them or from ``scene.rng`` follows them. The script runs with ``__name__`` set to
    ``"__bouncekit_scene__"``, so its ``if __name__ == "__main__"`` block is skipped.

    Raises:
        SceneLoadError: if the file does not exist or defines zero or several scenes.
        ConfigError: if the script's scene configuration (or an override) is invalid,
            or an override in ``params`` names a param the script never declared.
    """
    file = Path(path)
    if not file.is_file():
        raise SceneLoadError(f"scene file not found: {file}")
    overrides: dict[str, object] = {}
    if seed is not None:
        overrides["seed"] = seed
    if duration is not None:
        overrides["duration"] = duration
    scene_module._overrides.clear()
    scene_module._overrides.update(overrides)
    scene_module._param_overrides.clear()
    scene_module._param_overrides.update(params or {})
    try:
        namespace = runpy.run_path(str(file), run_name="__bouncekit_scene__")
    finally:
        scene_module._overrides.clear()
        scene_module._param_overrides.clear()
    scenes: list[Scene] = []
    for value in namespace.values():
        if isinstance(value, Scene) and not any(value is s for s in scenes):
            scenes.append(value)
    if len(scenes) != 1:
        raise SceneLoadError(
            f"{file} must define exactly one module-level Scene; found {len(scenes)}"
        )
    scene = scenes[0]
    declared = scene.params
    unknown = [name for name in (params or {}) if name not in declared]
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        names = ", ".join(declared)
        known = f"the script declares: {names}" if names else "the script declares no params"
        raise ConfigError(f"unknown param(s) {listed}; {known}")
    return scene


def _build_parser(scene_optional: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bouncekit", description="Render, preview or batch-render a bouncekit scene script."
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{render,preview,batch}")
    scene_kwargs: dict[str, object] = {"type": Path, "help": "scene script (.py)"}
    if scene_optional:
        scene_kwargs["nargs"] = "?"
        scene_kwargs["default"] = None

    render = sub.add_parser("render", help="render the scene to an MP4 file")
    render.add_argument("scene", **scene_kwargs)  # type: ignore[arg-type]
    render.add_argument("--seed", type=int, help="override the scene's seed")
    render.add_argument("--duration", type=float, help="override the duration in seconds")
    render.add_argument(
        "--out", type=Path, help="output path (default out/<stem>_seed<N>[_<name>-<value>...].mp4)"
    )
    render.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="override a scene.param (repeatable)")  # fmt: skip

    preview = sub.add_parser("preview", help="play the scene in a window")
    preview.add_argument("scene", **scene_kwargs)  # type: ignore[arg-type]
    preview.add_argument("--seed", type=int, help="override the scene's seed")
    preview.add_argument("--duration", type=float, help="override the duration in seconds")
    preview.add_argument(
        "--scale", type=float, default=DEFAULT_SCALE, help="window scale (default 0.45)"
    )
    preview.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                         help="override a scene.param (repeatable)")  # fmt: skip

    batch = sub.add_parser("batch", help="render the scene over seeds x param grids")
    batch.add_argument("scene", **scene_kwargs)  # type: ignore[arg-type]
    batch.add_argument("--seeds", metavar="SPEC",
                       help="seeds such as 1-10 or 3,7,9 (default: the script's seed)")  # fmt: skip
    batch.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                       help="override a scene.param in every job (repeatable)")  # fmt: skip
    batch.add_argument("--grid", action="append", default=[], metavar="NAME=V1,V2,...",
                       help="render every value of a scene.param (repeatable)")  # fmt: skip
    batch.add_argument("--duration", type=float, help="override the duration in seconds")
    batch.add_argument("--jobs", type=int, default=1, help="parallel worker processes (default 1)")
    batch.add_argument("--out-dir", type=Path, default=Path("out"),
                       help="output directory (default out)")  # fmt: skip
    batch.add_argument("--quiet", action="store_true", help="hide per-job 'wrote' lines")
    return parser


def _plan_batch(args: argparse.Namespace, script: Path) -> list[Job]:
    """Validate the batch options and plan the jobs; ``ConfigError`` names the option."""
    sets = parse_assignments(args.set, "--set")
    grid = parse_grid(args.grid)
    seeds = None if args.seeds is None else parse_seeds(args.seeds)
    if args.jobs < 1:
        raise ConfigError(f"--jobs must be an integer >= 1; got {args.jobs}")
    duration: float | None = args.duration
    if duration is not None and not (math.isfinite(duration) and duration > 0):
        raise ConfigError(f"--duration must be a positive finite number; got {duration!r}")
    return plan_jobs(
        script, seeds=seeds, sets=sets, grid=grid, duration=duration, out_dir=args.out_dir
    )


def _run_batch_command(args: argparse.Namespace, script: Path) -> int:
    """``bouncekit batch``: plan, check ffmpeg, run the jobs, report; returns the exit code."""
    try:
        jobs = _plan_batch(args, script)
        require_ffmpeg()
    except BouncekitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ERROR_EXIT
    args.out_dir.mkdir(parents=True, exist_ok=True)
    total = len(jobs)

    def report(result: JobResult) -> None:
        if result.ok:
            if not args.quiet:
                print(
                    f"[{result.index}/{total}] wrote {result.out} "
                    f"({result.frames} frames, {result.seconds} s)",
                    flush=True,
                )
        else:
            shown = result.out if result.out is not None else script.stem
            print(f"[{result.index}/{total}] FAILED {shown}: {result.error}", file=sys.stderr,
                  flush=True)  # fmt: skip

    results = run_batch(jobs, workers=args.jobs, on_result=report)
    failed = sum(not r.ok for r in results)
    print(f"batch: {total - failed} ok, {failed} failed")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None, default_scene: Path | None = None) -> int:
    """Entry point for the ``bouncekit`` command; returns the process exit code.

    ``default_scene`` is used by :meth:`Scene.run`: the scene argument becomes
    optional and a missing subcommand means ``preview``. Load, configuration and
    ffmpeg errors print ``error: ...`` to stderr and return 2.
    """
    args_list = list(sys.argv[1:] if argv is None else argv)
    if default_scene is not None and (not args_list or args_list[0].startswith("-")):
        args_list.insert(0, "preview")
    args = _build_parser(default_scene is not None).parse_args(args_list)
    script: Path | None = args.scene if args.scene is not None else default_scene
    assert script is not None  # argparse requires it unless default_scene is given
    if args.command == "batch":
        return _run_batch_command(args, script)
    try:
        overrides = parse_assignments(args.set, "--set")
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ERROR_EXIT
    if args.command == "render":
        job = Job(
            index=1,
            script=script,
            seed=args.seed,
            duration=args.duration,
            overrides=tuple(overrides),
            out_dir=Path("out"),
            out=args.out,
        )
        result = run_job(job)
        if not result.ok:
            print(f"error: {result.error}", file=sys.stderr)
            return ERROR_EXIT
        print(f"wrote {result.out} ({result.frames} frames)")
        return 0
    params = dict(overrides)

    def reload() -> Scene:
        return load_scene(script, seed=args.seed, duration=args.duration, params=params)

    try:
        reload()  # fail fast
        run_preview(reload, args.scale, watch=script, reload=reload)
    except BouncekitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ERROR_EXIT
    return 0
