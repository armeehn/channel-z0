#!/usr/bin/env python3
r"""Channel Z0 — GRAMOPHONE listening interval.

One Library and Archives Canada *Virtual Gramophone* 78 side, played whole,
with the picture generated from the sound itself. The record's groove IS the
side's loudness map, laid down in polar coordinates exactly as a cutting
lathe would: rim first, one turn per 1/78 min, label last. A tonearm tracks
playback inward; the groove already played turns station marigold behind it.

    +---------------------------- 854 ------------------------------+
    |   art viewport 0..447          |   panel 462..840             |
    |                                |  CH 0  LISTENING INTERVAL    |
    |        ,--------.              |  title / performer / dates   |
    |      /  ((( o )))  \  <-arm    |  LAC provenance + object id  |
    |      \  groove =   /           |  s.23 recording clock  -> PD |
    |        `--------'              |  s.6  work clock       -> PD |
    |   played = marigold, ahead     |  feeds, VU needle, clock     |
    |   of the stylus = grey         |  01:23 / 03:06               |
    +---------------------------------------------------------------+

Everything is derived: the loudness envelope comes from ffmpeg (`astats`,
one RMS figure per video frame — numpy does not import in LXC 111, so
ffmpeg is the DSP and Python only draws), the geometry from the side's own
duration, the panel text from the feed record. Deterministic: no clock, no
seed, no network at render time.

Standing rules honoured: no crosshair anywhere (the spindle is a plain hole,
the VU scale is an open arc); nothing is a subtitle element — the text is in
the picture, like the L-system panels; the clip fills the frame because the
gutter rails go DOWN for intervals.

    gramo.py envelope  SRC.mp3 ENV.json           # ffmpeg DSP pass
    gramo.py render    SIDE_ID SRC.mp3 ENV.json OUT.mp4
    gramo.py nfo       SIDE_ID OUT.nfo
    gramo.py check     SIDE_ID                    # rights clocks only
"""
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
from enum import Enum

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ── house spec (matches tools/z0-lsys and the anime family) ────────────────
W, H = 854, 480
FPS = 30
SR = 48000
NS = SR // FPS              # 1600 samples == one video frame
MAX_KBPS = 3000             # the interval assembler's encodability gate
MAX_SECONDS = 240           # 4:00, the longest junction the schedule books

# ── the record ──────────────────────────────────────────────────────────────
RPM = 78
ART_W = 448                 # whole macroblocks, same viewport as the L-systems
DISC_D = 420
R_OUT = DISC_D // 2
R_LABEL = 68
R_HOLE = 5
SUPER = 2                   # groove field is drawn at 2x and box-filtered down
GROOVE_PX = 3               # cosmetic ring pitch; the real pitch is sub-pixel
LEAD_IN_S = 1.5             # blank groove before the music, like a real side

# ── panel geometry (identical to the L-system specimens, measured) ──────────
PANEL_X = 462
PANEL_R = 840
PANEL_W = PANEL_R - PANEL_X
COLS = 52                   # 12 px mono in 378 px; a longer line is a bug

# ── palette ─────────────────────────────────────────────────────────────────
BG = (11, 11, 11)
PANEL_BG = (12, 12, 12)
SHELLAC = (16, 14, 13)
GROOVE_AHEAD = (150, 150, 146)
MARIGOLD = (0xFE, 0x9A, 0x0D)
IVORY = (236, 226, 200)
INK = (200, 200, 196)
LABEL = (120, 120, 116)
RULE = (48, 48, 46)

FONT_DIR = "/usr/share/fonts/liberation"
MONO = FONT_DIR + "/LiberationMono-%s.ttf"
SERIF = FONT_DIR + "/LiberationSerif-%s.ttf"

# ── the two clocks ──────────────────────────────────────────────────────────
# Recorded music has two independent copyright clocks in Canada and clearing
# one says nothing about the other. Both extensions were non-retroactive:
#   s.23 sound recording  50y -> 70y on 2015-06-23: fixed <= 1964 is out for good
#   s.6  musical work     50y -> 70y on 2022-12-30: author d. <= 1971 is out
# The Virtual Gramophone digitised discs cut 1900-1950, so every side clears
# the first clock by construction; the second must be proven per person.
RECORDING_LAST_FIXED = 1964
WORK_LAST_DEATH = 1971
VG_SPAN = (1900, 1950)

FFMPEG = shlex.split(os.environ.get("FFMPEG", "ffmpeg"))
FFPROBE = shlex.split(os.environ.get("FFPROBE", "ffprobe"))
HERE = os.path.dirname(os.path.abspath(__file__))
SIDES = os.path.join(HERE, "sides.json")

