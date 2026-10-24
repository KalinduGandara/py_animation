# Design — bouncekit (M0)

## 1. Architecture overview

```mermaid
flowchart LR
    script[scene script<br/>examples/single_ball.py] -->|builds| Scene
    cli[cli.py<br/>render / preview] -->|runpy + overrides| script
    cli --> Scene
    Scene -->|owns| World[world/<br/>Ball, CircleBoundary<br/>pymunk.Space]
    Scene -->|frames()| Renderer[render/<br/>Renderer protocol<br/>PygameRenderer]
    Renderer -->|reads state| World
    Scene -->|RGB bytes| Export[export/ffmpeg.py<br/>FfmpegWriter]
    Scene -->|RGB surfaces| Preview[render/preview.py<br/>pygame window]
    Export --> mp4[(out/*.mp4)]
```

Data flow per frame: `Scene.step_frame()` runs `substeps` fixed physics steps → `Renderer` draws the world (read-only) → bytes go to ffmpeg (render) or the surface is scaled to the window (preview). The simulation never reads wall-clock time; only the preview's pacing uses `pygame.time.Clock`.

## 2. Tech stack

| Concern | Choice | Why |
|---|---|---|
| Runtime | Python 3.12 via uv | SRS requires uv + ≥3.11; 3.12 is mature and supported by all deps |
| Physics | pymunk 7.3.1 | SRS; Chipmunk is deterministic when single-threaded with fixed dt |
| Rendering | pygame-ce 2.5.8 | SRS; off-screen `Surface` works without a display; `aacircle` available |
| Video | ffmpeg 9 (subprocess) | SRS; raw RGB24 pipe, no temp files |
| Tests / lint / types | pytest, ruff, mypy (dev only) | SDD quality gate (A3) |

numpy is already a declared dependency (needed from M1); M0 does not use it.

## 3. Package layout and responsibilities

```
src/bouncekit/
  __init__.py          # exports Scene, Ball, CircleBoundary, ConfigError, colors
  errors.py            # ConfigError, FfmpegError                              FR-001, FR-007
  colors.py            # Color = tuple[int,int,int]; parse_color()             FR-001
  config.py            # SceneConfig dataclass + validation                    FR-001, FR-005
  scene.py             # Scene: config, rng, object registry, step loop,
                       #   frames(), render(), preview(), run()               FR-001..FR-010
  world/
    __init__.py
    ball.py            # Ball handle (dynamic body + circle shape)            FR-004, FR-005
    circle.py          # CircleBoundary (kinematic body, N segments, gap)     FR-003
  render/
    __init__.py
    base.py            # Renderer Protocol                                    FR-008
    pygame_renderer.py # PygameRenderer (off-screen Surface)                  FR-008
    preview.py         # run_preview(): window, keys, pacing                  FR-009
  export/
    __init__.py
    ffmpeg.py          # require_ffmpeg(), FfmpegWriter context manager       FR-007
  cli.py               # argparse, load_scene(), overrides                    FR-010
examples/single_ball.py                                                       FR-011
tests/                                                                         NFR-*
```

Each world object knows how to draw itself through the `Renderer` protocol (`draw(renderer)`), so the scene just iterates its objects in insertion order.

## 4. Interfaces

### 4.1 Public API

```python
class Scene:
    def __init__(self, *, width=1080, height=1920, fps=60, duration=60.0, seed=0,
                 background="#000000", gravity=(0.0, 900.0), substeps=8,
                 max_speed=4000.0) -> None
    config: SceneConfig            # read-only after construction
    rng: random.Random
    frame: int                     # frames simulated so far
    time: float                    # frame / fps
    total_frames: int              # round(duration * fps)
    def add_circle(self, *, center, radius, thickness=8.0, color="#ffffff",
                   gap_degrees=0.0, angular_velocity=0.0, segments=128,
                   elasticity=1.0, tags=()) -> CircleBoundary
    def add_ball(self, *, pos, radius, velocity=(0.0, 0.0), elasticity=1.0,
                 color="#ffffff", tags=()) -> Ball
    def step_frame(self) -> None   # advance one frame (substeps fixed steps)
    def draw(self, renderer: Renderer) -> None
    def frames(self) -> Iterator[bytes]   # yields RGB24 for frames 0..total-1
    def render(self, out: str | Path) -> Path
    def preview(self, scale: float = 0.45) -> None
    def run(self) -> None          # CLI dispatch using sys.argv
```

`frames()` resets nothing; a scene is simulated once per process. Re-running (preview restart, determinism test) rebuilds the scene by re-executing the script / factory. This keeps "fresh scene = fresh state" trivially correct instead of writing reset logic for every object.

