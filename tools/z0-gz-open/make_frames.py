#!/usr/bin/env python3
"""Render the GROUND ZERO opening title sequence as PNG frames.

The sequence is a parody of the Mega Man X / X2 / X3 openings, done as if the
station had only ever had an 8-bit machine to do it on: publisher sting, a long
prologue crawl, a backlit hero shot, the logo arriving hard, and an attract
screen.  Mega Man X is a 16-bit game; the brief asked for 8-bit, so what is
borrowed is the *structure* and the timing, not the colour depth.

Everything is drawn on a 320x240 logical canvas — 4:3 with square pixels, an
8 px tile grid, and a fixed 16-colour palette.  320x240 doubles exactly to the
640x480 the station's other cards are authored at, so the encode can scale with
`neighbor` and every pixel stays a hard square.  4:3 is also what the channel
wants: at 854x480 a 4:3 item pillarboxes into precisely the gutters the on-air
rails live in, so nothing here is ever drawn under the furniture.

Usage:  make_frames.py OUTDIR [--stills]
"""
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzart
import gzfont

W, H = 320, 240
FPS = 30

# ── palette ───────────────────────────────────────────────────────────────
# Sixteen colours, and nothing is drawn outside them.  The station brand
# supplies ink / bone / marigold / pink / teal; the rest are the two ramps
# those need to survive a night sky and a metal logo.
BLACK    = (0x00, 0x00, 0x00)
INK      = (0x1d, 0x1a, 0x17)
INK_DEEP = (0x0b, 0x0a, 0x09)
STEEL_DK = (0x3a, 0x35, 0x2f)
STEEL    = (0x5c, 0x55, 0x4c)
BONE_DK  = (0x7c, 0x76, 0x6b)
BONE_DIM = (0xb9, 0xb2, 0xa4)
BONE     = (0xf6, 0xf1, 0xe7)
WHITE    = (0xff, 0xff, 0xff)
MARI_DP  = (0xa1, 0x5e, 0x01)
MARI     = (0xfe, 0x9a, 0x0d)
MARI_LT  = (0xff, 0xd0, 0x8a)
PINK     = (0xf0, 0x47, 0x7d)
TEAL     = (0x12, 0xb7, 0x95)
SKY_LO   = (0x16, 0x12, 0x24)
SKY_MD   = (0x2a, 0x21, 0x40)
SKY_HI   = (0x45, 0x30, 0x5c)
HILL     = (0x24, 0x1c, 0x33)
CLOUD    = (0x1e, 0x18, 0x2c)
CLOUD_HI = (0x36, 0x28, 0x4c)
GLOW_A   = (0x26, 0x22, 0x1d)
GLOW_B   = (0x30, 0x2a, 0x22)

TRIBAND = (PINK, MARI, TEAL)

# ── timeline ──────────────────────────────────────────────────────────────
# Frame counts, not seconds, because every motion below is authored in whole
# pixels per frame and a fractional duration would put the crawl on half-pixel
# steps.
T_STING  = 135   # 4.5 s  publisher sting
T_CRAWL  = 660   # 22.0 s prologue
T_HERO   = 450   # 15.0 s rooftop
T_SLAM   = 315   # 10.5 s logo
T_ATTRACT = 240  # 8.0 s  press start
TOTAL = T_STING + T_CRAWL + T_HERO + T_SLAM + T_ATTRACT   # 1800 = 60.0 s

C_STING = 0
C_CRAWL = C_STING + T_STING
C_HERO  = C_CRAWL + T_CRAWL
C_SLAM  = C_HERO + T_HERO
C_ATTRACT = C_SLAM + T_SLAM

# ── text ──────────────────────────────────────────────────────────────────
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
CRAWL_SPEED = 1        # px per frame, integer on purpose
CRAWL_HOLD = 60        # frames the last line sits still before the cut

WORDMARK = "RIPOSTE LABORATORIES INC."


