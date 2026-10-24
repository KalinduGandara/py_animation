# Clarifications — bouncekit

Source SRS: the user's master prompt ("Master Prompt: `bouncekit`"), current scope **M0 only**.

## Environment findings (2026-10-24)

- Working directory is empty and **not a git repository**.
- `uv` is **not installed**. System `python3` is 3.10.11; Homebrew has 3.13 and 3.14.
- `ffmpeg` 9.0.2 is installed at `/opt/homebrew/bin/ffmpeg`.

## Round 1 — questions

Answer by number; "accept defaults" accepts every recommended default.

### A. Tooling and workflow

1. **Installing uv.** Recommended: `brew install uv`, with uv managing Python 3.12 for the project. Reason: the SRS mandates uv and Python 3.11+; system Python is 3.10.
2. **Git.** The SDD workflow commits once per task. Recommended: `git init` with a `.gitignore` covering `out/`, `.venv/`, caches. Reason: per-task commits give traceability and rollback.

### B. Public API (affects scene scripts)

3. **How the CLI finds the scene.** Recommended: `bouncekit render scene.py` imports the file (so the `__main__` block does not run) and uses the single module-level `Scene` instance; zero or more than one is a clear error. `python scene.py` calls `scene.run()`, which parses the same CLI args and defaults to `preview`. Reason: keeps scene scripts exactly as in the SRS example, no registration boilerplate.
4. **Ring features in M0.** Recommended: `add_circle` implements `gap_degrees` and kinematic `angular_velocity` geometry now (world layer), but no escape detection (that is M2 rules). Reason: the API signature already has them and they are pure geometry; escape is a rule.
5. **Physics safety in M0.** Recommended: include the max-speed clamp and substep config in M0; defer constant-speed mode, ball caps and spatial hash to M2, where splitting first needs them. Reason: M0 has one ball.

### C. Determinism and verification

6. **Determinism scope.** Recommended: "bit-identical" means same machine + same locked dependency versions. Cross-platform float equality of Chipmunk is not promised. Reason: Chipmunk uses native floats; cross-platform identity is not achievable without a fixed-point engine.
7. **What the determinism test hashes.** Recommended: SHA-256 of each raw RGB frame before ffmpeg, compared across two runs. The MP4 file bytes are not asserted (encoder metadata may vary), but ffmpeg is run with `-fflags +bitexact` anyway. Reason: frames are what the framework controls.

### D. Preview and output

8. **Preview behaviour.** Recommended: plays at real-time `fps` (simulation stays fixed-step; if rendering falls behind, the preview slows down instead of skipping steps). Keys: Space pause, R restart, → single-step while paused, Esc/Q quit. Window scaled to fit the screen (default 0.45× for 1080×1920). Reason: same frames as the offline render, just displayed.
9. **Default output path.** Recommended: `out/<scene-file-stem>_seed<seed>.mp4`, directory created if missing. Reason: predictable and batch-friendly for M4.
10. **Visual quality in M0.** Recommended: anti-aliased pygame-ce primitives (`aacircle`/`aaline`), fixed colours only; trails, glow and colour modes stay in M3. Reason: SRS milestone split.

## Answers (2026-10-24)

User reply: "approved start implementing" → **all recommended defaults accepted** (1–10). User also asked to proceed straight to implementation (specs are still written, but phases 3–5 do not stop for separate approval) using workflows, with Sonnet for less complex tasks.

## Agreed assumptions

- A1. Python 3.12 via uv; `uv 0.13.5` installed with Homebrew; git initialised.
- A2. Installed versions: pymunk 7.3.1 (collision API `Space.on_collision(...)`, `Space.add_post_step_callback`), pygame-ce 2.5.8 (`draw.aacircle` available), numpy, ffmpeg 9.0.2.
- A3. Dev-only tooling `ruff` (lint) and `mypy` (type check) were added to the dev dependency group to satisfy the SDD lint/type-check gate. They are not runtime dependencies. (Flagged to the user.)
- A4. CLI seed/duration overrides are applied **before** the scene script executes (the script is re-executed via `runpy` with overrides active), so anything the script derives from `scene.rng` respects `--seed`.
- A5. Gap orientation: the gap is centred on angle 0° (pointing +x) in the ring's local frame; screen angles increase clockwise (y down). Rotation moves it.
- A6. Canvas width/height must be even (yuv420p requirement); validated with a clear error.

