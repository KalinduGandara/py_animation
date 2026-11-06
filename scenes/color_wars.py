"""Color Wars: two balls fight over a circle. Hitting free space (or your own colour) grows
your colour inward; hitting the other colour wears it away, at half the speed. First colour
to cover 30% of the circle wins.

Render:   uv run bouncekit render scenes/color_wars.py
Preview:  uv run bouncekit preview scenes/color_wars.py
Tweak:    --set target=0.4 --set erode=0.3 --set blue=#00b4d8 --set pink=#ff006e
"""

import copy
import math
from pathlib import Path

from bouncekit import Polygon, Scene
from bouncekit import sound as S
from bouncekit.colors import parse_color

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CX, CY = 540.0, 960.0
R = 430.0
WALL = 16.0
INNER = R - WALL / 2  # the ring's inner surface
BALL = 18.0
RAYS = 120
DTH = 2 * math.pi / RAYS

scene = Scene(duration=60.0, seed=1, background="#0a0a12", gravity=(0.0, 0.0))

speed = scene.param("speed", 1600.0)  # ball speed, px/s
depth = scene.param("depth", 32.0)  # how far one hit grows the wall, px
width = scene.param("width", 6)  # rays either side of the hit that change too
erode = scene.param("erode", 0.5)  # unfilling rate as a fraction of the filling rate
target = scene.param("target", 0.30)  # share of the circle that wins
slope = scene.param("slope", 0.8)  # max edge step between neighbour rays / their spacing
blue_hex = scene.param("blue", "#1e88e5")
pink_hex = scene.param("pink", "#e91e63")
FLOOR = BALL + 1
DECIDE_AT = 55.0  # if nobody reached the target, the leader wins here

TEAMS = {
    "blue": {"fill": parse_color(blue_hex), "name": "BLUE",
             "notes": S.scale("C4", mode="major_pentatonic", octaves=2, voice="marimba")},
    "pink": {"fill": parse_color(pink_hex), "name": "PINK",
             "notes": S.scale("A4", mode="minor_pentatonic", octaves=2, voice="pluck")},
}
CRUNCH = S.note("E2", voice="marimba")


def lighter(c: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = (round(v + (255 - v) * 0.45) for v in c)
    return (r, g, b)


scene.add_circle(center=(CX, CY), radius=R, thickness=WALL, color="#d8d8e8", glow=1.2,
                 tags={"wall"})
balls = {}
for team, x in (("blue", CX - 120), ("pink", CX + 120)):
    a = scene.rng.uniform(0.0, 2.0 * math.pi)
    balls[team] = scene.add_ball(
        pos=(x, CY), radius=BALL, velocity=(speed * math.cos(a), speed * math.sin(a)),
        color=lighter(TEAMS[team]["fill"]), trail=True, glow=1.5, constant_speed=True,
        tags={"ball", team},
    )

Pt = tuple[float, float]
# Per ray: layers from the wall inward, each [team, thickness]. The free edge is what is left.
stacks: list[list[list]] = [[] for _ in range(RAYS)]
pieces: list[list[Polygon]] = [[] for _ in range(RAYS)]  # drawn/solid pieces of wedge k
pending: list[tuple[str, float, float]] = []  # (team, hit angle, time)
state = {"blue": 0.0, "pink": 0.0, "winner": None}
moved = {t: {"pos": balls[t].position, "t": 0.0} for t in balls}


def front(st: list[list[list]], k: int) -> float:
    return INNER - sum(t for _, t in st[k % RAYS])


def at(r: float, angle: float) -> Pt:
    return (CX + r * math.cos(angle), CY + r * math.sin(angle))


def clip(poly: list[Pt], a: Pt, b: Pt, outer: bool) -> list[Pt]:
    """Keep the part of ``poly`` on the far (``outer``) or centre side of line a-b."""
    def side(p: Pt) -> float:
        s = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        c = (b[0] - a[0]) * (CY - a[1]) - (b[1] - a[1]) * (CX - a[0])
        return -s * c if outer else s * c

    out: list[Pt] = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def poly_area(pts: list[Pt]) -> float:
    pairs = zip(pts, pts[1:] + pts[:1], strict=True)
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs)) / 2


def wedge_quad(st: list[list[list]], k: int) -> list[Pt] | None:
    a, b = front(st, k), front(st, k + 1)
    if INNER - a < 0.5 and INNER - b < 0.5:
        return None
    t0, t1 = k * DTH, (k + 1) * DTH
    return [at(INNER + 1, t0), at(INNER + 1, t1), at(b, t1), at(a, t0)]


def wedge_pieces(st: list[list[list]], k: int) -> list[tuple[list[Pt], str]]:
    """Wedge k (rays k..k+1) as coloured convex pieces. Each half follows its own ray's
    layers, cut along chords at the layer depths; the inner side is the free edge."""
    a, b = front(st, k), front(st, k + 1)
    if INNER - a < 0.5 and INNER - b < 0.5:
        return []
    t0, t1 = k * DTH, (k + 1) * DTH
    tm = (t0 + t1) / 2
    pa, pb = at(a, t0), at(b, t1)
    mid = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
    halves = [
        ([at(INNER + 1, t0), at(INNER + 1, tm), mid, pa], k, k + 1, (t0, tm)),
        ([at(INNER + 1, tm), at(INNER + 1, t1), pb, mid], k + 1, k, (tm, t1)),
    ]
    out = []
    for half, ray, other, (u0, u1) in halves:
        layers = st[ray % RAYS] or st[other % RAYS]  # an empty ray borrows its neighbour's
        level = INNER
        for j, (team, thick) in enumerate(layers):
            part = half
            if j > 0:
                part = clip(part, at(level, u0), at(level, u1), outer=False)
            inner = level - thick
            if j < len(layers) - 1:
                part = clip(part, at(inner, u0), at(inner, u1), outer=True)
            if len(part) >= 3 and poly_area(part) > 1.0:
                out.append((part, team))
            level = inner
    return out


