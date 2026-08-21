#!/usr/bin/env python3
"""Render the GROUND ZERO opening title sequence as PNG frames.

A 16-bit opening in the grammar of the Mega Man X intros — publisher sting,
prologue crawl, a journey, an arrival, a name card, the logo — telling this
programme's own story: a distress signal leaves Earth, someone a long way off
answers it, comes through a wormhole, and puts her ship into a hillside in the
Okanagan where nobody sees her land.  She then goes and asks people what they
are doing, holding a baguette.

**Nothing in this sequence is a crosshair.**  An earlier pass built the whole
identity around a reticle — the O of ZERO was one.  It is gone: the O is a
planet with an orbit, the crawl's mark is a transmission bloom, and the
programme's designation reads LANDING SITE.  She is not aiming at anyone; the
premise is that she turned up to help.

The 16-bit part is specific: per-scanline gradients (HDMA), colour math for
every light source, depth planes separated by contrast, shaded sprites lit from
one direction, and a chrome ramp for the display face.

The canvas is 320x240 — 4:3 with square pixels, doubling exactly to the 640x480
the station's other cards are authored at, which pillarboxes into the channel's
854x480 precisely inside the on-air rails.

Usage:  make_frames.py OUTDIR [--stills]
"""
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzart
import gzfont
import gzpal as P

W, H = 320, 240
FPS = 30

TRIBAND = (P.PINK[2], P.ARMOUR[2], P.VISOR[2])

# ── timeline ──────────────────────────────────────────────────────────────
T_STING = 135      # 4.5 s
T_CRAWL = 420      # 14.0 s
T_SPACE = 210      # 7.0 s
T_WORM = 180       # 6.0 s
T_LAND = 240       # 8.0 s
T_FACE = 120       # 4.0 s
T_NAME = 150       # 5.0 s
T_SLAM = 210       # 7.0 s
T_ATTRACT = 135    # 4.5 s
TOTAL = (T_STING + T_CRAWL + T_SPACE + T_WORM + T_LAND + T_FACE + T_NAME
         + T_SLAM + T_ATTRACT)                                    # 1800

C_STING = 0
C_CRAWL = C_STING + T_STING
C_SPACE = C_CRAWL + T_CRAWL
C_WORM = C_SPACE + T_SPACE
C_LAND = C_WORM + T_WORM
C_FACE = C_LAND + T_LAND
C_NAME = C_FACE + T_FACE
C_SLAM = C_NAME + T_NAME
C_ATTRACT = C_SLAM + T_SLAM

PROLOGUE = [
    "IN THE YEAR 20XX,",
    "A DISTRESS SIGNAL",
    "LEFT EARTH.",
    "",
    "IT WAS FAINT, AND IT",
    "WAS NOT ADDRESSED",
    "TO ANYONE IN",
    "PARTICULAR.",
    "",
    "SOMEONE ANSWERED IT.",
    "",
    "SHE HAD BEEN LOOKING",
    "FOR A REASON",
    "TO COME HOME.",
]
CRAWL_PITCH = 18
CRAWL_SPEED = 1
CRAWL_HOLD = 60

WORDMARK = "RIPOSTE LABORATORIES INC."


# ── colour math ───────────────────────────────────────────────────────────
def new_frame(colour=P.BLACK):
    return Image.new("RGB", (W, H), colour)


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def add(base, lay, amount=1.0):
    """Additive colour math — the SNES main/sub screen add.  Every light source
    in the sequence goes through this: the moon, the signal, the wormhole, the
    engine, the fireball, the logo bloom."""
    rgb = lay.convert("RGB")
    if amount < 1.0:
        rgb = Image.blend(Image.new("RGB", (W, H), P.BLACK), rgb, amount)
    a = lay.getchannel("A")
    if a.getextrema() != (255, 255):
        rgb = Image.composite(rgb, Image.new("RGB", (W, H), P.BLACK), a)
    return ImageChops.add(base, rgb)


def over(base, lay):
    base.paste(lay, (0, 0), lay)
    return base


def vgrad(img, y0, y1, stops, x0=0, x1=W):
    """A gradient evaluated once per scanline.  This is the HDMA table."""
    d = ImageDraw.Draw(img)
    span = max(1, y1 - y0)
    for y in range(max(0, y0), min(H, y1)):
        d.line([(x0, y), (x1 - 1, y)], fill=P.stops_at(stops, (y - y0) / span))


def fade(img, k):
    if k >= 0.999:
        return img
    if k <= 0:
        return new_frame(P.BLACK)
    return Image.blend(new_frame(P.BLACK), img, k)


def flash(img, k, colour=P.WHITE):
    if k <= 0:
        return img
    lay = layer()
    ImageDraw.Draw(lay).rectangle([0, 0, W, H], fill=colour + (255,))
    return add(img, lay, min(1.0, k))


# ── type ──────────────────────────────────────────────────────────────────
_text_cache = {}


def text_img(s, colour, scale=1):
    key = (s, colour, scale)
    hit = _text_cache.get(key)
    if hit is not None:
        return hit
    cw = gzfont.SMALL_CELL * scale
    img = Image.new("RGBA", (max(1, cw * len(s)), gzfont.SMALL_H * scale),
                    (0, 0, 0, 0))
    px = img.load()
    for i, ch in enumerate(s):
        glyph = gzfont.SMALL.get(ch, gzfont.MISSING)
        ox = i * cw
        for gy, row in enumerate(glyph):
            for gx, on in enumerate(row):
                if not on:
                    continue
                for sy in range(scale):
                    for sx in range(scale):
                        px[ox + gx * scale + sx, gy * scale + sy] = colour + (255,)
    _text_cache[key] = img
    return img


def text_w(s, scale=1):
    return gzfont.SMALL_CELL * scale * len(s)


def blit_text(img, x, y, s, colour, scale=1, shadow=None):
    if shadow is not None:
        t = text_img(s, shadow, scale)
        img.paste(t, (x + scale, y + scale), t)
    t = text_img(s, colour, scale)
    img.paste(t, (x, y), t)


