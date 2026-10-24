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

---

## M2 — Rules engine

Scope: **Milestone M2 only**: tagged collision rules, escape, timers, conditions, spawn/destroy events, built-in actions (split, destroy, spawn, recolor, resize, set_velocity, flash, play, end_after), Python callback escape hatch, deferred mutation, cooldowns, ball caps, constant-speed mode, spatial hash. SRS references: [API] "Public API", [Arch] "Architecture" (`rules/` bullet), [Phys] "Physics details to handle", [Audio] "Audio", [P1]..[P5] core principles, [M2] milestone M2, [Eng] "Engineering standards". Assumptions: `clarifications.md` § "M2 assumptions" (C1..C24).

Terms: a **rule** is one registration (`on_collision`, `on_escape`, `on_spawn`, `on_destroy`, `every`, `at`, `when`) with a list of **handlers**; a handler is a built-in action (from `bouncekit.actions`) or a Python callable. A **step** is one `space.step(dt)`; `rate = fps × substeps`. An event's **subjects** `a`, `b` are the objects the rule's actions act on by default.

### FR-201 Event log — [Arch], [Audio], [P3]
- THE SYSTEM SHALL record every event as an immutable `Event(kind, step, frame, time, objects, speed, position)` in `scene.events`, where `kind` is one of `"collision"`, `"escape"`, `"spawn"`, `"destroy"`, `"timer"`, `"condition"`; `CollisionEvent` SHALL remain importable from `bouncekit.events` as the same class, so M1 code constructing `CollisionEvent(kind="collision", ...)` keeps working.
- `objects` SHALL be: collision → the two objects (FR-101); escape → `(ring, ball)`; spawn/destroy → `(ball,)` (or `(ring,)` for a destroyed ring); timer/condition → `()`.
- `speed` SHALL be: collision → FR-101 impact speed; escape/spawn/destroy → the ball's speed (px/s) at that moment (0.0 for a ring); timer/condition → `None`. `position` SHALL be the contact point, the ball centre, or `None` for timer/condition.
- `step`/`time` SHALL be the step in which the event happened (`time = step / rate`); `frame` SHALL be the video frame being simulated. `scene.events` SHALL be identical across two runs with the same seed.

### FR-202 Rule registration — [API], [Arch]
- THE SYSTEM SHALL provide `scene.on_collision(tag_a, tag_b, handlers=None, *, cooldown=None, object_cooldown=0.0)`, `scene.on_escape(ring, tag, handlers=None, *, margin=0.0)`, `scene.on_spawn(tag, handlers=None)`, `scene.on_destroy(tag, handlers=None)`, `scene.every(seconds, handlers=None)`, `scene.at(seconds, handlers=None)` and `scene.when(predicate, handlers=None)`.
- WHEN `handlers` is a list/tuple, each item SHALL be a built-in action or a callable; the method SHALL return `None`. WHEN `handlers` is omitted, the method SHALL return a decorator that registers the decorated function as the rule's only handler and returns the function unchanged (`@scene.on_collision("ball", "ball") def f(ctx, a, b, contact): ...`).
- Callable signatures SHALL be: collision `f(ctx, a, b, event)`; escape `f(ctx, ball, ring, event)`; spawn/destroy `f(ctx, obj, event)`; timer/condition `f(ctx, event)`. Return values are ignored.
- Subjects: collision → `a` carries `tag_a`, `b` carries `tag_b` (either shape order, FR-104); escape → `a` = ball, `b` = ring; spawn/destroy → `a` = the object, no `b`; timer/condition → no subjects.
- WHEN a tag is not a non-empty string, `handlers` is not a list/tuple of actions/callables, `ring` is not a `CircleBoundary`, `seconds` is not a positive finite number, `predicate` is not callable, or a cooldown/margin is negative or non-finite, THE SYSTEM SHALL raise `ConfigError` naming the argument and value.
- WHEN a rule's action targets subject `"b"` on a spawn/destroy/timer/condition rule, or subject `"a"` on a timer/condition rule, THE SYSTEM SHALL raise `ConfigError` at registration naming the action and the rule kind.
- `every(seconds)` SHALL fire at steps `k × n` for `k = 1, 2, …` with `n = round(seconds × rate)`; `at(seconds)` SHALL fire once at step `round(seconds × rate)`. WHEN `n` or that step is 0, THE SYSTEM SHALL raise `ConfigError`.
- `when(predicate)` SHALL evaluate `predicate(scene)` after every frame's last step and command application, and fire **once**, the first time it returns true; it SHALL never fire again (C9).