# ── primitives ────────────────────────────────────────────────────────────
def new_frame(colour=BLACK):
    return Image.new("RGB", (W, H), colour)


_text_cache = {}


def text_img(s, colour, scale=1):
    """One line of SMALL type as an RGBA image, cached."""
    key = (s, colour, scale)
    hit = _text_cache.get(key)
    if hit is not None:
        return hit
    cw = gzfont.SMALL_CELL * scale
    img = Image.new("RGBA", (max(1, cw * len(s)), gzfont.SMALL_H * scale), (0, 0, 0, 0))
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
    """The station's three-colour band, hard edges, 36/28/36 like the cards."""
    d = ImageDraw.Draw(img)
    a = int(w * 0.36)
    b = int(w * 0.64)
    d.rectangle([x, y, x + a - 1, y + h - 1], fill=PINK)
    d.rectangle([x + a, y, x + b - 1, y + h - 1], fill=MARI)
    d.rectangle([x + b, y, x + w - 1, y + h - 1], fill=TEAL)


BAYER4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]


def dither_band(img, y0, y1, c_top, c_bot):
    """Ordered-dither between two palette colours down a band.

    No blending: every pixel is one of the two colours.  A true gradient would
    put unlisted colours on screen and cost the whole 8-bit read.
    """
    px = img.load()
    span = max(1, y1 - y0)
    for y in range(y0, y1):
        f = (y - y0) / span
        lvl = f * 16
        for x in range(W):
            px[x, y] = c_bot if lvl > BAYER4[y & 3][x & 3] else c_top


def fade(img, k, steps=6):
    """Palette-style fade: k in 0..1, quantised so it steps rather than glides."""
    if k >= 0.999:
        return img
    q = round(k * steps) / steps
    out = img.point(lambda v: int(v * q))
    return out


def rings(d, cx, cy, radii, colour):
    for r in radii:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour)


# ── scene 1 · publisher sting ─────────────────────────────────────────────
def scene_sting(f):
    """Capcom-logo grammar: a wordmark, a chime, a flash, then PRESENTS."""
    img = new_frame(BLACK)
    y = 100
    x0 = (W - text_w(WORDMARK)) // 2

    if f < 6:
        return img

    # The wordmark types in, then the flash lands on the last character.
    shown = min(len(WORDMARK), int((f - 6) / 1.05))
    if shown:
        blit_text(img, x0, y, WORDMARK[:shown], BONE)

    if 44 <= f < 48:
        return new_frame(WHITE if f < 46 else BONE)

    if f >= 48:
        blit_text(img, x0, y, WORDMARK, BONE)
        triband(img, x0, y + 12, text_w(WORDMARK), 3)
    if f >= 62:
        blit_centre(img, y + 26, "PRESENTS", MARI)
    if f >= 74:
        blit_centre(img, y + 44, "A CHANNEL Z0 TRANSMISSION", STEEL, 1)

    if f >= T_STING - 24:
        img = fade(img, max(0.0, (T_STING - 6 - f) / 18))
    return img


# ── scene 2 · prologue crawl ──────────────────────────────────────────────
def _crawl_block():
    h = CRAWL_PITCH * len(PROLOGUE)
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    for i, line in enumerate(PROLOGUE):
        if not line:
            continue
        last = i == len(PROLOGUE) - 1
        colour = MARI if last else BONE
        x = (W - text_w(line)) // 2
        blit_text(img, x, i * CRAWL_PITCH, line, colour, 1, shadow=STEEL_DK)
        if last:
            d = ImageDraw.Draw(img)
            d.rectangle([x, i * CRAWL_PITCH + 10, x + text_w(line) - 1,
                         i * CRAWL_PITCH + 11], fill=MARI_DP)
    return img


CRAWL = None
DUST = [((i * 61) % W, (i * 37) % 320, BONE_DK if i % 5 == 0 else STEEL)
        for i in range(70)]


