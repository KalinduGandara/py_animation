# Tasks — bouncekit (M0)

Each task: tests first → implement → `uv run pytest && uv run ruff check . && uv run mypy` → tick here → log in `progress.md` → commit `feat(<area>): T-00X <desc> [FR-…]`.

- [x] T-001: Scaffolding — pyproject (entry point `bouncekit = "bouncekit.cli:main"`, pytest/ruff/mypy config, strict-ish mypy on `src`), package skeleton dirs, `.gitignore`, one trivial passing test.
  - Requirements: NFR-005
  - Files: pyproject.toml, src/bouncekit/**/__init__.py, tests/test_smoke.py
  - Done when: `uv run pytest`, `uv run ruff check .`, `uv run mypy` all pass.

- [x] T-002: Errors, colours, SceneConfig with validation.
  - Requirements: FR-001, FR-002
  - Files: errors.py, colors.py, config.py, tests/test_config.py
  - Done when: defaults, every validation error (odd/zero size, fps, duration, substeps, max_speed, bad colours) are tested and pass.

- [x] T-003: World — Scene core (config, rng, overrides hook, object registry, step loop), Ball (velocity clamp), CircleBoundary (segments, gap, rotation, neighbours).
  - Requirements: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, NFR-003
  - Files: scene.py, world/ball.py, world/circle.py, tests/test_world.py, tests/test_config.py
  - Done when: tests for gravity direction, closed ring containment, gap escape, rotation angle after N frames, step/frame counting, speed clamp, no tunnelling at max_speed, seam smoothness, add_* validation all pass.