### FR-203 Dispatch and deferred mutation — [P4], [Arch]
- After each step THE SYSTEM SHALL, in this order: (1) collect the step's collision events (FR-101), (2) clamp speeds (FR-005) and apply constant speed (FR-212), (3) detect escapes (FR-208), (4) emit due timer events, (5) dispatch all events of the step — plus spawn/destroy events produced by the previous step's commands, first — to matching rules, (6) apply the command queue.
- Dispatch SHALL run outside every pymunk callback. Events are processed in log order; for each event, matching rules in registration order; for each rule, handlers in list order.
- Built-in actions and the `ActionContext` methods `destroy`, `split`, `spawn`, `recolor`, `resize`, `set_velocity`, `flash`, `end_after` SHALL only append commands to the scene's queue; WHILE dispatch runs, THE SYSTEM SHALL NOT add, remove or modify any body or shape. `ctx.play` SHALL produce note triggers immediately (audio only, FR-211).
- THE SYSTEM SHALL apply queued commands in FIFO order after dispatch. A command whose target object is no longer alive (destroyed earlier, including earlier in the same queue) SHALL be skipped silently.
- Spawn/destroy events produced while applying commands SHALL be logged with the current step and dispatched at the next step (one cascade level per step, C6). Events of `when` rules SHALL be dispatched and their commands applied immediately after the frame's last step.
- `ActionContext` SHALL expose `scene`, `event`, `a`, `b` (subjects or `None`), `rng` (= `scene.rng`) and `time`.

### FR-204 Cooldowns — [Arch]
- `Scene(rule_cooldown=0.05)` SHALL set the default per-pair cooldown in seconds (`scene.config.rule_cooldown`); `on_collision(..., cooldown=None)` uses it, a number overrides it.
- WHEN a collision rule fired for an object pair less than `cooldown` seconds earlier (exact step gap, `(step − last) / rate < cooldown`), THE SYSTEM SHALL skip that rule's non-play handlers for the pair. WHEN `object_cooldown > 0` and the rule fired for subject `a` (with any partner) less than `object_cooldown` earlier, THE SYSTEM SHALL skip them likewise. A rule "fired" when its non-play handlers ran.
- `A.play` handlers SHALL NOT be subject to rule cooldowns; they keep the M1 trigger policy (FR-106: `min_retrigger_interval` per (play, `a`), per-frame cap) unchanged (C4).
- Escape (once per ball per ring), spawn, destroy, timer and condition rules have no cooldown.
- WHEN `rule_cooldown` is negative or non-finite, THE SYSTEM SHALL raise `ConfigError`.

### FR-205 Ball caps — [Phys]
- `Scene(max_balls=1000)` SHALL cap the number of live balls (`scene.config.max_balls`, positive int).
- WHEN `add_ball` would exceed `max_balls`, THE SYSTEM SHALL raise `ConfigError` naming `max_balls`.
- WHEN a split or spawn command would make the live ball count exceed `max_balls` or the action's `max_total`, THE SYSTEM SHALL refuse the whole command (no partial split/spawn, no events, no error), and continue the render.