def scene_crawl(f):
    img = new_frame(BLACK)
    d = ImageDraw.Draw(img)

    # A field of slow dust so the black is moving.  It reads as depth without
    # ever competing with the type for attention.
    for i, (x, y0, c) in enumerate(DUST):
        speed = 1 if i % 3 == 0 else 2
        y = (y0 - f * speed // 2) % 320 - 40
        if 0 <= y < H:
            d.point((x, y), fill=c)

    # The card's reticle, holding station off to the right, breathing.
    cx, cy = 318, 118
    rings(d, cx, cy, (64, 47, 30), STEEL_DK)
    pulse = 12 + int(7 * math.sin(f / 14.0))
    rings(d, cx, cy, (pulse,), MARI_DP)
    d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=MARI_DP)
    d.rectangle([cx - 74, cy, cx, cy + 1], fill=STEEL_DK)

    scroll = min(f * CRAWL_SPEED, (T_CRAWL - CRAWL_HOLD) * CRAWL_SPEED)
    img.paste(CRAWL, (0, H - scroll), CRAWL)

    if f < 12:
        img = fade(img, f / 12)
    if f >= T_CRAWL - 10:
        img = fade(img, max(0.0, (T_CRAWL - 1 - f) / 9))
    return img


# ── scene 3 · the rooftop ─────────────────────────────────────────────────
# The ridge dips where the hero stands, so his head and shoulders break the
# skyline instead of disappearing into it.  That dip is the whole composition:
# in a backlit shot the figure must be the darkest thing on screen and must sit
# against the lightest, and hills are neither.
HILLS = [(0, 148), (24, 140), (48, 145), (72, 138), (96, 149), (120, 153),
         (148, 151), (172, 139), (196, 127), (220, 135), (244, 130),
         (268, 141), (296, 133), (320, 143)]

RAIN = [((i * 53) % W, (i * 29) % 260, 4 + (i % 3) * 3) for i in range(64)]
RAIN_FG = [((i * 91) % W, (i * 67) % 260, 9 + (i % 2) * 4) for i in range(16)]

HERO_X, HERO_FOOT = 118, 162      # feet on the parapet, head on the moon
MOON_X, MOON_Y, MOON_R = 128, 132, 25

T_WIDE = 300          # frames of the wide shot before the cut to the visor


