#!/usr/bin/env python3
"""Render the GROUND ZERO opening title sequence as PNG frames.

A cold open, sixty seconds, played straight.  A distress signal leaves Earth
and is not addressed to anyone; it goes unanswered for a long time; something
answers; a ring of light opens and closes; something comes down into a
hillside in the Okanagan at night and nobody sees it land.  Somebody had to
answer it.  Then the lockup.

What it is not, on purpose.  The earlier passes were a Mega Man X title in
8- and then 16-bit: a publisher sting, a prologue crawl, a sprite of the
correspondent, an orchestra hit, PRESS START.  All of that is gone.  Nobody
is drawn: the correspondent is not a character on screen, and the story is
told in captions, light and landscape.  No drums, no fanfare, no attract
loop — the cue is a drone, a pulse, strings and bells.

Still 16-bit, and specifically so: per-scanline gradients (HDMA tables) for
every sky and field; additive colour math for every light source (the
transmission, the answering star, the ring, the descent, the bloom behind
the lockup); type cut from a ramp with a keyline and a cast shadow rather
than flat 8-bit cells; depth planes separated by contrast, not outline.

**Nothing in this sequence is a crosshair.**  The transmission is arcs
opening one way, the answering star is a bloom, the zero of ZERØ is a ring
and one bar (gzlogo.py).

The canvas is 320x240 — 4:3 with square pixels, doubling exactly to the
640x480 the station's other cards are authored at, which pillarboxes into the
channel's 854x480 precisely inside the on-air rails.

Usage:  make_frames.py OUTDIR [--stills]
"""
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzfont
import gzlogo
import gzpal as P

W, H = 320, 240
FPS = 30

TRIBAND = (P.PINK[2], P.ARMOUR[2], P.VISOR[2])

# ── timeline ──────────────────────────────────────────────────────────────
T_DARK = 90        # 3.0 s   ink, the station's name
T_SIGNAL = 360     # 12.0 s  the transmission leaving
T_FIELD = 300      # 10.0 s  the deep field; something answers
T_RING = 240       # 8.0 s   the ring opens and closes
T_LAND = 330       # 11.0 s  the descent, the hillside, nobody watching
T_CLAIM = 240      # 8.0 s   somebody had to answer it
T_LOCKUP = 240     # 8.0 s   GROUND ZERØ
TOTAL = T_DARK + T_SIGNAL + T_FIELD + T_RING + T_LAND + T_CLAIM + T_LOCKUP  # 1800

C_DARK = 0
C_SIGNAL = C_DARK + T_DARK
C_FIELD = C_SIGNAL + T_SIGNAL
C_RING = C_FIELD + T_FIELD
C_LAND = C_RING + T_RING
C_CLAIM = C_LAND + T_LAND
C_LOCKUP = C_CLAIM + T_CLAIM

IMPACT = 80            # frame within the landing scene
IMPACT_AT = C_LAND + IMPACT

WORDMARK = "A CHANNEL Z0 TRANSMISSION"
# Captions are two short lines at most, nineteen cells each at 2x: the
# register of a subtitle, not a crawl.
CAPTIONS = {
    "signal_1": ["A DISTRESS SIGNAL", "LEFT EARTH."],
    "signal_2": ["IT WAS ADDRESSED", "TO NO ONE."],
    "field_1": ["IT WENT UNANSWERED", "FOR A LONG TIME."],
    "field_2": ["THEN SOMETHING", "ANSWERED."],
    "land": ["NOBODY SAW IT LAND."],
    "claim": ["SOMEBODY HAD TO", "ANSWER IT."],
    "claim_sub": "FIELD INTERVIEWS · THE OKANAGAN",
    "desig": "DESIG. RL-Z0-GND · LANDING SITE",
    "times": "NIGHTLY 19:00 · ENCORE 22:00",
    "copy": "© 2026 RIPOSTE LABORATORIES INC.",
}
READOUT = ("1420.405 MHZ", "ORIGIN  EARTH", "ADDRESSEE  NONE")

# The ring's colour goes round its circumference: light blue, white, pink,
# and back.  It is the one thing in the sequence that says what it is about,
# and it says it once, quietly.
RING_STOPS = [(0.00, P.HAIR[1]), (0.25, P.WHITE), (0.50, P.PINK[1]),
              (0.75, P.WHITE), (1.00, P.HAIR[1])]