_YEARS = re.compile(r"(\d{4})\s*-\s*(\d{4})?\s*$")


class Clock(Enum):
    RECORDING = "s.23"
    WORK = "s.6"


class RightsError(Exception):
    pass


class EnvelopeError(Exception):
    pass


class LayoutError(Exception):
    pass


# ═══ rights ═════════════════════════════════════════════════════════════════

def death_year(person):
    """'Bolduc, Édouard, Mme, 1894-1941' -> 1941. None when not stated."""
    m = _YEARS.search(person)
    if not m or not m.group(2):
        return None

    return int(m.group(2))


def clear(side):
    """Both clocks, or raise. Never guesses a missing year."""
    if VG_SPAN[1] > RECORDING_LAST_FIXED:
        raise RightsError("collection span exceeds the recording clock")

    for person in side["persons"]:
        died = death_year(person)
        if died is None:
            raise RightsError("no death year for %r; work clock unprovable" % person)

        if died > WORK_LAST_DEATH:
            raise RightsError("%r died %d > %d; work runs to %d"
                              % (person, died, WORK_LAST_DEATH, died + 71))

    return {
        Clock.RECORDING: "fixed %d-%d  <= %d" % (*VG_SPAN, RECORDING_LAST_FIXED),
        Clock.WORK: ", ".join("d.%d" % death_year(p) for p in side["persons"]),
    }


def load_side(side_id, path=SIDES):
    with open(path) as fh:
        sides = json.load(fh)

    for side in sides:
        if side["id"] == side_id:
            return side

    raise KeyError(side_id)


# ═══ envelope (ffmpeg is the DSP) ═══════════════════════════════════════════

def envelope_cmd(src, out_txt):
    """One RMS level per video frame, written by ametadata to a file.

    `astats` only speaks at INFO, so the pass runs at -v info on purpose;
    the file sink is what we read, the log is noise."""
    chain = ("aformat=sample_fmts=fltp:sample_rates=%d:channel_layouts=mono,"
             "asetnsamples=n=%d:p=0,astats=metadata=1:reset=1,"
             "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=%s"
             % (SR, NS, out_txt.replace(":", "\\:")))
    return FFMPEG + ["-v", "info", "-nostdin", "-y", "-i", src,
                     "-af", chain, "-f", "null", "-"]


def parse_envelope(text):
    """ametadata lines -> dB per frame. Silence prints -inf; clamp it."""
    vals = []
    for line in text.splitlines():
        if "RMS_level=" not in line:
            continue

        v = line.split("=", 1)[1].strip()
        vals.append(-120.0 if v in ("-inf", "nan") else float(v))

    if not vals:
        raise EnvelopeError("no RMS lines; was the pass run below -v info?")

    return vals