def fill(st: list[list[list]], k: int, amount: float, team: str) -> None:
    k %= RAYS
    amount = min(amount, front(st, k) - FLOOR)
    if amount <= 0:
        return
    if st[k] and st[k][-1][0] == team:
        st[k][-1][1] += amount
    else:
        st[k].append([team, amount])


def wear(st: list[list[list]], k: int, amount: float, victim: str) -> None:
    k %= RAYS
    if st[k] and st[k][-1][0] == victim:
        st[k][-1][1] -= amount
        if st[k][-1][1] < 0.5:
            st[k].pop()


def after_hit(team: str, angle: float, rng) -> tuple[list[list[list]], bool]:  # type: ignore[no-untyped-def]
    """New layer stacks after ``team`` hits at ``angle``; True if it was an erosion."""
    st = copy.deepcopy(stacks)
    c = round(angle / DTH) % RAYS
    top = st[c][-1][0] if st[c] else None
    eroding = top is not None and top != team
    for j in range(-width, width + 1):
        amount = depth * (1 - abs(j) / (width + 1)) * rng.uniform(0.5, 1.0)
        if eroding:
            wear(st, c + j, amount * erode, top)
        else:
            fill(st, c + j, amount, team)
    if not eroding:  # slope limit: neighbours fill in so no notch is too sharp
        grow = 1 + slope * DTH
        for _ in range(2):
            for k in list(range(RAYS)) + list(reversed(range(RAYS))):
                for n in (k - 1, k + 1):
                    excess = front(st, k) - front(st, n) * grow
                    if excess > 0:
                        fill(st, k, excess, team)
    return st, eroding


def shares(st: list[list[list]]) -> dict[str, float]:
    out = {"blue": 0.0, "pink": 0.0}
    for layers in st:
        outer = INNER
        for team, thick in layers:
            inner = outer - thick
            out[team] += (outer * outer - inner * inner) / 2 * DTH
            outer = inner
    full = math.pi * INNER * INNER
    return {t: v / full for t, v in out.items()}


@scene.on_collision("ball", "wall")
def hit(ctx, ball, wall, event):  # type: ignore[no-untyped-def]
    if state["winner"]:
        return
    team = "blue" if "blue" in ball.tags else "pink"
    px, py = event.position
    angle = math.atan2(py - CY, px - CX) % (2 * math.pi)
    ctx.particles(pos=event.position, count=10, speed=380, lifetime=0.45, size=3,
                  color=TEAMS[team]["fill"])
    if all(t != team or abs((angle - a + math.pi) % (2 * math.pi) - math.pi) > DTH
           for t, a, _ in pending):
        pending.append((team, angle, ctx.time))


@scene.every(1 / 60)
def tick(ctx, event):  # type: ignore[no-untyped-def]
    if state["winner"]:
        return
    for team, ball in balls.items():  # safety net: re-aim a ball that is jammed
        m = moved[team]
        if ctx.time - m["t"] >= 0.5:
            bx, by = ball.position
            if math.hypot(bx - m["pos"][0], by - m["pos"][1]) < 4 * BALL:
                t = ctx.rng.uniform(0.0, 2.0 * math.pi)
                ctx.set_velocity(ball, (speed * math.cos(t), speed * math.sin(t)))
            m.update(pos=(bx, by), t=ctx.time)
    keep = []
    for team, angle, t in pending:
        st, eroding = after_hit(team, angle, ctx.rng)
        changed = sorted({w for k in range(RAYS) if st[k] != stacks[k] for w in (k - 1, k)})
        changed = [w % RAYS for w in changed]
        quads = [wedge_quad(st, w) for w in changed]
        clear = all(q is None or Polygon(None, points=q).distance(b.position) > BALL + 2
                    for q in quads for b in balls.values())
        if not clear:
            if ctx.time - t < 1.0:
                keep.append((team, angle, t))
            continue
        for w in changed:
            old = pieces[w]
            pieces[w] = [ctx.add_polygon(points=pts, color=TEAMS[owner]["fill"], tags={"wall"})
                         for pts, owner in wedge_pieces(st, w)]
            for p in old:
                ctx.destroy(p)
        stacks[:] = st
        if eroding:
            ctx.play(CRUNCH, gain=0.8)
        else:
            ctx.play(TEAMS[team]["notes"], pan=0.5)
    pending[:] = keep
    state.update(shares(stacks))
    leader = max(("blue", "pink"), key=lambda t: state[t])
    if state[leader] >= target or ctx.time >= DECIDE_AT:
        state["winner"] = leader
        ctx.particles(pos=(CX, CY), count=120, speed=900, lifetime=1.2, size=4,
                      color=TEAMS[leader]["fill"])
        ctx.end_after(3.0)


scene.add_text(f"First to {round(target * 100)}% wins!", pos=(540, 300), size=72, end=3.5)
for team, x in (("blue", 300), ("pink", 780)):
    scene.add_text(lambda s, t=team: f"{TEAMS[t]['name']} {math.floor(100 * state[t])}%",
                   pos=(x, 1560), size=72, color=lighter(TEAMS[team]["fill"]))
scene.add_text(lambda s: f"{TEAMS[state['winner']]['name']} WINS!" if state["winner"] else "",
               pos=(540, 960), size=130, color="#ffffff")

if __name__ == "__main__":
    scene.run()
