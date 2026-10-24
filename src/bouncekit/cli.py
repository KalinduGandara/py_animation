"""Command-line interface: ``bouncekit render`` and ``bouncekit preview``."""

import argparse
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

from bouncekit import scene as scene_module
from bouncekit.errors import BouncekitError, SceneLoadError
from bouncekit.render.preview import run_preview
from bouncekit.scene import Scene

DEFAULT_SCALE = 0.45
ERROR_EXIT = 2


def load_scene(path: str | Path, seed: int | None = None, duration: float | None = None) -> Scene:
    """Execute a scene script and return its single module-level ``Scene``.

    ``seed`` and ``duration`` (when not ``None``) override the script's own
    values; they are active while the script runs, so anything it derives from
    ``scene.rng`` follows them. The script runs with ``__name__`` set to
    ``"__bouncekit_scene__"``, so its ``if __name__ == "__main__"`` block is skipped.

    Raises:
        SceneLoadError: if the file does not exist or defines zero or several scenes.
        ConfigError: if the script's scene configuration (or an override) is invalid.
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
    try:
        namespace = runpy.run_path(str(file), run_name="__bouncekit_scene__")
    finally:
        scene_module._overrides.clear()
    scenes: list[Scene] = []
    for value in namespace.values():
        if isinstance(value, Scene) and not any(value is s for s in scenes):
            scenes.append(value)
    if len(scenes) != 1:
        raise SceneLoadError(
            f"{file} must define exactly one module-level Scene; found {len(scenes)}"
        )
    return scenes[0]


def _build_parser(scene_optional: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bouncekit", description="Render or preview a bouncekit scene script."
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{render,preview}")
    scene_kwargs: dict[str, object] = {"type": Path, "help": "scene script (.py)"}
    if scene_optional:
        scene_kwargs["nargs"] = "?"
        scene_kwargs["default"] = None

    render = sub.add_parser("render", help="render the scene to an MP4 file")
    render.add_argument("scene", **scene_kwargs)  # type: ignore[arg-type]
    render.add_argument("--seed", type=int, help="override the scene's seed")
    render.add_argument("--duration", type=float, help="override the duration in seconds")
    render.add_argument("--out", type=Path, help="output path (default out/<stem>_seed<N>.mp4)")

    preview = sub.add_parser("preview", help="play the scene in a window")
    preview.add_argument("scene", **scene_kwargs)  # type: ignore[arg-type]
    preview.add_argument("--seed", type=int, help="override the scene's seed")
    preview.add_argument("--duration", type=float, help="override the duration in seconds")
    preview.add_argument(
        "--scale", type=float, default=DEFAULT_SCALE, help="window scale (default 0.45)"
    )
    return parser


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
    try:
        if args.command == "render":
            scene = load_scene(script, seed=args.seed, duration=args.duration)
            out = args.out or Path("out") / f"{script.stem}_seed{scene.config.seed}.mp4"
            written = scene.render(out)
            print(f"wrote {written} ({scene.frame} frames)")
        else:
            load_scene(script, seed=args.seed, duration=args.duration)  # fail fast
            run_preview(
                lambda: load_scene(script, seed=args.seed, duration=args.duration), args.scale
            )
    except BouncekitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return ERROR_EXIT
    return 0
