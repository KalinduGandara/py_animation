# SRS — `bouncekit`, a Python framework for 2D physics ASMR videos

(The user's master prompt, saved verbatim as the source requirements. Milestone status and decisions live in the other `specs/` files.)

## Context

I'm a senior software engineer. I want to produce short vertical "satisfying physics" videos for YouTube Shorts / TikTok / Reels: balls bouncing inside circles, splitting or being destroyed on collision, escaping through gaps in rotating rings, with every collision producing a musical sound. Later I want to extend this to 2D Rube Goldberg–style chain-reaction videos.

Build a small, well-structured Python framework (working name `bouncekit`, easy to rename) so that each new video is a short Python scene script, and the framework handles physics, rules, rendering, audio and MP4 export.

Work in the milestones below. **Stop after each milestone**, show me what you built, how to run it, and the output file, and wait for my review before continuing. Do not build later milestones early. Prefer a working end-to-end result over abstraction; extract abstractions only when a second use case needs them.

## Tech stack

- Python 3.11+, managed with `uv` (`pyproject.toml`), type hints throughout.
- **Physics:** `pymunk`. Check the installed version's API before writing collision code (the collision-handler API changed in Pymunk 7; don't assume older examples are correct).
- **Rendering:** `pygame-ce` for both offline frame rendering and a live preview window. Put drawing behind a `Renderer` interface so a `skia-python` backend can be added later for better anti-aliasing and glow.
- **Audio:** `numpy` for synthesis/mixing, `soundfile` to write WAV, `mido` to read MIDI melodies.
- **Video:** `ffmpeg` via subprocess. Pipe raw RGB frames into ffmpeg's stdin (no intermediate PNGs). Fail early with a clear message if ffmpeg is not installed.
- **Tests:** `pytest`.

## Core principles (non-negotiable)

1. **Deterministic.** Fixed physics timestep with configurable substeps (default 60 fps × 8 substeps), seeded RNG owned by the scene, no wall-clock time anywhere in simulation. Same scene + same seed must produce bit-identical frames and audio.
2. **Offline rendering is the source of truth.** The preview window is a convenience; the MP4 render is what matters. Rendering speed doesn't need to be real-time.
3. **Physics, visuals and audio are decoupled.** The simulation emits events. The renderer reads world state each frame. The audio system consumes a timestamped event log after (or during) simulation. Visual-only effects (trails, particles, flashes) never touch physics.
4. **Never mutate the physics space inside a collision callback.** Rule actions (split, destroy, spawn, resize) are queued and applied after the step (Pymunk post-step callbacks or an equivalent command queue).
5. **Screen coordinates in the public API**: pixels, origin top-left, y down, gravity positive y. Default canvas 1080×1920 at 60 fps.

## Public API (target shape; refine as needed but keep this spirit)

```python
from bouncekit import Scene, actions as A, sound as S, colors as C

scene = Scene(
    width=1080, height=1920, fps=60, duration=60, seed=42, background="#0b0b12", gravity=(0, 900)
)

ring = scene.add_circle(
    center=(540, 960),
    radius=450,
    thickness=8,
    color="#ffffff",
    gap_degrees=0,
    angular_velocity=0,
    tags={"wall"},
)

scene.add_ball(
    pos=(540, 700),
    radius=20,
    velocity=(300, 0),
    elasticity=1.0,
    color=C.hue_cycle(),
    trail=True,
    tags={"ball"},
)

scene.on_collision(
    "ball",
    "wall",
    [
        A.split(into=2, spread_degrees=30, max_total=500),
        A.play(S.melody("assets/midi/song.mid", voice="pluck")),
        A.flash(ring, seconds=0.08),
    ],
)


@scene.on_collision("ball", "ball")
def custom(ctx, a, b, contact):  # escape hatch: plain Python
    if a.radius > 30:
        ctx.destroy(a)


scene.on_escape(ring, "ball", [A.destroy(), A.play(S.note("C6"))])
scene.when(lambda w: w.count("ball") >= 500, A.end_after(seconds=3))

if __name__ == "__main__":
    scene.run()  # CLI decides: preview or render
```

Object methods return handles (`Ball`, `CircleBoundary`, ...) that rules and callbacks can reference. Options are keyword arguments with sensible defaults. Use dataclasses for config, not loose dicts.

## Architecture (suggested modules)