`Ball`: `position`, `velocity` (get/set), `radius`, `color`, `tags: frozenset[str]`, `body`, `shape` (escape hatch to pymunk).
`CircleBoundary`: `center`, `radius`, `thickness`, `gap_degrees`, `angle_degrees` (current rotation), `color`, `tags`, `body`.

### 4.2 Renderer protocol (render/base.py)

```python
class Renderer(Protocol):
    width: int; height: int
    def clear(self, color: Color) -> None
    def circle(self, center: Vec, radius: float, color: Color) -> None          # filled, AA edge
    def thick_line(self, a: Vec, b: Vec, width: float, color: Color) -> None     # round caps
    def to_rgb_bytes(self) -> bytes                                              # width*height*3
```

The ring draws each present segment with `thick_line`; round caps (a filled circle of radius width/2 at each end) make consecutive segments join seamlessly and match the physics shape (segment radius = thickness/2). A future skia backend implements the same four methods.

### 4.3 ffmpeg (export/ffmpeg.py)

```
ffmpeg -hide_banner -loglevel error -y -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {fps} -i -
       -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart
       -fflags +bitexact -flags:v +bitexact {out}
```
`FfmpegWriter(path, width, height, fps)` is a context manager with `write(frame: bytes)`; it checks frame length, closes stdin on exit, waits, and raises `FfmpegError` with the stderr tail on non-zero exit (or on `BrokenPipeError`). `require_ffmpeg()` uses `shutil.which`, raising `FfmpegError("ffmpeg not found on PATH; install it, e.g. `brew install ffmpeg`")`. `Scene.render` calls it before simulating.

### 4.4 CLI (cli.py)

```
bouncekit render  SCENE.py [--seed N] [--duration S] [--out PATH]
bouncekit preview SCENE.py [--seed N] [--duration S] [--scale F]
```
- `load_scene(path, seed=None, duration=None) -> Scene`: sets module-level overrides in `scene.py` (`_overrides`), executes the file with `runpy.run_path(path, run_name="__bouncekit_scene__")` (so `if __name__ == "__main__"` is skipped), clears the overrides in `finally`, and returns the single `Scene` instance found in the resulting globals; otherwise raises `SceneLoadError` with the count found.
- `Scene.__init__` applies `_overrides` (seed/duration) before creating `rng`, so the script's own `scene.rng` usage follows the CLI seed.
- `Scene.run()` → `cli.main(sys.argv[1:], default_scene=Path(sys.argv[0]))`; with no subcommand it previews. It reloads the script via `load_scene` (so overrides apply), rather than using `self`.
- Importing `bouncekit` sets `PYGAME_HIDE_SUPPORT_PROMPT=1` (if unset) so the CLI prints only its own output.
- Errors (`ConfigError`, `FfmpegError`, `SceneLoadError`, missing file) print `error: ...` to stderr and exit 2; no traceback.
- Entry point: `[project.scripts] bouncekit = "bouncekit.cli:main"`.
- Implementation notes (T-006): `SceneLoadError` lives in `errors.py` (subclass of `BouncekitError`) and is also raised for a missing scene file. `main(argv=None, default_scene=None) -> int` returns the exit code (0 / 2); argparse usage errors keep argparse's own exit. The same `Scene` bound to several names counts once. `preview` loads the scene once up front so load errors exit 2 before a window opens, then hands `run_preview` a factory that reloads the script. `render/preview.py` exists as a `run_preview` placeholder until T-007.

### 4.5 Preview (render/preview.py)

`run_preview(make_scene: Callable[[], Scene], scale)` — builds a scene, opens a window of `(W·scale, H·scale)`, each loop: handle events, step if playing and not finished, draw via `PygameRenderer`, `smoothscale` to the window, `clock.tick(fps)`. R calls `make_scene()` again. The window title shows frame/total and "paused"/"done".

Implementation notes (T-007): logic lives in a `Preview` class (`handle_event`, `tick`, `run(max_frames)`); `run_preview(make_scene, scale=0.45, max_frames=None)` returns the final `Scene` (small addition for testability). Each loop draws the current frame, then steps once if playing and unfinished. `Scene.preview` passes itself first; restart reloads `sys.argv[0]` via `cli.load_scene` with the scene's seed/duration.

## 5. Physics details