### FR-206 Split — [Phys], [API], [M2]
- `A.split(*, into=2, spread_degrees=30.0, radius_scale=1.0, max_total=None, target="a")` and `ctx.split(ball, **same)` SHALL split a ball into `into` balls: the parent ball stays (same handle) as child 0 and `into − 1` new balls are spawned.
- Let `v` = the parent's velocity when the command is applied, `s = |v|` (or the parent's constant-speed target, FR-212), `θ = atan2(v)` (0 when `s = 0`). Child `i` (0..into−1) SHALL get velocity `s · (cos φᵢ, sin φᵢ)` with `φᵢ = θ + spread · (i / (into − 1) − ½)` (degrees → radians).
- Child `i` SHALL be placed at `parent_pos + (i − (into − 1)/2) · (2·r' + 1) · (−sin θ, cos θ)`, where `r' = parent_radius × radius_scale`; the parent is moved and resized to `r'` too.
- Every child SHALL have `generation = parent.generation + 1` and inherit colour, tags, elasticity and constant-speed mode; new children inherit the parent's rule cooldown and play-retrigger timestamps (C7). `add_ball` balls have generation 0.
- WHEN `r'` would violate the tunnelling condition (NFR-003) with any live ring, or the cap check (FR-205) fails, THE SYSTEM SHALL refuse the split: the parent is unchanged and no spawn events are emitted (C8).
- WHEN the target is not a live `Ball` (e.g. a ring), the command SHALL be a no-op.
- Each new child SHALL emit one spawn event (FR-201) in child order; the parent emits none.
- WHEN `into` is not an int ≥ 2, `spread_degrees` not in [0, 360], `radius_scale` not positive finite, `max_total` not `None` or a positive int, or `target` invalid, THE SYSTEM SHALL raise `ConfigError` at action construction.

### FR-207 Spawn and destroy — [API], [Arch]
- `A.spawn(*, pos, radius, velocity=(0.0, 0.0), count=1, color="#ffffff", tags=("ball",), elasticity=1.0, constant_speed=False, max_total=None)` and `ctx.spawn(**same)` SHALL add `count` balls. `pos`, `velocity` and `color` SHALL each accept a value or a callable `f(ctx) -> value`, evaluated once per ball, in ball order, when the handler runs (during dispatch).
- WHEN `count > 1`, ball `i` SHALL be offset from `pos` by `(i − (count − 1)/2) · (2·radius + 1)` px along +x.
- WHEN the spawn would violate the cap (FR-205) or the tunnelling condition with any live ring, THE SYSTEM SHALL refuse the whole command (C8). Each spawned ball SHALL emit a spawn event.
- `A.destroy(target="a")` and `ctx.destroy(obj)` SHALL remove a live ball or ring from the space, the scene's objects and drawing, set `obj.alive = False`, and emit one destroy event. Contacts with the removed object end (its pending `separate`s run outside the step).
- `scene.count(tag=None)` SHALL return the number of live objects carrying `tag` (all live objects for `None`); `scene.objects` SHALL list live objects only, in insertion order.

### FR-208 Escape — [Phys], [API]
- After each step, for every live ring with an escape rule and every live ball matching that rule's tag, WHEN `|ball.centre − ring.centre| > ring.radius + ring.thickness/2 + ball.radius + margin`, THE SYSTEM SHALL record one escape event for that (ring, ball) pair — at most once per pair for the scene's lifetime — and dispatch it to `on_escape` rules for that ring whose tag the ball carries.
- Escape detection SHALL use only positions after the step (no wall-clock, no randomness) and process rings in insertion order, then balls in insertion order.

### FR-209 Timers, conditions, end — [API], [M2]
- Timer events (FR-202) SHALL be logged with `kind="timer"` and dispatched in the step at which they fall; several due timers dispatch in registration order.
- `A.end_after(seconds)` / `ctx.end_after(seconds)` SHALL set `scene.total_frames = min(total_frames, F + round(seconds × fps))`, where `F` is the number of frames simulated once the current frame completes. `frames()`, `render()`, `preview()` and `audio_buffer()` SHALL stop at the new end (the MP4 and audio are shorter accordingly). Repeated calls keep the earliest end. `seconds` SHALL be a finite number ≥ 0, else `ConfigError`.

### FR-210 Object actions — [API], [Arch]
- `A.recolor(color, *, target="a")` SHALL set the target's base colour; `color` is a colour value or `f(ctx) -> colour`.
- `A.resize(*, radius=None, scale=None, target="a")` (exactly one of `radius`, `scale`) SHALL change a live ball's radius (mass = π r², moment updated); WHEN the new radius violates the tunnelling condition with a live ring, the command SHALL be refused; a ring target is a no-op.
- `A.set_velocity(*, velocity=None, speed=None, target="a")` (exactly one) SHALL set a live ball's velocity (value or `f(ctx)`), or rescale its speed keeping direction; the result is clamped to `max_speed`, and a constant-speed ball's target becomes the new speed.
- `A.flash(target="a", *, seconds=0.08, color="#ffffff")` SHALL be visual only: for `max(1, round(seconds × fps))` frames from the next drawn frame, the target is drawn in a colour linearly blended from `color` back to its base colour; physics state SHALL be identical with and without flash.
- For these actions and `split`/`destroy`, `target` SHALL be `"a"`, `"b"` or a world object handle; anything else raises `ConfigError`. Invalid colours/numbers raise `ConfigError` at action construction.