- `scene.py`: Scene, object registry, tags, run loop, lifecycle.
- `world/`: wrappers over Pymunk: balls, circle boundary (built from N arc segments, default 128, with optional gap and kinematic rotation), later segments/polygons/joints.
- `rules/`: event types (collision by tag pair, escape from boundary, timer `every`/`at`, condition predicate, spawn, destroy), built-in actions, action context with a deferred command queue, per-object/pair cooldowns so resting contact doesn't retrigger every substep.
- `render/`: Renderer interface, pygame backend, effects (trails via fading overlay, glow, impact particles, flashes), color modes (fixed, hue cycle per spawn, by speed, by generation).
- `audio/`: event log → audio buffer. See Audio section.
- `export/`: ffmpeg frame pipe, WAV writing, final mux (H.264, yuv420p, CRF ~18, AAC 192k, `+faststart`).
- `cli.py`: `bouncekit preview scene.py`, `bouncekit render scene.py --seed 7 --out out/x.mp4 --duration 45`, `bouncekit batch scene.py --seeds 1-10`.

## Physics details to handle

- Ball count hard cap (global and per action); refuse splits beyond it.
- Optional **constant-speed mode** per ball (renormalize velocity magnitude each step) to counter energy drift with perfect elasticity.
- Max speed clamp and enough substeps to prevent tunneling through thin boundary segments.
- Smooth collisions at segment seams (use segment radius; verify balls don't snag).
- Split behavior: children inherit speed, spread around the parent's velocity direction, spawn slightly separated so they don't instantly re-collide, optional radius change per generation.
- Escape detection for circles with gaps (ball center beyond radius + margin).
- Use Pymunk's spatial hash when ball count is large.

## Audio

- Every collision/escape/spawn event is logged with simulation time, involved objects, impact speed and position.
- Sound sources: single note, musical scale (cycles through notes, default major pentatonic), and **melody from MIDI** (each triggering hit plays the next note of the song, a key format for these videos).
- Voices: simple synth (sine/triangle with ADSR), Karplus-Strong pluck, marimba-like tone, and sample playback from WAV with pitch shifting.
- Gain scales with impact speed; optional stereo pan by x-position.
- **Polyphony limit** and per-frame trigger cap so exponential growth doesn't become noise; per-object minimum retrigger interval.
- Master bus: soft limiter + normalization to avoid clipping. 48 kHz output.
- Audio placement must be sample-accurate to event time.

## Milestones

**M0: Skeleton + first video (no sound).** Project setup, deterministic loop, ring boundary, one ball under gravity, offline render piped to ffmpeg, live preview window.
Acceptance: `bouncekit render examples/single_ball.py` produces a smooth 1080×1920 60 fps MP4; rendering twice with the same seed yields identical frame hashes (test).

**M1: Audio pipeline.** Event log, synth voices, scale + single-note sources, mixing, limiter, mux into MP4.
Acceptance: each bounce is audibly in sync at frame level; test that event times map to correct sample offsets.

**M2: Rules engine.** Tagged collisions, escape, timers, conditions, built-in actions (split, destroy, spawn, recolor, resize, set velocity, flash, play, end_after), Python callback escape hatch, deferred mutation, cooldowns, ball cap.
Acceptance: three example scenes render correctly: `split_on_wall.py` (ball doubles on each wall hit, capped), `escape_rotating_gap.py` (balls escape a rotating ring with a gap, each escape spawns two new balls inside), `destroy_on_contact.py`.

**M3: Visual polish + MIDI melodies.** Trails, glow, impact particles, color modes, MIDI melody source, sample voices, stereo pan, preview hot-reload when the scene file changes.
Acceptance: an example with a MIDI melody plays the tune note-by-note on hits and looks polished.

**M4: Batch + productivity.** CLI batch rendering over seeds/parameters, render metadata JSON beside each MP4 (seed, params, duration, event counts), optional title/text overlay, progress bar with ETA.

**M5 (later, only when I ask): Rube Goldberg primitives.** Static/dynamic segments, polygons, boxes, ramps, pivots/hinges/motors, dominoes, camera (follow, pan, zoom), and a fast authoring workflow in preview mode.

## Engineering standards

- Small, readable modules; docstrings on public API; README with quickstart and an API overview that stays updated each milestone.
- Tests for determinism, audio timing, deferred mutation and rule triggering.
- Clear errors for bad scene configuration.
- Don't add dependencies beyond the stack above without asking me.
- When a design decision is genuinely ambiguous, state your assumption briefly and proceed, or ask me if it affects the public API.