def measure(src, workdir):
    txt = os.path.join(workdir, "rms.txt")
    subprocess.run(envelope_cmd(src, txt), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(txt) as fh:
        return parse_envelope(fh.read())


def normalise(env, floor_db=-40.0, ceil_db=-12.0):
    """dB -> 0..1, clamped. The floor sits above shellac surface noise."""
    span = ceil_db - floor_db
    return [min(1.0, max(0.0, (v - floor_db) / span)) for v in env]


# ═══ the disc ═══════════════════════════════════════════════════════════════

def groove_field(env01, seconds):
    """L image (SUPER x DISC_D square): the side's loudness in polar form.

    Time runs rim -> label. A pixel at radius r, angle a sits on turn
    floor((R_OUT - r) / pitch) at fraction a/2pi of that turn, so
    t = (turn + a/2pi) * 60/RPM. Pitch comes out of the side's own length."""
    S = DISC_D * SUPER
    c = S / 2
    r_out, r_lab = R_OUT * SUPER, R_LABEL * SUPER
    turns = seconds * RPM / 60.0
    pitch = (r_out - r_lab) / turns
    n = len(env01)
    lead = int(LEAD_IN_S * FPS)

    field = Image.new("L", (S, S), 0)
    px = field.load()
    for y in range(S):
        dy = y - c
        for x in range(S):
            dx = x - c
            r = math.hypot(dx, dy)
            if r >= r_out or r <= r_lab:
                continue

            turn = int((r_out - r) / pitch)
            frac = (math.atan2(dy, dx) / (2 * math.pi)) % 1.0
            t = (turn + frac) * 60.0 / RPM
            i = int(t * FPS) - lead
            v = env01[i] if 0 <= i < n else 0.0

            # Cosmetic ring pitch on top of the loudness: reads as a record
            # even where the side is quiet. 30..255 keeps the field visible.
            ring = 0.8 + 0.2 * math.cos(2 * math.pi * r / (GROOVE_PX * SUPER))
            px[x, y] = int((30 + 225 * v) * ring)

    return field.resize((DISC_D, DISC_D), Image.BOX)


def label_disc(side, fonts):
    """The paper label: RGBA at DISC_D, transparent outside R_LABEL."""
    img = Image.new("RGBA", (DISC_D, DISC_D), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = DISC_D / 2
    d.ellipse((c - R_LABEL, c - R_LABEL, c + R_LABEL, c + R_LABEL), fill=IVORY)
    d.ellipse((c - R_LABEL + 4, c - R_LABEL + 4, c + R_LABEL - 4, c + R_LABEL - 4),
              outline=MARIGOLD, width=2)

    f_small, f_title = fonts["label_small"], fonts["label_title"]
    lines = [("CH 0", f_small), ("GRAMOPHONE", f_small),
             (fit_text(d, side["short"], f_title, 2 * R_LABEL - 26), f_title),
             ("%d RPM" % RPM, f_small)]
    ys = [c - 52, c - 38, c + 12, c + 34]
    for (text, font), y in zip(lines, ys):
        w = d.textlength(text, font=font)
        d.text((c - w / 2, y), text, font=font, fill=SHELLAC)

    d.ellipse((c - R_HOLE, c - R_HOLE, c + R_HOLE, c + R_HOLE), fill=BG)
    return img


def fit_text(d, text, font, width):
    """Shrink a label line with an ellipsis until it fits. The label is
    small and the full title lives in the panel, so truncation is fine."""
    if d.textlength(text, font=font) <= width:
        return text

    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1].rstrip()

    return text + "…"


def build_discs(field, label):
    """Two coloured discs from one field: ahead of the stylus, and played."""
    base = Image.new("RGB", (DISC_D, DISC_D), BG)
    mask = Image.new("L", (DISC_D, DISC_D), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, DISC_D - 1, DISC_D - 1), fill=255)

    def tint(colour):
        disc = ImageOps.colorize(field, SHELLAC, colour)
        out = Image.composite(disc, base, mask)
        out.paste(label, (0, 0), label)
        return out

    return tint(GROOVE_AHEAD), tint(MARIGOLD)


def stylus_radius(t, seconds):
    return R_OUT - (R_OUT - R_LABEL) * min(1.0, max(0.0, t / seconds))


def disc_frame(ahead, played, t, seconds):
    """Compose the played annulus over the unplayed disc, then spin it."""
    r = stylus_radius(t, seconds)
    c = DISC_D / 2
    inner = Image.new("L", (DISC_D, DISC_D), 0)
    ImageDraw.Draw(inner).ellipse((c - r, c - r, c + r, c + r), fill=255)
    frame = Image.composite(ahead, played, inner)

    angle = -(t * RPM / 60.0 * 360.0) % 360.0
    return frame.rotate(angle, resample=Image.BILINEAR, fillcolor=BG)


# ═══ the panel ══════════════════════════════════════════════════════════════

def load_fonts():
    return {
        "small": ImageFont.truetype(MONO % "Regular", 11),
        "code": ImageFont.truetype(MONO % "Regular", 12),
        "bold": ImageFont.truetype(MONO % "Bold", 12),
        "title": ImageFont.truetype(SERIF % "Bold", 22),
        "label_small": ImageFont.truetype(SERIF % "Bold", 12),
        "label_title": ImageFont.truetype(SERIF % "Bold", 15),
    }


def check_cols(lines):
    """Refuse silently-clipped text. Right-edge truncation is invisible in
    code and nearly invisible in a still, so it is an error here."""
    for line in lines:
        if len(line) > COLS:
            raise LayoutError("%d cols > %d: %r" % (len(line), COLS, line))


def wrap(text, cols=COLS):
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) > cols:
            lines.append(cur)
            cur = w
            continue

        cur = cand

    if cur:
        lines.append(cur)

    return lines