def blit_centre(img, y, s, colour, scale=1, shadow=None):
    blit_text(img, (W - text_w(s, scale)) // 2, y, s, colour, scale, shadow)


def triband(img, x, y, w, h):
    d = ImageDraw.Draw(img)
    a, b = int(w * 0.36), int(w * 0.64)
    d.rectangle([x, y, x + a - 1, y + h - 1], fill=TRIBAND[0])
    d.rectangle([x + a, y, x + b - 1, y + h - 1], fill=TRIBAND[1])
    d.rectangle([x + b, y, x + w - 1, y + h - 1], fill=TRIBAND[2])


def signal_arcs(d, cx, cy, phase, count=3, spacing=26, span=(150, 210),
                colour=None, alpha=170):
    """Concentric ARCS, opening one way — a transmission leaving, or arriving.

    Deliberately arcs and never rings-with-a-cross: the thing this replaced was
    a reticle, and a ring plus two crossed lines is a gunsight no matter what
    you call it in the caption.
    """
    for i in range(count):
        r = int(phase + i * spacing)
        if r < 6:
            continue
        a = int(alpha * max(0.0, 1.0 - (r / (spacing * (count + 1)))))
        if a <= 0:
            continue
        col = colour or P.stops_at(P.WORM_STOPS, (i / max(1, count - 1)))
        d.arc([cx - r, cy - r, cx + r, cy + r], span[0], span[1],
              fill=col + (a,))


# ── scene 1 · publisher sting ─────────────────────────────────────────────
def scene_sting(f):
    img = new_frame(P.BLACK)
    y = 100
    x0 = (W - text_w(WORDMARK)) // 2

    if f < 6:
        return img

    shown = min(len(WORDMARK), int((f - 6) / 1.05))
    if shown:
        blit_text(img, x0, y, WORDMARK[:shown], P.BONE[1])

    if 44 <= f < 50:
        blit_text(img, x0, y, WORDMARK, P.BONE[1])
        return flash(img, 1.0 - (f - 44) / 6.0)

    if f >= 50:
        blit_text(img, x0, y, WORDMARK, P.BONE[1])
        triband(img, x0, y + 12, text_w(WORDMARK), 3)
        if f < 84:
            k = (84 - f) / 34.0
            st = layer()
            ImageDraw.Draw(st).line(
                [(x0 - 20, y + 13), (x0 + text_w(WORDMARK) + 20, y + 13)],
                fill=P.WHITE + (int(200 * k),))
            img = add(img, st, k)
    if f >= 62:
        blit_centre(img, y + 26, "PRESENTS", P.ARMOUR[2])
    if f >= 74:
        blit_centre(img, y + 44, "A CHANNEL Z0 TRANSMISSION", P.STEEL[1])

    if f >= T_STING - 24:
        img = fade(img, max(0.0, (T_STING - 6 - f) / 18))
    return img


# ── scene 2 · prologue crawl ──────────────────────────────────────────────
def _crawl_block():
    h = CRAWL_PITCH * len(PROLOGUE)
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    for i, ln in enumerate(PROLOGUE):
        if not ln:
            continue
        last = i == len(PROLOGUE) - 1
        colour = P.HAIR[1] if last else P.BONE[1]
        x = (W - text_w(ln)) // 2
        blit_text(img, x, i * CRAWL_PITCH, ln, colour, 1, shadow=(0x14, 0x12, 0x22))
    return img


CRAWL = None
NEBULA = None
STARS = [((i * 61) % W, (i * 37) % 300, 1 + i % 3) for i in range(150)]


def _nebula():
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, [(0.0, (0x05, 0x04, 0x0e)), (0.55, (0x0d, 0x08, 0x1c)),
                      (1.0, (0x04, 0x03, 0x0a))])
    lay = layer()
    d = ImageDraw.Draw(lay)
    for cx, cy, r, col in ((70, 90, 62, (0x1a, 0x28, 0x4a)),
                           (240, 150, 78, (0x2e, 0x14, 0x30)),
                           (170, 40, 54, (0x14, 0x2a, 0x3e))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
    return add(img, lay.filter(ImageFilter.GaussianBlur(18)), 0.55)


def scene_crawl(f):
    img = NEBULA.copy()
    d = ImageDraw.Draw(img)

    for x, y0, plane in STARS:
        speed = (1, 2, 3)[plane - 1]
        y = (y0 - f * speed // 2) % 300 - 30
        if 0 <= y < H:
            d.point((x, y), fill=P.ramp_at(P.BONE, (3 - plane) * 0.28))

    # The signal itself, arriving from off frame right, over and over.
    glow = layer()
    gd = ImageDraw.Draw(glow)
    signal_arcs(gd, 330, 118, (f * 1.4) % 96, count=4, spacing=30, alpha=150)
    gd.ellipse([326, 114, 334, 122], fill=P.HAIR[1] + (190,))
    img = add(img, glow, 0.85)

    scroll = min(f * CRAWL_SPEED, (T_CRAWL - CRAWL_HOLD) * CRAWL_SPEED)
    img.paste(CRAWL, (0, H - scroll), CRAWL)

    if f < 14:
        img = fade(img, f / 14)
    if f >= T_CRAWL - 12:
        img = fade(img, max(0.0, (T_CRAWL - 1 - f) / 11))
    return img


# ── scene 3 · deep space, and the signal ──────────────────────────────────
EARTH_X, EARTH_Y, EARTH_R = 252, 112, 27


def _starfield(img, f, drift=1.0):
    d = ImageDraw.Draw(img)
    for x, y0, plane in STARS:
        speed = (1, 2, 4)[plane - 1] * drift
        xx = int(x - f * speed / 3) % (W + 20) - 10
        if 0 <= xx < W:
            d.point((xx, y0 % H), fill=P.ramp_at(P.BONE, (3 - plane) * 0.28))


def _earth(img):
    d = ImageDraw.Draw(img)
    d.ellipse([EARTH_X - EARTH_R, EARTH_Y - EARTH_R,
               EARTH_X + EARTH_R, EARTH_Y + EARTH_R], fill=P.OCEAN_D)
    for r in range(EARTH_R, 0, -1):
        t = 1.0 - r / EARTH_R
        d.ellipse([EARTH_X - r - 4, EARTH_Y - r, EARTH_X + r - 4, EARTH_Y + r],
                  fill=P.lerp(P.OCEAN_D, P.OCEAN, t * 0.9))
    for cx, cy, rx, ry in ((-8, -10, 9, 6), (4, 4, 11, 7), (-12, 8, 6, 4)):
        d.ellipse([EARTH_X + cx - rx, EARTH_Y + cy - ry,
                   EARTH_X + cx + rx, EARTH_Y + cy + ry], fill=P.LAND)
        d.ellipse([EARTH_X + cx - rx + 2, EARTH_Y + cy - ry + 1,
                   EARTH_X + cx + rx - 3, EARTH_Y + cy + ry - 1], fill=P.LAND_D)
    halo = layer()
    hd = ImageDraw.Draw(halo)
    for r, a in ((EARTH_R + 10, 28), (EARTH_R + 5, 44), (EARTH_R + 2, 70)):
        hd.ellipse([EARTH_X - r, EARTH_Y - r, EARTH_X + r, EARTH_Y + r],
                   outline=(0x7f, 0xc0, 0xff) + (a,), width=2)
    return add(img, halo.filter(ImageFilter.GaussianBlur(3)), 0.9)


def _ship(img, x, y, thrust=1.0, shake=0):
    ship = gzart.load_rocket()
    sx = x + (shake if (x + y) % 2 else -shake)
    plume = layer()
    pd = ImageDraw.Draw(plume)
    n = int(10 * thrust)
    for i in range(n):
        w_ = max(1, 5 - i // 2)
        pd.ellipse([sx - 3 - i * 2 - w_, y + 7 - w_ // 2,
                    sx - 3 - i * 2 + w_, y + 8 + w_ // 2],
                   fill=P.stops_at([(0.0, P.WHITE), (0.4, P.ARMOUR[1]),
                                    (1.0, P.PINK[2])], i / max(1, n - 1))
                   + (max(0, 210 - i * 22),))
    img = add(img, plume.filter(ImageFilter.GaussianBlur(1)), thrust)
    img.paste(ship, (sx, y), ship)
    return img


def scene_space(f):
    img = new_frame()
    vgrad(img, 0, H, P.SPACE_STOPS)
    _starfield(img, f)
    img = _earth(img)

    # The distress call: arcs leaving Earth, one set every 24 frames.
    glow = layer()
    gd = ImageDraw.Draw(glow)
    for k in range(3):
        ph = ((f + k * 24) * 1.6) % 72
        signal_arcs(gd, EARTH_X, EARTH_Y, ph + EARTH_R, count=3, spacing=22,
                    span=(120, 240), alpha=150)
    img = add(img, glow, 0.9)

    # She answers at f 120: the plume doubles and she starts closing.
    if f < 120:
        x = -30 + f * 0.55
        thrust = 0.55
    else:
        x = -30 + 120 * 0.55 + (f - 120) * 1.25
        thrust = 1.0
    img = _ship(img, int(x), EARTH_Y - 6, thrust, shake=1 if f > 120 else 0)

    if f >= 24:
        blit_text(img, 12, 200, "DISTRESS · SOURCE: SOL III", P.HAIR[1], 1,
                  shadow=P.BLACK)
    if f >= 44:
        blit_text(img, 12, 212, "NO ADDRESSEE", P.BONE[2], 1, shadow=P.BLACK)
    if f >= 122 and (f // 10) % 2 == 0:
        blit_text(img, 12, 224, "▸ ANSWERING", P.ARMOUR[2], 1, shadow=P.BLACK)

    if f < 14:
        img = fade(img, f / 14)
    if f >= T_SPACE - 8:
        img = fade(img, max(0.0, (T_SPACE - 1 - f) / 7))
    return img


# ── scene 4 · the wormhole ────────────────────────────────────────────────
def scene_worm(f):
    """A tunnel of rings rushing outward, in light blue, white and pink.

    This is the one place those three colours sit together, and it is the whole
    of what the sequence says about her out loud."""
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, [(0.0, (0x08, 0x06, 0x12)), (0.5, (0x12, 0x0c, 0x22)),
                      (1.0, (0x08, 0x06, 0x12))])
    cx, cy = 160, 118

    rings = layer()
    rd = ImageDraw.Draw(rings)
    speed = 3.0 + 5.0 * (f / T_WORM)
    for i in range(16):
        t = ((i * 22 + f * speed) % 352) / 352.0
        r = int(6 + t * t * 300)
        if r < 4 or r > 420:
            continue
        col = P.stops_at(P.WORM_STOPS, (i * 0.17 + f * 0.006) % 1.0)
        a = int(220 * (1.0 - t) ** 0.7)
        rd.ellipse([cx - r, cy - int(r * 0.72), cx + r, cy + int(r * 0.72)],
                   outline=col + (a,), width=max(1, int(1 + t * 5)))
    img = add(img, rings, 0.95)

    streaks = layer()
    sd = ImageDraw.Draw(streaks)
    for i in range(30):
        ang = i * 12 + f * 0.6
        rr = 20 + ((i * 37 + f * 9) % 240)
        x1 = cx + math.cos(math.radians(ang)) * rr
        y1 = cy + math.sin(math.radians(ang)) * rr * 0.72
        x2 = cx + math.cos(math.radians(ang)) * (rr + 26)
        y2 = cy + math.sin(math.radians(ang)) * (rr + 26) * 0.72
        sd.line([(x1, y1), (x2, y2)],
                fill=P.stops_at(P.WORM_STOPS, (i / 30.0)) + (110,))
    img = add(img, streaks, 0.8)

    img = _ship(img, cx - 14 + (1 if f % 3 else -1), cy - 7, 1.0, shake=1)

    if 20 <= f < 110:
        blit_centre(img, 210, "TRANSIT", P.BONE[2])

    if f < 10:
        img = fade(img, f / 10)
    if f >= T_WORM - 22:                       # blow out into the crash
        img = flash(img, (f - (T_WORM - 22)) / 21.0)
    return img


# ── scene 5 · the Okanagan, and the landing ───────────────────────────────
RIDGE_FAR = [(0, 138), (36, 128), (72, 134), (108, 120), (144, 132),
             (180, 116), (216, 126), (252, 118), (288, 130), (320, 124)]
RIDGE_NEAR = [(0, 152), (24, 145), (48, 150), (72, 142), (96, 152), (120, 156),
              (148, 154), (172, 144), (196, 133), (220, 140), (244, 136),
              (268, 146), (296, 138), (320, 148)]

MOON_X, MOON_Y, MOON_R = 62, 96, 24
CRASH_X, CRASH_Y = 214, 132
SASHA_X, SASHA_FOOT = 112, 206


def _ridge(d, pts, floor, colour):
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d.polygon([(x0, y0), (x1, y1), (x1, floor), (x0, floor)], fill=colour)


def _land_plate():
    """Sky, moon, two ranges, the lake and the near shore she lands on."""
    img = new_frame()
    vgrad(img, 0, 156, P.SKY_STOPS)
    d = ImageDraw.Draw(img)

    for i in range(70):
        x, y = (i * 71) % W, (i * 43) % 96
        d.point((x, y), fill=P.ramp_at(P.BONE, 0.35 + (i % 4) * 0.16))

    for r in range(MOON_R, 0, -1):
        t = 1.0 - r / MOON_R
        d.ellipse([MOON_X - r, MOON_Y - r, MOON_X + r, MOON_Y + r],
                  fill=P.lerp((0xd8, 0xd2, 0xc4), (0xff, 0xfb, 0xef), t * 0.8))
    for cx, cy, r in ((MOON_X - 9, MOON_Y - 6, 4), (MOON_X + 7, MOON_Y + 5, 6),
                      (MOON_X + 2, MOON_Y - 13, 3)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0xbe, 0xb7, 0xa8))
    halo = layer()
    hd = ImageDraw.Draw(halo)
    for r, a in ((56, 24), (42, 32), (32, 44), (27, 66)):
        hd.ellipse([MOON_X - r, MOON_Y - r, MOON_X + r, MOON_Y + r],
                   fill=(0x9a, 0x92, 0xb8) + (a,))
    img = add(img, halo.filter(ImageFilter.GaussianBlur(6)), 0.9)

    d = ImageDraw.Draw(img)
    _ridge(d, RIDGE_FAR, 160, (0x33, 0x24, 0x4c))     # far range, hazy
    _ridge(d, RIDGE_NEAR, 166, (0x1c, 0x14, 0x2c))    # near range, darker
    d.rectangle([0, 156, W, 166], fill=(0x1c, 0x14, 0x2c))

    vgrad(img, 164, 186, P.LAKE_STOPS)                 # the lake
    shim = layer()
    sd = ImageDraw.Draw(shim)
    for y in range(165, 186):
        wdt = 3 + (y - 165)
        sd.line([(MOON_X - wdt, y), (MOON_X + wdt, y)],
                fill=(0xd8, 0xd2, 0xc4) + (max(0, 52 - (y - 165) * 2),))
    for y in range(166, 186, 3):
        sd.line([(0, y), (W, y)], fill=(0x8a, 0x82, 0xa8, 38))
    img = add(img, shim, 0.8)

    d = ImageDraw.Draw(img)
    # The near shore: the darkest, highest-contrast plane, and where she stands.
    d.polygon([(0, 196), (90, 188), (200, 192), (320, 186), (320, H), (0, H)],
              fill=(0x05, 0x04, 0x08))
    d.polygon([(0, 196), (90, 188), (200, 192), (320, 186), (320, 188),
               (200, 194), (90, 190), (0, 198)], fill=(0x22, 0x1c, 0x18))
    for x in range(0, W, 11):
        d.point((x + (x // 11) % 4, 202 + (x // 37) % 3), fill=(0x1a, 0x17, 0x14))
    return img


LAND = None
SMOKE = [((i * 29) % 13 - 6, (i * 17) % 70, 3 + (i % 4)) for i in range(22)]


def _crash_site(img, f):
    """The ship, nose into the hillside, still burning."""
    ship = gzart.load_rocket().rotate(-52, expand=True, resample=Image.NEAREST)
    img.paste(ship, (CRASH_X - ship.width // 2, CRASH_Y - ship.height // 2), ship)

    fire = layer()
    fd = ImageDraw.Draw(fire)
    for i in range(7):
        r = 3 + (i + f // 3) % 6
        fd.ellipse([CRASH_X - 8 + i * 3 - r, CRASH_Y + 8 - r,
                    CRASH_X - 8 + i * 3 + r, CRASH_Y + 8 + r],
                   fill=P.stops_at([(0.0, P.WHITE), (0.5, P.ARMOUR[1]),
                                    (1.0, P.PINK[2])], (i / 6.0))
                   + (120,))
    img = add(img, fire.filter(ImageFilter.GaussianBlur(3)), 0.85)

    smoke = layer()
    sd = ImageDraw.Draw(smoke)
    for dx, y0, r0 in SMOKE:
        t = ((y0 + f * 1.1) % 90) / 90.0
        yy = CRASH_Y + 4 - t * 80
        rr = r0 + t * 9
        a = int(90 * (1.0 - t))
        sd.ellipse([CRASH_X + dx - rr + t * 14, yy - rr,
                    CRASH_X + dx + rr + t * 14, yy + rr],
                   fill=(0x3a, 0x33, 0x40) + (a,))
    return over(img, smoke.filter(ImageFilter.GaussianBlur(2)))


def scene_land(f):
    img = LAND.copy()

    # 0–66: she comes down.  A fireball on a diagonal, with a trail.
    if f < 70:
        k = f / 66.0
        x = 30 + k * (CRASH_X - 30)
        y = 6 + k * (CRASH_Y - 6)
        tr = layer()
        td = ImageDraw.Draw(tr)
        for i in range(18):
            kk = max(0.0, k - i * 0.012)
            tx = 30 + kk * (CRASH_X - 30)
            ty = 6 + kk * (CRASH_Y - 6)
            rr = max(1, 5 - i // 3)
            td.ellipse([tx - rr, ty - rr, tx + rr, ty + rr],
                       fill=P.stops_at([(0.0, P.WHITE), (0.5, P.ARMOUR[1]),
                                        (1.0, P.PINK[2])], i / 17.0)
                       + (max(0, 220 - i * 12),))
        img = add(img, tr.filter(ImageFilter.GaussianBlur(2)))
        if f >= 62:
            img = flash(img, (f - 62) / 8.0)
        if f < 10:
            img = flash(img, (10 - f) / 10.0)
        return img

    g = f - 70
    if g < 10:
        img = flash(img, (10 - g) / 12.0)

    img = _crash_site(img, g)

    sasha, _ = gzart.load()
    img.paste(sasha, (SASHA_X, SASHA_FOOT - gzart.H), sasha)

    # Her core and her antenna tips are light sources.
    glow = layer()
    gd = ImageDraw.Draw(glow)
    top = SASHA_FOOT - gzart.H
    gd.ellipse([SASHA_X + 15, top + 19, SASHA_X + 20, top + 24],
               fill=P.VISOR[1] + (150,))
    for ax in (12, 22):
        gd.ellipse([SASHA_X + ax - 2, top - 1, SASHA_X + ax + 2, top + 3],
                   fill=P.VISOR[1] + (170,))
    img = add(img, glow.filter(ImageFilter.GaussianBlur(2)), 0.9)

    if g >= 40:
        blit_text(img, 10, 212, "OKANAGAN LAKE, B.C.", P.ARMOUR[2], 1,
                  shadow=P.BLACK)
    if g >= 58:
        blit_text(img, 10, 224, "NOBODY SAW HER LAND", P.BONE[2], 1,
                  shadow=P.BLACK)

    if f >= T_LAND - 8:
        img = fade(img, max(0.0, (T_LAND - 1 - f) / 7))
    return img


# ── scene 6 · her face ────────────────────────────────────────────────────
def scene_face(f):
    """The push-in.  Drawn from primitives because it scales across its own
    duration, and a sprite blown up would be the only thing in the sequence
    with pixels a different size from everything else.

    The beat this replaces was a push-in on an armoured visor.  It is a face
    now, and she blinks and then smiles, because the story turned out to be
    about somebody arriving rather than somebody hunting."""
    k = f / T_FACE
    z = 1.0 + 0.18 * k
    cx, cy = 160, int(120 + 8 * k)

    img = new_frame()
    vgrad(img, 0, H, [(0.0, (0x0a, 0x08, 0x18)), (0.55, (0x1a, 0x12, 0x28)),
                      (1.0, (0x07, 0x06, 0x10))])

    embers = layer()
    ed = ImageDraw.Draw(embers)
    for i in range(26):
        ex = (i * 53 + f) % W
        ey = H - ((i * 37 + f * 2) % (H + 40)) + 20
        ed.point((ex, ey), fill=P.ARMOUR[1] + (150,))
    img = add(img, embers.filter(ImageFilter.GaussianBlur(1)), 0.7)
    d = ImageDraw.Draw(img)

    def s(v):
        return int(v * z)

    # ── hair behind ───────────────────────────────────────────────────────
    # Two earlier passes failed here in ways worth naming: flat quads pitched
    # over an oval read as a tent, and a deep zigzag fringe over a long jaw
    # read as a muzzle.  The fix is ordinary head geometry — a cranium with a
    # SHORT jaw, a hair mass only a little larger than it, and a shallow
    # fringe.  A specular band across the crown is what says "anime hair".
    sway = int(s(4) * math.sin(f / 9.0))
    d.ellipse([cx - s(104) + sway, cy - s(122), cx + s(104) + sway,
               cy + s(190)], fill=P.HAIR[3])
    d.ellipse([cx - s(96) + sway, cy - s(116), cx + s(96) + sway, cy + s(180)],
              fill=P.HAIR[2])
    d.arc([cx - s(92), cy - s(118), cx + s(92), cy - s(4)], 200, 340,
          fill=P.HAIR[0], width=max(4, s(11)))
    d.arc([cx - s(84), cy - s(110), cx + s(84), cy - s(14)], 210, 330,
          fill=P.HAIR[1], width=max(2, s(5)))
    # The pink lock has to sit INSIDE the hair silhouette.  Run out to the
    # ellipse edge it floats free of her head as a stripe on the background.
    d.polygon([(cx - s(86), cy - s(66)), (cx - s(62), cy - s(76)),
               (cx - s(46) + sway, cy + s(190)),
               (cx - s(78) + sway, cy + s(190))], fill=P.PINK[2])
    d.polygon([(cx - s(86), cy - s(66)), (cx - s(74), cy - s(71)),
               (cx - s(62) + sway, cy + s(190)),
               (cx - s(78) + sway, cy + s(190))], fill=P.PINK[1])

    # ── face: cranium plus a short jaw ────────────────────────────────────
    def head(shrink, colour):
        d.ellipse([cx - s(74) + shrink, cy - s(98) + shrink,
                   cx + s(74) - shrink, cy + s(52) - shrink], fill=colour)
        # Wider and shorter than the first attempt: tapering from +/-58 to
        # +/-26 over 56 units made a V, not a jaw.
        d.polygon([(cx - s(66) + shrink, cy + s(8)),
                   (cx + s(66) - shrink, cy + s(8)),
                   (cx + s(36) - shrink, cy + s(62)),
                   (cx - s(36) + shrink, cy + s(62))], fill=colour)
        d.ellipse([cx - s(38) + shrink, cy + s(40), cx + s(38) - shrink,
                   cy + s(72) - shrink], fill=colour)

    head(0, P.KEYLINE)
    head(max(1, s(3)), P.SKIN[1])

    # the shadow side, clipped to the head so it cannot spill onto the hair
    keep = Image.new("L", (W, H), 0)
    kd = ImageDraw.Draw(keep)
    kd.ellipse([cx - s(71), cy - s(95), cx + s(71), cy + s(49)], fill=255)
    kd.polygon([(cx - s(63), cy + s(8)), (cx + s(63), cy + s(8)),
                (cx + s(33), cy + s(60)), (cx - s(33), cy + s(60))], fill=255)
    kd.ellipse([cx - s(35), cy + s(40), cx + s(35), cy + s(69)], fill=255)
    side = Image.new("L", (W, H), 0)
    ImageDraw.Draw(side).ellipse([cx + s(18), cy - s(98), cx + s(150),
                                  cy + s(96)], fill=255)
    img.paste(new_frame(P.SKIN[2]), (0, 0), ImageChops.multiply(side, keep))
    d = ImageDraw.Draw(img)

    # ── eyes ──────────────────────────────────────────────────────────────
    blink = 56 <= f < 62
    ey = cy + s(4)
    for ex in (-32, 32):
        exx = cx + s(ex)
        if blink:
            d.line([(exx - s(22), ey), (exx + s(22), ey)],
                   fill=P.SKIN[4], width=max(2, s(4)))
            continue
        d.ellipse([exx - s(24), ey - s(22), exx + s(24), ey + s(22)],
                  fill=P.BONE[0])
        d.ellipse([exx - s(17), ey - s(18), exx + s(17), ey + s(20)],
                  fill=P.EYE[2])
        d.ellipse([exx - s(17), ey, exx + s(17), ey + s(20)], fill=P.EYE[1])
        d.ellipse([exx - s(8), ey - s(6), exx + s(8), ey + s(13)],
                  fill=P.EYE[4])
        d.ellipse([exx - s(13), ey - s(16), exx - s(4), ey - s(7)],
                  fill=P.BONE[0])
        d.ellipse([exx + s(5), ey + s(6), exx + s(10), ey + s(11)],
                  fill=P.BONE[0])
        d.arc([exx - s(27), ey - s(33), exx + s(27), ey + s(11)], 188, 352,
              fill=P.KEYLINE, width=max(2, s(5)))

    for bx in (-48, 48):
        blush = layer()
        ImageDraw.Draw(blush).ellipse(
            [cx + s(bx) - s(14), ey + s(24) - s(6),
             cx + s(bx) + s(14), ey + s(24) + s(6)], fill=P.PINK[1] + (80,))
        img = add(img, blush.filter(ImageFilter.GaussianBlur(3)), 0.6)
        d = ImageDraw.Draw(img)

    # ── mouth: a line that becomes a smile ────────────────────────────────
    if f < 84:
        d.line([(cx - s(9), cy + s(40)), (cx + s(9), cy + s(40))],
               fill=P.SKIN[4], width=max(1, s(2)))
    else:
        d.arc([cx - s(15), cy + s(30), cx + s(15), cy + s(48)], 20, 160,
              fill=P.PINK[3], width=max(2, s(3)))

    # ── fringe: shallow points, swaying ───────────────────────────────────
    pts = [(cx - s(96), cy - s(92))]
    for i in range(6):
        base = cx - s(96) + i * s(32)
        pts.append((base + s(16),
                    cy - s(58) + int(s(3) * math.sin(f / 7.0 + i))))
        pts.append((base + s(32), cy - s(70)))
    pts += [(cx + s(96), cy - s(92)), (cx + s(96), cy - s(126)),
            (cx - s(96), cy - s(126))]
    d.polygon(pts, fill=P.HAIR[2])
    d.polygon([(cx - s(94), cy - s(122)), (cx + s(2), cy - s(122)),
               (cx - s(22), cy - s(64)), (cx - s(56), cy - s(52)),
               (cx - s(80), cy - s(72))], fill=P.HAIR[1])

    # ── side locks, in front of the cheeks ────────────────────────────────
    for sgn in (-1, 1):
        d.polygon([(cx + sgn * s(96), cy - s(84)),
                   (cx + sgn * s(70), cy - s(60)),
                   (cx + sgn * s(64), cy + s(44)),
                   (cx + sgn * s(90), cy + s(18))],
                  fill=P.HAIR[2 if sgn < 0 else 3])

    # ── antennae ──────────────────────────────────────────────────────────
    for ax, tx in ((-26, -50), (26, 50)):
        d.line([(cx + s(ax), cy - s(112)), (cx + s(tx), cy - s(176))],
               fill=P.HAIR[3], width=max(2, s(3)))
        tip = layer()
        ImageDraw.Draw(tip).ellipse(
            [cx + s(tx) - s(7), cy - s(176) - s(7),
             cx + s(tx) + s(7), cy - s(176) + s(7)], fill=P.VISOR[1] + (220,))
        img = add(img, tip.filter(ImageFilter.GaussianBlur(3)))
        d = ImageDraw.Draw(img)

    # moonlight down the left edge of her face
    d.arc([cx - s(74), cy - s(98), cx + s(74), cy + s(52)], 150, 250,
          fill=P.BONE[1], width=2)

    if f < 8:
        img = fade(img, f / 8)
    if f >= T_FACE - 10:
        img = fade(img, max(0.0, (T_FACE - 1 - f) / 9))
    return img


# ── the display face ──────────────────────────────────────────────────────
LOGO_SCALE = 2
GLYPH_W = gzfont.LOGO_W * LOGO_SCALE
GLYPH_H = gzfont.LOGO_H * LOGO_SCALE
GAP = 3
SHEAR = 0.17


def _word(word, scale=LOGO_SCALE, orbit_last=False):
    """One word of the display face, cut from chrome: ten ramp stops read top
    to bottom, a specular rim, a keyline and a cast shadow, and a lean.

    `orbit_last` turns the final O into a little world with a ring round it.
    That position used to hold a reticle.  A planet is the same shape, carries
    the same weight in the lockup, and does not point at anybody."""
    gw, gh = gzfont.LOGO_W * scale, gzfont.LOGO_H * scale
    n = len(word)
    lean = int(gh * SHEAR)
    pad = 26 if orbit_last else 10
    w = n * gw + (n - 1) * GAP + pad + lean
    h = gh + 10 + (12 if orbit_last else 0)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    oy = 6 if orbit_last else 0

    cells = [(i * (gw + GAP), gzfont.LOGO[ch]) for i, ch in enumerate(word)]

    def stamp(dx, dy, colour_of):
        for ox, glyph in cells:
            for gy, row in enumerate(glyph):
                for gx, on in enumerate(row):
                    if not on:
                        continue
                    for sy in range(scale):
                        for sx in range(scale):
                            yy = gy * scale + sy
                            x = ox + gx * scale + sx + dx + int((gh - yy) * SHEAR)
                            y = yy + dy
                            if 0 <= x < w and 0 <= y < h:
                                px[x, y] = colour_of(gy) + (255,)

    def chrome(gy):
        t = gy / (gzfont.LOGO_H - 1)
        return P.CHROME[min(len(P.CHROME) - 1, int(t * len(P.CHROME)))]

    stamp(6, 6 + oy, lambda gy: (0, 0, 0))
    for ox_, oy_ in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1),
                     (2, 0), (0, 2)):
        stamp(2 + ox_, 2 + oy_ + oy, lambda gy: P.KEYLINE)
    stamp(1, 1 + oy, lambda gy: P.CHROME[0])
    stamp(2, 2 + oy, chrome)

    if orbit_last:
        ox = cells[-1][0] + 2 + int(gh * SHEAR / 2)
        cx = ox + gw // 2
        cy = 2 + oy + gh // 2
        d = ImageDraw.Draw(img)
        for rx, ry, col in ((gw // 2 + 12, 9, P.KEYLINE),
                            (gw // 2 + 11, 8, P.CHROME[6]),
                            (gw // 2 + 10, 7, P.CHROME[3])):
            d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=col,
                      width=2)
        d.ellipse([cx + gw // 2 + 4, cy - 4, cx + gw // 2 + 11, cy + 3],
                  fill=P.CHROME[1])
    return img


def _shine(img, phase):
    out = img.copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        band = phase - y
        for x in range(max(0, band - 7), min(w, band + 7)):
            r, g, b, a = px[x, y]
            if a and (r, g, b) != P.KEYLINE and (r, g, b) != (0, 0, 0):
                px[x, y] = (P.CHROME[0] if abs(x - band) < 3
                            else P.CHROME[1]) + (255,)
    return out


# ── scene 7 · the name card ───────────────────────────────────────────────
NAME_SASHA = None
NAME_ZERO = None

SPEC = [("ISSUE", "ONE (1) BAGUETTE"),
        ("BRIEF", "ASK WHAT PEOPLE ARE UP TO"),
        ("FINDINGS", "THERE ARE SOME BAD FOLK"),
        ("POSTING", "THE OKANAGAN, INDEFINITE")]


def scene_name(f):
    img = new_frame()
    vgrad(img, 0, H, [(0.0, (0x0b, 0x09, 0x14)), (0.5, (0x1c, 0x14, 0x22)),
                      (1.0, (0x08, 0x07, 0x0e))])

    bloom = layer()
    ImageDraw.Draw(bloom).ellipse([40, 40, 280, 200],
                                  fill=(0x2a, 0x3a, 0x5a) + (90,))
    img = add(img, bloom.filter(ImageFilter.GaussianBlur(26)), 0.9)
    d = ImageDraw.Draw(img)

    sw, sh = NAME_SASHA.size
    zw, zh = NAME_ZERO.size
    total = sw + 10 + zw
    nx = (W - total) // 2
    if f >= 4:
        img.paste(NAME_SASHA, (nx, 18), NAME_SASHA)
    if f >= 12:
        img.paste(NAME_ZERO, (nx + sw + 10, 18), NAME_ZERO)
    if 26 <= f < 70:
        ph = (f - 26) * 8 - 30
        a = _shine(NAME_SASHA, ph)
        b = _shine(NAME_ZERO, ph - 40)
        img.paste(a, (nx, 18), a)
        img.paste(b, (nx + sw + 10, 18), b)

    if f >= 20:
        d.rectangle([nx, 46, nx + total, 47], fill=P.CHROME[5])
        blit_centre(img, 52, "FIELD CORRESPONDENT · NON-TERRESTRIAL",
                    P.BONE[2])

    sasha, _ = gzart.load()
    if f >= 26:
        img.paste(sasha, ((W - gzart.W) // 2, 70), sasha)
        glow = layer()
        gd = ImageDraw.Draw(glow)
        bx = (W - gzart.W) // 2
        gd.ellipse([bx + 15, 89, bx + 20, 94], fill=P.VISOR[1] + (150,))
        for ax in (12, 22):
            gd.ellipse([bx + ax - 2, 69, bx + ax + 2, 73],
                       fill=P.VISOR[1] + (170,))
        img = add(img, glow.filter(ImageFilter.GaussianBlur(2)), 0.9)
        d = ImageDraw.Draw(img)

    for i, (k, v) in enumerate(SPEC):
        if f < 42 + i * 12:
            continue
        y = 140 + i * 13
        blit_text(img, 22, y, k, P.BONE[3])
        blit_text(img, 110, y, v, P.BONE[1])
        d.rectangle([22, y + 9, 300, y + 9], fill=(0x2c, 0x26, 0x36))

    if f >= 100:
        blit_centre(img, 200, "▸ SHE IS HERE TO HELP", P.ARMOUR[2])
    triband(img, 0, 235, W, 3)

    if f < 8:
        img = fade(img, f / 8)
    if f >= T_NAME - 12:
        img = fade(img, max(0.0, (T_NAME - 1 - f) / 11))
    return img


# ── scene 8 · the logo ────────────────────────────────────────────────────
LOGO_TOP = None
LOGO_BOT = None


def scene_slam(f):
    img = new_frame(P.INK)
    vgrad(img, 0, H, [(0.0, (0x0d, 0x0b, 0x14)), (0.45, (0x24, 0x1a, 0x18)),
                      (1.0, (0x0a, 0x08, 0x0c))])
    d = ImageDraw.Draw(img)

    if f < 4:
        return new_frame(P.WHITE)
    if f < 8:
        return new_frame(P.BONE[1])

    tw, th = LOGO_TOP.size
    bw, bh = LOGO_BOT.size
    tx, bx = (W - tw) // 2, (W - bw) // 2
    ty_end, by_end = 44, 44 + GLYPH_H + 6

    bloom = layer()
    ImageDraw.Draw(bloom).ellipse([W // 2 - 150, 56, W // 2 + 150, 156],
                                  fill=(0x60, 0x30, 0x08) + (110,))
    img = add(img, bloom.filter(ImageFilter.GaussianBlur(22)), 0.9)
    d = ImageDraw.Draw(img)

    sy = 0
    if f < 22:
        ty = ty_end - int((22 - f) ** 2 * 1.1)
    else:
        ty = ty_end
        if f < 30:
            sy = (30 - f) // 2 * (1 if f % 2 else -1)
    if f >= 10:
        img.paste(LOGO_TOP, (tx, ty + sy), LOGO_TOP)

    if f >= 28:
        bxx = bx + int((48 - f) ** 2 * 0.9) if f < 48 else bx
        img.paste(LOGO_BOT, (bxx, by_end), LOGO_BOT)

    if 48 <= f < 60:
        amp = (60 - f) // 3
        if amp:
            off = amp if f % 2 else -amp
            shifted = new_frame(P.BLACK)
            shifted.paste(img, (off, 0))
            img = shifted
        spark = layer()
        sd = ImageDraw.Draw(spark)
        for i in range(20):
            dx = (i * 23 + f * 5) % W
            dy = by_end + GLYPH_H + (i % 5) - (f - 48) * 2
            sd.point((dx, dy), fill=P.CHROME[1] + (200,))
        img = add(img, spark)
        d = ImageDraw.Draw(img)

    cyc = f % 210
    if 84 <= cyc < 140 and f >= 84:
        ph = (cyc - 84) * 7 - 40
        top = _shine(LOGO_TOP, ph)
        bot = _shine(LOGO_BOT, ph - 30)
        img.paste(top, (tx, ty_end), top)
        img.paste(bot, (bx, by_end), bot)

    if f >= 132:
        d.rectangle([48, 150, 271, 151], fill=(0x2e, 0x24, 0x1c))
        mx = ((f - 132) * 2) % 318 - 47
        x0, x1 = max(48, mx), min(271, mx + 47)
        if x1 >= x0:
            d.rectangle([x0, 150, x1, 151], fill=P.ARMOUR[2])

    if f >= 140:
        blit_centre(img, 164, "DESIG. RL-Z0-GND · LANDING SITE", P.BONE[2])
    if f >= 154:
        blit_centre(img, 178, "▸ THE DAY, FROM THE POINT IT HAPPENED",
                    P.ARMOUR[2])
    return img


def scene_attract(f):
    img = scene_slam(T_SLAM - 1 + f)
    if (f // 22) % 2 == 0:
        blit_centre(img, 198, "PRESS START", P.BONE[1])
    blit_centre(img, 212, "NIGHTLY 19:00 · ENCORE 22:00", P.ARMOUR[3])
    blit_centre(img, 224, "© 2026 RIPOSTE LABORATORIES INC.", P.STEEL[2])
    triband(img, 0, 235, W, 3)
    if f >= T_ATTRACT - 26:
        img = fade(img, max(0.0, (T_ATTRACT - 1 - f) / 25))
    return img


# ── driver ────────────────────────────────────────────────────────────────
def render(i):
    if i < C_CRAWL:
        return scene_sting(i - C_STING)
    if i < C_SPACE:
        return scene_crawl(i - C_CRAWL)
    if i < C_WORM:
        return scene_space(i - C_SPACE)
    if i < C_LAND:
        return scene_worm(i - C_WORM)
    if i < C_FACE:
        return scene_land(i - C_LAND)
    if i < C_NAME:
        return scene_face(i - C_FACE)
    if i < C_SLAM:
        return scene_name(i - C_NAME)
    if i < C_ATTRACT:
        return scene_slam(i - C_SLAM)
    return scene_attract(i - C_ATTRACT)


def main():
    global CRAWL, NEBULA, LAND, LOGO_TOP, LOGO_BOT, NAME_SASHA, NAME_ZERO
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    gzart.load()
    CRAWL = _crawl_block()
    NEBULA = _nebula()
    LAND = _land_plate()
    LOGO_TOP = _word("GROUND")
    LOGO_BOT = _word("ZERO", orbit_last=True)
    NAME_SASHA = _word("SASHA", scale=1)
    NAME_ZERO = _word("ZERO", scale=1)

    if "--stills" in sys.argv:
        marks = [20, 60, 100, 200, 400, 500, 560, 600, 640, 700, 740, 760,
                 790, 820, 860, 900, 940, 980, 1010, 1040, 1080, 1120, 1160,
                 1200, 1240, 1280, 1320, 1360, 1400, 1450, 1500, 1560, 1600,
                 1660, 1700, 1760]
        for i in marks:
            render(i).resize((640, 480), Image.NEAREST).save(
                os.path.join(outdir, f"still-{i:04d}.png"))
        print("stills written")
        return

    for i in range(TOTAL):
        render(i).save(os.path.join(outdir, f"f{i:05d}.png"))
        if i % 200 == 0:
            print(f"  {i}/{TOTAL}", flush=True)
    print(f"rendered {TOTAL} frames ({TOTAL / FPS:.1f}s) to {outdir}")


if __name__ == "__main__":
    main()
