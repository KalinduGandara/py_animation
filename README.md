# bouncekit

Deterministic 2D physics videos: describe a scene in Python, get a vertical
H.264 MP4 (1080x1920, 60 fps by default). Physics by pymunk, drawing by pygame,
encoding by ffmpeg (must be on `PATH`).

## Quickstart

```bash
uv sync
uv run bouncekit render examples/single_ball.py          # -> out/single_ball_seed42.mp4
uv run bouncekit render examples/single_ball.py --seed 7 --duration 5 --out out/x.mp4
uv run bouncekit preview examples/single_ball.py         # live window
uv run python examples/single_ball.py                    # same as preview
```

Preview keys: Space pause, Right step (paused), R restart, Esc/Q quit.
The same scene and seed always produce identical frames.

## A scene

```python
from bouncekit import Scene

scene = Scene(duration=10.0, seed=42)
scene.add_circle(center=(540, 960), radius=450)
scene.add_ball(pos=(540, 700), radius=30, velocity=(scene.rng.uniform(-300, 300), 0))

if __name__ == "__main__":
    scene.run()
```

## API overview

- `Scene(width=1080, height=1920, fps=60, duration=60.0, seed=0, background="#000000",
  gravity=(0, 900), substeps=8, max_speed=4000)` - one video. Coordinates are
  pixels, origin top-left, +y down. `scene.rng` is a `random.Random` seeded from `seed`.
- `scene.add_circle(center, radius, thickness=8, color, gap_degrees=0,
  angular_velocity=0, segments=128, elasticity=1, tags=())` -> `CircleBoundary`.
- `scene.add_ball(pos, radius, velocity=(0, 0), elasticity=1, color, tags=())` -> `Ball`.
- `scene.render(out)` encodes an MP4; `scene.preview(scale=0.45)` opens a window;
  `scene.run()` dispatches to the CLI (default `preview`).
- Colours: `"#rrggbb"` strings or RGB tuples; see `bouncekit.colors`.
- Invalid settings raise `ConfigError`.

## CLI

`bouncekit render <scene.py> [--seed N] [--duration S] [--out PATH]` and
`bouncekit preview <scene.py> [--seed N] [--duration S]`. The file is imported
(its `__main__` block does not run) and must define exactly one module-level
`Scene`. `--seed`/`--duration` apply before the script's own code runs, so values
drawn from `scene.rng` follow the CLI seed. Default output:
`out/<script-stem>_seed<seed>.mp4`.

## Development

```bash
uv run pytest -q && uv run ruff check . && uv run mypy
```
