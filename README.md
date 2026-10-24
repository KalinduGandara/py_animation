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

## Rules (M2)

Rules react to events (`Event`: `kind`, `step`, `frame`, `time`, `objects`, `speed`,
`position`) after each physics step; they never touch the space mid-step, so every
change is queued and applied right after dispatch. Each `scene.<rule>(..., handlers)`
takes a list of handlers (built-in actions and/or callables) run in order, or, with the
handlers omitted, works as a decorator:

```python
scene.on_collision("ball", "wall", [A.split(max_total=128), A.play(S.scale("C4"))])


@scene.on_collision("ball", "hazard")
def hit(ctx, a, b, event):  # a carries the first tag, b the second
    ctx.destroy(a)
```

Rule kinds and callback signatures:

| Rule | Fires | Callback |
|---|---|---|
| `on_collision(tag_a, tag_b, ..., cooldown=, object_cooldown=)` | objects start touching | `f(ctx, a, b, event)` |
| `on_escape(ring, tag, ..., margin=)` | a tagged ball leaves the ring (once per pair) | `f(ctx, ball, ring, event)` |
| `on_spawn(tag, ...)` / `on_destroy(tag, ...)` | a tagged object is added / removed | `f(ctx, obj, event)` |
| `every(seconds, ...)` / `at(seconds, ...)` | periodically / once at a time | `f(ctx, event)` |
| `when(predicate, ...)` | first frame `predicate(scene)` is true | `f(ctx, event)` |

Built-in actions (`from bouncekit import actions as A`; `target="a"` by default, or
`"b"`, or a ball/ring handle):

| Action | Effect |
|---|---|
| `A.play(source, gain=1.0)` | play a note |
| `A.destroy(target=)` | remove a ball or ring |
| `A.split(into=2, spread_degrees=30, radius_scale=1, max_total=None)` | split a ball into several |
| `A.spawn(pos=, radius=, velocity=, count=1, color=, tags=, constant_speed=, max_total=)` | add balls; `pos`/`velocity`/`color` may be `f(ctx)` |
| `A.recolor(color)`, `A.resize(...)`, `A.set_velocity(...)`, `A.flash(...)` | change look or motion |
| `A.end_after(seconds)` | end the video that long after the current frame |

`ctx` (`ActionContext`) has `scene`, `event`, `a`, `b`, `rng` (use it for all randomness),
`time` and the matching methods: `ctx.destroy(obj)`, `ctx.split(...)`, `ctx.spawn(...)`,
`ctx.recolor`, `ctx.resize`, `ctx.set_velocity`, `ctx.flash`, `ctx.play(source)`,
`ctx.end_after(seconds)`. Queued commands on an object that is already gone are skipped.

- **Cooldowns:** a collision rule skips its non-play handlers for a pair that fired
  less than `cooldown` seconds ago (default `Scene(rule_cooldown=0.05)`); `object_cooldown`
  does the same per object. `A.play` is governed by the audio trigger policy instead.
- **Caps and refusal:** `Scene(max_balls=1000)` caps live balls. A split or spawn that would
  exceed it (or its own `max_total`) or whose ball could tunnel through a ring is
  refused silently and deterministically; it never raises mid-render.
- **Constant speed:** `add_ball(..., constant_speed=True)` (also on `A.spawn`) keeps a
  ball at its initial speed after every step.
- **Ending early:** `A.end_after(seconds)` / `ctx.end_after(seconds)` shortens the video;
  `render` and `audio_buffer` stop there.
- Scenes with 100+ balls switch to pymunk's spatial hash automatically.

Examples (each renders with an AAC track): `examples/split_on_wall.py` (a ball doubles on
every wall hit up to a cap), `examples/escape_rotating_gap.py` (balls escape a rotating
gap and are replaced by two), `examples/destroy_on_contact.py` (a hazard destroys balls;
`every` spawns more; `when` + `end_after` ends the video).

## Effects and melody (M3)

Visual effects never change physics; `A.particles` draws from `scene.fx_rng`, so the
same seed still gives identical frames. Audio gets MIDI melodies, sample voices and panning.

