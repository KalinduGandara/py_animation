# Progress — bouncekit

## Log

- 2026-10-24: Phase 1–2 done; defaults accepted (see clarifications.md). uv installed, git initialised, uv project created with pymunk 7.3.1, pygame-ce 2.5.8, numpy; dev: pytest, ruff, mypy.
- 2026-10-24: requirements.md, design.md, tasks.md written for M0.
- 2026-10-24: T-001 done: pyproject tool config + entry point, package skeleton (world/render/export, cli stub), smoke tests; pytest/ruff/mypy pass.
- 2026-10-24: T-002 done: errors, colour parsing, frozen validated SceneConfig; tests/test_config.py; gate passes.
- 2026-10-24: T-003 done: Scene core (config, rng, `_overrides`, registry, fixed-step loop), Ball (speed clamp in velocity_func), CircleBoundary (segments, gap, rotation, set_neighbors); shared validators in config.py; tests/test_world.py + add_* validation; gate passes. Note: Chipmunk adds ~0.2% speed on head-on vertex hits (bounded by the clamp); neighbour-joined seams cut wall hops from ~10 px to ~2 px.

## Status

In progress: M0. Next: T-004.
