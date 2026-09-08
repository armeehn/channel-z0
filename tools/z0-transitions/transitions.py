#!/usr/bin/env python3
"""Segment transitions for Channel Z0's own programmes.

A transition is the four seconds between two segments of one show: the card
that says where the programme is going next.  GROUND ZERO, LAB HOUR and the
NEIGHBOURHOOD DESK have no footage yet (their slots play vintage shorts), so
this is the furniture arriving before the house — every segment card exists
the day the first segment does.

Three grammars, one generator, one manifest (segments.json):

    gz    GROUND ZERO.   320x240 doubled to 640x480, the 16-bit vocabulary
          of the opening title: a gradient plate with lit rules slides in,
          the ZERØ mark lands in its own light, the segment name types
          itself in ramp-cut type with a keyline, a sting.
    lab   LAB HOUR.      A drawing sheet.  Paper, a drafting grid, a title
          block, and the segment name revealed by a red cursor then
          DIMENSIONED — the width of the word, in millimetres, because in
          this programme everything gets measured.
    desk  NEIGHBOURHOOD DESK.  An index card drops onto the desk, a pushpin,
          and the segment name is rubber-stamped on it in station red.

Every card is 640x480 (4:3, like the station's other cards — it pillarboxes
exactly inside the on-air rails), 30 fps, 4.0 s, silent-stereo-safe AAC.
Deterministic: no clock, no seeds, no network.  The same checkout renders
the same bytes.

    transitions.py list
    transitions.py render SHOW SLUG OUTDIR      PNG frames
    transitions.py audio  SHOW SLUG OUT.wav
    transitions.py nfo    SHOW SLUG NAME        sidecar to stdout
    transitions.py stills OUTDIR                one review frame per card
"""
import json
import math
import os
import subprocess
import sys
import wave
from array import array

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
GZ_DIR = os.path.join(os.path.dirname(HERE), "z0-gz-open")
sys.path.insert(0, GZ_DIR)
import gzaudio as A          # noqa: E402
import gzfont                # noqa: E402
import gzlogo                # noqa: E402
import gzpal as P            # noqa: E402
import make_frames as MF     # noqa: E402  (the 320x240 text and gradient kit)

FPS = 30
SECONDS = 4.0
FRAMES = int(FPS * SECONDS)
OUT_W, OUT_H = 640, 480

# The synth allocates sixty seconds of buffer for the opening title.  A
# transition is four; telling the echo unit to stop at five keeps a mixdown
# under a second instead of ten, and nothing here is scheduled past the end.
A.N = int((SECONDS + 1.0) * A.RATE)

# House colours, as tools/z0-lib.sh has them.  Mirrored, not imported: this
# file has no shell.
INK = (0x14, 0x14, 0x14)
PAPER = (0xF2, 0xF0, 0xE9)
RED = (0xE0, 0x2A, 0x1B)
INK_2 = (0x6A, 0x6A, 0x6A)
GRID = (0xDA, 0xD7, 0xCE)
RULE_RED = (0xE8, 0xA0, 0x98)
RULE_BLUE = (0xC6, 0xD2, 0xE4)

FADE_OUT = 8              # frames of dip-to-ink at the end of a card

# GROUND ZERO card geometry (320x240).
GZ_PANEL = (70, 170)      # y extent of the stage-select band
GZ_MARK_X = 30
GZ_TEXT_X = 104
GZ_LINE_MAX = 12          # SMALL at 2x from x=104 leaves room for 12 cells
GZ_SUB_MAX = 27          # 216 px of cells from x=104 at 1x
GZ_TYPE_RATE = 2          # frames per character

# TTF cards (640x480).
TTF_TITLE_MAX = 16
TTF_TITLE_PX = 560        # 640 minus the 56 px left margin and a 24 px right one
TTF_SUB_MAX = 34
MM_PER_PX = 25.4 / 96     # the dimension line's unit, at the sheet's 96 dpi

FONT_DIRS = ("/usr/local/share/fonts/jetbrains",
             "/usr/share/fonts/truetype/jetbrains",
             "/usr/share/fonts/jetbrains")
FONT_FILES = {"xb": "JetBrainsMono-ExtraBold.ttf",
              "b": "JetBrainsMono-Bold.ttf",
              "r": "JetBrainsMono-Regular.ttf"}


class FontMissing(RuntimeError):
    pass


_fonts = {}


