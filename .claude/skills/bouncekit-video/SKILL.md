---
name: bouncekit-video
description: Turn a plain-language idea into a finished vertical "satisfying physics" MP4 (YouTube Shorts / TikTok / Reels) with the bouncekit library in this repo - balls bouncing in rings, splitting, escaping rotating gaps, being destroyed, with musical hits, trails, glow and text. Use this skill whenever the user describes a video, animation, short, reel or clip involving balls, circles/rings, bouncing, splitting, escaping, collisions or "satisfying"/ASMR physics, or asks to make/render/generate/create a bouncekit scene - even if they never say "bouncekit" or "scene script".
---

# Make a bouncekit video from a prompt

The deliverable is a rendered MP4 that matches the user's idea. A scene script that has not been rendered and checked is not done. bouncekit is the library in this repo; `README.md` is its API reference and `examples/*.py` are scenes known to work. Read the README sections you need before writing code. It is short, and guessing signatures wastes render cycles.

## Workflow

### 1. Turn the prompt into a scene plan

Write a short plan (for yourself, then for the user at the end) covering:

- **Setup**: rings (radius, thickness, gap, rotation), starting balls (count, size, speed, direction), gravity on or off.
- **Rules**: for each trigger, the effect. For example: ball hits wall → split + note; ball escapes → destroy + spawn 2; when 300 balls → end in 3 s.
- **Sound**: what plays on which event (scale, single note, melody) and with which voice.
- **Look**: background, colours, trails/glow/particles, text (a hook title, a live counter).
- **Story and length**: what the viewer waits for (escalation, a race, a countdown) and how it ends. Default to 30 s; Shorts must be ≤ 60 s.

Prompts are usually vague ("balls multiply until chaos"). Fill the gaps with choices that suit the genre instead of asking: a dark background, a bright ring, a 20–30 px ball, hue-cycling colours, a pluck or marimba scale, and a clear climax. Ask the user only when a gap would change the video and you can't sensibly default it. The common case is a specific copyrighted song: you can't download one, so ask for a `.mid` file or offer a public-domain tune. List the assumptions you made in your final message so the user can redirect you.

### 2. Write the scene script

Put it at `scenes/<slug>.py` (create `scenes/` if missing). The CLI loads exactly one module-level `Scene`. Start from this skeleton and keep the `if __name__` block:

```python
"""<One line saying what happens in this video>.

Render:   uv run bouncekit render scenes/<slug>.py
Preview:  uv run bouncekit preview scenes/<slug>.py
"""

import math
from pathlib import Path

from bouncekit import Scene
from bouncekit import actions as A
from bouncekit import colors as C
from bouncekit import sound as S

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CENTER = (540.0, 960.0)

scene = Scene(duration=30.0, seed=42, background="#07070d", gravity=(0.0, 0.0), max_balls=400)

ring = scene.add_circle(center=CENTER, radius=450, thickness=8, color="#e8e8ff", glow=1.0,
                        tags={"wall"})
scene.add_ball(pos=(540, 760), radius=22,
               velocity=(scene.rng.uniform(-600, 600), scene.rng.uniform(400, 700)),
               color=C.hue_cycle(step=29), trail=True, glow=1.0, constant_speed=True,
               tags={"ball"})

scene.on_collision("ball", "wall", [
    A.play(S.scale("C4", mode="major_pentatonic", octaves=2, voice="pluck"), pan=0.6),
    A.particles(count=10),
])

if __name__ == "__main__":
    scene.run()
```

Rules of thumb that save iterations:

