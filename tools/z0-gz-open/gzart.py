"""The GROUND ZERO hero sprite.

SASHA ZERO: slender, tall-legged, anime proportions — a head about a fifth of
her height, large eyes, and long hair with a silhouette of its own.  The
Bubblegum Crisis heritage survives as *accents* rather than as a shell: a
chest plate, a belt, gloves and boots over a dark bodysuit, not a hardsuit.
Marigold and teal are Channel Z0's; the pale blue hair with the pink streak is
hers.

She carries a baguette.  It is the microphone, and it has to read as bread at
twelve pixels, which is why it gets its own ramp and three score marks.

Nothing on her is a crosshair.  She is not here to aim at anyone.

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

W, H = 34, 62

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


def _wobble(pts, dx):
    return [(x + dx if y > 18 else x, y) for x, y in pts]


def build():
    """Standing, hair and scarf taking the wind, baguette up like a mic."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ── hair, behind everything: two long locks framing the whole figure ──
    hair_back = _fill(lambda d: d.polygon(
        [(10, 4), (24, 4), (27, 17), (26, 32), (24, 44), (20, 35),
         (20, 13), (14, 13), (14, 35), (10, 44), (8, 32), (7, 17)], fill=255))
    shade(img, hair_back, P.HAIR)
    streak = _fill(lambda d: d.polygon(
        [(8, 14), (11, 14), (12, 33), (9, 35)], fill=255))
    img.paste(P.PINK[2], (0, 0), streak)
    img.paste(P.PINK[1], (0, 0), _fill(lambda d: d.polygon(
        [(8, 14), (9, 14), (10, 33), (9, 34)], fill=255)))

    # ── the scarf, taking the wind to frame left ─────────────────────────
    # A ribbon, not a blob: it has to keep a constant width along its length
    # or it reads as a pink cloud stuck to her shoulder.
    scarf = _fill(lambda d: d.polygon(
        [(13, 17), (13, 20), (9, 22), (5, 20), (1, 24), (2, 26), (6, 23),
         (10, 25), (13, 23)], fill=255))
    shade(img, scarf, P.PINK)

    # ── legs: long, slim, dark ────────────────────────────────────────────
    legs = _fill(lambda d: (
        d.polygon([(14, 33), (17, 33), (17, 53), (14, 53)], fill=255),
        d.polygon([(19, 33), (22, 33), (22, 53), (19, 53)], fill=255)))
    shade(img, legs, P.SUIT)

    # Two boots with a gap between them.  Butted together at x18/19 they merged
    # into one orange mass and she appeared to be wearing a long skirt.
    boots = _fill(lambda d: (
        d.polygon([(13, 51), (17, 51), (17, 60), (11, 60)], fill=255),
        d.polygon([(20, 51), (24, 51), (26, 60), (20, 60)], fill=255)))
    shade(img, boots, P.ARMOUR)

    # ── far arm ───────────────────────────────────────────────────────────
    arm_r = _fill(lambda d: d.polygon(
        [(22, 19), (25, 19), (26, 31), (23, 31)], fill=255))
    shade(img, arm_r, P.SUIT)
    glove_r = _fill(lambda d: d.rectangle([23, 29, 26, 34], fill=255))
    shade(img, glove_r, P.ARMOUR)

    # ── hips ──────────────────────────────────────────────────────────────
    hips = _fill(lambda d: d.polygon(
        [(13, 29), (22, 29), (23, 35), (12, 35)], fill=255))
    shade(img, hips, P.ARMOUR)

    # ── torso ─────────────────────────────────────────────────────────────
    torso = _fill(lambda d: d.polygon(
        [(13, 17), (22, 17), (21, 25), (21, 31), (14, 31), (14, 25)],
        fill=255))
    shade(img, torso, P.SUIT)
    plate = _fill(lambda d: d.polygon(
        [(14, 18), (21, 18), (20, 25), (15, 25)], fill=255))
    shade(img, plate, P.ARMOUR)

    core = _fill(lambda d: d.ellipse([16, 20, 19, 23], fill=255))
    img.paste(P.TEAL[2], (0, 0), core)
    img.paste(P.TEAL[0], (0, 0), _fill(lambda d: d.rectangle([17, 21, 18, 22],
                                                             fill=255)))

    # ── near arm, raised, and the baguette it is holding ─────────────────
    arm_l = _fill(lambda d: d.polygon(
        [(10, 19), (13, 19), (13, 28), (10, 28)], fill=255))
    shade(img, arm_l, P.SUIT)
    glove_l = _fill(lambda d: d.rectangle([10, 25, 13, 30], fill=255))
    shade(img, glove_l, P.ARMOUR)

    bread = _fill(lambda d: d.polygon(
        [(10, 28), (13, 30), (18, 18), (16, 15), (13, 16)], fill=255))
    shade(img, bread, P.BREAD)
    for a, b in (((12, 25), (14, 26)), ((14, 21), (16, 22)),
                 ((15, 18), (17, 19))):
        img.paste(P.BREAD[4], (0, 0),
                  _fill(lambda d, a=a, b=b: d.line([a, b], fill=255)))

    # ── head ──────────────────────────────────────────────────────────────
    neck = _fill(lambda d: d.rectangle([16, 12, 19, 17], fill=255))
    shade(img, neck, P.SKIN, keyline=False)

    face = _fill(lambda d: d.ellipse([11, 3, 23, 16], fill=255))
    shade(img, face, P.SKIN)

    # Large eyes, and a highlight in each.  At this size the eye IS the face.
    for ex in (13, 18):
        img.paste(P.KEYLINE, (0, 0),
                  _fill(lambda d, ex=ex: d.rectangle([ex, 8, ex + 2, 12],
                                                     fill=255)))
        img.paste(P.EYE[2], (0, 0),
                  _fill(lambda d, ex=ex: d.rectangle([ex, 9, ex + 2, 12],
                                                     fill=255)))
        img.paste(P.EYE[1], (0, 0),
                  _fill(lambda d, ex=ex: d.rectangle([ex, 11, ex + 2, 12],
                                                     fill=255)))
        img.paste(P.EYE[0], (0, 0),
                  _fill(lambda d, ex=ex: d.point((ex, 9), fill=255)))
    img.paste(P.SKIN[3], (0, 0), _fill(lambda d: d.point((17, 14), fill=255)))
    img.paste(P.PINK[2], (0, 0),
              _fill(lambda d: d.line([(16, 15), (18, 15)], fill=255)))

    # ── fringe over the top of the head ──────────────────────────────────
    fringe = _fill(lambda d: d.polygon(
        [(10, 3), (24, 3), (25, 11), (22, 7), (20, 10), (17, 6), (14, 10),
         (12, 7), (9, 11)], fill=255))
    shade(img, fringe, P.HAIR)

    # ── antennae.  Cheapest possible way to say "not from here". ─────────
    ant = _fill(lambda d: (
        d.line([(14, 4), (12, 0)], fill=255),
        d.line([(20, 4), (22, 0)], fill=255)))
    img.paste(P.HAIR[3], (0, 0), ant)
    for tip in ((12, 0), (22, 0)):
        img.paste(P.TEAL[1], (0, 0),
                  _fill(lambda d, t=tip: d.ellipse([t[0] - 1, t[1], t[0] + 1,
                                                    t[1] + 2], fill=255)))
    return img


