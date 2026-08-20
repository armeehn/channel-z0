#!/usr/bin/env python3
"""Render the GROUND ZERO opening title sequence as PNG frames.

A parody of the Mega Man X / X2 / X3 openings: publisher sting, a long prologue
crawl, a lit hero shot, a push-in on the visor, the logo arriving hard, and an
attract screen.

**This is the 16-bit pass.**  The first version of this file was 8-bit — a
fixed sixteen-colour palette with ordered dither wherever two of them met.  A
16-bit frame is a different machine and the differences are specific, not
vague:

  * per-scanline gradients (what HDMA is for) instead of dithered bands;
  * colour math — layers that add or blend rather than replace, which is where
    the rain, the cloud, the moon glow, the lightning and the logo glow come
    from;
  * shaded sprites with a single light direction, instead of silhouettes;
  * atmospheric perspective: three depth planes that differ in *contrast*, not
    just in position.

The canvas stays 320x240 — 4:3 with square pixels, doubling exactly to the
640x480 the station's other cards are authored at, which pillarboxes into the
channel's 854x480 precisely inside the on-air rails.  What changed is what is
drawn on it, not how big it is.

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
T_STING = 135
T_CRAWL = 660
T_HERO = 450
T_SLAM = 315
T_ATTRACT = 240
TOTAL = T_STING + T_CRAWL + T_HERO + T_SLAM + T_ATTRACT      # 1800 = 60.0 s

C_STING = 0
C_CRAWL = C_STING + T_STING
C_HERO = C_CRAWL + T_CRAWL
C_SLAM = C_HERO + T_HERO
C_ATTRACT = C_SLAM + T_SLAM

T_WIDE = 300          # frames of the wide shot before the cut to the visor

PROLOGUE = [
    "IN THE YEAR 20XX,",
    "THE LOCAL STATIONS",
    "WENT DARK.",
    "",
    "THE TOWERS WERE SOLD.",
    "THE NEWSROOMS WERE",
    "CONSOLIDATED INTO ONE",
    "FEED, TRANSMITTED",
    "FROM SOMEWHERE ELSE.",
    "",
    "FOR A WHILE,",
    "NOBODY NOTICED.",
    "",
    "THEN THE FEED BEGAN",
    "REPORTING WEATHER",
    "THAT WAS NOT",
    "HAPPENING HERE.",
    "",
    "FROM A SERVICE CLOSET",
    "IN KELOWNA, B.C.,",
    "ONE TRANSMITTER",
    "CAME BACK ON.",
    "",
    "ITS OPERATORS CALL THE",
    "PLACE WHERE IT HAPPENED",
    "GROUND ZERO.",
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
    """Additive colour math — the SNES main/sub screen add.  Used for every
    light source: moon glow, the core, lightning, the logo, the visor flare."""
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
    """Smooth, not quantised.  A 16-bit fade is colour math against black, and
    it has as many steps as it likes."""
    if k >= 0.999:
        return img
    if k <= 0:
        return new_frame(P.BLACK)
    return Image.blend(new_frame(P.BLACK), img, k)


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
        # The flash is colour math against the frame, so it ramps instead of
        # being one white frame with hard edges either side of it.
        k = 1.0 - (f - 44) / 6.0
        blit_text(img, x0, y, WORDMARK, P.BONE[1])
        glow = layer()
        ImageDraw.Draw(glow).rectangle([0, 0, W, H], fill=P.WHITE + (255,))
        return add(img, glow, k)

    if f >= 50:
        blit_text(img, x0, y, WORDMARK, P.BONE[1])
        triband(img, x0, y + 12, text_w(WORDMARK), 3)
        # a lens streak along the band, decaying
        if f < 84:
            k = (84 - f) / 34.0
            st = layer()
            ImageDraw.Draw(st).line([(x0 - 20, y + 13), (x0 + text_w(WORDMARK) + 20,
                                                         y + 13)],
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
        colour = P.ARMOUR[2] if last else P.BONE[1]
        x = (W - text_w(ln)) // 2
        blit_text(img, x, i * CRAWL_PITCH, ln, colour, 1, shadow=(0x14, 0x12, 0x22))
        if last:
            ImageDraw.Draw(img).rectangle(
                [x, i * CRAWL_PITCH + 10, x + text_w(ln) - 1,
                 i * CRAWL_PITCH + 11], fill=P.ARMOUR[3])
    return img


CRAWL = None
NEBULA = None
STARS = [((i * 61) % W, (i * 37) % 300, 1 + i % 3) for i in range(150)]


def _nebula():
    """A deep-field wash behind the crawl.  Three overlapping soft clouds,
    blurred — the one place a blur is right, because it is standing in for the
    sub-screen at half intensity."""
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, [(0.0, (0x05, 0x04, 0x0e)), (0.55, (0x0d, 0x08, 0x1c)),
                      (1.0, (0x04, 0x03, 0x0a))])
    lay = layer()
    d = ImageDraw.Draw(lay)
    for cx, cy, r, col in ((70, 90, 62, (0x2a, 0x10, 0x3a)),
                           (240, 150, 78, (0x10, 0x1e, 0x3e)),
                           (170, 40, 54, (0x33, 0x16, 0x22))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
    lay = lay.filter(ImageFilter.GaussianBlur(18))
    return add(img, lay, 0.55)


def scene_crawl(f):
    img = NEBULA.copy()
    d = ImageDraw.Draw(img)

    # Three star planes at different speeds and brightnesses.  Parallax is the
    # cheapest 16-bit effect there is and the crawl is where it shows.
    for x, y0, plane in STARS:
        speed = (1, 2, 3)[plane - 1]
        y = (y0 - f * speed // 2) % 300 - 30
        if 0 <= y < H:
            d.point((x, y), fill=P.ramp_at(P.BONE, (3 - plane) * 0.28))

    # The card's reticle, holding station off the right edge, breathing.
    glow = layer()
    gd = ImageDraw.Draw(glow)
    cx, cy = 318, 118
    for r in (64, 47, 30):
        gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   outline=P.ARMOUR[3] + (110,))
    pulse = 12 + int(7 * math.sin(f / 14.0))
    gd.ellipse([cx - pulse, cy - pulse, cx + pulse, cy + pulse],
               outline=P.ARMOUR[2] + (200,))
    gd.line([(cx - 74, cy), (cx, cy)], fill=P.ARMOUR[3] + (90,))
    img = add(img, glow, 0.85)

    scroll = min(f * CRAWL_SPEED, (T_CRAWL - CRAWL_HOLD) * CRAWL_SPEED)
    img.paste(CRAWL, (0, H - scroll), CRAWL)

    if f < 14:
        img = fade(img, f / 14)
    if f >= T_CRAWL - 12:
        img = fade(img, max(0.0, (T_CRAWL - 1 - f) / 11))
    return img


# ── scene 3 · the rooftop ─────────────────────────────────────────────────
# Two ranges, and the far one is deliberately lower-contrast than the near one.
# Atmospheric perspective is what separates depth planes when they are all the
# same hue; position alone reads as one flat cut-out.
RIDGE_FAR = [(0, 138), (36, 128), (72, 134), (108, 120), (144, 132),
             (180, 116), (216, 126), (252, 118), (288, 130), (320, 124)]
RIDGE_NEAR = [(0, 150), (24, 143), (48, 148), (72, 140), (96, 150), (120, 154),
              (148, 152), (172, 142), (196, 131), (220, 138), (244, 134),
              (268, 144), (296, 136), (320, 146)]

RAIN = [((i * 53) % W, (i * 29) % 260, 4 + (i % 3) * 3) for i in range(80)]
RAIN_FG = [((i * 91) % W, (i * 67) % 260, 9 + (i % 2) * 4) for i in range(20)]

HERO_X, HERO_FOOT = 148, 172
MOON_X, MOON_Y, MOON_R = 96, 108, 27


def _ridge(d, pts, floor, colour):
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d.polygon([(x0, y0), (x1, y1), (x1, floor), (x0, floor)], fill=colour)


def _sky():
    """The static plate: sky, moon, two ranges, the lake, the roof."""
    img = new_frame()
    vgrad(img, 0, 152, P.SKY_STOPS)
    d = ImageDraw.Draw(img)

    for i in range(70):
        x, y = (i * 71) % W, (i * 43) % 96
        d.point((x, y), fill=P.ramp_at(P.BONE, 0.35 + (i % 4) * 0.16))

    # The moon: a shaded disc, then an additive halo.  The halo is why the
    # clouds in front of it read as translucent later.
    md = ImageDraw.Draw(img)
    for r in range(MOON_R, 0, -1):
        t = 1.0 - r / MOON_R
        md.ellipse([MOON_X - r, MOON_Y - r, MOON_X + r, MOON_Y + r],
                   fill=P.lerp((0xd8, 0xd2, 0xc4), (0xff, 0xfb, 0xef), t * 0.8))
    for cx, cy, r in ((MOON_X - 10, MOON_Y - 7, 5), (MOON_X + 8, MOON_Y + 5, 7),
                      (MOON_X + 2, MOON_Y - 15, 3)):
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0xbe, 0xb7, 0xa8))

    halo = layer()
    hd = ImageDraw.Draw(halo)
    for r, a in ((60, 26), (46, 34), (36, 46), (30, 70)):
        hd.ellipse([MOON_X - r, MOON_Y - r, MOON_X + r, MOON_Y + r],
                   fill=(0x9a, 0x92, 0xb8) + (a,))
    img = add(img, halo.filter(ImageFilter.GaussianBlur(6)), 0.9)

    d = ImageDraw.Draw(img)
    _ridge(d, RIDGE_FAR, 156, (0x33, 0x24, 0x4c))       # far range, hazy
    _ridge(d, RIDGE_NEAR, 160, (0x1c, 0x14, 0x2c))      # near range, darker
    d.rectangle([0, 152, W, 160], fill=(0x1c, 0x14, 0x2c))

    vgrad(img, 158, 174, P.LAKE_STOPS)                   # the lake
    d = ImageDraw.Draw(img)
    shim = layer()
    sd = ImageDraw.Draw(shim)
    for y in range(159, 174):
        wdt = 3 + (y - 159)
        sd.line([(MOON_X - wdt, y), (MOON_X + wdt, y)],
                fill=(0xd8, 0xd2, 0xc4) + (54 - (y - 159) * 3,))
    for y in range(160, 174, 3):
        sd.line([(0, y), (W, y)], fill=(0x8a, 0x82, 0xa8, 40))
    img = add(img, shim, 0.8)

    d = ImageDraw.Draw(img)
    d.rectangle([0, 160, W, 161], fill=(0x0d, 0x0a, 0x16))   # bridge deck
    for x in range(6, W, 24):
        d.rectangle([x, 161, x + 1, 166], fill=(0x0d, 0x0a, 0x16))
    d.polygon([(198, 160), (206, 147), (214, 160)], fill=(0x0d, 0x0a, 0x16))

    # Foreground: roof and parapet, the darkest and highest-contrast plane.
    d.rectangle([0, 174, W, H], fill=(0x05, 0x04, 0x08))
    d.rectangle([0, 174, W, 175], fill=P.STEEL[3])
    d.rectangle([116, 162, 206, 175], fill=(0x05, 0x04, 0x08))
    d.rectangle([116, 162, 206, 162], fill=P.STEEL[3])
    for x in range(0, W, 12):
        d.point((x + (x // 12) % 4, 178), fill=(0x1a, 0x17, 0x14))

    mx = 268                                                  # the mast
    d.rectangle([mx, 74, mx + 5, 174], fill=(0x05, 0x04, 0x08))
    for y in range(78, 174, 8):
        d.line([(mx, y), (mx + 5, y + 8)], fill=(0x18, 0x15, 0x22))
        d.line([(mx + 5, y), (mx, y + 8)], fill=(0x18, 0x15, 0x22))
    d.rectangle([mx - 3, 74, mx + 8, 75], fill=(0x18, 0x15, 0x22))
    return img


SKY = None


def _rain_layer(frames, f, length, dx, alpha):
    lay = layer()
    d = ImageDraw.Draw(lay)
    for i, (x, y0, sp) in enumerate(frames):
        y = (y0 + f * sp) % 300 - 30
        if -length < y < H:
            d.line([(x, y), (x - dx, y + length)],
                   fill=P.BONE[2 if i % 4 else 1] + (alpha,))
    return lay


def _clouds(f):
    """Three planes, each translucent so the moon shows through them."""
    lay = layer()
    d = ImageDraw.Draw(lay)
    for speed, col, y0, hgt, n, a in ((3, (0x6a, 0x48, 0x74), 70, 9, 6, 150),
                                      (2, (0x3e, 0x2a, 0x50), 86, 12, 7, 175),
                                      (1, (0x24, 0x18, 0x32), 104, 14, 6, 200)):
        for i in range(n):
            cw = 54 + (i * 23) % 62
            x = ((i * 61) + f * speed // 2) % (W + 140) - 70
            base = y0 + (i % 3) * 5
            for seg in range(0, cw, 6):
                lump = (i + seg) % 4
                d.rectangle([x + seg, base + lump, x + seg + 5, base + hgt],
                            fill=col + (a,))
    return lay


def _wide(f):
    img = SKY.copy()

    strike = (118 <= f < 132) or (238 <= f < 250)
    # A strike is an additive ramp, not a white frame: bright, then two decays.
    lk = 0.0
    if strike:
        n = (f - 118) if f < 132 else (f - 238)
        lk = (1.0, 0.75, 0.30, 0.85, 0.55, 0.28, 0.14, 0.07,
              0.03, 0.0, 0.0, 0.0, 0.0, 0.0)[min(n, 13)]

    img = over(img, _clouds(f))
    img = over(img, _rain_layer(RAIN, f, 7, 2, 120))

    hero, hero_lit = gzart.load()
    sprite = hero_lit if lk > 0.5 else hero
    img.paste(sprite, (HERO_X, HERO_FOOT - gzart.H), sprite)

    # The core, and the visor, are light sources: they go through colour math
    # so they bloom against the dark plate instead of just being teal pixels.
    glow = layer()
    gd = ImageDraw.Draw(glow)
    top = HERO_FOOT - gzart.H
    gd.ellipse([HERO_X + 15, top + 21, HERO_X + 21, top + 27],
               fill=P.VISOR[1] + (160,))
    gd.polygon([(HERO_X + 12, top + 7), (HERO_X + 24, top + 7),
                (HERO_X + 23, top + 14), (HERO_X + 13, top + 14)],
               fill=P.VISOR[1] + (110,))
    img = add(img, glow.filter(ImageFilter.GaussianBlur(2)), 0.9)

    d = ImageDraw.Draw(img)
    if (f // 20) % 2 == 0:
        beacon = layer()
        ImageDraw.Draw(beacon).ellipse([266, 68, 274, 76],
                                       fill=P.PINK[2] + (200,))
        img = add(img, beacon.filter(ImageFilter.GaussianBlur(2)))

    img = over(img, _rain_layer(RAIN_FG, f, 13, 5, 165))

    if lk > 0:
        bolt = layer()
        bd = ImageDraw.Draw(bolt)
        bd.rectangle([0, 0, W, 152], fill=(0x6a, 0x5a, 0x8a) + (int(120 * lk),))
        bd.line([(232, 0), (224, 42), (242, 46), (226, 100)],
                fill=P.WHITE + (int(255 * lk),), width=2)
        img = add(img, bolt, min(1.0, lk))

    if f >= 190:
        blit_text(img, 10, 214, "KELOWNA, B.C.", P.ARMOUR[2], 1, shadow=P.BLACK)
        blit_text(img, 10, 226, "TRANSMITTER RL-Z0 · 19:00", P.BONE[2], 1,
                  shadow=P.BLACK)
    return img


def _helmet(f):
    """The push-in on the visor.

    Drawn from primitives because it scales across its own duration, and a
    sprite blown up would be the only thing in the sequence with pixels a
    different size from everything else.  The head is cropped by the frame on
    purpose: a close-up that fits inside the safe area is a portrait.
    """
    dur = T_HERO - T_WIDE
    img = new_frame((0x06, 0x05, 0x0c))
    vgrad(img, 0, H, [(0.0, (0x0a, 0x08, 0x14)), (0.6, (0x14, 0x0e, 0x22)),
                      (1.0, (0x06, 0x05, 0x0c))])
    d = ImageDraw.Draw(img)

    k = f / max(1, dur)
    z = 1.0 + 0.20 * k
    cx, cy = 160, int(126 + 10 * k)
    strike = 96 <= f < 106
    flare = f >= 126

    def s(v):
        return int(v * z)

    img = over(img, _rain_layer(RAIN, f * 2, 15, 5, 70))

    lit = P.BONE[0] if strike else P.ARMOUR[1]
    dim = P.BONE[3] if strike else P.ARMOUR[3]

    dome = [cx - s(104), cy - s(152), cx + s(104), cy + s(64)]
    chin = [(cx - s(74), cy + s(28)), (cx + s(74), cy + s(28)),
            (cx + s(40), cy + s(104)), (cx - s(40), cy + s(104))]
    d.ellipse(dome, fill=P.KEYLINE)
    d.polygon(chin, fill=P.KEYLINE)

    # Radial shading on the dome: concentric fills from the light, off frame
    # left.  Sixty steps, which no 8-bit palette could have held.
    inner = [dome[0] + s(7), dome[1] + s(7), dome[2] - s(7), dome[3] - s(7)]
    lx, ly = cx - s(70), cy - s(88)
    steps = 46
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(s(230) * t)
        d.ellipse([lx - r, ly - r, lx + r, ly + r],
                  fill=P.ramp_at(P.ARMOUR, min(1.0, 0.20 + t * 1.05)))
    keep = Image.new("L", (W, H), 0)
    ImageDraw.Draw(keep).ellipse(inner, fill=255)
    shaded = img.copy()
    img = new_frame((0x06, 0x05, 0x0c))
    vgrad(img, 0, H, [(0.0, (0x0a, 0x08, 0x14)), (0.6, (0x14, 0x0e, 0x22)),
                      (1.0, (0x06, 0x05, 0x0c))])
    img = over(img, _rain_layer(RAIN, f * 2, 15, 5, 70))
    d = ImageDraw.Draw(img)
    d.ellipse(dome, fill=P.KEYLINE)
    d.polygon(chin, fill=P.KEYLINE)
    img.paste(shaded, (0, 0), keep)
    d = ImageDraw.Draw(img)

    d.polygon([(cx - s(66), cy + s(30)), (cx + s(66), cy + s(30)),
               (cx + s(35), cy + s(96)), (cx - s(35), cy + s(96))],
              fill=P.STEEL[3])
    d.polygon([(cx - s(66), cy + s(30)), (cx - s(58), cy + s(30)),
               (cx - s(32), cy + s(96)), (cx - s(35), cy + s(96))],
              fill=P.STEEL[1])
    for i, yy in enumerate(range(cy + s(52), cy + s(92), s(12))):
        hw = s(30) - i * s(6)
        d.rectangle([cx - hw, yy, cx + hw, yy + s(4)], fill=P.KEYLINE)

    for side in (-1, 1):                       # ear pods
        px_, py_ = cx + side * s(97), cy + s(6)
        for rr, col in ((s(32), P.KEYLINE), (s(27), P.ARMOUR[3]),
                        (s(19), P.SUIT[4]), (s(8), P.ARMOUR[1])):
            d.ellipse([px_ - rr, py_ - rr, px_ + rr, py_ + rr], fill=col)

    d.polygon([(cx - s(92), cy - s(44)), (cx + s(92), cy - s(44)),
               (cx + s(88), cy - s(24)), (cx - s(88), cy - s(24))],
              fill=P.ARMOUR[3])
    d.polygon([(cx - s(92), cy - s(44)), (cx + s(92), cy - s(44)),
               (cx + s(90), cy - s(38)), (cx - s(90), cy - s(38))],
              fill=P.ARMOUR[1])
    for rr in (s(26), s(15)):
        d.ellipse([cx - rr, cy - s(76) - rr, cx + rr, cy - s(76) + rr],
                  outline=dim)
    d.line([(cx - s(40), cy - s(76)), (cx + s(40), cy - s(76))], fill=dim)
    d.line([(cx, cy - s(110)), (cx, cy - s(50))], fill=dim)

    outer = [(cx - s(94), cy - s(20)), (cx + s(94), cy - s(20)),
             (cx + s(74), cy + s(26)), (cx - s(74), cy + s(26))]
    inner_v = [(cx - s(86), cy - s(14)), (cx + s(86), cy - s(14)),
               (cx + s(69), cy + s(19)), (cx - s(69), cy + s(19))]
    d.polygon(outer, fill=P.KEYLINE)

    clip = Image.new("L", (W, H), 0)
    ImageDraw.Draw(clip).polygon(inner_v, fill=255)

    if flare:
        g = (f - 126) / max(1, dur - 126)
        d.polygon(inner_v, fill=P.WHITE if g > 0.5 else P.BONE[1])
        blow = layer()
        bd = ImageDraw.Draw(blow)
        rr = int(40 + 320 * g)
        bd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                   fill=P.BONE[1] + (int(200 * g),))
        img = add(img, blow.filter(ImageFilter.GaussianBlur(10)), min(1.0, g))
    else:
        glass = new_frame()
        vgrad(glass, cy - s(14), cy + s(19),
              [(0.0, P.VISOR[1]), (0.45, P.VISOR[2]), (1.0, P.VISOR[4])])
        img.paste(glass, (0, 0), clip)
        d = ImageDraw.Draw(img)
        scan = layer()
        sd = ImageDraw.Draw(scan)
        for yy in range(cy - s(14), cy + s(19), 3):
            sd.line([(cx - s(90), yy), (cx + s(90), yy)],
                    fill=(0x00, 0x30, 0x28, 120))
        gl = cx - s(86) + (f * 6) % (s(180) + 60) - 30
        sd.polygon([(gl, cy - s(14)), (gl + 18, cy - s(14)),
                    (gl + 7, cy + s(19)), (gl - 11, cy + s(19))],
                   fill=P.BONE[0] + (180,))
        scan = Image.composite(scan, layer(), clip)
        img = over(img, scan)
        d = ImageDraw.Draw(img)
    d.line([(cx - s(74), cy + s(26)), (cx + s(74), cy + s(26))], fill=lit)

    d.arc(dome, 186, 268, fill=lit)
    d.arc([dome[0] + 2, dome[1] + 2, dome[2] - 2, dome[3] - 2], 194, 262,
          fill=dim)

    img = over(img, _rain_layer(RAIN_FG, f * 2, 14, 6, 150))

    if strike:
        fl = layer()
        ImageDraw.Draw(fl).rectangle([0, 0, W, H],
                                     fill=P.BONE[1] + (int(70 * (1 - (f - 96) / 10)),))
        img = add(img, fl, 0.9)

    if f < 8:
        img = fade(img, f / 8)
    return img


def scene_hero(f):
    if f < T_WIDE:
        img = _wide(f)
        if f < 14:
            img = fade(img, f / 14)
        if f >= T_WIDE - 6:
            img = fade(img, max(0.0, (T_WIDE - 1 - f) / 5))
        return img
    return _helmet(f - T_WIDE)


# ── scene 4 · the logo ────────────────────────────────────────────────────
LOGO_SCALE = 2
GLYPH_W = gzfont.LOGO_W * LOGO_SCALE
GLYPH_H = gzfont.LOGO_H * LOGO_SCALE
GAP = 3
SHEAR = 0.17          # the letters lean; every one of these logos leans


def _logo_word(word, reticle_last=False):
    """One word of the display face, cut from chrome.

    Ten ramp stops read top to bottom — sky reflection, hot specular, body,
    core shadow, then the warm bounce a metal letter picks up off whatever it
    is standing on — plus a bevel, a keyline and a cast shadow.  The 8-bit
    version of this was three flat bands, which is the single biggest visible
    difference between the two passes.
    """
    n = len(word)
    lean = int(GLYPH_H * SHEAR)
    w = n * GLYPH_W + (n - 1) * GAP + 10 + lean
    h = GLYPH_H + 10
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()

    cells = []
    for i, ch in enumerate(word):
        ox = i * (GLYPH_W + GAP)
        cells.append((ox, None if (reticle_last and i == n - 1)
                      else gzfont.LOGO[ch]))

    def stamp(dx, dy, colour_of):
        for ox, glyph in cells:
            if glyph is None:
                continue
            for gy, row in enumerate(glyph):
                for gx, on in enumerate(row):
                    if not on:
                        continue
                    for sy in range(LOGO_SCALE):
                        for sx in range(LOGO_SCALE):
                            yy = gy * LOGO_SCALE + sy
                            x = ox + gx * LOGO_SCALE + sx + dx \
                                + int((GLYPH_H - yy) * SHEAR)
                            y = yy + dy
                            if 0 <= x < w and 0 <= y < h:
                                px[x, y] = colour_of(gy) + (255,)

    def chrome(gy):
        t = gy / (gzfont.LOGO_H - 1)
        return P.CHROME[min(len(P.CHROME) - 1, int(t * len(P.CHROME)))]

    stamp(6, 6, lambda gy: (0, 0, 0))                    # cast shadow
    for ox_, oy_ in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1),
                     (2, 0), (0, 2)):
        stamp(2 + ox_, 2 + oy_, lambda gy: P.KEYLINE)    # keyline
    # Bevel: stamp the face once more, offset up-left in pure specular, then
    # the real face on top of it.  Deriving the bevel from the composite alpha
    # instead put white dots all over the letters — that alpha includes the
    # keyline and the cast shadow, and the shear's stair-steps then read as
    # edges in the middle of a stroke.
    stamp(1, 1, lambda gy: P.CHROME[0])                  # specular rim
    stamp(2, 2, chrome)                                  # face

    if reticle_last:
        # The last O of ZERO is the programme's own mark, straight off the
        # COMING SOON card: the epicentre reticle, not a letter.
        ox = cells[-1][0] + 2 + int(GLYPH_H * SHEAR / 2)
        cx = ox + GLYPH_W // 2
        cy = 2 + GLYPH_H // 2
        d = ImageDraw.Draw(img)
        d.rectangle([cx - 22, cy - 2, cx + 22, cy + 2], fill=P.KEYLINE)
        d.rectangle([cx - 2, cy - 22, cx + 2, cy + 22], fill=P.KEYLINE)
        d.rectangle([cx - 21, cy - 1, cx + 21, cy + 1], fill=P.CHROME[5])
        d.rectangle([cx - 1, cy - 21, cx + 1, cy + 21], fill=P.CHROME[5])
        for r, c in ((18, P.KEYLINE), (17, P.CHROME[2]), (16, P.CHROME[4]),
                     (13, P.KEYLINE), (12, P.CHROME[5]), (8, P.CHROME[3]),
                     (7, P.CHROME[1])):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c)
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=P.CHROME[1])
    return img


LOGO_TOP = None
LOGO_BOT = None


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
    ty_end, by_end = 48, 48 + GLYPH_H + 6

    # An additive bloom behind the mark, so the chrome has something to sit in.
    bloom = layer()
    bd = ImageDraw.Draw(bloom)
    bd.ellipse([W // 2 - 150, 60, W // 2 + 150, 160],
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
    if f >= 12:
        img.paste(LOGO_TOP, (tx, ty + sy), LOGO_TOP)

    if f >= 30:
        bxx = bx + int((52 - f) ** 2 * 0.9) if f < 52 else bx
        img.paste(LOGO_BOT, (bxx, by_end), LOGO_BOT)

    if 52 <= f < 64:
        amp = (64 - f) // 3
        if amp:
            off = amp if f % 2 else -amp
            shifted = new_frame(P.BLACK)
            shifted.paste(img, (off, 0))
            img = shifted
        spark = layer()
        sd = ImageDraw.Draw(spark)
        for i in range(20):
            dx = (i * 23 + f * 5) % W
            dy = by_end + GLYPH_H + (i % 5) - (f - 52) * 2
            sd.point((dx, dy), fill=P.CHROME[1] + (200,))
        img = add(img, spark)
        d = ImageDraw.Draw(img)

    cyc = f % 260
    if 96 <= cyc < 152 and f >= 96:
        ph = (cyc - 96) * 7 - 40
        top = _shine(LOGO_TOP, ph)
        bot = _shine(LOGO_BOT, ph - 30)
        img.paste(top, (tx, ty_end), top)
        img.paste(bot, (bx, by_end), bot)

    if f >= 70:
        rcx = bx + (len("ZERO") - 1) * (GLYPH_W + GAP) + 2 \
            + int(GLYPH_H * SHEAR / 2) + GLYPH_W // 2
        rcy = by_end + 2 + GLYPH_H // 2
        ping = (f - 70) % 74
        if ping < 48:
            pl = layer()
            rr = 20 + ping
            ImageDraw.Draw(pl).ellipse([rcx - rr, rcy - rr, rcx + rr, rcy + rr],
                                       outline=P.ARMOUR[2] + (int(150 * (1 - ping / 48)),))
            img = add(img, pl)
            d = ImageDraw.Draw(img)

    if f >= 150:
        d.rectangle([48, 150, 271, 151], fill=(0x2e, 0x24, 0x1c))
        mx = ((f - 150) * 2) % 318 - 47
        x0, x1 = max(48, mx), min(271, mx + 47)
        if x1 >= x0:
            d.rectangle([x0, 150, x1, 151], fill=P.ARMOUR[2])

    if f >= 160:
        blit_centre(img, 164, "DESIG. RL-Z0-GND · EPICENTRE", P.BONE[2])
    if f >= 176:
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
    if i < C_HERO:
        return scene_crawl(i - C_CRAWL)
    if i < C_SLAM:
        return scene_hero(i - C_HERO)
    if i < C_ATTRACT:
        return scene_slam(i - C_SLAM)
    return scene_attract(i - C_ATTRACT)


def main():
    global CRAWL, SKY, NEBULA, LOGO_TOP, LOGO_BOT
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    gzart.load()
    CRAWL = _crawl_block()
    NEBULA = _nebula()
    SKY = _sky()
    LOGO_TOP = _logo_word("GROUND")
    LOGO_BOT = _logo_word("ZERO", reticle_last=True)

    if "--stills" in sys.argv:
        for i in (20, 60, 100, 200, 400, 700, 780, 820, 900, 1000, 1100,
                  1150, 1180, 1220, 1240, 1250, 1256, 1270, 1300, 1350, 1420,
                  1550, 1600, 1700):
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
