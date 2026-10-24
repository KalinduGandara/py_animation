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