NIGHT_STOPS = [(0.00, (0x04, 0x05, 0x10)), (0.55, (0x0a, 0x0e, 0x24)),
               (0.85, (0x18, 0x1e, 0x3a)), (1.00, (0x2a, 0x2c, 0x44))]
LAKE_STOPS = [(0.00, (0x1a, 0x1e, 0x32)), (1.00, (0x05, 0x05, 0x0c))]
SPACE_STOPS = [(0.00, (0x02, 0x02, 0x08)), (0.50, (0x05, 0x05, 0x12)),
               (1.00, (0x02, 0x02, 0x08))]
SIGNAL_STOPS = [(0.00, (0x03, 0x03, 0x08)), (0.70, (0x06, 0x08, 0x14)),
                (1.00, (0x10, 0x18, 0x26))]
CLAIM_STOPS = [(0.00, (0x0b, 0x09, 0x14)), (0.5, (0x18, 0x12, 0x1e)),
               (1.00, (0x08, 0x07, 0x0e))]
LOCKUP_STOPS = [(0.0, (0x0d, 0x0b, 0x14)), (0.45, (0x24, 0x1a, 0x18)),
                (1.0, (0x0a, 0x08, 0x0c))]

HORIZON_Y = 168        # the hills meet the lake here
CAP_Y = 200            # captions sit low, like subtitles on a documentary


# ── colour math ───────────────────────────────────────────────────────────
def new_frame(colour=P.BLACK):
    return Image.new("RGB", (W, H), colour)


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def add(base, lay, amount=1.0):
    """Additive colour math — the SNES main/sub screen add.  Every light source
    in the sequence goes through this."""
    rgb = lay.convert("RGB")
    if amount < 1.0:
        rgb = Image.blend(Image.new("RGB", (W, H), P.BLACK), rgb, amount)
    a = lay.getchannel("A")
    if a.getextrema() != (255, 255):
        rgb = Image.composite(rgb, Image.new("RGB", (W, H), P.BLACK), a)
    return ImageChops.add(base, rgb)


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


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def window(f, f_in, f_hold, f_out, ramp=18):
    """0..1 envelope: up over `ramp` frames from f_in, hold, down over `ramp`
    from f_out."""
    if f < f_in or f > f_out + ramp:
        return 0.0
    if f < f_in + ramp:
        return ease((f - f_in) / ramp)
    if f <= f_out:
        return 1.0
    return ease(1 - (f - f_out) / ramp)


# ── type ──────────────────────────────────────────────────────────────────
# Captions are the 6x7 face cut from a ramp — light at the top of the glyph,
# darker at the foot — with a keyline and a one-pixel cast shadow.  Flat
# single-colour cells are the 8-bit tell; the ramp and the keyline are what
# a 16-bit title did with the same bitmap.
_text_cache = {}


def text_img(s, ramp=P.BONE, scale=2, keyline=True):
    key = (s, tuple(ramp[:2]), scale, keyline)
    hit = _text_cache.get(key)
    if hit is not None:
        return hit
    cw = gzfont.SMALL_CELL * scale
    pad = 2
    img = Image.new("RGBA", (max(1, cw * len(s)) + 2 * pad + scale,
                             gzfont.SMALL_H * scale + 2 * pad + scale), (0, 0, 0, 0))
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    for i, ch in enumerate(s):
        glyph = gzfont.SMALL.get(ch, gzfont.MISSING)
        ox = pad + i * cw
        for gy, row in enumerate(glyph):
            for gx, on in enumerate(row):
                if on:
                    x, y = ox + gx * scale, pad + gy * scale
                    md.rectangle([x, y, x + scale - 1, y + scale - 1], fill=255)
    # shadow, keyline, then the ramp row by row
    img.paste(P.INK_DEEP + (255,), (0, 0),
              ImageChops.offset(mask, scale, scale))
    if keyline:
        grown = mask.copy()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
        img.paste(P.KEYLINE + (255,), (0, 0), ImageChops.subtract(grown, mask))
    rows = gzfont.SMALL_H * scale
    for y in range(rows):
        band = Image.new("L", img.size, 0)
        ImageDraw.Draw(band).rectangle([0, pad + y, img.size[0], pad + y], fill=255)
        band = ImageChops.multiply(band, mask)
        img.paste(P.ramp_at(ramp, 0.15 + 0.6 * y / max(1, rows - 1)) + (255,),
                  (0, 0), band)
    _text_cache[key] = img
    return img


