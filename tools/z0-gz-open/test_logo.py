#!/usr/bin/env python3
"""Checks on the GROUND ZERO lockup.  Run before a build; CI runs it too."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gzlogo
import gzpal as P

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def test_default_is_bos():
    check(gzlogo.VARIANT == "bos", "default variant is %r, not bos" % gzlogo.VARIANT)


def test_lockup_aligns():
    """GROUND's letters must sit inside ZERO's span, both edges within a
    face pixel: the tracking is computed, not eyeballed."""
    for v in gzlogo.VARIANTS:
        top, bot, dx = gzlogo.lockup(1, v)
        tx, ty, tw, th = top.info["letters"]
        bx, by, bw, bh = bot.info["letters"]
        left = (tx + dx) - bx
        right = (bx + bw) - (tx + dx + tw)
        check(0 <= left <= 3 and 0 <= right <= 3,
              "%s: GROUND misaligned (left %d right %d)" % (v, left, right))


def test_mark_is_square_and_flat():
    m = gzlogo.mark(3, "bos")
    x, y, w, h = m.info["letters"]
    check(w == h == 2 * gzlogo.BOS_R * 3, "bos mark is %dx%d, not square" % (w, h))
    colours = {c[:3] for _, c in m.getcolors(1 << 16) if c[3]}
    check(colours == {P.ARMOUR[2]}, "bos mark is not one flat colour: %r" % colours)


def test_no_crosshair():
    """A ring with one diagonal bar.  The horizontal and vertical midlines
    inside the ring must be EMPTY — a ring plus crossed lines is a gunsight
    whatever the caption calls it.  This is the standing constraint as code."""
    s = 4
    m = gzlogo.mark(s, "bos")
    x, y, w, h = m.info["letters"]
    cx, cy = x + w // 2, y + h // 2
    px = m.load()
    r = (gzlogo.BOS_R - gzlogo.BOS_STROKE - 1) * s
    for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r)):
        check(px[cx + dx, cy + dy][3] == 0,
              "crosshair: mark is opaque on the midline at %+d,%+d" % (dx, dy))
    # and the bar IS there, on the rising diagonal
    d = int(r * 0.7)
    check(px[cx + d, cy - d][3] and px[cx - d, cy + d][3], "the bar is missing")


def test_deterministic():
    a = gzlogo.word("ZERO", 2, P.ARMOUR, bos_last=True, flat=True).tobytes()
    b = gzlogo.word("ZERO", 2, P.ARMOUR, bos_last=True, flat=True).tobytes()
    check(a == b, "word() is not deterministic")


def test_every_variant_renders():
    for v in gzlogo.VARIANTS:
        img = gzlogo.review_card(v)
        check(img.size == (640, 480), "%s: review card is %r" % (v, img.size))


def test_face_covers_the_words():
    for ch in "GROUNDZEROSASHA":
        check(ch in gzlogo.FACE, "face lacks %r" % ch)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    for f in FAILS:
        print("FAIL", f)
    print("%d tests, %d failures" % (len(tests), len(FAILS)))
    sys.exit(1 if FAILS else 0)
