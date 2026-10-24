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

---

## M1 — Audio pipeline

Scope: **Milestone M1 only**: event log, synth voices, single-note and scale sources, mixing, limiter, WAV + AAC mux into the MP4. SRS references: [Audio] = SRS "Audio" section, [P1]/[P3]/[P4] = core principles 1/3/4, [API] = "Public API", [Arch] = "Architecture", [M1] = milestone M1, [Stack] = "Tech stack". Assumptions: `clarifications.md` § "M1 assumptions" (B1..B15).

### FR-101 Collision event log — [Audio], [P3], [P4], [Arch]
- THE SYSTEM SHALL install one wildcard pymunk 7 collision handler (`space.on_collision(begin=..., separate=...)`, no collision types) whose callbacks only record data and never add, remove or modify bodies or shapes.
- WHEN two world objects (a `Ball` or a `CircleBoundary`, identified by handle, not by pymunk shape) start touching, THE SYSTEM SHALL append one `CollisionEvent(kind="collision", step, time, frame, objects, speed, position)` to `scene.events`.
- `step` SHALL be the 1-based global physics step count at the end of the step in which contact began (`frame_before × substeps + substep_index + 1`), and `time` SHALL equal `step / (fps × substeps)`.
- `speed` SHALL be `|(v_a − v_b) · n|` at the contact point, using the body velocities seen in the `begin` callback (before that step's collision impulse); `position` SHALL be the contact point in screen pixels.
- WHEN several shapes of the same two objects begin touching in one step (e.g. a ball hitting a ring seam touches two segments), THE SYSTEM SHALL record exactly one event for that object pair, with the largest speed (B2).
- WHILE an object pair is already in contact through at least one shape pair, a new shape-pair contact between the same two objects (e.g. a ball rolling from one ring segment to the next) SHALL NOT record an event (B2).
- `scene.events` SHALL be in recording order (step, then pymunk callback order) and SHALL be identical across two runs with the same seed.

### FR-102 Pitch and note source — [Audio], [API]
- `S.note(pitch, *, voice="sine")` SHALL return an immutable `Note` source. `pitch` SHALL accept a note name (`"C5"`, `"F#4"`, `"Bb3"`; octave −1..9, A4 = 440 Hz, 12-TET), a MIDI number `int` 0..127, or a frequency `float` in Hz (B3).
- WHEN the pitch is an unknown name, an int outside 0..127, a non-positive/non-finite float, or the result is outside 20 Hz..20 kHz, THE SYSTEM SHALL raise `ConfigError` naming `pitch` and the value.
- `voice` SHALL accept a voice name (`"sine"`, `"triangle"`, `"pluck"`, `"marimba"`) or a voice dataclass instance; an unknown name SHALL raise `ConfigError` listing the valid names.

### FR-103 Scale source — [Audio], [API]
- `S.scale(root="C4", *, mode="major_pentatonic", octaves=2, voice="sine")` SHALL return a `Scale` source whose notes are the mode's degrees ascending from `root` for `octaves` octaves, plus the root `octaves` octaves up (B5). Modes: `major`, `minor`, `major_pentatonic`, `minor_pentatonic`, `chromatic`.
- Each time a play action using a given `Scale` instance actually triggers a note, THE SYSTEM SHALL use the next note, wrapping to the first after the last. Triggers dropped by FR-106 limits SHALL NOT advance the cursor. The same instance used in several rules SHALL share one cursor per scene (B6).
- WHEN `mode` is unknown or `octaves` is not an int in 1..8, THE SYSTEM SHALL raise `ConfigError`.
- Example: `S.scale("C4", octaves=1)` yields C4 D4 E4 G4 A4 C5, then C4 again.

### FR-104 Collision sound rule — [API], [Audio]
- `scene.on_collision(tag_a, tag_b, actions)` SHALL register a rule; in M1, `actions` SHALL be a list/tuple whose items are all `A.play(source, *, gain=1.0)` results, otherwise `ConfigError` (other actions arrive in M2).
- WHEN a collision event's objects carry `tag_a` and `tag_b` (in either order), THE SYSTEM SHALL fire every action of the rule once, with `a` = the object carrying `tag_a` (B7). Rules fire in registration order; events in `scene.events` order.
- Rules SHALL be dispatched after each frame's physics steps, outside collision callbacks, and SHALL produce `NoteTrigger`s, not audio, during simulation.

### FR-105 Voices — [Audio]
- THE SYSTEM SHALL provide voices as frozen dataclasses: `Sine` and `Triangle` (with an `ADSR` envelope), `Pluck` (Karplus-Strong), `Marimba` (decaying inharmonic partials). Each has a fixed `duration` in seconds, and each `render(hz, seed)` returns mono float64 samples at 48 kHz with peak ≤ 1.0 and a first sample of 0.0.
- `Pluck` SHALL be in tune within 5 cents from C4 to E7, and its excitation SHALL be band-limited so its true (inter-sample) peak stays within 6 % of its sample peak. `Pluck` and `Marimba` SHALL fade linearly to exactly 0.0 over their last 50 ms, so a note cut at its duration does not click. (Added 2026-10-24 after M1 review: integer delay lines played C7 +33 cents; full-band noise had a true peak 1.43× its sample peak; both voices ended with a step.)
- `Pluck` noise SHALL come from `numpy.random.default_rng` seeded from `(scene seed, voice parameters, pitch)` only, so equal inputs give bit-identical output (B4).
- WHEN a voice parameter is out of range (non-positive duration, negative envelope time, sustain outside [0, 1], damping outside (0, 1)), THE SYSTEM SHALL raise `ConfigError` naming the field.
- Rendered notes SHALL be cached per `(voice, hz, seed)` for the scene's mix.

### FR-106 Trigger policy — [Audio]
- Gain: a trigger's gain SHALL be `play.gain × min(1, speed / reference_speed) ** 0.5` (B8).
- WHEN `speed < min_impact_speed`, THE SYSTEM SHALL NOT trigger.
- WHEN the same play action was triggered by the same object `a` less than `min_retrigger_interval` seconds earlier, THE SYSTEM SHALL NOT trigger.
- WHEN `max_triggers_per_frame` notes have already triggered in the current video frame (all rules together), further triggers in that frame SHALL be dropped in event order (B9).
- WHEN a new note starts while `max_polyphony` notes are still sounding, THE SYSTEM SHALL cut the oldest sounding note with a 5 ms linear fade-out starting at the new note's onset (voice stealing, B10).
- Defaults come from `AudioConfig` (FR-108); a bad value SHALL raise `ConfigError`.

### FR-107 Mixer and master bus — [Audio], [P1]
- THE SYSTEM SHALL mix into a 48 000 Hz stereo float buffer of exactly `round(frames × 48000 / fps)` samples for the simulated frames (integer arithmetic, half up). M1 notes are centred (equal in both channels); pan arrives in M3.
- A trigger at physics step `s` SHALL place the note's sample 0 at offset `round(s × 48000 / (fps × substeps))`, computed with integer arithmetic (half up). Samples past the buffer end SHALL be dropped.
- The master bus SHALL apply `tanh` soft limiting to the summed signal, then scale the whole buffer so its peak is `peak_dbfs` (default −1 dBFS ≈ 0.891); an all-zero buffer stays zero. Then the last 5 ms SHALL be faded out linearly.
- `scene.audio_buffer()` SHALL return this buffer (`float32`, shape `(n, 2)`).

### FR-108 Audio configuration — [API]
- `Scene(..., audio=AudioConfig(...))` SHALL accept an `AudioConfig` frozen dataclass, stored as `scene.config.audio`, with defaults `min_impact_speed=40.0` px/s, `reference_speed=1500.0` px/s, `min_retrigger_interval=0.05` s, `max_triggers_per_frame=6`, `max_polyphony=24`, `peak_dbfs=-1.0`. Sample rate is fixed at 48 000 Hz.
- WHEN a field is out of range (negative speed/interval, non-positive reference speed or counts, `peak_dbfs` > 0), THE SYSTEM SHALL raise `ConfigError` naming the field and value.

### FR-109 Export with audio — [Stack], [Arch], [M1]
- WHEN a scene has at least one sound rule, `render` SHALL encode the video as in FR-007 to a temporary file, write the mix as a 32-bit float WAV with `soundfile`, and mux with ffmpeg: video stream copied, audio AAC 192 kb/s, 48 000 Hz, 2 channels, `+faststart`. Temporary files SHALL be removed, also on failure.
- Before writing the WAV, THE SYSTEM SHALL scale the mix down, only if needed, so its 8× oversampled true peak is ≤ `peak_dbfs` (`limit_true_peak`), so the decoded AAC track does not exceed full scale. `scene.audio_buffer()` is unchanged (sample-peak normalised, FR-107). (Added 2026-10-24 after M1 review: a −1 dBFS sample peak decoded to +0.25 dBFS.)
- WHEN a scene has no sound rules, THE SYSTEM SHALL write a video-only MP4 exactly as in M0 (no audio stream) (B11).
- WHEN ffmpeg fails during muxing, THE SYSTEM SHALL raise `FfmpegError` with the stderr tail.

### FR-110 Example — [M1]
- `examples/bounce_notes.py` SHALL define a ball in a ring whose every wall hit plays the next note of `S.scale("C4", mode="major_pentatonic", voice="pluck")`.

### Non-functional (M1)
- **NFR-101 Audio determinism** [P1]: Rendering the same scene with the same seed twice SHALL produce byte-identical `audio_buffer()` and identical `scene.events` (automated test). Different seeds with rng-derived motion SHALL differ.
- **NFR-102 Sync** [M1]: In the rendered WAV, the first non-zero sample of each isolated note SHALL be at its trigger offset or offset + 1 (voices start at 0.0); every trigger SHALL land at most one video frame (`48000 / fps` samples) before the frame that first shows the contact, never after. The muxed MP4's audio stream duration SHALL match the video duration within 50 ms (ffprobe).
- **NFR-103 Headroom**: The final buffer's peak SHALL be ≤ 1.0 even with 200 simultaneous full-gain triggers.
- **NFR-104 Test speed / tooling**: NFR-005 and NFR-007 continue to hold (full suite < 60 s; pytest, ruff, mypy pass). `soundfile` is the only new runtime dependency.
- **NFR-105 Docs**: README quickstart + API overview cover the M1 sound API; public API has docstrings.

### Out of scope for M1
Rules other than collision → `A.play` (split, destroy, spawn, escape, timers, conditions, flash, end_after, callback escape hatch, decorator form of `on_collision`, pair cooldowns, ball cap) — M2. Escape/spawn events — M2. MIDI melody source, WAV sample voices with pitch shifting, stereo pan by x — M3. Audio in the live preview window (preview stays silent) — later (B12). Batch/metadata/event counts — M4. Configurable sample rate.