def text_w(s, scale=2):
    return gzfont.SMALL_CELL * scale * len(s) + 4 + scale


def blit_text(img, x, y, s, ramp=P.BONE, scale=2, k=1.0, keyline=True):
    """Draw a caption at opacity k.  Alpha is scaled, not the colour, so the
    ramp and the shadow fade together."""
    if k <= 0.0:
        return
    t = text_img(s, ramp, scale, keyline)
    a = t.getchannel("A")
    if k < 0.999:
        a = a.point(lambda v: int(v * k))
    img.paste(t, (x - 2, y - 2), a)


def blit_centre(img, y, s, ramp=P.BONE, scale=2, k=1.0, keyline=True):
    blit_text(img, (W - text_w(s, scale)) // 2 + 2, y, s, ramp, scale, k, keyline)


CAP_LEAD = 18


def caption(img, key, k, y=CAP_Y, ramp=P.BONE):
    lines = CAPTIONS[key]
    y -= CAP_LEAD * (len(lines) - 1) // 2
    for i, line in enumerate(lines):
        blit_centre(img, y + i * CAP_LEAD, line, ramp, 2, k)


def triband(img, x, y, w, h):
    d = ImageDraw.Draw(img)
    a, b = int(w * 0.36), int(w * 0.64)
    d.rectangle([x, y, x + a - 1, y + h - 1], fill=TRIBAND[0])
    d.rectangle([x + a, y, x + b - 1, y + h - 1], fill=TRIBAND[1])
    d.rectangle([x + b, y, x + w - 1, y + h - 1], fill=TRIBAND[2])


# ── stars ─────────────────────────────────────────────────────────────────
def _hash(i, salt=0):
    x = (i * 2654435761 + salt * 40503) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 1274126177) & 0xFFFFFFFF
    return (x ^ (x >> 16)) & 0xFFFFFFFF


STARS = [(_hash(i, 1) % W, _hash(i, 2) % H, 1 + _hash(i, 3) % 3) for i in range(150)]


def star_field(img, drift, bright=1.0):
    lay = layer()
    px = lay.load()
    for x, y, depth in STARS:
        xx = int((x - drift * depth * 0.12) % W)
        v = int((70 + 55 * depth) * bright)
        col = (v, v, min(255, v + 12), 255)
        px[xx, y] = col
        if depth == 3:
            px[(xx + 1) % W, y] = (v // 2, v // 2, v // 2, 255)
    return add(img, lay)


def bloom(img, cx, cy, r, colour, amount=1.0, blur=None):
    """A soft additive light: a disc, blurred, added."""
    lay = layer()
    ImageDraw.Draw(lay).ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour + (255,))
    lay = lay.filter(ImageFilter.GaussianBlur(blur if blur is not None else max(2, r * 0.9)))
    return add(img, lay, amount)


# ── scene 1 · dark ────────────────────────────────────────────────────────
def scene_dark(f):
    img = new_frame(P.BLACK)
    blit_centre(img, 112, WORDMARK, P.BONE, 1, window(f, 30, 66, 70, 14), keyline=False)
    return img


# ── scene 2 · the signal ──────────────────────────────────────────────────
SIGNAL_SRC = (28, 214)