def panel_lines(side, verdict, seconds):
    """Everything static on the panel, as (text, style) rows."""
    rows = [
        ("CH 0  LISTENING INTERVAL", "label"),
        ("", "title"),                                   # title drawn in serif
        (side["performer"], "ink"),
        (side["persons_display"], "label"),
        ("", "gap"),
        ("%d RPM · SHELLAC · MONO · %d:%02d" % (RPM, seconds // 60, seconds % 60), "ink"),
        ("LIBRARY AND ARCHIVES CANADA", "ink"),
        ("VIRTUAL GRAMOPHONE  obj/m2/f7/%s" % side["id"], "label"),
        ("", "rule"),
        ("RECORDING  %-5s %s" % (Clock.RECORDING.value, verdict[Clock.RECORDING]), "ink"),
        ("           PUBLIC DOMAIN, PERMANENTLY", "bold"),
        ("WORK       %-5s %s" % (Clock.WORK.value, verdict[Clock.WORK]), "ink"),
        ("           PUBLIC DOMAIN, PERMANENTLY", "bold"),
        ("", "gap"),
    ]
    for line in wrap("Both clocks have to run out. A public-domain "
                     "recording of a living work is still an infringement."):
        rows.append((line, "label"))

    rows.append(("", "gap"))
    for line in wrap("LAC FEEDS: " + " · ".join(side["feeds"])):
        rows.append((line, "label"))

    check_cols([r[0] for r in rows])
    return rows


def panel_static(side, verdict, seconds, fonts):
    """The unchanging right-hand panel, drawn once."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((ART_W, 0, W - 1, H - 1), fill=PANEL_BG)
    for y in (10, 68, 408):
        d.line((PANEL_X, y, PANEL_R, y), fill=RULE)

    colour = {"label": LABEL, "ink": INK, "bold": MARIGOLD}
    font = {"label": fonts["small"], "ink": fonts["code"], "bold": fonts["bold"]}
    y = 15
    for text, style in panel_lines(side, verdict, seconds):
        if style == "title":
            title = fit_text(d, side["title"], fonts["title"], PANEL_W)
            d.text((PANEL_X, 28), title, font=fonts["title"], fill=IVORY)
            y = 60 + 16
            continue

        if style == "gap":
            y += 8
            continue

        if style == "rule":
            d.line((PANEL_X, y + 4, PANEL_R, y + 4), fill=RULE)
            y += 12
            continue

        d.text((PANEL_X, y), text, font=font[style], fill=colour[style])
        y += 16

    # Bottom strip: provenance of the renderer itself, like the L-systems'
    # `src sha1`. What is on screen is what is in the repo.
    sha = hashlib.sha1(open(__file__, "rb").read()).hexdigest()[:12]
    d.text((PANEL_X, 418), "tools/z0-gramo/gramo.py  sha1 %s" % sha,
           font=fonts["small"], fill=LABEL)
    d.text((PANEL_X, 434), "groove = RMS/frame, rim first, 1 turn per 1/%d min"
           % RPM, font=fonts["small"], fill=LABEL)
    return img


# VU meter: an open arc with a needle. An arc plus a needle is a dial; a ring
# plus crossed lines would be a gunsight, which is why there is no ring.
VU_CX, VU_CY, VU_R = 800, 398, 34
VU_MIN_DB, VU_MAX_DB = -40.0, 0.0
VU_LEFT_DEG, VU_RIGHT_DEG = 160, 20       # y-up angles of the scale ends


def vu_angle(db):
    f = min(1.0, max(0.0, (db - VU_MIN_DB) / (VU_MAX_DB - VU_MIN_DB)))
    return math.radians(VU_LEFT_DEG - (VU_LEFT_DEG - VU_RIGHT_DEG) * f)


def draw_vu(d, db, fonts):
    box = (VU_CX - VU_R, VU_CY - VU_R, VU_CX + VU_R, VU_CY + VU_R)
    d.arc(box, start=-VU_LEFT_DEG, end=-VU_RIGHT_DEG, fill=INK, width=2)
    for k in range(5):
        a = math.radians(VU_LEFT_DEG - (VU_LEFT_DEG - VU_RIGHT_DEG) * k / 4)
        x0, y0 = VU_CX + (VU_R - 6) * math.cos(a), VU_CY - (VU_R - 6) * math.sin(a)
        x1, y1 = VU_CX + VU_R * math.cos(a), VU_CY - VU_R * math.sin(a)
        d.line((x0, y0, x1, y1), fill=INK, width=1)

    a = vu_angle(db)
    d.line((VU_CX, VU_CY, VU_CX + (VU_R - 2) * math.cos(a),
            VU_CY - (VU_R - 2) * math.sin(a)), fill=MARIGOLD, width=2)
    d.text((VU_CX - VU_R - 24, VU_CY - 8), "VU", font=fonts["small"], fill=LABEL)


def draw_arm(d, t, seconds):
    """Tonearm from a top-right pivot to the stylus on the groove."""
    cx, cy = ART_W / 2, H / 2
    px, py = ART_W - 26, 34
    r = stylus_radius(t, seconds)
    ang = math.atan2(py - cy, px - cx)
    sx, sy = cx + r * math.cos(ang), cy + r * math.sin(ang)

    d.line((px, py, sx, sy), fill=INK, width=3)
    d.ellipse((px - 7, py - 7, px + 7, py + 7), fill=INK)
    d.rectangle((sx - 4, sy - 4, sx + 4, sy + 4), fill=MARIGOLD)


def clock_text(t, seconds):
    return "%02d:%02d / %02d:%02d" % (t // 60, t % 60, seconds // 60, seconds % 60)


# ═══ render ═════════════════════════════════════════════════════════════════

def frames(side, env, seconds, fonts):
    """Yield RGB frames. `seconds` is the clip length, `env` dB per frame."""
    verdict = clear(side)
    env01 = normalise(env)
    field = groove_field(env01, seconds)
    ahead, played = build_discs(field, label_disc(side, fonts))
    static = panel_static(side, verdict, seconds, fonts)
    ox, oy = (ART_W - DISC_D) // 2, (H - DISC_D) // 2
    total = int(round(seconds * FPS))

    for i in range(total):
        t = i / FPS
        img = static.copy()
        img.paste(disc_frame(ahead, played, t, seconds), (ox, oy))
        d = ImageDraw.Draw(img)
        draw_arm(d, t, seconds)
        db = env[i] if i < len(env) else -120.0
        draw_vu(d, db, fonts)
        d.text((PANEL_X, 390), clock_text(int(t), int(seconds)),
               font=fonts["bold"], fill=IVORY)
        yield img


def encode_cmd(src, out, seconds):
    """Raw RGB on stdin + the side's audio -> house-spec MP4.

    CRF 23 like the assembler; ErsatzTV re-encodes on air, what matters is
    that the groove edges survive. Audio is transcoded once, mono -> stereo
    AAC 48 kHz, and NOT processed: this is the disc as LAC published it."""
    return FFMPEG + ["-v", "error", "-nostdin", "-y",
                     "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
                     "-r", str(FPS), "-i", "-",
                     "-i", src,
                     "-t", "%.3f" % seconds,
                     "-c:v", "libx264", "-crf", "23", "-preset", "medium",
                     "-pix_fmt", "yuv420p", "-g", str(FPS * 2),
                     "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2",
                     "-movflags", "+faststart", out]


def duration(src):
    out = subprocess.check_output(FFPROBE + ["-v", "error", "-show_entries",
                                             "format=duration", "-of",
                                             "default=nw=1:nk=1", src])
    return float(out.decode().strip())


def render(side, src, env, out):
    seconds = min(duration(src), float(MAX_SECONDS))
    fonts = load_fonts()
    proc = subprocess.Popen(encode_cmd(src, out, seconds), stdin=subprocess.PIPE)
    for img in frames(side, env, seconds, fonts):
        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")


# ═══ NFO ════════════════════════════════════════════════════════════════════

NFO = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>{name}</title>
  <sorttitle>{name}</sorttitle>
  <mpaa>Z0-GENERAL</mpaa>
  <outline>{outline}</outline>
  <plot>{plot}</plot>
  <tag>media</tag>
  <tag>gramophone</tag>
</movie>
"""


def nfo(side, name):
    """Tags: media + gramophone. Deliberately NOT `generative` — the NFO
    replaces the folder tags, so a file staged in /media/generative with
    this sidecar stays out of the interval pool until the schedule names
    `tag:gramophone` (a NEW tag: rebuild the search index, not just rescan)."""
    outline = "%s — %s. LAC Virtual Gramophone %s." % (
        side["title"], side["performer"], side["id"])
    plot = outline + " Recording PD (s.23, fixed <=1950); work PD (s.6, %s)." % (
        ", ".join("d.%d" % death_year(p) for p in side["persons"]))
    return NFO.format(name=name, outline=esc(outline), plot=esc(plot))


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ═══ CLI ════════════════════════════════════════════════════════════════════

def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "check":
        side = load_side(argv[2])
        for k, v in clear(side).items():
            print("%-10s %-5s %s" % (k.name, k.value, v))
        return 0

    if cmd == "envelope":
        src, out = argv[2], argv[3]
        env = measure(src, os.path.dirname(os.path.abspath(out)))
        with open(out, "w") as fh:
            json.dump(env, fh)
        print("%d frames, peak %.1f dB" % (len(env), max(env)))
        return 0

    if cmd == "render":
        side = load_side(argv[2])
        with open(argv[4]) as fh:
            env = json.load(fh)
        render(side, argv[3], env, argv[5])
        return 0

    if cmd == "nfo":
        side = load_side(argv[2])
        name = os.path.splitext(os.path.basename(argv[3]))[0]
        with open(argv[3], "w") as fh:
            fh.write(nfo(side, name))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
