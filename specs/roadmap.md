# Roadmap: viral video ideas, framework improvements, growth plan

Written 2026-11-06 after web research. Nothing here is built yet unless it says so; each
framework item still goes through the normal spec → tasks → tests flow and needs the user's
go-ahead (CLAUDE.md: no later milestones without asking).

## 1. What the research says (and how much to trust it)

Sources are listed at the end. Most are tool vendors and blogs, so treat numbers as rules of
thumb, not facts. The points below are the ones several independent sources agree on.

| Finding | Confidence | What it means for us |
|---|---|---|
| The genre ("Will the ball escape?", "ball bouncing brainrot") went viral on Shorts in Nov 2023 and stayed popular through 2024; it is now crowded with tool-made clones. | High (Know Your Meme) | Plain "ball in ring" is not enough any more; we need a twist, a story or a competition the copy tools can't do easily. |
| The first 1–3 s decide most of it: early swipe-away is the strongest negative signal. | Medium (many blogs agree, no official doc) | Motion and stakes from frame 1; the hook text must be readable at once; no slow intro. |
| Retention % beats length; replays (loops) are a strong positive signal. | Medium | Aim for 20–40 s; end on a frame that loops into the start, or a climax that makes people rewatch. |
| Music synced to hits, growth/escalation, spawners, escape-gap tension and races are the recurring formats. | High (all genre sources) | We already have these; combine them with competition. |
| One coder-creator found maze videos did best. | Low (one creator) | Worth a test: mazes are now possible with static polygons. |
| Team/country battles and "pick your side" prompts drive comments. | Low–medium (anecdotal) | Competition formats with named teams; ask viewers to pick before the end. |
| Sound volume/pitch tied to impact speed and size makes hits feel better. | Medium | Already done (louder impacts play louder); extend to size and add more voices. |

## 2. Video idea backlog

Ranked by expected pull (competition and suspense first) and by cost. "Now" means it can be made
with the current library; otherwise the needed framework item (§3) is named.

| # | Idea | Hook text | Why it should work | Needs |
|---|---|---|---|---|
| 1 | **Color Wars, 4 teams** (extend `color_wars.py`): 4 named colours, last to 30% loses / first wins | "Pick your color 👇" | Comment bait, real uncertainty, series-able | Now |
| 2 | **Maze escape**: one ball in a polygon maze inside the ring; each wall hit plays a note | "Can it find the exit?" | Maze reported as best performer; long tension | Now (static polygons) |
| 3 | **Plinko prediction**: 100 balls drop through pegs into 5 labelled slots | "Which slot wins?" | Viewers predict, then watch to check | Now (`examples/static_shapes.py` base) |
| 4 | **Escape race**: 2–4 coloured balls in one spinning-gap ring, first out wins | "Which one escapes first?" | Simple, fast payoff, loopable | Now |
| 5 | **Shrinking arena / last ball standing**: ring shrinks every N s (replace with a smaller ring), balls touching a hazard die | "Only one survives" | Elimination suspense | Now (destroy + `ctx.add_circle`); nicer with F4 |
| 6 | **Guess the song**: hits reveal a public-domain melody note by note | "Guess the song before it ends" | Comments + rewatches | Now |
| 7 | **Name battles**: balls carry names/emoji (countries, zodiac, games) | "Your country vs mine" | Identity drives comments and shares | F1 labels (and F6 images for flags) |
| 8 | **Spinning hexagon / square containers**, nested shapes that rotate | "Escape the hexagon" | Fresh shapes vs endless circles | F3 kinematic polygons |
| 9 | **1 vs 100**: one big ball vs 100 tiny ones, colour takeover | "Can 1 beat 100?" | Underdog story | Now (Color Wars ideas + ball-ball rules) |
| 10 | **Countdown fill**: the circle fills in exactly 30 s to a beat | "Wait for the drop" | Music + climax | F5 beat sync |

Make each as a **series** (Part 1, 2, 3 with a new seed, team or rule), because a series
gives the algorithm repeat viewers and gives us A/B data.

## 3. Framework improvements (proposed milestone M6, plus the rest of M5)

Ordered by how many backlog ideas they unlock per unit of work.