### FR-211 Play on any event — [Audio], [API]
- `A.play` (and `ctx.play(source, *, gain=1.0)`) SHALL work in every rule kind. For events with `speed is None` (timer, condition) the trigger gain SHALL be `play.gain` and `min_impact_speed` SHALL NOT apply; otherwise FR-106 applies unchanged. The retrigger key is (play, `a`), with `a = None` for subject-less events.
- The per-frame trigger cap SHALL count triggers per event `frame`, so per-step dispatch gives the same triggers as M1's per-frame dispatch.
- `render` SHALL mux an audio track WHEN any rule contains an `A.play` or any trigger was produced; otherwise the MP4 stays video-only (B11).

### FR-212 Constant speed and spatial hash — [Phys]
- `scene.add_ball(..., constant_speed=False)`: WHEN true, after every step (after the max-speed clamp) THE SYSTEM SHALL rescale the ball's velocity to its target speed (initial `|velocity|`) keeping direction; a zero velocity stays zero. WHEN `constant_speed` is true and the initial speed is 0 or above `max_speed`, THE SYSTEM SHALL raise `ConfigError`.
- THE SYSTEM SHALL switch the space to pymunk's spatial hash (`space.use_spatial_hash(dim, count)`) exactly once, after command application in the first step at which the live ball count is ≥ 100, with `dim = 2 × the largest live ball radius` and `count = 10 000` (C14). It never switches back.

### FR-213 Examples — [M2]
- `examples/split_on_wall.py`: one ball in a ring; `on_collision("ball", "wall", [A.split(...), A.play(S.scale(...))])` doubles the ball count on each wall hit until a cap (≤ 256 balls).
- `examples/escape_rotating_gap.py`: a ring with a gap and non-zero `angular_velocity`; `on_escape(ring, "ball", [A.destroy(), A.spawn(count=2, pos=ring centre, ...), A.play(...)])`.
- `examples/destroy_on_contact.py`: balls are destroyed on contact with a tagged hazard (via a built-in `A.destroy` and/or a Python callback), with `every` spawning new balls and a `when` + `end_after` ending the video.
- Each example SHALL render with `bouncekit render` to an MP4 with an AAC track.

### Non-functional (M2)
- **NFR-201 Determinism** [P1], [M2]: Two builds of the split example (or an equivalent small split scene) with the same seed SHALL produce identical frame SHA-256 hashes, identical `audio_buffer()` bytes and identical event logs (automated); a different seed SHALL differ.
- **NFR-202 No crash mid-render** [Phys], [Eng]: Cap or tunnelling violations at runtime (split, spawn, resize) SHALL be refused deterministically, never raised; tested with a scene that hits both limits.
- **NFR-203 Deferred mutation is tested** [P4], [Eng]: a test SHALL show that during dispatch (built-in and callback handlers) the space's bodies/shapes are unchanged, and that the queued change is visible after the step.
- **NFR-204 Compatibility**: All M0/M1 tests SHALL pass unmodified; M0/M1 example outputs are unchanged.
- **NFR-205 Tooling, speed, docs** [Eng]: pytest, ruff, mypy pass; the full suite runs in < 90 s; no new runtime dependencies; README quickstart + API overview cover M2; public API has docstrings.

### Out of scope for M2
Trails, glow, particles, colour modes such as `C.hue_cycle()` / by speed / by generation (M3); MIDI melodies, sample voices, stereo pan, hot-reload (M3); batch, metadata JSON with event counts, text overlay, progress bar (M4); spawning rings or other shapes, segments, polygons, joints, camera (M5); `when` rules that re-fire on every rising edge; rule removal/enable-disable at runtime; per-rule priorities; audio in the preview.