- **Determinism:** use `scene.rng` during setup and `ctx.rng` inside rules (`A.spawn(velocity=f)` where `f(ctx)` uses `ctx.rng`). Never use `random`, `time` or numpy's global RNG: the library promises the same seed gives the same video, and other randomness breaks that.
- **Coordinates:** pixels, origin top-left, +y down, canvas 1080×1920, centre (540, 960). Keep key action and text within y ≈ 250–1650; platform UI covers the top and bottom.
- **Motion style:** "bounces forever, never slows": `gravity=(0, 0)` + `constant_speed=True`. "Falls and bounces": gravity around `(0, 900)`, `elasticity` 0.9–1.0, no constant speed.
- **Tunnelling guard:** `add_ball`/`add_circle` raise `ConfigError` if `max_speed / (fps*substeps) >= ball radius + ring thickness/2`. With the defaults (4000 px/s, 60 fps × 8 substeps = 8.33 px per step) keep `radius + thickness/2 > 8.4`. For tiny balls, lower `Scene(max_speed=...)` or raise `substeps`.
- **Growth needs a cap:** splitting or spawning doubles fast. Set `Scene(max_balls=...)` and/or `max_total=` on `A.split`/`A.spawn`; caps refuse extra balls quietly. 200–500 balls looks busy and still renders in reasonable time. Over 1000 is slow.
- **Ball size for big counts:** N balls fill about 30% of a ring of radius R when `radius ≈ 0.55 · R / √N`. For example, 256 balls in R = 450 means radius ≈ 15. The skeleton's 22 px suits a few dozen balls.
- **Spawned balls start plain:** split children inherit trail, glow and colour mode, but `A.spawn` balls have no parent. Pass `color=`, `trail=True` and `glow=` to `A.spawn` to match the look.
- **Shrinking splits:** `A.split(radius_scale=0.8)` makes children smaller. Once they would break the tunnelling guard the split is refused. That's fine, but a scene that "stops splitting" early is usually this.
- **Escapes:** a ring with `gap_degrees` + `angular_velocity` plus `scene.on_escape(ring, "ball", [...])`. Escaped balls keep flying off-screen, so add `A.destroy()` unless the brief wants them visible outside.
- **Pacing (how fast things happen):** a ball at speed v in a ring of radius R hits the wall roughly every `1.5 · R / v` seconds. So "split on every hit" doubles the count about that often: 1 → 256 takes about `8 × 1.5R/v`, which is ~10 s at 520 px/s in R = 450. Each hit escapes through a rotating gap with probability roughly `(gap − 2·asin(r/R)) / 360`. These are only first guesses. The reliable way is to **measure from the smoke render**: its event counts per second (`escape`, `spawn`) extrapolate to the full length. Tune speed, gap or caps **before** the full render; a wasted full render costs minutes. If the brief fixes the length ("40 seconds") and the growth would finish early, lower the speed or end on `when` + `end_after`.
- **Ending on the climax:** `scene.when(lambda s: s.count("ball") >= N, [A.end_after(3)])` or `scene.at(t, [...])`. The video ends there, and the audio with it.
- **Sound:** every hit can play. Repeat noise is limited automatically (6 new notes per frame, 24 at once, 0.05 s retrigger per object). Voices: `"pluck"` and `"marimba"` sound the most "satisfying"; `S.sample(ASSETS/"samples"/"kalimba.wav", root="A4")` is a kalimba. `S.scale` climbs a scale; `S.melody(path, voice=...)` plays the next chord of a MIDI file on each hit, so the hits become the rhythm of the tune. Only notes that actually play advance a scale or melody, so a busy frame that drops hits never makes the tune skip; it just plays the next note on the next allowed hit.
- **A tune from the prompt:** for a public-domain melody (Twinkle Twinkle, Ode to Joy, Für Elise opening, a folk tune), write the note order with `scripts/notes_to_midi.py` (only the order matters):
  `uv run python .claude/skills/bouncekit-video/scripts/notes_to_midi.py assets/midi/<name>.mid "C4 C4 G4 G4 A4 A4 G4"`. `assets/midi/ode_to_joy.mid` is already there.
- **Text:** `scene.add_text("Hook?", pos=(540, 300), size=72, end=3.0)` for a hook; `scene.add_text(lambda s: f"{s.count('ball')} balls", pos=(540, 1650), size=52)` for a live counter of balls.
- **Counting events** (escapes, splits, hits): keep a counter in the script, raise it from a callback rule (it can sit next to an action-list rule for the same event) and read it in the text lambda:

  ```python
  escaped = {"n": 0}

  @scene.on_escape(ring, "ball")
  def count_escape(ctx, ball, _ring, event):
      escaped["n"] += 1

  scene.add_text(lambda s: f"ESCAPED: {escaped['n']}", pos=(540, 1600), size=64)
  ```

  It is deterministic because rules run in simulation order. Avoid scanning `scene.events` every frame; it grows with every contact.