| ID | Item | Unlocks | Size |
|---|---|---|---|
| F1 | **Ball labels**: `add_ball(..., label="BR")` / text or emoji drawn on the ball, follows it, inherited on split | 7, 1, 9 | S |
| F2 | **Seed scoring in batch**: `bouncekit batch ... --score expr` ranks renders by a metric from metadata (closeness of a race, final count, time to end) and writes `ranking.json`; `--keep-best N` | every competition video (pick the closest race automatically) | S |
| F3 | **Kinematic (rotating/moving) polygons** and **resizable rings** (rest of M5) | 8, 5, rotating mazes | M |
| F4 | **Arena tools**: `A.shrink_ring`, timed hazards, safe-zone guides in preview (top/bottom UI bars) | 5, all (hook placement) | S |
| F5 | **Beat/tempo sync**: schedule events on a tempo (`scene.on_beat(bpm)`) and a background music bed mixed under hit notes | 10, polish everywhere | M |
| F6 | **Image sprites**: PNG for balls/backgrounds (flags, logos the user owns) | 7 | M |
| F7 | **Loop-friendly endings**: helper that cross-fades the last 0.5 s into frame 0, or starts/ends on the same composition | retention on all videos | S |
| F8 | **Export pack**: thumbnail PNG of the climax frame, title/description/hashtag text file from scene metadata, optional 4:5 and 1:1 crops | upload workflow | S |
| F9 | **Render speed**: profile polygon/glow drawing (Color Wars renders at ~4.4 s per video second); cache static layers, draw unchanged polygons once | faster batches = more A/B | M |
| F10 | **More sound**: SFX voices (pop, crunch, whoosh), pitch by ball size, sidechain-style ducking under the music bed | polish | S |

Suggested order: F2 → F1 → F7 → F8 (cheap, help every upload), then F3 → F4 → F5 → F9 → F6 → F10.

## 4. How to get more views

1. **Hook in frame 1**: motion already on screen, a question with stakes ("Only one survives"),
   large text inside the safe zone (y ≈ 250–1650). Never start on a static frame.
2. **20–40 s, then stop**: end right after the climax (`end_after` 2–3 s). Longer only if the
   story keeps escalating.
3. **Loop it**: last frame should lead back into the first (F7), so replays count.
4. **Competition and prediction**: teams, races, "pick your color"; pin a comment asking for
   predictions. Name teams after things people identify with (F1).
5. **Series and consistency**: one format per week as Part 1/2/3; post daily or near-daily on
   Shorts, TikTok and Reels (same MP4; the 1080×1920 export already fits all three).
6. **Pick the best seed, not the first**: render 5–10 seeds with `bouncekit batch`, choose the
   closest race / best climax (F2 automates this).
7. **A/B the hook**: same scene, two hook texts or colours (`--set`), post both a day apart, keep
   what retains better.
8. **Read the analytics, not the blogs**: YouTube Studio retention curves show where viewers
   leave; feed that back (e.g. if people leave at 5 s, make the first escalation earlier). Log
   each upload's params + seed (the metadata JSON already has them) next to its views.
9. **Sound on**: keep hits musical and impacts loud; add a music bed later (F5).
10. **Originality**: avoid copying a specific creator's video; our edge is mechanics the
    no-code tools can't do (territory battles, growing walls, mazes, layered rules).

## 5. Next session checklist

- Ask the user which backlog ideas to make next (top picks: 1, 2, 3, 4).
- Ask whether to start F2 (seed scoring) and F1 (ball labels) as milestone M6.
- Keep `specs/progress.md` "Where we left off" and README "What you can make" up to date.

## Sources

- Know Your Meme, "Will the Ball Escape? / Ball Bouncing Brainrot": https://knowyourmeme.com/memes/will-the-ball-escape-ball-bouncing-brainrot
- Fun Circle Games, "Viral Growth Blueprint: Dominating TikTok with 'Satisfying' Content" (vendor): https://funcirclegames.pages.dev/blog/viral-growth-blueprint-tiktok-satisfying-content
- BallEngine on Product Hunt (vendor): https://www.producthunt.com/p/fun-circle-games/ballengine-app
- Korpi AI, "How to Make Ball Escape Ring Videos with AI" (vendor): https://korpi.ai/blog/how-to-make-ball-escape-ring-videos-with-ai
- Recapio digest of "I Used Code to Go Viral on Social Media" (Green Code): https://recapio.com/digest/i-used-code-to-go-viral-on-social-media-by-green-code
- Pythonic Bounce, "Bringing Python simulations to life, now with sound": https://pythonic-bounce.beehiiv.com/p/bringing-python-simulations-to-life-now-with-sound
- JoinBrands, "YouTube Shorts Best Practices (2026)": https://joinbrands.com/blog/youtube-shorts-best-practices/
- DEV Community, "YouTube Shorts algorithm hacks: what actually works in 2026": https://dev.to/ytzoloai/youtube-shorts-algorithm-hacks-what-actually-works-in-2026-439b
- Aibrify, "YouTube Shorts retention curve playbook": https://aibrify.com/blog/youtube-shorts-retention-curve-playbook
- go-viral.app, "YouTube Shorts Algorithm 2026": https://www.go-viral.app/blog/youtube-shorts-algorithm-2026/
- "100 Countries Marble Elimination — Full Plan" (template doc): https://secure-show.pages.dev/d/doc_mnmabhcl_c4a8a1bf
- Wikipedia, "Oddly satisfying videos": https://en.wikipedia.org/wiki/Oddly_satisfying_videos
