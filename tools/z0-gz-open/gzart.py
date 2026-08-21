"""The GROUND ZERO hero sprite.

SASHA ZERO, built on Zero from Mega Man Zero: the enormous ponytail, the
crested helmet with a gem set in the brow, gems on the shoulders and knees,
red armour with gold trim over a dark bodysuit, and a slim, long-legged build.

Three things are hers rather than his.  The ponytail is pale blue with a pink
streak instead of blonde; the gems are the station's teal instead of green; and
what she carries at her side, in the hand and at the angle Zero carries the
Z-Saber, is a baguette.  It is the microphone.  It has to read as bread at
twelve pixels, which is why it gets its own ramp and three score marks.

The gold is Channel Z0's marigold, so the reference and the brand land on the
same colour and neither has to give way.

Nothing on her is a crosshair.  She is not here to aim at anyone.

The organic vessel below is deliberately NOT a rocket: no nose cone, no fins,
no engine bell.  It is a shell with ribs, a membrane, a lit core and trailing
filaments — something grown, that came a long way, and broke.

Built from primitives into a 36x58 RGBA rather than hand-typed as ASCII art.
At this size the difference that matters is not authorship, it is *shading*:
a 16-bit sprite is lit — highlight edge, mid body, shadow edge, hard black
keyline — and getting that consistent across twenty separate body parts by
hand-typing colour keys is how you end up with a character lit from four
directions at once.  Here one `shade()` call does every part, from one light,
which is off frame left where the moon is.

Palette entries come from gzpal so the sprite cannot introduce a colour the
rest of the frame does not have.
"""
from PIL import Image, ImageChops, ImageDraw

import gzpal as P

W, H = 40, 64

# One light, off frame left.  Every part is shaded against this and nothing
# else, which is what stops the figure reading as a collage.
LIGHT_DX = -1


def _mask():
    return Image.new("L", (W, H), 0)


def _edges(mask):
    """Left-lit and right-shadowed one-pixel edges of a filled mask."""
    shifted_r = ImageChops.offset(mask, 1, 0)
    shifted_l = ImageChops.offset(mask, -1, 0)
    hi = ImageChops.subtract(mask, shifted_r)      # nothing to my left
    lo = ImageChops.subtract(mask, shifted_l)      # nothing to my right
    return hi, lo


def _outline(mask):
    grown = mask.copy()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
    return ImageChops.subtract(grown, mask)


def shade(dst, mask, ramp, keyline=True, hi_i=0, mid_i=2, lo_i=4):
    """Paint a filled mask as a lit solid: highlight edge, body, shadow edge."""
    hi, lo = _edges(mask)
    if keyline:
        dst.paste(P.KEYLINE, (0, 0), _outline(mask))
    dst.paste(ramp[mid_i], (0, 0), mask)
    dst.paste(ramp[lo_i], (0, 0), lo)
    dst.paste(ramp[hi_i], (0, 0), hi)


def _fill(shape_fn):
    m = _mask()
    shape_fn(ImageDraw.Draw(m))
    return m