def _sky():
    """The static plate for the wide shot: sky, moon, hills, lake, roof.

    Built once.  Six flat values from SKY_LO at the top to BLACK in the
    foreground, ordered so that every layer is lighter than the one in front
    of it — which is what makes a silhouette possible at all.
    """
    img = new_frame(SKY_LO)
    dither_band(img, 0, 72, SKY_LO, SKY_LO)
    dither_band(img, 72, 112, SKY_LO, SKY_MD)
    dither_band(img, 112, 152, SKY_MD, SKY_HI)
    d = ImageDraw.Draw(img)

    for i in range(52):                                   # stars
        x, y = (i * 71) % W, (i * 43) % 74
        d.point((x, y), fill=BONE_DK if i % 4 else BONE_DIM)

    # The moon is the backlight.  Everything downstream is read against it.
    for r, c in ((MOON_R + 9, SKY_HI), (MOON_R + 4, CLOUD_HI)):
        d.ellipse([MOON_X - r, MOON_Y - r, MOON_X + r, MOON_Y + r], fill=c)
    d.ellipse([MOON_X - MOON_R, MOON_Y - MOON_R,
               MOON_X + MOON_R, MOON_Y + MOON_R], fill=BONE_DIM)
    for cx, cy, r in ((MOON_X - 9, MOON_Y - 6, 4), (MOON_X + 7, MOON_Y + 4, 6),
                      (MOON_X + 2, MOON_Y - 13, 3)):      # maria
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BONE_DK)

    for i in range(len(HILLS) - 1):                       # Okanagan ridge
        x0, y0 = HILLS[i]
        x1, y1 = HILLS[i + 1]
        d.polygon([(x0, y0), (x1, y1), (x1, 158), (x0, 158)], fill=HILL)
    d.rectangle([0, 152, W, 158], fill=HILL)

    d.rectangle([0, 158, W, 172], fill=SKY_MD)            # the lake
    for y in range(159, 172, 3):                          # ripple
        for x in range(0, W, 2):
            if (x + y) & 3:
                continue
            d.point((x, y), fill=SKY_HI)
    for y in range(159, 172):                             # moonpath, kept faint
        wdt = 2 + (y - 159) // 3
        for x in range(MOON_X - wdt, MOON_X + wdt):
            if (x + y) & 3 == 0:
                d.point((x, y), fill=BONE_DK)

    # The bridge, because the lake needs one thing on it that says where this is.
    d.rectangle([0, 160, W, 161], fill=INK_DEEP)
    for x in range(6, W, 24):
        d.rectangle([x, 161, x + 1, 166], fill=INK_DEEP)
    d.polygon([(198, 160), (206, 148), (214, 160)], fill=INK_DEEP)

    # Foreground: the roof, and the parapet the hero is standing on.  Both are
    # pure black — the near plane has to be the darkest value in the frame or
    # the depth reads backwards.
    d.rectangle([0, 172, W, H], fill=BLACK)
    d.rectangle([0, 172, W, 173], fill=STEEL_DK)
    d.rectangle([84, 162, 174, 173], fill=BLACK)
    d.rectangle([84, 162, 174, 162], fill=STEEL_DK)
    for x in range(0, W, 16):                             # roof gravel edge
        d.point((x + (x // 16) % 3, 175), fill=STEEL_DK)

    mx = 284                                              # the mast
    d.rectangle([mx, 84, mx + 5, 172], fill=BLACK)
    for y in range(88, 172, 8):
        d.line([(mx, y), (mx + 5, y + 8)], fill=STEEL_DK)
        d.line([(mx + 5, y), (mx, y + 8)], fill=STEEL_DK)
    d.rectangle([mx - 3, 84, mx + 8, 85], fill=STEEL_DK)
    return img


SKY = None


def _blit_mask(img, mask, x, y, colour, mw, mh):
    px = img.load()
    for gy in range(mh):
        yy = y + gy
        if not (0 <= yy < H):
            continue
        row = mask[gy]
        for gx in range(mw):
            if row[gx]:
                xx = x + gx
                if 0 <= xx < W:
                    px[xx, yy] = colour


def _rain(d, frames, f, colour_a, colour_b, length=6, dx=2):
    for i, (x, y0, sp) in enumerate(frames):
        y = (y0 + f * sp) % 300 - 30
        if -length < y < H:
            d.line([(x, y), (x - dx, y + length)],
                   fill=colour_a if i % 4 else colour_b)


def _wide(f):
    img = SKY.copy()
    d = ImageDraw.Draw(img)

    strike = (118 <= f < 126) or (238 <= f < 246)
    peak = (118 <= f < 121) or (238 <= f < 241)

    if peak:
        d.rectangle([0, 0, W, 152], fill=SKY_HI)
        for i in range(len(HILLS) - 1):
            x0, y0 = HILLS[i]
            x1, y1 = HILLS[i + 1]
            d.polygon([(x0, y0), (x1, y1), (x1, 172), (x0, 172)], fill=INK_DEEP)
        d.rectangle([0, 158, W, 172], fill=CLOUD_HI)
        d.rectangle([0, 172, W, H], fill=BLACK)
        d.rectangle([84, 162, 174, 173], fill=BLACK)
        for xoff, col in ((0, BONE), (1, WHITE)):
            d.line([(232 + xoff, 0), (224 + xoff, 42), (242 + xoff, 46),
                    (226 + xoff, 100)], fill=col)

    # Two cloud layers, ragged along the top so they read as weather and not
    # as bars.  The far layer is lighter: it is nearer the moon.
    for speed, col, y0, hgt, n in ((2, CLOUD_HI, 74, 8, 6), (1, CLOUD, 92, 11, 7)):
        for i in range(n):
            cw = 54 + (i * 23) % 58
            x = ((i * 61) + f * speed // 2) % (W + 130) - 65
            base = y0 + (i % 3) * 5
            for seg in range(0, cw, 6):
                lump = ((i + seg) % 4)
                d.rectangle([x + seg, base + lump, x + seg + 5,
                             base + hgt], fill=col)

    _rain(d, RAIN, f, BONE_DK, STEEL)

    body = BLACK
    _blit_mask(img, gzart.BODY, HERO_X, HERO_FOOT - gzart.HERO_H, body,
               gzart.HERO_W, gzart.HERO_H)
    _blit_mask(img, gzart.MIC_M, HERO_X + 19, HERO_FOOT - 12, BLACK,
               gzart.MIC_W, gzart.MIC_H)
    _blit_mask(img, gzart.RIM, HERO_X, HERO_FOOT - gzart.HERO_H,
               BONE if strike else MARI, gzart.HERO_W, gzart.HERO_H)
    _blit_mask(img, gzart.VISOR, HERO_X, HERO_FOOT - gzart.HERO_H,
               WHITE if peak else TEAL, gzart.HERO_W, gzart.HERO_H)

    if (f // 20) % 2 == 0:                                # mast beacon
        d.rectangle([285, 80, 288, 83], fill=PINK)

    _rain(d, RAIN_FG, f, BONE_DIM, BONE_DK, length=11, dx=4)

    if f >= 190:
        blit_text(img, 10, 214, "KELOWNA, B.C.", MARI, 1, shadow=BLACK)
        blit_text(img, 10, 226, "TRANSMITTER RL-Z0 · 19:00", BONE_DIM, 1,
                  shadow=BLACK)
    return img


def _helmet(f):
    """The push-in on the visor — the shot the whole rooftop beat exists for.

    Drawn from primitives rather than a sprite: it is the one shot that scales
    across its own duration, and a 1x mask blown up would be the only thing in
    the sequence with pixels a different size from everything else.

    The head is cropped by the frame on purpose.  A close-up that fits inside
    the safe area is not a close-up, it is a portrait, and the first pass of
    this shot looked like a flowerpot for exactly that reason.
    """
    dur = T_HERO - T_WIDE
    img = new_frame(INK_DEEP)
    d = ImageDraw.Draw(img)

    k = f / max(1, dur)                        # 0 -> 1 across the shot
    z = 1.0 + 0.20 * k
    cx, cy = 160, int(126 + 10 * k)
    strike = 96 <= f < 104
    flare = f >= 126

    def s(v):
        return int(v * z)

    for i in range(0, H, 4):                   # wet air
        d.line([(0, i), (W, i)], fill=INK if (i // 4) % 2 else INK_DEEP)
    r = s(150)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0x14, 0x11, 0x1d))
    _rain(d, RAIN, f * 2, STEEL_DK, INK, length=14, dx=5)

    lit = BONE if strike else MARI
    dim = BONE_DK if strike else MARI_DP

    # silhouette: dome + a chin that TAPERS, which is the whole difference
    # between a helmet and a plant pot
    dome = [cx - s(104), cy - s(152), cx + s(104), cy + s(64)]
    chin = [(cx - s(74), cy + s(28)), (cx + s(74), cy + s(28)),
            (cx + s(40), cy + s(104)), (cx - s(40), cy + s(104))]
    d.ellipse(dome, fill=BLACK)
    d.polygon(chin, fill=BLACK)
    d.ellipse([dome[0] + s(7), dome[1] + s(7), dome[2] - s(7), dome[3] - s(7)],
              fill=INK)
    d.polygon([(cx - s(66), cy + s(30)), (cx + s(66), cy + s(30)),
               (cx + s(35), cy + s(96)), (cx - s(35), cy + s(96))],
              fill=STEEL_DK)
    for i, yy in enumerate(range(cy + s(52), cy + s(92), s(12))):   # chin vent
        hw = s(30) - i * s(6)
        d.rectangle([cx - hw, yy, cx + hw, yy + s(4)], fill=BLACK)

    for side in (-1, 1):                       # ear pods
        px_ = cx + side * s(97)
        py_ = cy + s(6)
        for rr, col in ((s(32), BLACK), (s(27), MARI_DP), (s(19), INK_DEEP),
                        (s(8), MARI)):
            d.ellipse([px_ - rr, py_ - rr, px_ + rr, py_ + rr], fill=col)

    # brow band, and the programme's reticle etched into it
    d.polygon([(cx - s(92), cy - s(44)), (cx + s(92), cy - s(44)),
               (cx + s(88), cy - s(24)), (cx - s(88), cy - s(24))],
              fill=MARI_DP)
    d.polygon([(cx - s(92), cy - s(44)), (cx + s(92), cy - s(44)),
               (cx + s(90), cy - s(38)), (cx - s(90), cy - s(38))], fill=MARI)
    for rr in (s(26), s(15)):
        d.ellipse([cx - rr, cy - s(76) - rr, cx + rr, cy - s(76) + rr],
                  outline=dim)
    d.line([(cx - s(40), cy - s(76)), (cx + s(40), cy - s(76))], fill=dim)
    d.line([(cx, cy - s(110)), (cx, cy - s(50))], fill=dim)

    # the visor
    outer = [(cx - s(94), cy - s(20)), (cx + s(94), cy - s(20)),
             (cx + s(74), cy + s(26)), (cx - s(74), cy + s(26))]
    inner = [(cx - s(86), cy - s(14)), (cx + s(86), cy - s(14)),
             (cx + s(69), cy + s(19)), (cx - s(69), cy + s(19))]
    d.polygon(outer, fill=BLACK)

    if flare:
        g = (f - 126) / max(1, dur - 126)
        d.polygon(inner, fill=WHITE if g > 0.5 else BONE)
        rr = int(40 + 300 * g)
        for step in (0, 3, 7):
            d.ellipse([cx - rr + step, cy - rr + step, cx + rr - step,
                       cy + rr - step], outline=WHITE if g > 0.7 else BONE_DIM)
    else:
        d.polygon(inner, fill=TEAL)
        for yy in range(cy - s(14), cy + s(19), 3):
            d.line([(cx - s(86), yy), (cx + s(86), yy)], fill=(0x0d, 0x8a, 0x70))
        # Travelling glint, clipped to the glass.  Unclipped it ran out over
        # the ear pod and read as a white sticker on the side of his head.
        gl = cx - s(86) + (f * 6) % (s(180) + 60) - 30
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(
            [(gl, cy - s(14)), (gl + 16, cy - s(14)),
             (gl + 6, cy + s(19)), (gl - 10, cy + s(19))], fill=BONE + (255,))
        clip = Image.new("L", (W, H), 0)
        ImageDraw.Draw(clip).polygon(inner, fill=255)
        img.paste(layer, (0, 0), Image.composite(
            layer.getchannel("A"), Image.new("L", (W, H), 0), clip))
        d = ImageDraw.Draw(img)
        d.polygon(inner, outline=(0x0d, 0x8a, 0x70))
    d.line([(cx - s(74), cy + s(26)), (cx + s(74), cy + s(26))], fill=lit)

    # Rim light on the side facing the moon.  Only the upper-left quadrant:
    # a full sweep of the dome ellipse runs behind the chin and reads as a
    # loose wire lying across his face.
    d.arc(dome, 186, 268, fill=lit)
    d.arc([dome[0] + 2, dome[1] + 2, dome[2] - 2, dome[3] - 2], 194, 262,
          fill=dim)

    _rain(d, RAIN_FG, f * 2, BONE_DIM, BONE_DK, length=13, dx=5)

    if f < 8:
        img = fade(img, f / 8)
    return img


def scene_hero(f):
    if f < T_WIDE:
        img = _wide(f)
        if f < 12:
            img = fade(img, f / 12)
        if f >= T_WIDE - 6:
            img = fade(img, max(0.0, (T_WIDE - 1 - f) / 5))
        return img
    return _helmet(f - T_WIDE)


# ── scene 4 · the logo ────────────────────────────────────────────────────
LOGO_SCALE = 2
GLYPH_W = gzfont.LOGO_W * LOGO_SCALE       # 32
GLYPH_H = gzfont.LOGO_H * LOGO_SCALE       # 36
GAP = 3


def _logo_word(word, reticle_last=False):
    """One word of the display face: black shadow, black outline, marigold ramp.

    The ramp is three flat bands, not a blend — same reason as dither_band.
    """
    n = len(word)
    w = n * GLYPH_W + (n - 1) * GAP + 6
    h = GLYPH_H + 6
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()

    cells = []
    for i, ch in enumerate(word):
        ox = i * (GLYPH_W + GAP)
        if reticle_last and i == n - 1:
            cells.append((ox, None))
            continue
        cells.append((ox, gzfont.LOGO[ch]))

    def band(gy):
        f = gy / gzfont.LOGO_H
        return MARI_LT if f < 0.28 else (MARI if f < 0.66 else MARI_DP)

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
                            x = ox + gx * LOGO_SCALE + sx + dx
                            y = gy * LOGO_SCALE + sy + dy
                            if 0 <= x < w and 0 <= y < h:
                                px[x, y] = colour_of(gy) + (255,)

    stamp(4, 4, lambda gy: BLACK)                        # cast shadow
    for ox_, oy_ in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)):
        stamp(1 + ox_, 1 + oy_, lambda gy: BLACK)        # keyline
    stamp(1, 1, band)                                    # face

    if reticle_last:
        # The last O of ZERO is the programme's own mark, straight off the
        # COMING SOON card: the epicentre reticle, not a letter.
        ox = cells[-1][0] + 1
        cx = ox + GLYPH_W // 2
        cy = 1 + GLYPH_H // 2
        d = ImageDraw.Draw(img)
        for r, c in ((17, BLACK), (16, MARI), (12, BLACK), (11, MARI_DP),
                     (7, MARI)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c)
        d.rectangle([cx - 20, cy - 1, cx + 20, cy + 1], fill=MARI_DP)
        d.rectangle([cx - 1, cy - 20, cx + 1, cy + 20], fill=MARI_DP)
        d.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], fill=MARI)
    return img


LOGO_TOP = None      # GROUND
LOGO_BOT = None      # ZERO, with the reticle O


def _shine(img, phase):
    """A diagonal specular band sweeping the letters, the classic logo move."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        band = phase - y
        for x in range(max(0, band - 6), min(w, band + 6)):
            r, g, b, a = px[x, y]
            if a and (r, g, b) != BLACK:
                px[x, y] = (MARI_LT if abs(x - band) > 3 else BONE) + (255,)
    return out


def scene_slam(f):
    img = new_frame(INK)
    d = ImageDraw.Draw(img)

    if f < 3:
        return new_frame(WHITE)
    if f < 6:
        return new_frame(BONE)

    # A marigold glow behind the mark so the black keyline has something to
    # separate from, and the frame is not flat ink.
    for i, r in enumerate((156, 124, 96, 70, 48)):
        col = GLOW_B if i >= 3 else GLOW_A
        box = [W // 2 - r, 96 - r // 2, W // 2 + r, 96 + r // 2]
        for step in range(3):
            d.ellipse([box[0] + step, box[1] + step, box[2] - step,
                       box[3] - step], outline=col if (i + step) & 1 else INK)

    tw, th = LOGO_TOP.size
    bw, bh = LOGO_BOT.size
    tx = (W - tw) // 2
    bx = (W - bw) // 2
    ty_end, by_end = 52, 52 + GLYPH_H + 8

    sx = sy = 0
    # GROUND drops in and lands at f 22; ZERO arrives from the right at f 52.
    if f < 22:
        ty = ty_end - int((22 - f) ** 2 * 1.1)
    else:
        ty = ty_end
        if f < 30:
            sy = (30 - f) // 2 * (1 if f % 2 else -1)
    if f >= 12:
        img.paste(LOGO_TOP, (tx + sx, ty + sy), LOGO_TOP)

    if f >= 30:
        if f < 52:
            bxx = bx + int((52 - f) ** 2 * 0.9)
        else:
            bxx = bx
        img.paste(LOGO_BOT, (bxx, by_end), LOGO_BOT)

    if 52 <= f < 62:                       # impact judder on the whole frame
        amp = (62 - f) // 3
        if amp:
            off = amp if f % 2 else -amp
            shifted = new_frame(INK)
            shifted.paste(img, (off, 0))
            img = shifted
            d = ImageDraw.Draw(img)
        for i in range(14):                # dust kicked off the baseline
            dx = (i * 23 + f * 5) % W
            dy = by_end + GLYPH_H + (i % 4) - (f - 52)
            d.point((dx, dy), fill=BONE_DK)

    # The shine repeats on a long cycle rather than firing once.  The logo is
    # on screen for eighteen seconds and the station's own cards carry a moving
    # accent for exactly this reason: a truly static frame reads as a frozen
    # channel, not as a title card.
    cyc = f % 260
    if 96 <= cyc < 150 and f >= 96:
        ph = (cyc - 96) * 7 - 40
        top = _shine(LOGO_TOP, ph)
        bot = _shine(LOGO_BOT, ph - 30)
        img.paste(top, (tx, ty_end), top)
        img.paste(bot, (bx, by_end), bot)

    if f >= 70:
        # The mark keeps ranging, out of the reticle that replaces the O.
        rcx = bx + (len("ZERO") - 1) * (GLYPH_W + GAP) + 1 + GLYPH_W // 2
        rcy = by_end + 1 + GLYPH_H // 2
        ping = (f - 70) % 74
        if ping < 46:
            rr = 20 + ping
            d.ellipse([rcx - rr, rcy - rr, rcx + rr, rcy + rr],
                      outline=MARI_DP if ping < 22 else GLOW_B)

    if f >= 150:                           # the sliding accent marker
        d.rectangle([48, 150, 271, 151], fill=GLOW_B)
        mx = ((f - 150) * 2) % 318 - 47      # enters and leaves the track
        x0, x1 = max(48, mx), min(271, mx + 47)
        if x1 >= x0:
            d.rectangle([x0, 150, x1, 151], fill=MARI)

    if f >= 160:
        blit_centre(img, 164, "DESIG. RL-Z0-GND · EPICENTRE", BONE_DIM)
    if f >= 176:
        blit_centre(img, 178, "▸ THE DAY, FROM THE POINT IT HAPPENED", MARI)
    return img


# ── scene 5 · attract ─────────────────────────────────────────────────────
def scene_attract(f):
    # Keep the slam's clock running so the marker keeps sliding and the shine
    # comes round once more instead of freezing on the cut.
    img = scene_slam(T_SLAM - 1 + f)
    if (f // 22) % 2 == 0:
        blit_centre(img, 198, "PRESS START", BONE)
    blit_centre(img, 212, "NIGHTLY 19:00 · ENCORE 22:00", MARI_DP)
    blit_centre(img, 224, "© 2026 RIPOSTE LABORATORIES INC.", STEEL)
    triband(img, 0, 235, W, 3)
    if f >= T_ATTRACT - 24:
        img = fade(img, max(0.0, (T_ATTRACT - 1 - f) / 23))
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
    global CRAWL, SKY, LOGO_TOP, LOGO_BOT
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    CRAWL = _crawl_block()
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
