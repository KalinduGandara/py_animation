# bouncekit

Python framework for deterministic 2D physics "satisfying" videos (vertical MP4). Specs are the source of truth: read `specs/` first (`requirements.md`, `design.md`, `tasks.md`, `progress.md`, `clarifications.md`). Work milestone by milestone (M0..M5); never build later milestones early.

## Stack
Python 3.12 (uv), pymunk 7.3.1, pygame-ce, numpy, ffmpeg (subprocess). Dev: pytest, ruff, mypy.

## Commands
- Install: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .` (format: `uv run ruff format .`)
- Types: `uv run mypy`
- Render: `uv run bouncekit render examples/single_ball.py [--seed N] [--duration S] [--out PATH]`
- Preview: `uv run bouncekit preview examples/single_ball.py`

## Conventions
- Determinism is non-negotiable: fixed timestep, `scene.rng` only, no wall-clock in simulation, insertion-ordered containers.
- Never mutate the pymunk space inside a collision callback; queue changes.
- Public API: screen pixels, origin top-left, +y down; keyword-only options; dataclasses for config; raise `ConfigError` with field + value for bad config.
- Renderer only reads world state. Drawing goes through the `Renderer` protocol.
- pymunk 7 API: `space.on_collision(...)`, `space.add_post_step_callback(...)` — don't copy pre-7 examples.
- Per task: tests first; tick `specs/tasks.md`; append to `specs/progress.md`; commit `feat(area): T-00X desc [FR-…]`.
- No new runtime dependencies without asking the user.