def scene_signal(f):
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, SIGNAL_STOPS)

    # The transmission: arcs leaving the bottom-left corner, opening one way,
    # each one dimmer than the last as the signal thins out over distance.
    lay = layer()
    d = ImageDraw.Draw(lay)
    cx, cy = SIGNAL_SRC
    for i in range(7):
        r = (f * 1.15 + i * 46) % 322
        if r < 8:
            continue
        a = int(150 * max(0.0, 1 - r / 322) ** 1.4)
        d.arc([cx - r, cy - r, cx + r, cy + r], 270, 360, fill=P.VISOR[1] + (a,), width=2)
    lay = lay.filter(ImageFilter.GaussianBlur(0.8))
    img = add(img, lay, 0.85)
    img = bloom(img, cx, cy, 6, P.VISOR[1], 0.5 + 0.2 * math.sin(f / 5.0), 5)

    # The trace: what the signal sounds like, weakening as it goes.
    amp = 22 * max(0.15, 1 - f / T_SIGNAL)
    pts = []
    for x in range(40, W - 24):
        t = (x + f * 3) / 17.0
        y = 76 + amp * (math.sin(t) * 0.6 + math.sin(t * 2.7 + 1.3) * 0.3
                        + math.sin(t * 0.31 + f / 40.0) * 0.4)
        pts.append((x, y))
    tr = layer()
    ImageDraw.Draw(tr).line(pts, fill=P.BONE[1] + (200,), width=1)
    img = add(img, tr.filter(ImageFilter.GaussianBlur(0.6)), 0.9)
    d = ImageDraw.Draw(img)
    d.line([(40, 76), (W - 24, 76)], fill=(0x18, 0x1c, 0x2a))

    # The readout, small, top right.
    k = window(f, 12, T_SIGNAL - 30, T_SIGNAL - 20, 12)
    for i, line in enumerate(READOUT):
        blit_text(img, W - 24 - text_w(line, 1) + 2, 14 + i * 11, line, P.BONE, 1, k * 0.8,
                  keyline=False)

    caption(img, "signal_1", window(f, 40, 150, 160))
    caption(img, "signal_2", window(f, 200, 320, 330))
    return img


# ── scene 3 · the deep field ──────────────────────────────────────────────
ANSWER = (214, 92)


def scene_field(f, drift=None):
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, SPACE_STOPS)
    img = star_field(img, drift if drift is not None else f)
    caption(img, "field_1", window(f, 24, 140, 150))

    # One star answers: a bloom that grows with the strings.
    if f >= 160:
        k = ease((f - 160) / 90)
        img = bloom(img, ANSWER[0], ANSWER[1], 2 + int(6 * k), P.HAIR[0], 0.5 + 0.5 * k, 3 + 4 * k)
        img = bloom(img, ANSWER[0], ANSWER[1], 1, P.WHITE, k, 0.6)
    caption(img, "field_2", window(f, 200, 285, 290))
    return img


# ── scene 4 · the ring ────────────────────────────────────────────────────
def ring(img, cx, cy, r, rot, amount=1.0, width=3):
    if r < 1:
        return img
    lay = layer()
    d = ImageDraw.Draw(lay)
    for a in range(0, 360, 2):
        col = P.stops_at(RING_STOPS, ((a + rot) % 360) / 360.0)
        d.arc([cx - r, cy - r, cx + r, cy + r], a, a + 3, fill=col + (255,), width=width)
    glow = lay.filter(ImageFilter.GaussianBlur(max(2, r * 0.12)))
    img = add(img, glow, 0.7 * amount)
    return add(img, lay, amount)


def scene_ring(f):
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, SPACE_STOPS)
    img = star_field(img, T_FIELD + f * 0.4)
    cx, cy = ANSWER
    # It opens over four seconds, holds, and closes in one.
    if f < 120:
        r = 84 * ease(f / 120)
        amt = 1.0
    elif f < 200:
        r = 84
        amt = 1.0
    else:
        r = 84 * (1 - ease((f - 200) / 36))
        amt = 1.0
    rot = f * 1.1
    img = bloom(img, cx, cy, 3, P.WHITE, 0.6, 1.0)
    img = ring(img, cx, cy, r, rot, amt)
    if f >= 236:
        img = flash(img, (f - 235) / 4.0, P.BONE[1])
    return img


# ── scene 5 · the descent, the hillside ───────────────────────────────────
def _hill(seed, base, amp):
    pts = []
    for x in range(-4, W + 5, 4):
        y = base
        for k, (freq, ph) in enumerate(((0.011, 0.4), (0.027, 2.1), (0.061, 4.4))):
            y += amp * (0.6 ** k) * math.sin(x * freq + ph + seed * 1.7)
        pts.append((x, y))
    return pts


HILLS = [(_hill(1, 122, 22), (0x14, 0x17, 0x2c)),
         (_hill(2, 140, 16), (0x0d, 0x0f, 0x1e)),
         (_hill(3, 156, 10), (0x07, 0x08, 0x12))]