def build():
    """Standing, ponytail taking the wind, baguette held low at her side."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── the ponytail: the single most identifiable thing about the design ──
    # It attaches behind the helmet, sweeps out and falls past the knee.  At
    # this size it is most of the silhouette, so it is drawn first and big.
    tail = _fill(lambda d: d.polygon(
        [(16, 11), (12, 14), (6, 24), (3, 38), (4, 50), (8, 60), (12, 62),
         (11, 57), (8, 48), (8, 36), (11, 25), (16, 17)], fill=255))
    shade(img, tail, P.HAIR)
    streak = _fill(lambda d: d.polygon(
        [(14, 13), (10, 24), (7, 38), (8, 50), (11, 59), (12, 55), (10, 47),
         (10, 37), (13, 25), (16, 16)], fill=255))
    img.paste(P.PINK[2], (0, 0), streak)
    img.paste(P.PINK[1], (0, 0), _fill(lambda d: d.polygon(
        [(14, 13), (11, 24), (9, 38), (10, 50), (11, 55), (11, 47), (12, 37),
         (14, 25), (16, 16)], fill=255)))
    band = _fill(lambda d: d.polygon(
        [(13, 10), (17, 12), (15, 17), (11, 15)], fill=255))
    shade(img, band, P.ARMOUR)

    # ── legs ──────────────────────────────────────────────────────────────
    legs = _fill(lambda d: (
        d.rectangle([17, 38, 20, 55], fill=255),
        d.rectangle([22, 38, 25, 55], fill=255)))
    shade(img, legs, P.SUIT)

    # Knee guards stay SHORT.  Run from 41 to 47 with boots from 52 they left
    # five pixels of undersuit and the whole lower body read as one red block.
    knees = _fill(lambda d: (
        d.polygon([(16, 42), (21, 42), (21, 46), (16, 46)], fill=255),
        d.polygon([(21, 42), (26, 42), (26, 46), (21, 46)], fill=255)))
    shade(img, knees, P.RED)
    for gx in (18, 23):
        img.paste(P.VISOR[2], (0, 0),
                  _fill(lambda d, gx=gx: d.ellipse([gx, 43, gx + 1, 44],
                                                   fill=255)))

    # A pixel of gap, or the two boots merge into one red trapezoid.
    boots = _fill(lambda d: (
        d.polygon([(16, 54), (20, 54), (20, 62), (13, 62)], fill=255),
        d.polygon([(23, 54), (27, 54), (30, 62), (23, 62)], fill=255)))
    shade(img, boots, P.RED)
    cuffs = _fill(lambda d: (
        d.rectangle([16, 54, 20, 55], fill=255),
        d.rectangle([23, 54, 27, 55], fill=255)))
    shade(img, cuffs, P.ARMOUR, keyline=False)

    # ── far arm, and the baguette held at her side ───────────────────────
    arm_r = _fill(lambda d: d.rounded_rectangle([26, 25, 30, 36], 2, fill=255))
    shade(img, arm_r, P.SUIT)
    brace_r = _fill(lambda d: d.rounded_rectangle([26, 34, 31, 43], 2, fill=255))
    shade(img, brace_r, P.RED)

    # Held low and angled forward, which is how Zero holds the saber when he
    # is not using it.  It is a baguette.
    bread = _fill(lambda d: d.polygon(
        [(28, 42), (31, 41), (38, 55), (36, 58), (33, 56)], fill=255))
    shade(img, bread, P.BREAD)
    for a, b in (((30, 45), (32, 44)), ((32, 49), (34, 48)),
                 ((34, 53), (36, 52))):
        img.paste(P.BREAD[4], (0, 0),
                  _fill(lambda d, a=a, b=b: d.line([a, b], fill=255)))

    # ── hips and waist ────────────────────────────────────────────────────
    hips = _fill(lambda d: d.polygon(
        [(16, 34), (26, 34), (27, 41), (15, 41)], fill=255))
    shade(img, hips, P.RED)
    waist = _fill(lambda d: d.rectangle([18, 31, 24, 36], fill=255))
    shade(img, waist, P.SUIT, keyline=False)

    # ── torso ─────────────────────────────────────────────────────────────
    torso = _fill(lambda d: d.polygon(
        [(16, 19), (26, 19), (25, 28), (25, 33), (17, 33), (17, 28)],
        fill=255))
    shade(img, torso, P.RED)
    crest = _fill(lambda d: d.polygon(
        [(17, 19), (25, 19), (23, 25), (19, 25)], fill=255))
    shade(img, crest, P.ARMOUR, keyline=False)
    core = _fill(lambda d: d.ellipse([19, 25, 23, 29], fill=255))
    img.paste(P.KEYLINE, (0, 0), _outline(core))
    img.paste(P.VISOR[2], (0, 0), core)
    img.paste(P.VISOR[0], (0, 0),
              _fill(lambda d: d.rectangle([20, 26, 21, 27], fill=255)))

    # ── shoulders, each with a gem ────────────────────────────────────────
    pauldrons = _fill(lambda d: (
        d.polygon([(10, 22), (12, 18), (17, 18), (18, 23), (16, 27), (11, 27)],
                  fill=255),
        d.polygon([(31, 22), (29, 18), (24, 18), (23, 23), (25, 27), (30, 27)],
                  fill=255)))
    shade(img, pauldrons, P.RED)
    for gx in (12, 27):
        img.paste(P.KEYLINE, (0, 0),
                  _fill(lambda d, gx=gx: d.ellipse([gx, 21, gx + 3, 24],
                                                   fill=255)))
        img.paste(P.VISOR[2], (0, 0),
                  _fill(lambda d, gx=gx: d.ellipse([gx + 1, 22, gx + 2, 23],
                                                   fill=255)))

    arm_l = _fill(lambda d: d.rounded_rectangle([11, 25, 15, 36], 2, fill=255))
    shade(img, arm_l, P.SUIT)
    brace_l = _fill(lambda d: d.rounded_rectangle([10, 34, 15, 43], 2, fill=255))
    shade(img, brace_l, P.RED)

    # ── head ──────────────────────────────────────────────────────────────
    neck = _fill(lambda d: d.rectangle([19, 15, 23, 20], fill=255))
    shade(img, neck, P.SKIN, keyline=False)

    # ── head ──────────────────────────────────────────────────────────────
    # The face goes down FIRST and the helmet only covers the crown and the
    # sides.  Drawn the other way round the dome came down over the eyes and
    # she had no face at all — which is the one thing Zero's design does not do.
    face = _fill(lambda d: d.ellipse([15, 4, 26, 18], fill=255))
    shade(img, face, P.SKIN)

    for ex in (17, 22):
        img.paste(P.KEYLINE, (0, 0),
                  _fill(lambda d, ex=ex: d.rectangle([ex, 10, ex + 2, 13],
                                                     fill=255)))
        img.paste(P.EYE[2], (0, 0),
                  _fill(lambda d, ex=ex: d.rectangle([ex, 11, ex + 2, 13],
                                                     fill=255)))
        img.paste(P.EYE[0], (0, 0),
                  _fill(lambda d, ex=ex: d.point((ex, 11), fill=255)))
    img.paste(P.SKIN[3], (0, 0),
              _fill(lambda d: d.line([(20, 16), (22, 16)], fill=255)))

    # side guards, down the cheeks, framing the face rather than covering it
    guards = _fill(lambda d: (
        d.polygon([(14, 4), (17, 6), (16, 15), (13, 12)], fill=255),
        d.polygon([(27, 4), (24, 6), (25, 15), (28, 12)], fill=255)))
    shade(img, guards, P.RED)

    fins = _fill(lambda d: (
        d.polygon([(12, 15), (15, 8), (17, 11), (14, 18)], fill=255),
        d.polygon([(29, 15), (26, 8), (24, 11), (27, 18)], fill=255)))
    shade(img, fins, P.RED)

    helm = _fill(lambda d: (
        d.ellipse([14, 0, 27, 12], fill=255),
        d.polygon([(14, 4), (27, 4), (27, 8), (14, 8)], fill=255)))
    helm = ImageChops.subtract(
        helm, _fill(lambda d: d.ellipse([15, 7, 26, 20], fill=255)))
    shade(img, helm, P.RED)

    blade = _fill(lambda d: d.polygon(
        [(17, 0), (24, 0), (27, 5), (14, 5)], fill=255))
    shade(img, blade, P.ARMOUR, keyline=False)

    gem = _fill(lambda d: d.polygon(
        [(20, 1), (23, 4), (20, 7), (17, 4)], fill=255))
    img.paste(P.KEYLINE, (0, 0), _outline(gem))
    img.paste(P.VISOR[2], (0, 0), gem)
    img.paste(P.VISOR[0], (0, 0),
              _fill(lambda d: d.line([(19, 3), (20, 2)], fill=255)))
    return img


ROCKET_W, ROCKET_H = 32, 20


def rocket():
    """Her vessel — grown, not built.

    No nose cone, no fins, no engine bell.  A ribbed shell tapering forward, a
    membrane along the back, a lit core showing through, and filaments trailing
    behind it.  It is meant to look like something that was alive on the way
    here and is not any more.
    """
    img = Image.new("RGBA", (ROCKET_W, ROCKET_H), (0, 0, 0, 0))

    # trailing filaments first, so the hull overlaps their roots
    fil = _fill_sz(ROCKET_W, ROCKET_H, lambda d: (
        d.line([(6, 9), (0, 5), (3, 3)], fill=255),
        d.line([(6, 10), (1, 12), (4, 15)], fill=255),
        d.line([(7, 11), (2, 17)], fill=255)))
    shade(img, fil, P.VISOR, keyline=False)

    membrane = _fill_sz(ROCKET_W, ROCKET_H, lambda d: d.polygon(
        [(9, 7), (17, 1), (24, 3), (22, 7)], fill=255))
    shade(img, membrane, P.VISOR)

    hull = _fill_sz(ROCKET_W, ROCKET_H, lambda d: (
        d.ellipse([4, 5, 26, 15], fill=255),
        d.polygon([(20, 5), (31, 10), (20, 15)], fill=255),
        d.polygon([(9, 12), (18, 12), (16, 18), (11, 17)], fill=255)))
    shade(img, hull, P.SHELL)

    # ribs, which is what stops it reading as a fuselage
    for rx in (10, 13, 16, 19):
        img.paste(P.SHELL[3], (0, 0),
                  _fill_sz(ROCKET_W, ROCKET_H,
                           lambda d, rx=rx: d.arc([rx - 3, 5, rx + 3, 15],
                                                  250, 110, fill=255)))

    core = _fill_sz(ROCKET_W, ROCKET_H, lambda d: d.ellipse([12, 8, 17, 13],
                                                            fill=255))
    img.paste(P.KEYLINE, (0, 0), _outline_sz(ROCKET_W, ROCKET_H, core))
    img.paste(P.VISOR[2], (0, 0), core)
    img.paste(P.VISOR[0], (0, 0),
              _fill_sz(ROCKET_W, ROCKET_H,
                       lambda d: d.ellipse([13, 9, 15, 11], fill=255)))
    return img


def _fill_sz(w, h, shape_fn):
    m = Image.new("L", (w, h), 0)
    shape_fn(ImageDraw.Draw(m))
    return m


def _outline_sz(w, h, mask):
    grown = mask.copy()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
    return ImageChops.subtract(grown, mask)


HERO = None
HERO_LIT = None


ROCKET = None


def load():
    """Sasha, the flash-lit copy of her, and the ship."""
    global HERO, HERO_LIT, ROCKET
    if HERO is None:
        HERO = build()
        HERO_LIT = _relight(HERO)
        ROCKET = rocket()
    return HERO, HERO_LIT


def load_rocket():
    load()
    return ROCKET


def _relight(src):
    """A lightning frame does not re-render the sprite, it re-maps its palette
    — which is exactly what the hardware would have done."""
    out = src.copy()
    px = out.load()
    for y in range(out.size[1]):
        for x in range(out.size[0]):
            r, g, b, a = px[x, y]
            if not a:
                continue
            px[x, y] = P.FLASH_MAP.get((r, g, b), (r, g, b)) + (255,)
    return out
