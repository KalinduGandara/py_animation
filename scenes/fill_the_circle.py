"""The wall grows inward wherever the ball hits it - jagged, solid, no gaps - playing
Für Elise note by note, until only a ball-sized pocket is left.

Render:   uv run bouncekit render scenes/fill_the_circle.py
Preview:  uv run bouncekit preview scenes/fill_the_circle.py
Look:     --set color=#ff9f1c --set color2=#2ec4b6 --set texture=rings
          textures: solid, rings, gradient, rainbow, checker
"""

import colorsys
import math
from pathlib import Path

from bouncekit import ConfigError, Polygon, Scene
from bouncekit import sound as S
from bouncekit.colors import parse_color

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CX, CY = 540.0, 960.0
R = 430.0
WALL = 16.0
INNER = R - WALL / 2  # the ring's inner surface
BALL = 18.0
RAYS = 120  # the growing edge is RAYS points, one per ray from the centre
TEXTURES = ("solid", "rings", "gradient", "rainbow", "checker")

scene = Scene(duration=50.0, seed=42, background="#080712", gravity=(0.0, 0.0))

speed = scene.param("speed", 1800.0)  # ball speed, px/s
depth = scene.param("depth", 36.0)  # how far one hit pushes the wall in, px
width = scene.param("width", 6)  # rays either side of the hit that move too
slope = scene.param("slope", 0.8)  # max radius step between neighbour rays / their spacing
snug = scene.param("snug", 2.2)  # "FILLED!" once the empty area is <= snug x the ball's area
color = scene.param("color", "#b8a6ff")  # fill colour
color2 = scene.param("color2", "#5b45c9")  # second colour for rings/gradient/checker
texture = scene.param("texture", "solid")
band = scene.param("band", 30.0)  # stripe width for rings/gradient/checker, px
if texture not in TEXTURES:
    raise ConfigError(f"texture must be one of {', '.join(TEXTURES)}; got {texture!r}")
C1, C2 = parse_color(color), parse_color(color2)
BAND = band if texture in ("rings", "gradient", "checker") else 1e9  # one piece when unbanded
FLOOR = BALL + 1  # the edge never comes closer to the centre than this
BALL_AREA = math.pi * BALL * BALL

scene.add_circle(center=(CX, CY), radius=R, thickness=WALL, color=C1, glow=1.5, tags={"wall"})
a0 = scene.rng.uniform(0.0, 2.0 * math.pi)
ball = scene.add_ball(pos=(CX, CY), radius=BALL,
                      velocity=(speed * math.cos(a0), speed * math.sin(a0)),
                      color="#ffffff", trail=True, glow=1.5, constant_speed=True, tags={"ball"})

tune = S.melody(ASSETS / "midi" / "fur_elise.mid",
                voice=S.sample(ASSETS / "samples" / "kalimba.wav", root="A4"))

Pt = tuple[float, float]
ANG = [2 * math.pi * k / RAYS for k in range(RAYS)]
edge = [INNER] * RAYS  # current edge radius per ray
pieces: list[list[Polygon]] = [[] for _ in range(RAYS)]  # solid pieces between ray k and k+1
pending: list[tuple[float, float]] = []  # (hit angle, time) waiting for the ball to clear
state = {"empty": 0.0, "last": 0.0, "over": False}
moved = {"pos": (CX, CY), "t": 0.0}  # where the ball was half a second ago


def point(r: float, k: int) -> Pt:
    t = ANG[k % RAYS]
    return (CX + r * math.cos(t), CY + r * math.sin(t))


def area(radii: list[float]) -> float:
    s = math.sin(2 * math.pi / RAYS) / 2
    return sum(radii[k] * radii[(k + 1) % RAYS] * s for k in range(RAYS))


FULL = area([INNER] * RAYS)


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


def wedge(radii: list[float], k: int) -> list[Pt] | None:
    """The solid quad between ray k and k+1, or None while it has no depth."""
    a, b = radii[k], radii[(k + 1) % RAYS]
    if INNER - a < 0.5 and INNER - b < 0.5:
        return None
    return [point(INNER + 1, k), point(INNER + 1, k + 1), point(b, k + 1), point(a, k)]


