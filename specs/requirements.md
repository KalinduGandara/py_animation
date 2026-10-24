# Requirements — bouncekit (M0)

Source: the user's master prompt ("SRS"). Section references use the SRS headings:
**[Ctx]** Context, **[Stack]** Tech stack, **[P1..P5]** Core principles 1–5, **[API]** Public API,
**[Arch]** Architecture, **[Phys]** Physics details, **[M0]** Milestone M0, **[Eng]** Engineering standards.
Clarification decisions are referenced as **[C#]** (see `clarifications.md`).

Scope: **Milestone M0 only** (skeleton + first video, no sound).

---

## Functional requirements

### FR-001 Scene construction — [API], [P5], [Eng]
As a scene author, I create a `Scene` with keyword options so that one script defines one video.
- WHEN `Scene()` is constructed with no arguments, THE SYSTEM SHALL use width 1080, height 1920, fps 60, substeps 8, duration 60 s, seed 0, background `"#000000"`, gravity `(0, 900)`.
- WHEN `Scene(width=, height=, fps=, duration=, seed=, background=, gravity=, substeps=)` is given, THE SYSTEM SHALL store them in a `SceneConfig` dataclass exposed as `scene.config`.
- WHEN width or height is not a positive even integer, fps/duration/substeps are not positive, or duration is shorter than one frame, THE SYSTEM SHALL raise `ConfigError` naming the field and the bad value [C/A6].
- WHEN a colour string is not `#rgb`/`#rrggbb` and a colour tuple is not 3 ints in 0–255, THE SYSTEM SHALL raise `ConfigError` naming the value.

### FR-002 Coordinates — [P5]
- THE SYSTEM SHALL accept all positions, velocities and gravity in screen pixels, origin top-left, +y down; positive gravity y pulls balls down the screen.

### FR-003 Ring boundary — [API], [Arch], [Phys], [C4]
As a scene author, I add a circular boundary with `scene.add_circle(center, radius, thickness=8, color="#ffffff", gap_degrees=0, angular_velocity=0, segments=128, elasticity=1.0, tags=set())` and receive a `CircleBoundary` handle.
- THE SYSTEM SHALL build the ring from `segments` straight segments on a kinematic body, with segment radius `thickness / 2`.
- WHEN `gap_degrees > 0`, THE SYSTEM SHALL omit every segment whose angular midpoint lies within the gap, centred on local angle 0° (A5); a ball can pass through the opening.
- WHEN `angular_velocity` (degrees/second, positive = clockwise on screen) is non-zero, THE SYSTEM SHALL rotate the ring at that rate and its collisions SHALL follow the rotation.
- WHEN radius ≤ 0, thickness ≤ 0, segments < 8, or gap not in [0, 360), THE SYSTEM SHALL raise `ConfigError`.
- Neighbouring segments SHALL be joined smoothly so a ball rolling along the inside does not snag at seams.

### FR-004 Ball — [API], [Phys]
As a scene author, I add a ball with `scene.add_ball(pos, radius, velocity=(0,0), elasticity=1.0, color="#ffffff", tags=set())` and receive a `Ball` handle exposing at least `position`, `velocity`, `radius`, `color`, `tags`.
- THE SYSTEM SHALL simulate the ball as a dynamic body affected by scene gravity, bouncing off rings with the given elasticity and zero friction.
- WHEN radius ≤ 0, THE SYSTEM SHALL raise `ConfigError`.

### FR-005 Fixed timestep simulation — [P1], [Phys]
- THE SYSTEM SHALL advance the physics by exactly `substeps` steps of `1 / (fps × substeps)` seconds per frame, with no wall-clock input.
- Frame `i` SHALL show the state after `i` frames of simulation (frame 0 = initial state); a render SHALL contain `round(duration × fps)` frames.
- WHEN any ball's speed would exceed `scene.config.max_speed` (default 4000 px/s), THE SYSTEM SHALL clamp its velocity magnitude to `max_speed` keeping direction. The clamp SHALL hold after every physics step, including steps with collision impulses (e.g. from a spinning ring).

### FR-006 Seeded RNG — [P1]
- THE SYSTEM SHALL expose `scene.rng` (a `random.Random` seeded from `seed`) as the only source of randomness for scene scripts.

### FR-007 Offline render to MP4 — [P2], [Stack], [Arch], [M0]
- WHEN `bouncekit render scene.py` runs, THE SYSTEM SHALL draw every frame off-screen and pipe raw RGB24 frames to ffmpeg's stdin (no intermediate image files).
- THE SYSTEM SHALL encode H.264, `yuv420p`, CRF 18, `+faststart`, at the scene's width, height and fps.
- WHEN no `--out` is given, THE SYSTEM SHALL write `out/<scene-file-stem>_seed<seed>.mp4`, creating the directory [C9].
- WHEN ffmpeg is not on `PATH`, THE SYSTEM SHALL fail before simulating with a message telling the user to install ffmpeg.
- WHEN ffmpeg exits with an error, THE SYSTEM SHALL raise an error that includes ffmpeg's stderr tail.

### FR-008 Rendering visuals — [Stack], [Arch], [C10]
- THE SYSTEM SHALL draw the background colour, each ring (with its gap and current rotation) and each ball in its colour, using anti-aliased primitives.
- Edges SHALL be smooth: every pixel's value SHALL equal the analytic one-pixel coverage of the shape (`clip(0.5 − signed distance, 0, 1)`) within ±1 level; rings SHALL be drawn as true arcs (not chords) whose gap ends are round caps at the physics segment end points. (Added 2026-10-24 after user saw jagged ring edges.)
- All drawing SHALL go through a `Renderer` interface; the pygame-ce backend is the only implementation in M0.

### FR-009 Live preview — [Stack], [P2], [C8]
- WHEN `bouncekit preview scene.py` runs (or `python scene.py` with no subcommand), THE SYSTEM SHALL open a window showing the same frames as the offline render, scaled to fit (default 0.45×), paced at the scene fps.
- Keys: Space toggles pause; → advances one frame while paused; R restarts from frame 0 with the same seed; Esc/Q or closing the window quits.
- WHEN rendering falls behind real time, THE SYSTEM SHALL slow playback, never skip simulation steps.
- WHEN the scene duration ends, THE SYSTEM SHALL hold the last frame until the user restarts or quits.

### FR-010 CLI — [Arch], [API], [C3]
- `bouncekit render <scene.py> [--seed N] [--duration S] [--out PATH]` and `bouncekit preview <scene.py> [--seed N] [--duration S]`.
- THE SYSTEM SHALL load the scene file without running its `__main__` block and use its single module-level `Scene` instance.
- WHEN the file defines zero or more than one `Scene` instance, THE SYSTEM SHALL exit non-zero with a message saying how many were found.
- `--seed` and `--duration` SHALL take effect before the script's own code runs, so values derived from `scene.rng` follow the CLI seed [A4].
- `scene.run()` called from a script run as `__main__` SHALL dispatch to the same CLI using `sys.argv`, defaulting to `preview`.
- WHEN the scene file does not exist, THE SYSTEM SHALL exit non-zero with a clear message.

### FR-011 Example scene — [M0]
- `examples/single_ball.py` SHALL define a ring of radius 450 centred at (540, 960) and one ball under gravity, whose initial horizontal velocity is drawn from `scene.rng`.

---

## Non-functional requirements

- **NFR-001 Determinism** [P1], [M0], [C6], [C7]: Rendering the same scene with the same seed twice on the same machine with the locked dependencies SHALL yield identical SHA-256 hashes for every raw RGB frame. Verified by an automated test.
- **NFR-002 Output format** [M0]: The example render SHALL be 1080×1920, 60 fps, H.264 yuv420p (verified with ffprobe).
- **NFR-003 No tunnelling** [Phys]: WHEN `ball.radius + ring.thickness / 2 > max_speed / (fps × substeps)`, a ball at `max_speed` SHALL NOT pass through the ring (verified by a test running a fast ball for several seconds). WHEN a ball/ring pair violates that condition, `add_ball`/`add_circle` SHALL raise `ConfigError` naming the fix (more substeps, lower max_speed, bigger ball, thicker ring). (User decision 2026-10-24: error, not warning.)
- **NFR-004 Decoupling** [P3]: The renderer SHALL only read world state; rendering a frame SHALL NOT change physics state (verified by test: physics state with and without rendering is identical).
- **NFR-005 Tooling** [Stack], [Eng]: Python ≥ 3.11 via uv, type hints throughout; `pytest`, `ruff check`, and `mypy` pass.
- **NFR-006 Docs** [Eng]: Public API has docstrings; `README.md` has quickstart + API overview.
- **NFR-007 Test speed**: The full test suite runs in under 60 s (tests use small canvases and short durations).

## Out of scope for M0

Audio of any kind (M1); rules engine, collision handlers, escape detection, split/destroy/spawn, ball caps, cooldowns, constant-speed mode, spatial hash (M2); trails, glow, particles, flashes, colour modes such as `hue_cycle`, MIDI, hot-reload (M3); `batch` command, metadata JSON, text overlay, progress bar (M4); segments, polygons, joints, camera (M5); skia backend.