SITE = (176, 150)      # where it comes down, on the middle hill


def _land_plate():
    img = new_frame(P.BLACK)
    vgrad(img, 0, HORIZON_Y, NIGHT_STOPS)
    d = ImageDraw.Draw(img)
    for pts, col in HILLS:
        d.polygon(pts + [(W + 4, HORIZON_Y), (-4, HORIZON_Y)], fill=col)
    vgrad(img, HORIZON_Y, H, LAKE_STOPS)
    # the lake carries a little of the sky
    for x in range(0, W, 3):
        v = 6 + (_hash(x, 9) % 7)
        d.line([(x, HORIZON_Y), (x, HORIZON_Y + 18 + _hash(x, 4) % 22)],
               fill=(0x12 + v, 0x14 + v, 0x28 + v))
    return img


LAND = None


def scene_land(f):
    img = LAND.copy()
    d = ImageDraw.Draw(img)

    # The descent: a streak from high right to the site, a bright head with a
    # cooling tail.  It is small.  Nobody is watching.
    x0, y0 = 296, -6
    sx, sy = SITE
    if 18 <= f < IMPACT:
        t = ease((f - 18) / (IMPACT - 18))
        hx, hy = x0 + (sx - x0) * t, y0 + (sy - y0) * t
        tail = layer()
        td = ImageDraw.Draw(tail)
        for i in range(1, 22):
            u = max(0.0, t - i * 0.012)
            px_, py_ = x0 + (sx - x0) * u, y0 + (sy - y0) * u
            a = int(200 * (1 - i / 22) ** 1.6)
            td.point((px_, py_), fill=P.ARMOUR[0] + (a,))
        img = add(img, tail.filter(ImageFilter.GaussianBlur(0.7)))
        img = bloom(img, hx, hy, 2, P.WHITE, 1.0, 1.2)
        img = bloom(img, hx, hy, 5, P.ARMOUR[1], 0.6, 4)

    if f >= IMPACT:
        g = f - IMPACT
        if g < 3:
            img = flash(img, 1.0 - g * 0.3, P.BONE[1])
        # The bloom at the site, decaying; the ground glow lingers longest.
        k = math.exp(-g / 40.0)
        img = bloom(img, sx, sy, 6 + int(30 * (1 - k)), P.ARMOUR[1], 0.9 * k, 6 + 10 * (1 - k))
        img = bloom(img, sx, sy, 3, P.WHITE, 0.8 * math.exp(-g / 12.0), 1.5)
        # dust, rising and thinning
        if g < 180:
            u = g / 180.0
            dl = layer()
            ImageDraw.Draw(dl).ellipse([sx - 10 - 26 * u, sy - 6 - 30 * u, sx + 10 + 26 * u, sy + 4],
                                       fill=(0x2c, 0x28, 0x30, int(120 * (1 - u) ** 1.5)))
            dl = dl.filter(ImageFilter.GaussianBlur(4 + 6 * u))
            img.paste(dl, (0, 0), dl)
        # the lake takes the glow
        img = bloom(img, sx, HORIZON_Y + 14, 22, P.ARMOUR[3], 0.35 * k, 10)

    caption(img, "land", window(f, 150, 268, 280))
    if f >= T_LAND - 30:
        img = fade(img, 1 - (f - (T_LAND - 30)) / 30.0)
    return img


