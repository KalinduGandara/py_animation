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