- Space: `pymunk.Space()` (single-threaded), `gravity` from config, `iterations = 10` set explicitly, damping 1.0.
- Step: `dt = 1 / (fps * substeps)`; `step_frame` calls `space.step(dt)` `substeps` times. `frame += 1`.
- Ball: `Body(mass, moment)` with mass = π·r² (density 1), `moment_for_circle`; `Circle` with `elasticity`, `friction = 0`. Velocity clamp: `Scene.step_frame` calls `ball.clamp_speed(max_speed)` for every ball after **each** `space.step`. (Changed after review: a clamp in `velocity_func` missed collision impulses, which Chipmunk applies after velocity integration, so speeds reached ~4100 px/s against a spinning ring.)
- Ring: kinematic `Body` at `center`, `angular_velocity = radians(deg_per_s)` (pymunk positive angle = clockwise on screen because +y is down). Segment endpoints at angles `θ_k = 2πk/N` in body-local coords; segment k is skipped if its midpoint angle (normalised to (−180°, 180°]) has |angle| < gap/2. Consecutive present segments get `set_neighbors` for smooth seams. Each segment has `radius = thickness/2`, `elasticity`, `friction = 0`.
- Effective elasticity in pymunk is the product of both shapes; defaults 1.0 × 1.0 = 1.0.
- Tunnelling: a collision is caught only if the ball cannot cross a segment's centre line in one step, i.e. `max_speed·dt < ball.radius + thickness/2`. At 4000 px/s and dt = 1/480 s that is 8.33 px, so with an 8 px ring the ball radius must be > 4.33 px (review measured: r=4 escapes 5/8 runs, r=5 escapes 0/8). `add_ball`/`add_circle` check every new ball/ring pair and emit `TunnellingWarning` (in `errors.py`, exported from the package) when violated. NFR-003 tests the safe case; a test checks the warning.

## 6. Determinism strategy (NFR-001)

- No wall-clock time, no unseeded randomness, no threading in the simulation. Objects are stored and drawn in insertion order (lists, not sets).
- Draw order and pixel output depend only on state; pygame software rendering is deterministic.
- Test: build a small scene (e.g. 270×480, 30 fps, 2 s) twice via a factory, hash every frame with SHA-256, and compare the lists. A second test checks that different seeds (with an rng-derived velocity) produce different hashes, which proves the hash is sensitive.

## 7. Error handling and configuration

- All config validation happens at construction (`SceneConfig.__post_init__`, `add_*`) and raises `ConfigError("<field> must be ...; got <value>")`.
- Config is dataclasses (`SceneConfig`, frozen). No config files in M0.
- No logging framework; the CLI prints one line when the render finishes (`wrote out/x.mp4 (N frames)`).

## 8. Testing strategy

| Test file | Covers |
|---|---|
| `tests/test_config.py` | FR-001 defaults/validation, colours, FR-003/FR-004 validation |
| `tests/test_world.py` | FR-002 gravity direction, FR-003 gap passes ball / closed ring holds it / rotation, FR-005 step count + clamp, NFR-003 no tunnelling, seam smoothness (ball rolls along bottom without speed spikes) |
| `tests/test_render.py` | FR-008 frame size/colour pixels, NFR-004 rendering doesn't mutate physics |
| `tests/test_determinism.py` | NFR-001 frame-hash equality; different seed differs |
| `tests/test_export.py` | FR-007 tiny real ffmpeg encode probed with ffprobe; missing ffmpeg error (monkeypatched `shutil.which`); bad frame length |
| `tests/test_cli.py` | FR-010 load_scene single/zero/many, overrides applied before script code, `__main__` block not run, missing file, render subcommand end-to-end on a tiny scene |

Preview (FR-009) is tested by running `run_preview` with `SDL_VIDEODRIVER=dummy` for a few frames with a test hook (`max_frames` argument), plus manual check.

## 9. Key decisions

| Decision | Alternatives | Why chosen |
|---|---|---|
| Re-run the script for restart / determinism instead of `Scene.reset()` | Snapshot & restore pymunk state | Rebuild is always correct and needs no per-object reset code |
| CLI overrides via module-level `_overrides` read in `Scene.__init__` | Parse `sys.argv` inside `Scene`; require a `make_scene(seed)` factory | Keeps the SRS script shape; works for both `bouncekit render` and `python scene.py` |
| Objects draw themselves via the Renderer protocol | Renderer knows every object type | Adding an object type touches one file; backends only implement primitives |
| Ring = N straight segments with `set_neighbors` | pymunk `Poly`, or analytic circle collision | SRS asks for arc segments; supports gaps and rotation directly |
| Velocity clamp in `velocity_func` | Clamp after `space.step` | Applied every substep inside pymunk's integration, before position update |