# ── scene 6 · the claim ───────────────────────────────────────────────────
def scene_claim(f):
    img = new_frame(P.BLACK)
    vgrad(img, 0, H, CLAIM_STOPS)
    k = window(f, 20, 190, 205, 24)
    caption(img, "claim", k, y=104)
    d = ImageDraw.Draw(img)
    if k > 0:
        w = int(180 * k)
        d.rectangle([W // 2 - w // 2, 138, W // 2 + w // 2, 138], fill=P.RED[2])
    blit_centre(img, 148, CAPTIONS["claim_sub"], P.ARMOUR, 1, window(f, 60, 190, 205, 24),
                keyline=False)
    return img


# ── scene 7 · the lockup ──────────────────────────────────────────────────
LOGO_TOP = None
LOGO_BOT = None
LOGO_DX = 0
LOGO_Y = 60


def scene_lockup(f):
    img = new_frame(P.INK)
    vgrad(img, 0, H, LOCKUP_STOPS)
    d = ImageDraw.Draw(img)

    tlx, tly, tlw, tlh = LOGO_TOP.info["letters"]
    blx, bly, blw, blh = LOGO_BOT.info["letters"]
    bx = (W - blw) // 2 - blx
    tx = bx + LOGO_DX
    ty = LOGO_Y - tly
    by = LOGO_Y + tlh + 5 - bly
    zero_cx = bx + blx + blw - gzlogo.last_cell_w() * 3 // 2
    zero_cy = by + bly + blh // 2

    # Light first, then the word: a warm bloom behind the zero grows in and
    # the lockup resolves out of it.
    k = ease(f / 42.0)
    img = bloom(img, zero_cx, zero_cy, 40, (0x50, 0x28, 0x08), 0.9 * k, 26)
    for im, pos in ((LOGO_TOP, (tx, ty)), (LOGO_BOT, (bx, by))):
        a = im.getchannel("A")
        if k < 0.999:
            a = a.point(lambda v: int(v * k))
        img.paste(im, pos, a)
    d = ImageDraw.Draw(img)

    # The horizon draws outward from under the zero, dent first.
    if f >= 40:
        h = ease((f - 40) / 40.0)
        x0 = int(zero_cx - (zero_cx - 48) * h)
        x1 = int(zero_cx + (271 - zero_cx) * h)
        gzlogo.horizon(d, x0, x1, 150, zero_cx, 30, 6, (0x3a, 0x2e, 0x24), P.INK_DEEP)

    blit_centre(img, 164, CAPTIONS["desig"], P.BONE, 1, window(f, 90, 400, 400, 16), keyline=False)
    blit_centre(img, 178, CAPTIONS["times"], P.ARMOUR, 1, window(f, 118, 400, 400, 16), keyline=False)
    blit_centre(img, 222, CAPTIONS["copy"], P.BONE, 1, window(f, 140, 400, 400, 16) * 0.55,
                keyline=False)
    if f >= 150:
        triband(img, 0, H - 3, W, 3)
    if f >= T_LOCKUP - 24:
        img = fade(img, 1 - (f - (T_LOCKUP - 24)) / 24.0)
    return img


# ── dispatch ──────────────────────────────────────────────────────────────
def render(i):
    if i < C_SIGNAL:
        return scene_dark(i - C_DARK)
    if i < C_FIELD:
        return scene_signal(i - C_SIGNAL)
    if i < C_RING:
        return scene_field(i - C_FIELD)
    if i < C_LAND:
        return scene_ring(i - C_RING)
    if i < C_CLAIM:
        return scene_land(i - C_LAND)
    if i < C_LOCKUP:
        return scene_claim(i - C_CLAIM)
    return scene_lockup(i - C_LOCKUP)


def check_fits():
    """Refuse to render if any fixed caption would run off the frame.  The
    only symptom of an overlong caption is a sentence quietly missing its last
    characters — invisible in the code, invisible unless you look at the
    right edge of one still."""
    for key, val in CAPTIONS.items():
        lines = val if isinstance(val, list) else [val]
        scale = 2 if isinstance(val, list) else 1
        for s in lines:
            assert text_w(s, scale) <= W - 8, f"caption too wide at {scale}x: {s!r}"
            assert all(c in gzfont.SMALL for c in s), f"caption uses a missing glyph: {s!r}"
    for s in READOUT + (WORDMARK,):
        assert text_w(s, 1) <= W - 8, f"too wide: {s!r}"
    assert TOTAL == 1800, TOTAL


def main():
    global LAND, LOGO_TOP, LOGO_BOT, LOGO_DX
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    check_fits()
    LAND = _land_plate()
    LOGO_TOP, LOGO_BOT, LOGO_DX = gzlogo.lockup(1)

    if "--stills" in sys.argv:
        marks = [50, 130, 200, 300, 400, 500, 560, 640, 700, 800, 870, 940,
                 980, 1040, 1069, 1075, 1100, 1160, 1240, 1300, 1380, 1450,
                 1520, 1600, 1660, 1720, 1780]
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
