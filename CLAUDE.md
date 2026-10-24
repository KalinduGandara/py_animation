# bouncekit

Python framework for deterministic 2D physics "satisfying" videos (vertical MP4). Specs are the source of truth: read `specs/` first (`srs.md` = original requirements, `requirements.md`, `design.md`, `tasks.md`, `progress.md`, `clarifications.md`). Work milestone by milestone (M0..M5); never build later milestones early.

## Stack
Python 3.12 (uv), pymunk 7.3.1, pygame-ce, numpy, soundfile (from M1), mido (from M3), ffmpeg (subprocess). Dev: pytest, ruff, mypy.

## Commands
- Install: `uv sync`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .` (format: `uv run ruff format .`)
- Types: `uv run mypy`
- Render: `uv run bouncekit render examples/single_ball.py [--seed N] [--duration S] [--out PATH]`
- Preview: `uv run bouncekit preview examples/single_ball.py` (silent; audio is offline only)
- Render with sound (M1): `uv run bouncekit render examples/bounce_notes.py`
- Rules examples (M2): `uv run bouncekit render examples/split_on_wall.py` (also `escape_rotating_gap.py`, `destroy_on_contact.py`)
- Melody + effects (M3): `uv run bouncekit render examples/midi_melody.py`; preview hot-reloads the scene file on save
- Regenerate assets (M3): `uv run python scripts/make_assets.py` (writes `assets/midi/`, `assets/samples/`; output must stay byte-identical)

## Conventions
- Determinism is non-negotiable: fixed timestep, `scene.rng` only, no wall-clock in simulation, insertion-ordered containers.
- Never mutate the pymunk space inside a collision callback; queue changes. Rules (M2) dispatch after every `space.step`; actions and `ActionContext` methods only append commands, which are applied FIFO after dispatch (`rules/`). Use `ctx.rng`/`scene.rng` for randomness in actions and callbacks.
- Runtime cap/tunnelling violations (split, spawn, resize) are refused silently and deterministically, never raised mid-render.
- Public API: screen pixels, origin top-left, +y down; keyword-only options; dataclasses for config; raise `ConfigError` with field + value for bad config.
- Audio: collision callbacks only record events; rules turn them into note triggers after each frame; the mixer runs once after simulation. Sample offsets use integer math on the physics step count (never `time * 48000`). 48 kHz stereo float.
- Renderer only reads world state. Drawing goes through the `Renderer` protocol.
- Effects (M3: trails, glow, particles, colour modes) are visual-only: never touch pymunk, `scene.rng` or `scene.events`; particle randomness uses `scene.fx_rng`; effect state advances per `scene.frame`, never per `draw` call. Effect-free scenes must keep M2 frame bytes; unpanned mixes must keep M1 audio bytes.
- pymunk 7 API: `space.on_collision(...)`, `space.add_post_step_callback(...)` — don't copy pre-7 examples.
- Per task: tests first; tick `specs/tasks.md`; append to `specs/progress.md`; commit `feat(area): T-<id> desc [FR-…]`.
- No new runtime dependencies without asking the user (SRS stack — numpy, soundfile, mido, pymunk, pygame-ce — is approved).