- **Tweakable knobs:** expose the numbers the user is likely to tune with `scene.param("gap", 40.0)`, so they can re-render with `--set gap=60` or sweep with `bouncekit batch`.

Keep lines ≤ 100 characters; the repo's `uv run ruff check .` covers `scenes/` too.

### 3. Smoke test (seconds, not minutes)

```bash
uv run bouncekit render scenes/<slug>.py --duration 4 --quiet --out out/<slug>_draft.mp4
```

This catches `ConfigError`s and script errors quickly. Error messages name the field and the fix; apply it and rerun.

### 4. Full render and check it against the plan

```bash
uv run bouncekit render scenes/<slug>.py --quiet
uv run python .claude/skills/bouncekit-video/scripts/inspect_video.py out/<slug>_seed42.mp4 --frames 6 --at 1.0
```

The inspector prints the streams, the event counts from the metadata JSON (collisions, splits as `spawn`, escapes, destroys, sound triggers) and writes `out/<slug>_seed42_sheet.png`, six frames from start to end. `--at 1.0` also saves the frame at 1 s, which shows a hook title that the evenly spaced sheet can miss. **Open the PNGs with the Read tool and look at them.** Note that `collision` counts every contact including ball-to-ball, and `spawn` includes split children. Then compare against the plan:

| You expected | Check | Typical fix |
|---|---|---|
| Things happen early | `events` counts > 0; frame 2 already differs from frame 1 | faster or more balls, smaller ring, bigger gap |
| Escalation (splits / spawns) | `spawn` count grows; later frames are busier | raise caps; `radius_scale` closer to 1 |
| Escapes | `escape` > 0 | larger `gap_degrees`, faster rotation, higher speed |
| Sound throughout | audio stream present, `sound_triggers` in the dozens or more | add `A.play` on the main collision |
| Balls stay visible | nothing stuck at the edges or gone too soon | `A.destroy()` on escape; check the ring centre and radius |
| It ends well | final frame shows the climax | `when` + `end_after`, or adjust `duration` |
| It looks polished | trails/glow visible, colours vary, text readable | `trail=True, glow=1.0`, `C.hue_cycle`, `A.particles`, `glow=` on the ring |

Iterate until the sheet tells the story the user asked for, usually one to three renders. Rendering takes about 1–3 s of wall time per second of video with trails and glow (a 40 s neon scene took ~100 s), and longer with hundreds of balls. Smoke renders are where iteration is cheap.

### 5. Report

Tell the user:
- the MP4 path and its length;
- what happens in the video (one or two sentences, based on what you saw, not what you intended);
- the assumptions you made;
- how to change it: re-render with another seed (`--seed 7`), the exposed params (`--set name=value`), `uv run bouncekit preview scenes/<slug>.py` (live, reloads when the file is saved, but silent), and `uv run bouncekit batch scenes/<slug>.py --seeds 1-5 --jobs 4` to pick the best of several.

The audio and the trail/glow look can't be judged from stills. Say you checked the sound numerically (the trigger counts), not by listening.

## Where to look

- `README.md`: every public function, its options and defaults; read the section you need (Rules, Effects and melody, Parameters/batches/text).
- `examples/`: working scenes to adapt. `split_on_wall.py` (doubling with a cap), `escape_rotating_gap.py` (escape → spawn 2), `destroy_on_contact.py` (hazard ring, timers, `when` + `end_after`), `midi_melody.py` (polished: trails, glow, particles, melody, pan), `param_sweep.py` (params + text overlay).
- Need behaviour the built-in actions don't cover? Use a callback rule: `@scene.on_collision("ball", "wall")` then `def hit(ctx, ball, wall, event): ...`, calling `ctx.split/spawn/destroy/recolor/resize/set_velocity/flash/play/particles/end_after`. Changes are queued and applied safely after the physics step.
- Things the library cannot do yet (M5, not built): static segments, polygons, boxes, ramps, hinges, dominoes and camera moves. If the brief needs them, say so and offer the closest ring-based version.
