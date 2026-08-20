"""The GROUND ZERO hero sprite.

A Bubblegum Crisis hardsuit, in station colours: the silhouette is what does
the work at this size — big rounded-square pauldrons carried high and flared
well outside the body, a narrow waist, hip flares, chunky forearm bracers,
heavy boots, and a full-face helmet with a crown fin, swept-back ear fins and
a wraparound visor.  Those are the Knight Sabers' read; the marigold shell and
the teal core are Channel Z0's.

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

W, H = 36, 58

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
    """Planted, mic down, looking very slightly off camera.

    Proportion is the whole battle at 58 px.  The first pass gave her
    Knight-Saber shoulders at full reference scale and everything from the
    helmet to the bracers fused into one orange mass — so the pauldrons are
    pulled in, and a run of dark undersuit is kept visible between pauldron and
    bracer, and between hip and boot.  Armour reads as armour only where
    something not-armour separates the plates.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── backpack, behind everything ───────────────────────────────────────
    pack = _fill(lambda d: d.rounded_rectangle([14, 18, 22, 30], 3, fill=255))
    shade(img, pack, P.STEEL)
    thrust = _fill(lambda d: (
        d.rounded_rectangle([10, 24, 13, 32], 1, fill=255),
        d.rounded_rectangle([23, 24, 26, 32], 1, fill=255)))
    shade(img, thrust, P.STEEL)

    # ── legs: armour thigh, dark shin, heavy boot ─────────────────────────
    thighs = _fill(lambda d: (
        d.rounded_rectangle([13, 40, 17, 47], 2, fill=255),
        d.rounded_rectangle([19, 40, 23, 47], 2, fill=255)))
    shade(img, thighs, P.ARMOUR)

    shins = _fill(lambda d: (
        d.rectangle([14, 46, 17, 52], fill=255),
        d.rectangle([19, 46, 22, 52], fill=255)))
    shade(img, shins, P.SUIT)

    boots = _fill(lambda d: (
        d.polygon([(11, 51), (17, 51), (17, 57), (9, 57)], fill=255),
        d.polygon([(19, 51), (25, 51), (27, 57), (19, 57)], fill=255)))
    shade(img, boots, P.ARMOUR)
    soles = _fill(lambda d: (
        d.rectangle([9, 56, 17, 57], fill=255),
        d.rectangle([19, 56, 27, 57], fill=255)))
    shade(img, soles, P.STEEL, keyline=False)

    # ── far arm, bracer and the microphone ────────────────────────────────
    arm_r = _fill(lambda d: d.rounded_rectangle([26, 25, 31, 36], 2, fill=255))
    shade(img, arm_r, P.SUIT)
    brace_r = _fill(lambda d: d.rounded_rectangle([25, 35, 32, 44], 2, fill=255))
    shade(img, brace_r, P.ARMOUR)
    mic = _fill(lambda d: (
        d.ellipse([27, 44, 31, 48], fill=255),
        d.rectangle([28, 47, 30, 55], fill=255)))
    shade(img, mic, P.STEEL)

    # ── hips and the narrow waist above them ──────────────────────────────
    hips = _fill(lambda d: d.polygon(
        [(12, 34), (24, 34), (23, 41), (13, 41)], fill=255))
    shade(img, hips, P.ARMOUR)
    waist = _fill(lambda d: d.rectangle([15, 29, 21, 35], fill=255))
    shade(img, waist, P.SUIT, keyline=False)

    # ── chest plate ───────────────────────────────────────────────────────
    chest = _fill(lambda d: d.polygon(
        [(13, 19), (23, 19), (22, 27), (21, 31), (15, 31), (14, 27)], fill=255))
    shade(img, chest, P.ARMOUR)
    seam = _fill(lambda d: d.rectangle([18, 20, 18, 30], fill=255))
    img.paste(P.ARMOUR[4], (0, 0), seam)

    core = _fill(lambda d: d.ellipse([15, 21, 21, 27], fill=255))
    img.paste(P.TEAL[2], (0, 0), core)
    img.paste(P.TEAL[1], (0, 0), _fill(lambda d: d.ellipse([16, 22, 20, 26],
                                                           fill=255)))
    img.paste(P.TEAL[0], (0, 0), _fill(lambda d: d.ellipse([17, 23, 19, 25],
                                                           fill=255)))

    # ── pauldrons: flared and rounded-square, but pulled in ───────────────
    pauldrons = _fill(lambda d: (
        d.polygon([(4, 21), (6, 17), (12, 17), (13, 22), (12, 26), (5, 26)],
                  fill=255),
        d.polygon([(32, 21), (30, 17), (24, 17), (23, 22), (24, 26), (31, 26)],
                  fill=255)))
    shade(img, pauldrons, P.ARMOUR)

    arm_l = _fill(lambda d: d.rounded_rectangle([5, 25, 10, 36], 2, fill=255))
    shade(img, arm_l, P.SUIT)
    brace_l = _fill(lambda d: d.rounded_rectangle([4, 35, 11, 44], 2, fill=255))
    shade(img, brace_l, P.ARMOUR)

    # ── head ──────────────────────────────────────────────────────────────
    neck = _fill(lambda d: d.rectangle([16, 14, 20, 20], fill=255))
    shade(img, neck, P.SUIT, keyline=False)

    # Fins sweep back and down off the temples.  Angled up they read as ears.
    fins = _fill(lambda d: (
        d.polygon([(5, 17), (11, 9), (12, 13), (8, 19)], fill=255),
        d.polygon([(31, 17), (25, 9), (24, 13), (28, 19)], fill=255)))
    shade(img, fins, P.ARMOUR)

    # The dome needs real height above the visor or the head reads as a visor
    # with some orange around it rather than as a helmet.
    helm = _fill(lambda d: (
        d.ellipse([11, 0, 25, 15], fill=255),
        d.polygon([(12, 8), (24, 8), (23, 18), (13, 18)], fill=255)))
    shade(img, helm, P.ARMOUR)

    crownfin = _fill(lambda d: d.polygon(
        [(17, 0), (20, 2), (20, 8), (17, 8)], fill=255))
    shade(img, crownfin, P.ARMOUR, keyline=False)

    chin = _fill(lambda d: d.polygon(
        [(14, 14), (22, 14), (21, 18), (15, 18)], fill=255))
    shade(img, chin, P.STEEL, keyline=False)

    # ── the visor: most of the face, the way these helmets are ────────────
    visor = _fill(lambda d: d.polygon(
        [(12, 7), (24, 7), (23, 14), (13, 14)], fill=255))
    img.paste(P.KEYLINE, (0, 0), _outline(visor))
    img.paste(P.VISOR[3], (0, 0), visor)
    img.paste(P.VISOR[2], (0, 0),
              _fill(lambda d: d.polygon([(13, 8), (23, 8), (22, 12), (14, 12)],
                                        fill=255)))
    img.paste(P.VISOR[1], (0, 0),
              _fill(lambda d: d.polygon([(13, 8), (18, 8), (17, 11), (14, 11)],
                                        fill=255)))
    img.paste(P.VISOR[0], (0, 0),
              _fill(lambda d: d.rectangle([14, 8, 16, 9], fill=255)))
    return img


HERO = None
HERO_LIT = None


def load():
    """Two copies: the moonlit one, and the one a lightning strike makes."""
    global HERO, HERO_LIT
    if HERO is None:
        HERO = build()
        HERO_LIT = _relight(HERO)
    return HERO, HERO_LIT


def _relight(src):
    """A lightning frame does not re-render the sprite, it re-maps its palette
    — which is exactly what the hardware would have done."""
    out = src.copy()
    px = out.load()
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if not a:
                continue
            px[x, y] = P.FLASH_MAP.get((r, g, b), (r, g, b)) + (255,)
    return out