ROCKET_W, ROCKET_H = 28, 15


def rocket():
    """A rocket, pointing right.  Used in space, in the wormhole, and — turned
    forty-five degrees and on fire — coming down over the lake."""
    img = Image.new("RGBA", (ROCKET_W, ROCKET_H), (0, 0, 0, 0))

    fins = _fill_sz(ROCKET_W, ROCKET_H, lambda d: (
        d.polygon([(4, 4), (9, 4), (5, 0)], fill=255),
        d.polygon([(4, 10), (9, 10), (5, 14)], fill=255)))
    shade(img, fins, P.PINK)

    body = _fill_sz(ROCKET_W, ROCKET_H,
                    lambda d: d.rounded_rectangle([2, 4, 20, 10], 2, fill=255))
    shade(img, body, P.BONE)

    nose = _fill_sz(ROCKET_W, ROCKET_H,
                    lambda d: d.polygon([(18, 4), (27, 7), (18, 10)], fill=255))
    shade(img, nose, P.ARMOUR)

    bell = _fill_sz(ROCKET_W, ROCKET_H,
                    lambda d: d.polygon([(0, 3), (3, 5), (3, 9), (0, 11)],
                                        fill=255))
    shade(img, bell, P.STEEL)

    port = _fill_sz(ROCKET_W, ROCKET_H,
                    lambda d: d.ellipse([9, 5, 14, 10], fill=255))
    img.paste(P.KEYLINE, (0, 0), _outline_sz(ROCKET_W, ROCKET_H, port))
    img.paste(P.VISOR[3], (0, 0), port)
    img.paste(P.VISOR[1], (0, 0),
              _fill_sz(ROCKET_W, ROCKET_H,
                       lambda d: d.ellipse([10, 6, 12, 8], fill=255)))
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
