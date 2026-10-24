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

## M2 assumptions

Made by the spec author with the recommended default (user delegated, Round 2); reported to the user at the end.

- C1. **Dispatch runs after every physics step** (not once per frame as in M1). Reason: actions such as split must start from the post-bounce state; per-step dispatch keeps M1 audio identical because the per-frame cap is keyed on `event.frame`.
- C2. **One FIFO command queue** applied after dispatch replaces pymunk post-step callbacks. Reason: same safety (nothing mutates inside `space.step`), preserves ordering between commands, easy to test.
- C3. **Commands targeting a dead object are skipped silently.** Reason: two rules may legitimately act on the same ball in one step (e.g. destroy and split); first wins deterministically.
- C4. **Rule cooldowns gate only non-play handlers; `A.play` keeps the M1 retrigger policy.** Reason: gating play too would change M1 behaviour (M1 policy tests) and double-limit audio.
- C5. **Default pair cooldown 0.05 s (`Scene(rule_cooldown=0.05)`), object cooldown 0 (off).** Reason: the M1 recorder already suppresses resting contact; the cooldown only absorbs micro-bounce re-contacts.
- C6. **Spawn/destroy events from commands are dispatched at the next step** (one cascade level per step). Reason: avoids unbounded same-step loops (spawn ↔ destroy) without an arbitrary iteration limit.
- C7. **Split keeps the parent as child 0** and new children inherit the parent's cooldown and retrigger timestamps. Reason: stable handles, no destroy events per split, and children touching the same wall do not instantly re-split or re-play.
- C8. **Caps and tunnelling at runtime refuse the whole command** (no partial split, no radius clamp, no exception). Reason: deterministic, never crashes a long render, and the shrinking-split visual simply stops at the limit.
- C9. **`when` fires once**, the first frame its predicate is true, evaluated after the frame. Reason: matches the SRS `end_after` use; predicates may be costly (counting), so per frame not per step.
- C10. **Timer times are rounded to whole steps**; `every` starts at `t = seconds`, not 0; zero-step timers are errors. Reason: integer step math like M1 sample offsets; an event at t = 0 would precede any physics.
- C11. **Escape threshold**: centre beyond `radius + thickness/2 + ball radius + margin` (ball fully outside the ring band), `margin=0` default, once per (ring, ball). Reason: the ball visibly leaves before the event; never fires for a ball bouncing on the wall.
- C12. **Default ball cap `max_balls=1000`**; `add_ball` beyond it is a `ConfigError` (script time), runtime spawns are refused. Reason: keeps renders tractable; script-time errors are cheap to fix.
- C13. **`max_total` counts all live balls in the scene** after the action, not only balls produced by that action. Reason: matches "ball doubles each wall hit, capped" in the SRS example.
- C14. **Spatial hash switches automatically once at 100 live balls**, `dim = 2 × largest radius`, `count = 10 000`, never back. Reason: SRS asks for it "when ball count is large"; no example needs tuning, so no public option.
- C15. **Constant speed target = initial |velocity|**, updated by `set_velocity`; split children inherit it; must be > 0 and ≤ `max_speed`. Reason: simplest rule that counters energy drift without fighting the clamp.
- C16. **Split geometry**: directions spread evenly over `spread_degrees` centred on the parent's direction; children placed side by side perpendicular to it, `2r' + 1` px apart. If a child would overlap a ring wall (e.g. a grazing hit, where the perpendicular points into the wall, or `radius_scale > 1`), the whole formation is translated radially to 0.5 px clear of that wall, rings in insertion order, worst child first (≤ 8 passes per ring). Reason: children diverge immediately and do not overlap each other; the solver cannot be trusted with wall overlap (a grown child can be pushed out through a closed ring, and an overlapping child is drawn inside the wall). Revised after the M2 review.
- C17. **Spawn values may be callables `f(ctx)`** evaluated during dispatch, per ball. Reason: escape example needs random velocities from `scene.rng` without a mini-language; dispatch-time evaluation fixes rng order.
- C18. **Subjects**: collision `a` = object with `tag_a`; escape `a` = ball, `b` = ring; spawn/destroy `a` = object; timers/conditions none. Targeting a missing subject is a registration-time `ConfigError`. Reason: catches mistakes before rendering.
- C19. **Callback signatures**: collision `(ctx, a, b, event)`, escape `(ctx, ball, ring, event)`, spawn/destroy `(ctx, obj, event)`, timer/condition `(ctx, event)`. Reason: follows the SRS `custom(ctx, a, b, contact)` shape; the event is always last.
- C20. **Event model**: one `Event` dataclass with `kind`; `CollisionEvent` is an alias; timer/condition events have `speed=None`, `position=None`. Play on such events uses `play.gain` and skips `min_impact_speed`. Reason: uniform log for audio and M4 metadata; M1 code keeps working.
- C21. **`end_after` only shortens the video**, earliest end wins, counted from the end of the current frame. Reason: predictable; duration remains the upper bound.
- C22. **Flash = colour blend from flash colour back to base over `round(seconds·fps)` frames** (min 1), drawn by the scene, not stored in physics. Reason: visual-only per SRS P3; glow/particles are M3.
- C23. **`destroy` works on rings too; `split`/`resize`/`set_velocity` on a ring are no-ops.** Reason: breaking a ring is a natural effect; ring geometry changes are M5 territory.
- C24. **`render` muxes audio when any rule has `A.play` or any trigger was produced** (e.g. `ctx.play` in a callback). Reason: callback-only sound must not be lost; rule-less scenes stay video-only (B11).