def font(weight, size):
    """JetBrains Mono, the storefront's face; any monospace if it is absent.
    Raises rather than falling back to PIL's bitmap default, which would
    render a card that looks finished and is not."""
    key = (weight, size)
    if key in _fonts:
        return _fonts[key]
    path = None
    for d in FONT_DIRS:
        p = os.path.join(d, FONT_FILES[weight])
        if os.path.isfile(p):
            path = p
            break
    if path is None:
        try:
            q = "monospace:bold" if weight != "r" else "monospace"
            path = subprocess.run(["fc-match", "-f", "%{file}", q],
                                  capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            path = ""
        if not path or not os.path.isfile(path):
            raise FontMissing("no monospace TTF for the %s card" % weight)
    _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def load_manifest():
    with open(os.path.join(HERE, "segments.json")) as fh:
        return json.load(fh)


SHOWS = load_manifest()


def cards():
    """Every (show_key, segment) in manifest order, numbered."""
    for key, show in SHOWS.items():
        n = 0
        total = sum(1 for s in show["segments"] if s.get("kind", "segment") == "segment")
        for seg in show["segments"]:
            kind = seg.get("kind", "segment")
            if kind == "segment":
                n += 1
            yield key, dict(seg, kind=kind, number=n if kind == "segment" else 0,
                            total=total)


def find(show, slug):
    for key, seg in cards():
        if key == show and seg["slug"] == slug:
            return SHOWS[key], seg
    raise KeyError((show, slug))


def clip_name(show, seg):
    return "z0-tr-%s-%s" % (show, seg["slug"])


def ease_out(t):
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_in(t):
    t = min(1.0, max(0.0, t))
    return t ** 3


def ease_back(t):
    """Overshoot and settle — the card landing on the desk."""
    t = min(1.0, max(0.0, t))
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def dip(img, f):
    if f < FRAMES - FADE_OUT:
        return img
    a = (f - (FRAMES - FADE_OUT) + 1) / FADE_OUT
    return Image.blend(img, Image.new("RGB", img.size, INK), a)


# ── GROUND ZERO ───────────────────────────────────────────────────────────
_MARK = None


def _mark():
    global _MARK
    if _MARK is None:
        _MARK = gzlogo.mark(scale=2)
    return _MARK


def gz_header(show, seg):
    if seg["kind"] == "segment":
        return "%s · %02d OF %02d" % (show["title"], seg["number"], seg["total"])
    return "%s · STAND BY" % show["title"]


def gz_frame(show, seg, f):
    W, H = MF.W, MF.H
    img = MF.new_frame(P.INK)
    MF.vgrad(img, 0, H, [(0.0, (0x0d, 0x0b, 0x14)), (0.45, (0x24, 0x1a, 0x18)),
                         (1.0, (0x0a, 0x08, 0x0c))])
    y0, y1 = GZ_PANEL

    # The band slides in from the right and stops flush: a gradient plate
    # with lit rules, not a flat box.
    t = ease_out(f / 14)
    px = int((W + 8) * (1 - t))
    if px < W:
        MF.vgrad(img, y0, y1, [(0.0, (0x1a, 0x14, 0x22)), (0.5, (0x10, 0x0c, 0x16)),
                               (1.0, (0x1a, 0x14, 0x22))], x0=px, x1=W)
        d = ImageDraw.Draw(img)
        d.rectangle([px, y0, W, y0 + 1], fill=P.ARMOUR[2])
        d.rectangle([px, y1 - 1, W, y1], fill=P.ARMOUR[2])
        rule = MF.layer()
        rd = ImageDraw.Draw(rule)
        rd.rectangle([px, y0, W, y0 + 1], fill=P.ARMOUR[1] + (255,))
        rd.rectangle([px, y1 - 1, W, y1], fill=P.ARMOUR[1] + (255,))
        img = MF.add(img, rule.filter(ImageFilter.GaussianBlur(2.2)), 0.55)

    # The mark comes the other way, lands, and has a warm light behind it.
    if f >= 6:
        m = _mark()
        mt = ease_out((f - 6) / 16)
        mx = int(-m.size[0] + (GZ_MARK_X + m.size[0]) * mt)
        my = (y0 + y1) // 2 - m.size[1] // 2
        img = MF.bloom(img, mx + m.size[0] // 2, my + m.size[1] // 2, 22,
                       (0x48, 0x22, 0x06), 0.8 * mt, 14)
        img.paste(m, (mx, my), m)

    if f >= 14:
        MF.blit_text(img, GZ_TEXT_X, y0 + 12, gz_header(show, seg), P.BONE, 1, 0.75,
                     keyline=False)

    # The name types itself, one cell every two frames, block cursor.
    if f >= 24:
        shown = (f - 24) // GZ_TYPE_RATE
        total = sum(len(l) for l in seg["lines"])
        y = y0 + 28
        left = shown
        cursor = None
        for ln in seg["lines"]:
            part = ln[:max(0, left)]
            MF.blit_text(img, GZ_TEXT_X, y, part, P.BONE, 2)
            if left < len(ln) or ln is seg["lines"][-1]:
                cursor = (GZ_TEXT_X + len(part) * gzfont.SMALL_CELL * 2, y)
            if left < len(ln):
                break
            left -= len(ln)
            y += gzfont.SMALL_H * 2 + 4
        y = y0 + 28 + (len(seg["lines"]) - 1) * (gzfont.SMALL_H * 2 + 4)
        if cursor and (shown < total or (f // 8) % 2 == 0):
            MF.blit_text(img, cursor[0], cursor[1], "█", P.ARMOUR, 2, keyline=False)
        if shown >= total + 3:
            MF.blit_text(img, GZ_TEXT_X, y + gzfont.SMALL_H * 2 + 8,
                         "▸ " + seg["sub"], P.ARMOUR, 1, keyline=False)

    if f >= 14:
        MF.triband(img, 0, H - 4, W, 4)

    img = dip(img, f)
    return img.resize((OUT_W, OUT_H), Image.NEAREST)


# ── LAB HOUR ──────────────────────────────────────────────────────────────
LAB_TITLE_XY = (56, 168)
LAB_DIM_Y = 150


def _grid(d, x0, y0, x1, y1):
    for x in range(0, OUT_W, 20):
        if x0 <= x <= x1:
            d.line([(x, y0), (x, y1)], fill=GRID, width=1)
    for y in range(0, OUT_H, 20):
        if y0 <= y <= y1:
            d.line([(x0, y), (x1, y)], fill=GRID, width=1)


def _arrow(d, x, y, direction, colour):
    s = 9
    d.polygon([(x, y), (x - direction * s, y - 4), (x - direction * s, y + 4)],
              fill=colour)


def sheet_id(show, seg):
    if seg["kind"] == "segment":
        return "%s-%02d" % (show["sheet"], seg["number"])
    return "%s-BRK" % show["sheet"]


def lab_frame(show, seg, f):
    img = Image.new("RGB", (OUT_W, OUT_H), INK)
    d = ImageDraw.Draw(img)
    xb = font("xb", 60)
    b16 = font("b", 15)
    r20 = font("r", 20)

    # Paper wipes down over the ink, grid and all.
    reveal = int(OUT_H * ease_out(f / 12))
    if reveal > 0:
        d.rectangle([0, 0, OUT_W, reveal], fill=PAPER)
        _grid(d, 0, 0, OUT_W, reveal)
    if f < 12:
        return img

    # Title block, bottom right, the way a drawing sheet carries one.
    bw, bh = 300, 78
    bx, by = OUT_W - 24 - bw, OUT_H - 24 - bh
    d.rectangle([bx, by, bx + bw, by + bh], fill=PAPER, outline=INK, width=2)
    d.line([(bx, by + 26), (bx + bw, by + 26)], fill=INK, width=2)
    d.line([(bx, by + 52), (bx + bw, by + 52)], fill=INK, width=2)
    rows = ["RIPOSTE LABORATORIES · %s" % show["title"],
            ("SEGMENT %02d OF %02d" % (seg["number"], seg["total"]))
            if seg["kind"] == "segment" else "BREAK · STAND BY",
            "SHEET %s · REV A" % sheet_id(show, seg)]
    for i, row in enumerate(rows):
        d.text((bx + 10, by + 6 + 26 * i), row, font=b16, fill=INK)

    # The name, revealed by a red cursor.
    title = " ".join(seg["lines"])
    tx, ty = LAB_TITLE_XY
    l, t, r, bb = xb.getbbox(title)
    tw = r - l
    layer = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((tx, ty), title, font=xb, fill=INK + (255,))
    cur = ease_out((f - 14) / 30)
    cx = tx + int((tw + 8) * cur)
    crop = layer.crop((0, 0, min(OUT_W, cx), OUT_H))
    img.paste(crop, (0, 0), crop)
    if f < 46:
        d.rectangle([cx, ty - 4, cx + 6, ty + (bb - t) + 8], fill=RED)

    # Then it is dimensioned.
    if f >= 46:
        g = ease_out((f - 46) / 20)
        mid = tx + tw / 2
        half = (tw / 2) * g
        x0, x1 = int(mid - half), int(mid + half)
        y = LAB_DIM_Y
        d.line([(x0, y), (x1, y)], fill=RED, width=2)
        if g > 0.3:
            _arrow(d, x0, y, -1, RED)
            _arrow(d, x1, y, 1, RED)
        if g >= 1.0:
            d.line([(tx, y - 10), (tx, ty + 4)], fill=RED, width=1)
            d.line([(tx + tw, y - 10), (tx + tw, ty + 4)], fill=RED, width=1)
            label = "%.2f" % (tw * MM_PER_PX)
            ll, lt, lr, lb = b16.getbbox(label)
            lw = lr - ll
            d.rectangle([mid - lw / 2 - 6, y - 22, mid + lw / 2 + 6, y - 2], fill=PAPER)
            d.text((mid - lw / 2, y - 22), label, font=b16, fill=RED)

    if f >= 60:
        d.text((tx + 2, ty + (bb - t) + 18), seg["sub"], font=r20, fill=INK_2)

    return dip(img, f)


# ── NEIGHBOURHOOD DESK ────────────────────────────────────────────────────
CARD_W, CARD_H = 520, 300
CARD_TILT = -3
STAMP_TILT = -7
STAMP_SIZE = 46
STAMP_PAD = 18
STAMP_MAX = CARD_W - 20   # the stamp stays on the card


def _speckle(x, y):
    """Deterministic rubber-stamp texture: a hash, not a random source, so
    the frames are the same bytes every build."""
    return ((x * 73856093) ^ (y * 19349663)) % 97 < 14


def _card(show, seg, f):
    card = Image.new("RGBA", (CARD_W, CARD_H), PAPER + (255,))
    d = ImageDraw.Draw(card)
    b14 = font("b", 14)
    r20 = font("r", 20)
    d.line([(0, 44), (CARD_W, 44)], fill=RULE_RED, width=2)
    for y in range(72, CARD_H, 28):
        d.line([(0, y), (CARD_W, y)], fill=RULE_BLUE, width=1)
    d.text((22, 14), show["title"], font=b14, fill=INK_2)
    filed = "No. %04d · FILED 18:00" % (40 + seg["number"])
    fl, ft, fr, fb = b14.getbbox(filed)
    d.text((CARD_W - 22 - (fr - fl), 14), filed, font=b14, fill=INK_2)

    # The stamp slams down: big and faint, then settled and solid.
    if f >= 24:
        st = ease_out((f - 24) / 6)
        scale = 1.6 - 0.6 * st
        alpha = int(255 * st)
        xb = font("xb", STAMP_SIZE)
        title = " ".join(seg["lines"])
        l, t, r, bb = xb.getbbox(title)
        tw, th = r - l, bb - t
        pad = STAMP_PAD
        sw, sh = tw + 2 * pad, th + 2 * pad
        stamp = Image.new("RGBA", (sw + 8, sh + 8), (0, 0, 0, 0))
        sd = ImageDraw.Draw(stamp)
        sd.rounded_rectangle([4, 4, sw + 4, sh + 4], radius=10, outline=RED + (255,), width=5)
        sd.text((4 + pad - l, 4 + pad - t), title, font=xb, fill=RED + (255,))
        px = stamp.load()
        for yy in range(stamp.size[1]):
            for xx in range(stamp.size[0]):
                r_, g_, b_, a_ = px[xx, yy]
                if a_ and _speckle(xx, yy):
                    px[xx, yy] = (r_, g_, b_, a_ // 4)
        if scale != 1.0:
            stamp = stamp.resize((int(stamp.size[0] * scale), int(stamp.size[1] * scale)),
                                 Image.BILINEAR)
        stamp = stamp.rotate(STAMP_TILT, resample=Image.BICUBIC, expand=True)
        if alpha < 255:
            a = stamp.getchannel("A").point(lambda v: v * alpha // 255)
            stamp.putalpha(a)
        cx, cy = CARD_W // 2, 128
        card.alpha_composite(stamp, (cx - stamp.size[0] // 2, cy - stamp.size[1] // 2))

    if f >= 40:
        shown = (f - 40) // 2
        d.text((26, 228), seg["sub"][:shown], font=r20, fill=INK)
        if shown < len(seg["sub"]) and (f // 4) % 2 == 0:
            l, t, r, bb = r20.getbbox(seg["sub"][:shown])
            d.rectangle([26 + (r - l) + 2, 228, 26 + (r - l) + 12, 250], fill=INK)
    return card


def desk_frame(show, seg, f):
    img = Image.new("RGB", (OUT_W, OUT_H), INK)
    d = ImageDraw.Draw(img)
    # A faint desk edge so the card has somewhere to land.
    d.line([(0, 436), (OUT_W, 436)], fill=(0x22, 0x22, 0x22), width=2)

    card = _card(show, seg, f).rotate(CARD_TILT, resample=Image.BICUBIC, expand=True)
    cw, ch = card.size
    rest_y = 92
    if f < 18:
        y = int(-ch + (rest_y + ch) * ease_back(f / 18))
    elif f >= FRAMES - 14:
        y = rest_y + int(560 * ease_in((f - (FRAMES - 14)) / 14))
    else:
        y = rest_y
    x = (OUT_W - cw) // 2

    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), (0, 0), card.getchannel("A"))
    img.paste(shadow, (x + 6, y + 8), shadow)
    img.paste(card, (x, y), card)

    if 18 <= f < FRAMES - 14:
        px_, py_ = OUT_W // 2 + 6, rest_y + 30
        d.ellipse([px_ - 10, py_ - 10, px_ + 10, py_ + 10], fill=(0x90, 0x14, 0x0e))
        d.ellipse([px_ - 9, py_ - 9, px_ + 7, py_ + 7], fill=RED)
        d.ellipse([px_ - 6, py_ - 6, px_ - 2, py_ - 2], fill=(0xFF, 0xB0, 0xA8))
    return img


RENDERERS = {"gz": gz_frame, "lab": lab_frame, "desk": desk_frame}


def frame(show_key, slug, f):
    show, seg = find(show_key, slug)
    return RENDERERS[show["grammar"]](show, seg, f)


# ── sound ─────────────────────────────────────────────────────────────────
GZ_CHORDS = ("Am", "F", "G", "E", "Dm")


def _clear():
    for buf in (A.L, A.R, A.ECHO_L, A.ECHO_R):
        buf[:] = array("d", bytes(8 * len(buf)))


def gz_sting(seg):
    """The title cue's own vocabulary: a pulse, a short string swell on the
    segment's chord, a bell.  No drums, no fanfare."""
    chord = "Dm" if seg["kind"] != "segment" else GZ_CHORDS[(seg["number"] - 1) % len(GZ_CHORDS)]
    A.pulse(0.0, 0.20)
    A.voice(0.0, 2.6, A.ROOTS[chord], "bass", 0.12, atk=0.05, dec=0.3, sus=0.8, rel=0.6)
    A.pad(0.05, 2.6, chord, 0.05, atk=0.35, rel=0.8)
    tones = A.PADS[chord]
    A.bell(0.55, tones[2], 0.06, -0.2, dur=1.0)
    A.bell(2.6, tones[0][:-1] + str(int(tones[0][-1]) + 1), 0.045, 0.2, dur=0.9)


def lab_sting(seg):
    A.voice(0.0, 0.5, "E5", "bell", 0.07, atk=0.004, dec=0.2, sus=0.3, rel=0.3, echo=0.3)
    A.hat(14 / FPS, 0.04)
    A.hat(44 / FPS, 0.04)
    A.voice(66 / FPS, 0.35, "A5", "bell", 0.08, pan=-0.2, atk=0.003, dec=0.12, sus=0.3, rel=0.25, echo=0.3)
    A.voice(66 / FPS + 0.14, 0.5, "E6", "bell", 0.08, pan=0.2, atk=0.003, dec=0.15, sus=0.3, rel=0.35, echo=0.3)


def desk_sting(seg):
    A.kick(18 / FPS, 0.40)
    A.kick(30 / FPS, 0.48)
    A.snare(30 / FPS, 0.22)
    for i in range(len(seg["sub"])):
        A.hat((40 + 2 * i) / FPS, 0.028)


STINGS = {"gz": gz_sting, "lab": lab_sting, "desk": desk_sting}


def audio(show_key, slug, path):
    show, seg = find(show_key, slug)
    _clear()
    STINGS[show["grammar"]](seg)
    A.mixdown()
    n = int(SECONDS * A.RATE)
    peak = max(max(abs(v) for v in A.L[:n]), max(abs(v) for v in A.R[:n])) or 1.0
    # Same headroom rule as the title: never the loudest thing on the channel.
    gain = 0.82 / peak
    tail = int(0.25 * A.RATE)
    out = array("h", bytes(4 * n))
    for i in range(n):
        g = gain * (min(1.0, (n - i) / tail))
        a = max(-1.0, min(1.0, A.L[i] * g))
        b = max(-1.0, min(1.0, A.R[i] * g))
        out[2 * i] = int(a * 32767)
        out[2 * i + 1] = int(b * 32767)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(A.RATE)
        w.writeframes(out.tobytes())


# ── sidecar ───────────────────────────────────────────────────────────────
NFO = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>{title}</title>
  <sorttitle>{sort}</sorttitle>
  <mpaa>Z0-GENERAL</mpaa>
  <outline>{outline}</outline>
  <plot>{outline} Segment transition, 4 s.</plot>
  <tag>media</tag>
  <tag>transitions</tag>
  <tag>{show}</tag>
</movie>
"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nfo(show_key, slug):
    """Tags are the folder chain media/transitions/<show> verbatim: the NFO
    REPLACES folder tags, so a sidecar that forgot one would silently drop the
    file out of its pool."""
    show, seg = find(show_key, slug)
    name = " ".join(seg["lines"])
    title = "%s - %s" % (show["title"], name)
    outline = "%s transition card: %s. %s." % (show["title"], name, seg["sub"].rstrip("."))
    return NFO.format(title=esc(title), sort=esc(title.lower()),
                      outline=esc(outline), show=show_key)


# ── checks that run before any frame ──────────────────────────────────────
def check_manifest():
    """Refuse to render a card whose words do not fit.  Every limit here was
    found by rendering a card that looked finished with its last word gone."""
    seen = set()
    for key, show in SHOWS.items():
        kinds = [s.get("kind", "segment") for s in show["segments"]]
        assert kinds.count("segment") >= 3, key
        slugs = [s["slug"] for s in show["segments"]]
        assert "break-out" in slugs and "break-in" in slugs, key
        for seg in show["segments"]:
            name = clip_name(key, seg)
            assert name not in seen, name
            seen.add(name)
            assert len(seg["lines"]) in (1, 2), name
            if show["grammar"] == "gz":
                for ln in seg["lines"]:
                    assert len(ln) <= GZ_LINE_MAX, (name, ln)
                    assert all(c in gzfont.SMALL for c in ln), (name, ln)
                assert len(seg["sub"]) + 2 <= GZ_SUB_MAX, (name, seg["sub"])
                assert len(gz_header(show, dict(seg, kind=seg.get("kind", "segment"),
                                                number=1, total=9))) <= GZ_SUB_MAX, name
                assert all(c in gzfont.SMALL for c in seg["sub"]), (name, seg["sub"])
            else:
                title = " ".join(seg["lines"])
                assert len(title) <= TTF_TITLE_MAX, name
                assert len(seg["sub"]) <= TTF_SUB_MAX, name
                # The character cap is a proxy; the font is the judge, where
                # it is installed.  "BACK AT THE BENCH" was 17 characters and
                # 590 px, and lost its H off the right edge of the sheet.
                try:
                    if show["grammar"] == "lab":
                        l, t, r, b = font("xb", 60).getbbox(title)
                        assert r - l <= TTF_TITLE_PX, (name, r - l)
                    else:
                        l, t, r, b = font("xb", STAMP_SIZE).getbbox(title)
                        assert r - l + 2 * STAMP_PAD <= STAMP_MAX, (name, r - l)
                except FontMissing:
                    pass


def main():
    check_manifest()
    cmd = sys.argv[1]
    if cmd == "list":
        for key, seg in cards():
            print(clip_name(key, seg))
        return
    if cmd == "render":
        show_key, slug, outdir = sys.argv[2:5]
        os.makedirs(outdir, exist_ok=True)
        for f in range(FRAMES):
            frame(show_key, slug, f).save(os.path.join(outdir, "f%05d.png" % f))
        print("rendered %d frames" % FRAMES)
        return
    if cmd == "audio":
        show_key, slug, path = sys.argv[2:5]
        audio(show_key, slug, path)
        print(path)
        return
    if cmd == "nfo":
        show_key, slug = sys.argv[2:4]
        sys.stdout.write(nfo(show_key, slug))
        return
    if cmd == "stills":
        outdir = sys.argv[2]
        os.makedirs(outdir, exist_ok=True)
        for key, seg in cards():
            frame(key, seg["slug"], 84).save(os.path.join(outdir, clip_name(key, seg) + ".png"))
        print("stills written")
        return
    raise SystemExit("unknown command %r" % cmd)


if __name__ == "__main__":
    main()
