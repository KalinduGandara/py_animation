# Clarifications — bouncekit

Source SRS: `specs/srs.md` (the user's master prompt, verbatim). Scope: M0–M4 (M5 later, only when asked).

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


## Round 2 — M0 review (2026-10-24)

User decisions:
- Tunnelling risk is a `ConfigError`, not a warning.
- Ring edges looked jagged → fixed with signed-distance anti-aliasing (see design §4.2).
- ruff and mypy stay as dev tools.
- Untested CRF/faststart and preview pacing: "handle appropriately" → automated tests added.
- **Implement M1–M4 now without stopping between milestones** (overrides the SRS "stop after each milestone"); M5 (Rube Goldberg) stays out of scope. Use workflows; Sonnet for less complex tasks.
- `soundfile` and `mido` are in the SRS stack, so adding them in M1/M3 needs no further approval. Any other new runtime dependency still needs the user.
- For each milestone, genuinely ambiguous decisions are made by the spec author with the recommended default, recorded below as "M<n> assumptions", and reported to the user at the end.

## M1 assumptions

Made by the spec author with the recommended default (user delegated: "handle appropriately"); reported to the user at the end.

- B1. **Event time = end of the substep** in which contact began (`step / (fps·substeps)`); the sound plays up to one frame before the frame that first shows the contact, never after. Reason: exact, integer-derivable and within the SRS's frame-level sync.
- B2. **One event per object pair per contact**, not per pymunk shape pair: seam double-hits are merged (max speed) and rolling onto the next ring segment does not re-fire. Reason: measured in planning — a seam hit fires two `begin`s in one substep, which would double every note.
- B3. **Pitch typing**: `str` = note name (A4 = 440 Hz, 12-TET, `#`/`b`), `int` = MIDI 0..127, `float` = Hz. Reason: matches common music-library conventions; `440` (int) is rejected as MIDI out of range, which surfaces the mistake.
- B4. **Pluck noise seeded from (scene seed, pitch, damping)**, not from the trigger index as first proposed. Reason: per-trigger seeds defeat the note cache; repeated plucks of one pitch sounding identical is acceptable and still deterministic per seed.
- B5. **Scale includes the top root** (`octaves` octaves of degrees + root `octaves` up) and only ascends, wrapping to the bottom. Reason: ending on the root sounds resolved; up/down patterns can come with M3 melodies.
- B6. **Scale cursor per `Scale` instance per scene**, advanced only by notes that actually play. Reason: sources stay immutable values; dropped triggers would otherwise skip notes audibly.
- B7. **Rule matching** is by tags in either order; `a` is the object with `tag_a`. Retrigger interval is keyed by (play action, `a`). Reason: matches the SRS `on_collision("ball", "wall", ...)` reading; per-pair cooldowns are M2.
- B8. **Gain curve** `gain × min(1, speed / 1500) ** 0.5` with a 40 px/s floor below which nothing plays. Reason: square root keeps soft hits audible; floor removes rolling/resting micro-contacts.
- B9. **Defaults**: `max_triggers_per_frame=6`, `max_polyphony=24`, `min_retrigger_interval=0.05 s`, `peak_dbfs=-1`. Per-frame overflow keeps the first triggers in event order. Reason: sensible for one-to-hundreds of balls; first-N is simplest deterministic choice.
- B10. **Polyphony overflow steals the oldest note** (5 ms fade) instead of dropping the new one. Reason: during exponential growth the newest hits must stay audible.
- B11. **Scenes without sound rules render video-only MP4s** (exactly as M0), no silent track. Reason: no behaviour change for M0 scenes; no needless encode.
- B12. **Preview stays silent in M1.** Reason: optional per plan; real-time pygame.mixer playback adds sync code with no effect on the offline output (source of truth). Revisit with M3 hot-reload.
- B13. **Stereo, centred in M1**, 48 kHz fixed (not configurable); WAV written as 32-bit float to a temp dir and deleted after muxing. Reason: SRS fixes 48 kHz; pan is M3; float avoids quantising the deterministic buffer.
- B14. **Master bus = `tanh` then peak-normalise to -1 dBFS, then a 5 ms fade-out at the end.** Quiet scenes are therefore raised to -1 dBFS too. Reason: simplest limiter that guarantees ≤ 1.0; consistent loudness across videos. M1 review addendum (2026-10-24): the guarantee held only for the WAV samples; before AAC encoding the delivered mix is additionally limited to a −1 dBTP true peak (FR-109), the usual headroom for lossy delivery.
- B15. **Default voice is `"sine"`.** Reason: neutral, predictable; the example uses `"pluck"`.
