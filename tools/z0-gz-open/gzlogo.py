"""The GROUND ZERO lockup — the programme's logo, drawn from code.

Redesigned 2026-09-08.  The first identity was a ten-stop chrome pastiche of
the Mega Man X title card: the letters said "16-bit" and nothing else, and the
O of ZERO had once been a reticle.  This lockup says what the programme is:

    GROUND   small, tracked wide, bone.  The place.
    ZERØ     large, marigold.  The zero is the landing site, and the slash
             through it is the baguette — the programme's one prop doing the
             job a slashed zero does anyway (this is a nought, not an O).
             She did not aim at anything.  She turned up with bread.

Under it, on the title card, the horizon: one rule with a dent where the
ship went in.

The face is a new 14x16 heavy grotesque with one-pixel chamfers — squarer
than the old rounded 16x18 so it reads at the 107-px rail sizes the channel
actually airs at.  The same lockup serves the opening title at 3x and a
segment card at 1x, which is the whole point of drawing it once from data.

Three variants, one switch (GZ_LOGO_VARIANT, default `bos`):

    bos     Ben Bos / Total Design.  Flat, one weight, no bevel, no shadow,
            no keyline.  The zero is a ring and a bar on the face's own
            grid — three units of stroke, forty-five degrees, ends cut
            square — and nothing else.  The baguette survives as a
            proportion, not a picture.  This is the logo.
    slash   The same lockup with a top-lit bevel and the loaf drawn as a
            loaf: crust, scores, tips.  The illustrated reading.
    orbit   The ring painted through the wormhole.  Kept for the record.

    python3 gzlogo.py OUT.png [--variant bos|slash|orbit]

renders a 640x480 review still.
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzpal as P

FACE_W, FACE_H = 14, 16

# ── the face ──────────────────────────────────────────────────────────────
# Three-pixel stems, one-pixel chamfers, counters left open.  Only the letters
# the programme needs: GROUND ZERO and the name card's SASHA.
_F = {
"G": [
".############.",
"##############",
"###........###",
"###...........",
"###...........",
"###...........",
"###...........",
"###....#######",
"###....#######",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
".############.",
],
"R": [
"#############.",
"##############",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
"#############.",
"###....###....",
"###.....###...",
"###......###..",
"###.......###.",
"###........###",
"###........###",
"###........###",
"###........###",
],
"O": [
".############.",
"##############",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
".############.",
],
"U": [
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
".############.",
],
"N": [
"######.....###",
"######.....###",
"###.###....###",
"###.###....###",
"###.###....###",
"###..###...###",
"###..###...###",
"###..###...###",
"###...###..###",
"###...###..###",
"###...###..###",
"###....###.###",
"###....###.###",
"###....###.###",
"###.....######",
"###.....######",
],
"D": [
"############..",
"#############.",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"#############.",
"############..",
],
"Z": [
"##############",
"##############",
"..........####",
".........####.",
"........####..",
".......####...",
"......####....",
".....####.....",
"....####......",
"...####.......",
"..####........",
".####.........",
"####..........",
"###...........",
"##############",
"##############",
],
"E": [
"##############",
"##############",
"###...........",
"###...........",
"###...........",
"###...........",
"############..",
"############..",
"###...........",
"###...........",
"###...........",
"###...........",
"###...........",
"###...........",
"##############",
"##############",
],
"S": [
".############.",
"##############",
"###........###",
"###...........",
"###...........",
"####..........",
".#########....",
"..##########..",
"....#########.",
"..........####",
"...........###",
"...........###",
"###........###",
"###........###",
"##############",
".############.",
],
"A": [
".############.",
"##############",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
"##############",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
],
"H": [
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"##############",
"##############",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
"###........###",
],
}
FACE = {ch: [[c == "#" for c in row] for row in rows] for ch, rows in _F.items()}

for _ch, _g in FACE.items():
    assert len(_g) == FACE_H, (_ch, len(_g))
    for _r in _g:
        assert len(_r) == FACE_W, (_ch, len(_r))

GAP = 2            # between glyphs, in face pixels, before tracking
PAD = 2            # keyline room round the word, in face pixels
SHADOW = 1         # hard cast shadow, in face pixels

# The baguette, in units of the glyph cell it crosses.
BREAD_LEN = 1.62   # of cell height — the tips clear the ring both ends
BREAD_THICK = 0.30 # of cell width
BREAD_ANGLE = 58   # degrees from horizontal, rising to the right: a slash
BREAD_SCORES = 3

# The wormhole, for the orbit variant: light blue, white, pink and no more.
WORM_STOPS = [(0.0, P.HAIR[1]), (0.5, P.WHITE), (1.0, P.PINK[1])]

VARIANTS = ("bos", "slash", "orbit")
VARIANT = os.environ.get("GZ_LOGO_VARIANT", "bos")
assert VARIANT in VARIANTS, VARIANT

# The Bos mark, in face units: a ring and a bar, same stroke, on the grid.
BOS_R = 8          # outer radius — the mark is a 16-unit square, the face height
BOS_STROKE = 3     # the face's stem, so the mark and the letters are one weight
BOS_BAR = 22       # bar length; at 45° its box is 15.6 units, inside the square


def _outline(mask):
    grown = mask.copy()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
    return ImageChops.subtract(grown, mask)


def _bevel(dst, mask, ramp, scale, keyline=True, shadow=True):
    """Paint a mask as a flat, top-lit solid.

    Shadow first (a hard offset copy in deep ink), then the keyline, then the
    body, then one scaled row of highlight where nothing sits above a pixel
    and one of shade where nothing sits below.  That is the whole 16-bit
    vocabulary this logo allows itself."""
    if shadow:
        dst.paste(P.INK_DEEP, (0, 0),
                  ImageChops.offset(mask, SHADOW * scale, SHADOW * scale))
    if keyline:
        dst.paste(P.KEYLINE, (0, 0), _outline(mask))
    hi = ImageChops.subtract(mask, ImageChops.offset(mask, 0, scale))
    lo = ImageChops.subtract(mask, ImageChops.offset(mask, 0, -scale))
    dst.paste(ramp[2], (0, 0), mask)
    dst.paste(ramp[3], (0, 0), lo)
    dst.paste(ramp[0], (0, 0), hi)


def _flat(dst, mask, colour):
    dst.paste(colour, (0, 0), mask)


def _bos_mark(dst, cx, cy, unit, colour):
    """Ring and bar.  PIL cuts the bar's ends square, which is the point:
    a geometric slash, not a drawn one."""
    import math
    d = ImageDraw.Draw(dst)
    r = BOS_R * unit
    d.ellipse([cx - r, cy - r, cx + r - 1, cy + r - 1], outline=colour,
              width=BOS_STROKE * unit)
    half = BOS_BAR * unit / 2 * math.cos(math.radians(45))
    d.line([(cx - half, cy + half), (cx + half, cy - half)], fill=colour,
           width=BOS_STROKE * unit)


def _stamp(mask, glyph, x0, y0, scale):
    d = ImageDraw.Draw(mask)
    for gy, row in enumerate(glyph):
        for gx, on in enumerate(row):
            if on:
                x = x0 + gx * scale
                y = y0 + gy * scale
                d.rectangle([x, y, x + scale - 1, y + scale - 1], fill=255)


def _worm_paint(dst, mask, x0, w):
    """Colour a mask left to right through the wormhole stops."""
    px = dst.load()
    mp = mask.load()
    mw, mh = mask.size
    for y in range(mh):
        for x in range(mw):
            if not mp[x, y]:
                continue
            t = min(1.0, max(0.0, (x - x0) / max(1, w)))
            for i in range(len(WORM_STOPS) - 1):
                a, ca = WORM_STOPS[i]
                b, cb = WORM_STOPS[i + 1]
                if a <= t <= b:
                    u = (t - a) / (b - a)
                    px[x, y] = tuple(int(ca[k] + (cb[k] - ca[k]) * u)
                                     for k in range(3)) + (255,)
                    break


def _baguette(dst, cx, cy, cell_w, cell_h, scale):
    """A pointed loaf across the zero, bottom-left to top-right.

    Drawn as a mask and bevelled like the letters so it is the same material
    as the type — a prop in the lockup, not a sticker on it."""
    import math
    L = BREAD_LEN * cell_h
    T = max(3 * scale, int(BREAD_THICK * cell_w))
    a = math.radians(BREAD_ANGLE)
    ux, uy = math.cos(a), -math.sin(a)          # along the loaf
    vx, vy = -uy, ux                             # across it
    tip = T * 0.9
    half = L / 2
    pts = [
        (cx + ux * half, cy + uy * half),                                # right tip
        (cx + ux * (half - tip) + vx * T / 2, cy + uy * (half - tip) + vy * T / 2),
        (cx - ux * (half - tip) + vx * T / 2, cy - uy * (half - tip) + vy * T / 2),
        (cx - ux * half, cy - uy * half),                                # left tip
        (cx - ux * (half - tip) - vx * T / 2, cy - uy * (half - tip) - vy * T / 2),
        (cx + ux * (half - tip) - vx * T / 2, cy + uy * (half - tip) - vy * T / 2),
    ]
    mask = Image.new("L", dst.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    _bevel(dst, mask, P.BREAD, scale)

    # The scores: short diagonal cuts along the crust, drawn off-axis the way
    # a baker slashes them, so the loaf reads as bread and not as a bar.
    d = ImageDraw.Draw(dst)
    sa = math.radians(BREAD_ANGLE - 40)
    sx, sy = math.cos(sa), -math.sin(sa)
    for i in range(BREAD_SCORES):
        t = (i - (BREAD_SCORES - 1) / 2) * (L * 0.22)
        px_, py_ = cx + ux * t, cy + uy * t
        d.line([(px_ - sx * T * 0.28, py_ - sy * T * 0.28),
                (px_ + sx * T * 0.28, py_ + sy * T * 0.28)],
               fill=P.BREAD[4], width=scale)


def word(text, scale=1, ramp=P.BONE, tracking=0, slash_last=False,
         orbit_last=False, bos_last=False, flat=False):
    """One word of the face as an RGBA image.

    `tracking` adds face pixels between glyphs.  `flat` paints the body
    colour only — no bevel, shadow or keyline.  For the zero of ZERO:
    `bos_last` replaces the final glyph with the ring-and-bar mark,
    `slash_last` draws the baguette through it, `orbit_last` paints it
    through the wormhole."""
    assert sum((slash_last, orbit_last, bos_last)) <= 1
    n = len(text)
    adv = (FACE_W + GAP + tracking) * scale
    last_w = (2 * BOS_R if bos_last else FACE_W) * scale
    letters_w = (n - 1) * FACE_W * scale + last_w + (n - 1) * (GAP + tracking) * scale
    over = int(FACE_H * scale * (BREAD_LEN - 1) / 2) + 2 * scale if slash_last else 0
    w = letters_w + 2 * PAD * scale + SHADOW * scale + 2 * over
    h = FACE_H * scale + 2 * PAD * scale + SHADOW * scale + 2 * over
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x0 = PAD * scale + over
    y0 = PAD * scale + over

    mask = Image.new("L", (w, h), 0)
    last_mask = Image.new("L", (w, h), 0)
    for i, ch in enumerate(text):
        if i == n - 1 and bos_last:
            break
        glyph = FACE[ch]
        target = last_mask if (i == n - 1 and (slash_last or orbit_last)) else mask
        _stamp(target, glyph, x0 + i * adv, y0, scale)

    if flat:
        _flat(img, mask, ramp[2])
    else:
        _bevel(img, mask, ramp, scale)
    lx = x0 + (n - 1) * adv
    if bos_last:
        _bos_mark(img, lx + BOS_R * scale, y0 + FACE_H * scale // 2, scale,
                  ramp[2])
    elif orbit_last:
        _bevel(img, last_mask, ramp, scale)
        body = ImageChops.subtract(
            last_mask, ImageChops.lighter(
                ImageChops.subtract(last_mask, ImageChops.offset(last_mask, 0, scale)),
                ImageChops.subtract(last_mask, ImageChops.offset(last_mask, 0, -scale))))
        _worm_paint(img, body, lx, FACE_W * scale)
    elif slash_last:
        _bevel(img, last_mask, ramp, scale)
        _baguette(img, lx + FACE_W * scale / 2, y0 + FACE_H * scale / 2,
                  FACE_W * scale, FACE_H * scale, scale)
    img.info["letters"] = (x0, y0, letters_w, FACE_H * scale)
    return img


def last_cell_w(variant=None):
    """Width, in face units, of the cell the zero occupies."""
    return 2 * BOS_R if (variant or VARIANT) == "bos" else FACE_W


def mark(scale=1, variant=None):
    """The zero alone — the mark that stands for the programme where the
    whole lockup will not fit (a segment card, a bug)."""
    variant = variant or VARIANT
    if variant == "bos":
        return word("O", scale=scale, ramp=P.ARMOUR, bos_last=True, flat=True)
    return word("O", scale=scale, ramp=P.ARMOUR, slash_last=True)


def lockup(scale=1, variant=None):
    """GROUND over ZERØ.  Returns (top, bottom, x-offset of top so that the
    two words' letters share a left edge and a right edge)."""
    variant = variant or VARIANT
    assert variant in VARIANTS, variant
    flat = variant == "bos"
    bot = word("ZERO", scale=3 * scale, ramp=P.ARMOUR, flat=flat,
               bos_last=(variant == "bos"),
               slash_last=(variant == "slash"),
               orbit_last=(variant == "orbit"))
    bx, by, bw, bh = bot.info["letters"]
    # Track GROUND out until its letters span exactly the width of ZERO's.
    n = len("GROUND")
    natural = n * FACE_W * scale + (n - 1) * GAP * scale
    tracking = max(0, (bw - natural) // ((n - 1) * scale))
    top = word("GROUND", scale=scale, ramp=P.BONE, tracking=tracking, flat=flat)
    tx, ty, tw, th = top.info["letters"]
    # Centre any remainder rather than leave it all on the right.
    top_dx = bx - tx + (bw - tw) // 2
    return top, bot, top_dx


def horizon(d, x0, x1, y, dent_x, dent_w, dent_d, colour, ground):
    """The rule under the title with the landing dent in it.  `ground` fills
    below the dent so the crater reads as a hole, not a kink in a line."""
    hw = dent_w // 2
    pts = [(x0, y), (dent_x - hw, y), (dent_x - hw // 2, y + dent_d),
           (dent_x + hw // 2, y + dent_d), (dent_x + hw, y), (x1, y)]
    d.polygon([(dent_x - hw, y), (dent_x - hw // 2, y + dent_d),
               (dent_x + hw // 2, y + dent_d), (dent_x + hw, y)], fill=ground)
    d.line(pts, fill=colour, width=2)


def review_card(variant=None):
    variant = variant or VARIANT
    """A 640x480 still for looking at the lockup on its own."""
    W, H = 320, 240
    img = Image.new("RGB", (W, H), P.INK)
    top, bot, dx = lockup(1, variant)
    bx, by, bw, bh = bot.info["letters"]
    x = (W - bw) // 2 - bx
    y = 62
    img.paste(top, (x + dx, y), top)
    img.paste(bot, (x, y + top.size[1] + 2), bot)
    d = ImageDraw.Draw(img)
    zero_cx = x + bx + bw - FACE_W * 3 // 2
    horizon(d, 40, W - 40, 172, zero_cx, 30, 6, P.BONE[2], P.INK_DEEP)
    return img.resize((640, 480), Image.NEAREST)


if __name__ == "__main__":
    out = sys.argv[1]
    variant = VARIANT
    if "--variant" in sys.argv:
        variant = sys.argv[sys.argv.index("--variant") + 1]
    review_card(variant).save(out)
    print(out)