- [x] T-004: Renderer protocol, PygameRenderer, `Scene.draw` / `Scene.frames`, determinism tests.
  - Requirements: FR-008, NFR-001, NFR-004
  - Files: render/base.py, render/pygame_renderer.py, scene.py, world/*.py (draw), tests/test_render.py, tests/test_determinism.py
  - Done when: frame size/pixel colour tests, render-doesn't-mutate-physics test, same-seed identical hashes, different-seed differing hashes all pass.

- [x] T-005: ffmpeg export — `require_ffmpeg`, `FfmpegWriter`, `Scene.render`.
  - Requirements: FR-007, NFR-002
  - Files: export/ffmpeg.py, scene.py, tests/test_export.py
  - Done when: tiny real encode probes as h264/yuv420p with right size+fps; missing-ffmpeg and bad-frame-length errors tested.

- [x] T-006: CLI — `load_scene` with overrides, `render`/`preview` subcommands, `Scene.run`, error exit codes.
  - Requirements: FR-010, FR-006
  - Files: cli.py, scene.py, tests/test_cli.py, tests/fixtures/*.py
  - Done when: single/zero/many scenes, override-before-script, `__main__` skipped, missing file, and end-to-end `render` on a tiny fixture scene tested and passing.

- [x] T-007: Live preview window.
  - Requirements: FR-009
  - Files: render/preview.py, scene.py, tests/test_preview.py
  - Done when: preview runs headless (`SDL_VIDEODRIVER=dummy`) for N frames via a `max_frames` hook; key handling unit-tested via posted events (pause, step, restart, quit).

- [x] T-008: Example scene, README, end-to-end verification.
  - Requirements: FR-011, NFR-002, NFR-006, NFR-007
  - Files: examples/single_ball.py, README.md
  - Done when: `uv run bouncekit render examples/single_ball.py` produces `out/single_ball_seed42.mp4` that ffprobe reports as 1080×1920, 60 fps, h264, yuv420p; README has quickstart + API overview; full suite < 60 s.

---

## M1 — Audio pipeline

Same per-task loop as M0: tests first → implement → gate (`uv run pytest -q && uv run ruff check . && uv run mypy`) → tick here → log in `progress.md` → commit `feat(<area>): T-10X <desc> [FR-…]`.

- [x] T-101: Vertical slice — collision event log, `S.note` + `A.play` + `scene.on_collision`, `Sine` voice, basic mixer (exact offsets, tanh + peak normalise + end fade, stereo), `scene.audio_buffer()`, WAV + mux in `render`. Add `soundfile` to runtime deps (`uv add soundfile`).
  - Requirements: FR-101, FR-102 (note, pitch parsing), FR-104, FR-105 (Sine + ADSR only), FR-107, FR-109, NFR-101, NFR-102, NFR-103
  - Files: pyproject.toml, uv.lock, src/bouncekit/events.py, sound.py, actions.py, audio/__init__.py, audio/voices.py, audio/mixer.py, export/audio.py, export/ffmpeg.py, config.py (AudioConfig with defaults, validation can be minimal here), scene.py, __init__.py; tests/test_events.py, tests/test_sound.py, tests/test_mixer.py, tests/test_audio_export.py
  - Done when: tests pass for — event `step`/`time` of a ball dropped onto a ring equal the analytic substep; one event per seam hit; no events while a ball rests/rolls on the ring after settling; event speed ≈ pre-impact speed; handler never mutates the space; pitch parsing (names, sharps/flats, MIDI, Hz, errors); `sample_offset` exact for chosen (fps, substeps, step) incl. half-up; `num_samples`; isolated note's first non-zero sample at offset/offset+1 and silence before; 200 full-gain triggers peak ≤ 1.0 and peak == 10**(-1/20) within 1e-6; same seed → identical `audio_buffer()` bytes and events, different seed differs; tiny real render with a sound rule → ffprobe shows `aac`, 48000 Hz, 2 channels, durations match within 50 ms, temp files removed; scene without sound rules still yields no audio stream; mux failure → `FfmpegError` with stderr; on_collision rejects non-Play actions/bad tags.

- [x] T-102: Remaining voices — `Triangle`, `Pluck` (Karplus-Strong, seeded noise), `Marimba`; voice name lookup + `ConfigError` for unknown names and bad parameters; per-mix render cache keyed `(voice, hz, seed)`.
  - Requirements: FR-102 (voice argument), FR-105, NFR-101
  - Files: src/bouncekit/audio/voices.py, audio/mixer.py, sound.py, tests/test_voices.py
  - Done when: tests pass for — every voice: length = round(duration·48000), first sample 0.0, peak ≤ 1, finite; dominant frequency (zero crossings or FFT in the test) within 2% of hz for 220/440/880 Hz; Pluck identical for same (seed, hz) and different for different seeds; Marimba drops partials above 20 kHz; parameter validation errors name the field; cache hit returns equal arrays and voice.render is called once per key (monkeypatched counter).

- [x] T-103: Scale source and trigger policy — `S.scale` (modes, octaves, top root, per-scene cursor shared by instance), `AudioConfig` full validation, gain curve, `min_impact_speed`, `min_retrigger_interval`, `max_triggers_per_frame`, polyphony voice stealing with 5 ms fade.
  - Requirements: FR-103, FR-106, FR-108
  - Files: src/bouncekit/sound.py, config.py, scene.py, audio/mixer.py, tests/test_scale.py, tests/test_policy.py, tests/test_config.py (new AudioConfig cases only)
  - Done when: tests pass for — scale note lists (C4 major_pentatonic octaves=1 → C4 D4 E4 G4 A4 C5; each mode's intervals), wrap-around, dropped triggers don't advance the cursor, shared instance shares cursor, fresh scene restarts at 0; gain formula at speeds 0/ref/2·ref; below-threshold speed ignored; retrigger interval per (play, object) with two balls; per-frame cap drops later events in order; polyphony: with max_polyphony=2 three overlapping notes → first note cut with a linear 5 ms fade starting at the third note's offset; every AudioConfig field's bad value raises ConfigError naming it.

- [x] T-104: Example, README, docs — `examples/bounce_notes.py` (ball in ring, `on_collision("ball", "wall", [A.play(S.scale("C4", voice="pluck"))])`), README quickstart + M1 API overview (sound sources, voices, AudioConfig defaults, render now muxes AAC, no-sound scenes stay video-only, preview is silent), docstrings check, traceability in progress.md; render the example and verify with ffprobe.
  - Requirements: FR-110, NFR-102, NFR-104, NFR-105
  - Files: examples/bounce_notes.py, README.md, tests/test_example.py (new tests only), specs/progress.md
  - Done when: tests pass for — example loads with one ring tagged "wall", one ball tagged "ball", a scale-pluck rule; a 3 s render has an aac 48000 Hz stereo stream and ≥ 1 trigger whose WAV onset lands at its sample offset; README test checks the M1 section mentions `on_collision`, `S.scale`, `A.play`, `AudioConfig`; `uv run bouncekit render examples/bounce_notes.py` succeeds; full suite < 60 s.

---

## M2 — Rules engine

Same per-task loop: tests first → implement → gate (`uv run pytest -q && uv run ruff check . && uv run mypy`) → tick here → log in `progress.md` → commit `feat(<area>): T-20X <desc> [FR-…]`. Existing M0/M1 tests must pass unmodified (NFR-204).

- [ ] T-201: Vertical slice — `Event` (+ `CollisionEvent` alias), `rules/` package (`Rule`, `RuleEngine`, `ActionContext`, command queue), per-step dispatch pipeline in `step_frame` (M2.1), `_dispatch` kept as entry point with per-`event.frame` trigger cap, handler lists with built-ins + callables and the decorator form for `on_collision`, `A.destroy` / `ctx.destroy` + destroy events + `on_destroy`, `scene.count`, live-only `objects`, monotonic object indices, pair/object cooldowns with `Scene(rule_cooldown=)`, render audio decision (FR-211 last bullet).
  - Requirements: FR-201, FR-202 (collision, destroy, decorator, validation), FR-203, FR-204, FR-207 (destroy, count), FR-211, NFR-203, NFR-204
  - Files: src/bouncekit/events.py, actions.py, rules/__init__.py, rules/context.py, rules/engine.py, rules/commands.py, config.py, scene.py, world/ball.py, world/circle.py; tests/test_rules.py, tests/test_destroy.py
  - Done when: tests pass for — a callback and a built-in destroy see the space unchanged during dispatch (bodies/shapes identical, ball still present) and the ball is gone after the step; destroy removes from space/objects/drawing, sets `alive=False`, logs one destroy event, and a destroyed ring's ball contacts end; commands on already-destroyed objects are skipped; decorator returns the function and receives `(ctx, a, b, event)` with `a` carrying `tag_a`; list form mixing action + callable runs in order; rules in registration order; pair cooldown blocks a second fire within 0.05 s and allows it after (exact step gap), `cooldown=` override, `object_cooldown` across partners; play handlers ignore cooldowns (M1 policy tests untouched); destroy event dispatches to `on_destroy` at the next step; `ConfigError` for bad tags/handlers/cooldowns and `"b"` target on an `on_destroy` rule; all M0/M1 tests pass unchanged.

- [ ] T-202: Split, spawn, caps — `A.split`/`ctx.split` (parent = child 0, spread, separation, radius_scale, generation, inheritance of cooldown + retrigger timestamps), `A.spawn`/`ctx.spawn` (callable values evaluated during dispatch, multi-ball offsets), spawn events + `on_spawn`, `Scene(max_balls=)` + `add_ball` cap error, per-action `max_total`, runtime refusal on cap/tunnelling, cascade one level per step; determinism test of a split scene.
  - Requirements: FR-205, FR-206, FR-207 (spawn), FR-202 (on_spawn), NFR-201, NFR-202
  - Files: src/bouncekit/actions.py, rules/commands.py, rules/context.py, rules/engine.py, scene.py, world/ball.py, config.py; tests/test_split.py, tests/test_spawn.py, tests/test_determinism.py (new tests only)
  - Done when: tests pass for — split of a ball with velocity (300, 0), into=3, spread 60 gives directions −30/0/+30° at equal speed, positions per FR-206, all generation 1, same handle for child 0; radius_scale applied to all; refused split when cap or `max_total` exceeded (count unchanged, no events) and when `r'` violates tunnelling (no exception, render continues); `add_ball` beyond `max_balls` raises `ConfigError`; a ball touching the wall at split time does not re-split its children within the cooldown and no extra notes play; spawn with callable velocity consumes `scene.rng` in ball order; spawn events emitted per child and dispatched next step; on_spawn → spawn chain grows by one level per step only; two builds of a split scene give identical frame hashes, audio bytes and event keys, a different seed differs; bad split/spawn arguments raise `ConfigError` at construction.

- [ ] T-203: Escape, timers, conditions, end — `on_escape(ring, tag, margin=)` with once-per-pair escape events, `every`/`at` timer events, `when` (fires once, after the frame), `A.end_after`/`ctx.end_after` shrinking `total_frames` for frames/render/preview/audio, decorator form for all registration methods, subject-target validation per rule kind.
  - Requirements: FR-202 (escape/timer/condition), FR-208, FR-209, FR-211 (speed-less play)
  - Files: src/bouncekit/rules/engine.py, rules/context.py, actions.py, scene.py; tests/test_escape.py, tests/test_timers.py
  - Done when: tests pass for — a ball leaving through a gap logs exactly one escape event at the first step its centre passes `radius + thickness/2 + r + margin` (computed independently in the test), none for a closed ring; escape rule dispatches `(ctx, ball, ring, event)` with `a` = ball; `every(0.5)` at 60×8 fires at steps 240, 480, …; `at(1.0)` once at step 480; seconds rounding to 0 steps raises; `when` fires once on the first true frame even if it stays true; `end_after(1.0)` at frame 30 of a 5 s scene gives `total_frames == 91` (F = 31) and `frames()` yields 91 frames and `audio_buffer()` has `num_samples(91, fps)` samples; earliest end wins; play on a timer event uses `play.gain` and ignores `min_impact_speed`; `"a"` target on a timer rule raises `ConfigError`.

- [ ] T-204: Object actions, constant speed, spatial hash — `A.recolor`, `A.resize`, `A.set_velocity`, `A.flash` (visual-only blend in `Scene.draw`, `draw(renderer, color=None)`), `ctx` equivalents, `add_ball(constant_speed=)` with renormalisation after the clamp, automatic spatial hash switch at 100 balls.
  - Requirements: FR-210, FR-212
  - Files: src/bouncekit/actions.py, rules/commands.py, rules/context.py, world/ball.py, world/circle.py, scene.py; tests/test_object_actions.py, tests/test_constant_speed.py
  - Done when: tests pass for — recolor changes the drawn pixel colour; resize changes radius/mass/moment and is refused below the tunnelling limit; set_velocity by value/callable/speed clamps to max_speed and updates a constant-speed target; flash draws the flash colour on the next frame and fades back over `round(seconds·fps)` frames, and physics state with vs. without flash is identical; a constant-speed ball in a ring with gravity keeps `|v|` equal to its initial speed within 1e-9 after every step for 5 s; `constant_speed` with zero or > max_speed initial speed raises; `use_spatial_hash` is called exactly once (monkeypatched spy) with `(2 × max radius, 10000)` when the ball count reaches 100 and not before.

- [ ] T-205: Examples, README, docs — `examples/split_on_wall.py`, `examples/escape_rotating_gap.py`, `examples/destroy_on_contact.py` (each with sound), README quickstart + M2 API overview (rule kinds, handler list vs decorator + callback signatures, built-in actions table, ActionContext, cooldowns, caps and refusal behaviour, constant speed, end_after), docstrings check, traceability rows in progress.md; render each example and verify with ffprobe.
  - Requirements: FR-213, NFR-201, NFR-205
  - Files: examples/split_on_wall.py, examples/escape_rotating_gap.py, examples/destroy_on_contact.py, README.md, tests/test_example.py (new tests only), specs/progress.md
  - Done when: tests pass for — each example loads via `cli.load_scene` with the expected rules; short (≈2–3 s, small override) renders of each produce h264 + aac 48000 Hz stereo; split example's ball count doubles on the first wall hits and never exceeds its cap; escape example logs ≥ 1 escape and the ball count grows by one per escape (destroy 1, spawn 2) until the cap; destroy example logs ≥ 1 destroy event and ends at its `end_after` frame or the duration; README test checks the M2 section mentions `on_collision`, `on_escape`, `every`, `when`, `A.split`, `A.spawn`, `A.destroy`, `end_after`, `ctx`; `uv run bouncekit render` succeeds for all three examples at full size; full suite < 90 s.