```python
from bouncekit import colors as C

scene.add_circle(center=(540, 960), radius=450, glow=1.0, tags={"wall"})
scene.add_ball(pos=(540, 800), radius=22, color=C.hue_cycle(), trail=True, glow=1.0, tags={"ball"})
tune = S.melody(
    "assets/midi/ode_to_joy.mid", voice=S.sample("assets/samples/kalimba.wav", root="A4")
)
scene.on_collision("ball", "wall", [A.play(tune, pan=0.8), A.particles(count=14)])
```

- `EffectsConfig(trail_seconds=0.3, glow_blur=18.0, max_particles=2000)`: pass as
  `Scene(effects=EffectsConfig(...))`.
- `add_ball(..., trail=True, glow=1.0)` leaves a fading trail and a blurred light (glow 0..4);
  `add_circle(..., glow=)` lights the ring. Split and spawned balls inherit both.
- `A.particles(count=12, speed=400, lifetime=0.5, size=3, color=None, drag=2, pos=None)` bursts
  impact particles at the contact point; `ctx.particles(...)` does the same from a callback.
- Colour modes (`from bouncekit import colors as C`): `C.fixed(c)`, `C.hue_cycle(start=, step=)`
  (next hue per new ball), `C.by_speed(slow=, fast=)`, `C.by_generation(...)`; rings take plain colours.
- `S.melody(path, voice=, track=None, transpose=0)` plays a MIDI file one chord per hit
  and wraps; the hits set the rhythm. `S.sample(path, root="C4", duration=None)` is a voice
  that pitch-shifts an audio file; use it as `voice=` of `S.note`, `S.scale` or `S.melody`.
- `A.play(source, gain=1.0, pan=0.0)`: `pan` in [0, 1] places the note by the event's x
  position (0 centred, 1 full left-to-right width).
- Preview hot-reload: `bouncekit preview scene.py` watches the file and reloads on save;
  errors in the script are shown and the last good scene keeps running.
- `uv run python scripts/make_assets.py` regenerates `assets/midi/ode_to_joy.mid` and
  `assets/samples/kalimba.wav` deterministically.

See `examples/midi_melody.py` (`uv run bouncekit render examples/midi_melody.py`).

## Parameters, batches and text (M4)

```python
gap = scene.param("gap", 40.0)      # `--set gap=60` -> 60.0 (typed like the default)
ring = scene.add_circle(center=(540, 960), radius=450, gap_degrees=gap, tags={"wall"})
scene.add_text("Can it escape?", pos=(540, 260), size=72, end=3.0)
scene.add_text(lambda s: f"balls: {s.count('ball')}", pos=(540, 1700), size=48)
```

```bash
uv run bouncekit render examples/param_sweep.py --set gap=60 --set speed=450
uv run bouncekit batch examples/param_sweep.py --seeds 1-3 --grid gap=30,60 --jobs 2 --out-dir out/sweep
```

- `scene.param(name, default)` declares a param and returns the `--set name=value` override
  (parsed as `bool`, `int`, `float` or `str` like the default) or the default. It never
  touches `scene.rng`.
- `bouncekit batch <scene.py>` renders every seed x grid combination: `--seeds 1-3` or
  `1,5,9`, `--grid name=v1,v2` (repeatable; the cartesian product), `--set` for fixed
  overrides, `--duration`, `--jobs N` worker processes, `--out-dir DIR`, `--quiet`.
  A failing job is reported and does not stop the others; the exit code is non-zero if any failed.
- Names: `<out-dir>/<stem>_seed<seed>_<name>-<value>.mp4` (one `_name-value` per override).
- Each MP4 gets a metadata `.json` beside it: `scene`, `video`, `seed`, `params`, `duration`,
  `frames`, `fps`, `size`, `events` (counts per kind), `sound_triggers`, `versions`,
  `render_seconds`. Everything but `render_seconds` is deterministic.
- `scene.add_text(text, pos=, size=64, color=, start=0, end=None)` draws centred text
  (a string or `f(scene) -> str`), visible from `start` to `end` seconds.
- `render` and `batch` show a progress bar with an ETA on a terminal; `--quiet` hides it.

See `examples/param_sweep.py`.

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
