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
- Ball speed is clamped to `max_speed` after every physics step. If a ball at
  `max_speed` could pass through a ring in one step (`max_speed / (fps * substeps)` >=
  `ball radius + ring thickness / 2`), `add_ball`/`add_circle` raise `ConfigError`
  saying how to fix it (more `substeps`, lower `max_speed`, bigger ball, thicker ring).

## Sound (M1)

Collisions can play notes. Tag objects, register a rule, and `render` muxes an
AAC track (48 kHz stereo) into the MP4. Scenes with no sound rules stay
video-only; `preview` is always silent.

```python
from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import sound as S

scene = Scene(duration=10.0, seed=42)
scene.add_circle(center=(540, 960), radius=450, tags={"wall"})
scene.add_ball(pos=(540, 700), radius=30, tags={"ball"})
scene.on_collision("ball", "wall", [A.play(S.scale("C4", voice="pluck"))])
```

See `examples/bounce_notes.py` (`uv run bouncekit render examples/bounce_notes.py`).

- `scene.on_collision(tag_a, tag_b, [A.play(...)])` - when tagged objects start
  touching (either order), run the actions. Rules run in registration order.
- `A.play(source, gain=1.0)` - play a sound source.
- Sound sources: `S.note("C4", voice="sine")` always plays one pitch (a name like
  `"C#4"` or a frequency in Hz); `S.scale("C4", mode="major_pentatonic", octaves=2,
  voice="sine")` plays the next scale note on each trigger and wraps. Modes: `major`,
  `minor`, `major_pentatonic`, `minor_pentatonic`, `chromatic`.
- Voices: `"sine"`, `"triangle"`, `"pluck"` (Karplus-Strong), `"marimba"`, or an
  instance such as `Pluck(duration=0.5)`.
- `AudioConfig` (pass as `Scene(audio=AudioConfig(...))`), defaults: `min_impact_speed=40`
  px/s, `reference_speed=1500` px/s (full gain), `min_retrigger_interval=0.05` s,
  `max_triggers_per_frame=6`, `max_polyphony=24`, `peak_dbfs=-1.0`.
- Louder impacts play louder; the mix is normalised to `peak_dbfs`. Output is
  deterministic for a given seed.

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