def piece_color(k: int, j: int) -> tuple[int, int, int]:
    """Colour of band j (0 = at the wall) of wedge k, by texture."""
    if texture == "rings":
        return C1 if j % 2 == 0 else C2
    if texture == "checker":
        return C1 if (j + k // 5) % 2 == 0 else C2
    if texture == "gradient":
        t = min(j / 10, 1.0)
        r, g, b = (round(c2 + (c1 - c2) * t) for c1, c2 in zip(C1, C2, strict=True))
        return (r, g, b)
    if texture == "rainbow":
        r, g, b = colorsys.hsv_to_rgb(k / RAYS, 0.6, 1.0)
        return (round(r * 255), round(g * 255), round(b * 255))
    return C1


def bands(radii: list[float], k: int) -> list[tuple[list[Pt], tuple[int, int, int]]]:
    """Wedge k cut exactly along chords at INNER - j * BAND: (points, colour), wall first."""
    quad = wedge(radii, k)
    if quad is None:
        return []
    deepest = min(radii[k], radii[(k + 1) % RAYS])
    out = []
    j = 0
    while INNER - j * BAND > deepest:
        part = quad
        if j > 0:
            lvl = INNER - j * BAND
            part = clip(part, point(lvl, k), point(lvl, k + 1), outer=False)
        lvl = INNER - (j + 1) * BAND
        if lvl > deepest:
            part = clip(part, point(lvl, k), point(lvl, k + 1), outer=True)
        if len(part) >= 3 and poly_area(part) > 1.0:
            out.append((part, piece_color(k, j)))
        j += 1
    return out


def pushed(angle: float, rng) -> list[float]:  # type: ignore[no-untyped-def]
    """The edge after a hit at ``angle``: a jagged dent, then the slope limit."""
    radii = list(edge)
    centre = round(angle / (2 * math.pi) * RAYS)
    for j in range(-width, width + 1):
        k = (centre + j) % RAYS
        dent = depth * (1 - abs(j) / (width + 1)) * rng.uniform(0.5, 1.0)
        radii[k] = max(FLOOR, radii[k] - dent)
    # Slope limit relative to the ray spacing at that radius: no notch sharper than
    # ~2 * atan(slope), so the ball can never wedge itself into one.
    gap = 2 * math.pi / RAYS
    for _ in range(2):  # sweep both ways so the limit spreads around the ring
        for k in range(RAYS):
            radii[k] = min(radii[k], radii[k - 1] * (1 + slope * gap))
        for k in reversed(range(RAYS)):
            radii[k] = min(radii[k], radii[(k + 1) % RAYS] * (1 + slope * gap))
    return radii


@scene.on_collision("ball", "wall")
def hit(ctx, b, wall, event):  # type: ignore[no-untyped-def]
    if state["over"]:
        return
    ctx.play(tune)
    ctx.particles(pos=event.position, count=10, speed=380, lifetime=0.45, size=3)
    px, py = event.position
    angle = math.atan2(py - CY, px - CX) % (2 * math.pi)
    step = 2 * math.pi / RAYS
    if all(abs((angle - a + math.pi) % (2 * math.pi) - math.pi) > step for a, _ in pending):
        pending.append((angle, ctx.time))


@scene.every(1 / 60)
def grow(ctx, event):  # type: ignore[no-untyped-def]
    if state["over"]:
        return
    if ctx.time - moved["t"] >= 0.5:  # safety net: a ball that barely moved is jammed
        bx, by = ball.position
        if math.hypot(bx - moved["pos"][0], by - moved["pos"][1]) < 4 * BALL:
            t = ctx.rng.uniform(0.0, 2.0 * math.pi)
            ctx.set_velocity(ball, (speed * math.cos(t), speed * math.sin(t)))
        moved.update(pos=(bx, by), t=ctx.time)
    keep = []
    for angle, t in pending:
        radii = pushed(angle, ctx.rng)
        changed = [k for k in range(RAYS)
                   if radii[k] != edge[k] or radii[(k + 1) % RAYS] != edge[(k + 1) % RAYS]]
        quads = [wedge(radii, k) for k in changed]
        clear = all(q is None or Polygon(None, points=q).distance(ball.position) > BALL + 2
                    for q in quads)
        if not clear:
            if ctx.time - t < 1.0:  # retry while the ball moves away; drop after 1 s
                keep.append((angle, t))
            continue
        for k in changed:
            old = pieces[k]
            pieces[k] = [ctx.add_polygon(points=pts, color=c, tags={"wall"})
                         for pts, c in bands(radii, k)]
            if pieces[k]:  # a soft flash on the growing front only
                ctx.flash(pieces[k][-1], seconds=0.15, color="#ffffff")
            for p in old:
                ctx.destroy(p)
        edge[:] = radii
        state["last"] = ctx.time
    pending[:] = keep
    state["empty"] = area(edge)
    stuck = state["empty"] < 0.2 * FULL and ctx.time - state["last"] > 3.0
    if state["empty"] <= snug * BALL_AREA or stuck:
        state["over"] = True
        ctx.end_after(2.5)


def label(s: Scene) -> str:
    filled = 1 - state["empty"] / FULL
    if state["over"] and state["empty"] <= snug * BALL_AREA:
        return "FILLED!"
    pct = min(math.floor(100 * filled), 99)  # 100% only means the pocket is ball-sized
    return f"{pct}% FILLED" if state["over"] else f"{pct}%"


scene.add_text("Will it fill the circle?", pos=(540, 300), size=72, color="#ffffff", end=3.5)
scene.add_text(label, pos=(540, 1560), size=96, color=C1)

if __name__ == "__main__":
    scene.run()
