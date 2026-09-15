#!/usr/bin/env python3
r"""Channel Z0 — GRAMOPHONE sides for LUNCH LOOPS.

One Library and Archives Canada *Virtual Gramophone* 78 side, played whole,
with the picture generated from the sound itself. The record's groove IS the
side's loudness map, laid down in polar coordinates exactly as a cutting
lathe would: rim first, one turn per 1/78 min, label last. A tonearm tracks
playback inward; the groove already played turns station marigold behind it.

    +--------------------- 640 (4:3) ---------------------+
    |   art viewport 0..319      |   panel 332..628       |
    |                            |  CH 0  GRAMOPHONE      |
    |        ,------.            |  title / performer     |
    |      /  (( o ))  \ <-arm   |  LAC object id         |
    |      \  groove   /         |  s.23 recording  -> PD |
    |        `------'            |  s.6  work       -> PD |
    |   played = marigold,       |  VU needle, clock      |
    |   ahead of stylus = grey   |  01:23 / 03:06         |
    +-----------------------------------------------------+

4:3, like every other LUNCH LOOPS card: the block airs with the gutter rails
up, and a 16:9 item puts its edges under the rails. ErsatzTV pillarboxes
this into the same 640 px the prairie cards occupy.

Everything is derived: the loudness envelope comes from ffmpeg (`astats`,
one RMS figure per video frame — numpy does not import in LXC 111, so
ffmpeg is the DSP and Python only draws), the geometry from the side's own
duration, the panel text from the manifest. Deterministic: no clock, no
seed, no network at render time.

Standing rules honoured: no crosshair anywhere (the spindle is a plain hole,
the VU scale is an open arc); nothing is a subtitle element — the text is in
the picture, like the L-system panels.

    gramo.py select    STAGE.json SRC_DIR OUT.json   # manifest from round 3
    gramo.py check     [SIDE_ID]                     # rights clocks only
    gramo.py stamp                                   # write status into sides.json
    gramo.py envelope  SRC.mp3 ENV.json              # ffmpeg DSP pass
    gramo.py render    SIDE_ID SRC.mp3 ENV.json OUT.mp4
    gramo.py stem      SIDE_ID                       # library file stem
    gramo.py tex                                     # docs table
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

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:         # z0-nfo.py imports the clocks on hosts without Pillow
    Image = ImageDraw = ImageFont = ImageOps = None

# ── card spec (matches the LUNCH LOOPS music cards: 4:3, 30 fps) ────────────
W, H = 640, 480
FPS = 30
SR = 48000
NS = SR // FPS              # 1600 samples == one video frame
MAX_KBPS = 3000             # the interval assembler's encodability gate
MAX_MINUTES = 9             # every lunch pool is bounded minutes:[0 TO 9]

# ── the disc ────────────────────────────────────────────────────────────────
RPM = 78
ART_W = 320                 # left half; whole macroblocks
DISC_D = 300
R_OUT = DISC_D // 2
R_LABEL = 52
R_HOLE = 4
SUPER = 2                   # groove field is drawn at 2x and box-filtered down
GROOVE_PX = 3               # cosmetic ring pitch; the real pitch is sub-pixel
LEAD_IN_S = 1.5             # blank groove before the music, like a real side

# ── the panel (the L-system panel's proportions at 4:3) ─────────────────────
PANEL_X = 332
PANEL_R = 628
PANEL_W = PANEL_R - PANEL_X
COLS = 40                   # 12 px mono in 296 px; a longer line is a bug
ROW = 16
PANEL_TOP = 66              # first text row, under the title
PANEL_FLOOR = 390           # static rows must end above the clock and VU

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

FONT_DIR = os.environ.get("GRAMO_FONT_DIR", "/usr/share/fonts/liberation")
MONO = FONT_DIR + "/LiberationMono-%s.ttf"
SERIF = FONT_DIR + "/LiberationSerif-%s.ttf"

# ── the two clocks ──────────────────────────────────────────────────────────
# Recorded music has two independent copyright clocks in Canada and clearing
# one says nothing about the other. Both extensions were non-retroactive:
#   s.23 sound recording  50y -> 70y on 2015-06-23: fixed <= 1964 is out for good
#   s.6  musical work     50y -> 70y on 2022-12-30: author d. <= 1971 is out
# The recording year is the disc's own ID3 date where LAC stamped one; the
# Virtual Gramophone digitised discs cut 1900-1950, which is the fallback.
# The work clock is proven only where the author is named and dated or the
# work has none: a performer's death date says nothing about a song somebody
# else wrote, and the feeds credit performers. Where the feed is silent the
# side carries a `work` block researched against LAC's own catalogue record
# (composer heading, statement of responsibility) with the source URL:
#
#   "basis": "named",
#   "work": {"composers": ["Adam, Adolphe, 1803-1856"],
#            "lyricists": ["Cappeau, Placide, 1808-1877"],
#            "arrangers": [],                      # optional; also clocked
#            "source": "https://www.bac-lac.gc.ca/.../Item.aspx?idNumber=N",
#            "unresolved": "why the clock cannot be read"}   # optional
#
# Every author listed must be dated and dead by WORK_LAST_DEATH; a missing
# year or an `unresolved` note holds the side. Nothing is ever guessed.
RECORDING_LAST_FIXED = 1964
WORK_LAST_DEATH = 1971
VG_SPAN = (1900, 1950)

FFMPEG = shlex.split(os.environ.get("FFMPEG", "ffmpeg"))
FFPROBE = shlex.split(os.environ.get("FFPROBE", "ffprobe"))
HERE = os.path.dirname(os.path.abspath(__file__))
SIDES = os.path.join(HERE, "sides.json")

_YEARS = re.compile(r"(\d{4})\??\s*-\s*(\d{4})?\s*$")         # "1832?-1893": an uncertain birth is fine
_DIED_ONLY = re.compile(r"\b[md]\.?\s*(\d{4})\s*$")     # "Desmarteaux, Alexandre, m. 1926", "d. 1900"
_CORPORATE = re.compile(r"trio|quartet|band|orchestra|groupe|abbey|chorus|"
                        r"habitants|quatuor|choeur", re.I)
_TRAD_FORM = re.compile(r"\b(reel|gigue|quadrille|cotillon|clog|set carr|"
                        r"brandy|jig)\b", re.I)


class Clock(Enum):
    RECORDING = "s.23"
    WORK = "s.6"


class Basis(Enum):
    """Why the WORK clock can be read off the record at all."""
    OWN = "own"             # the credited performer wrote the material
    TRAD = "trad"           # traditional dance tune, no author
    CHANT = "chant"         # plainchant, no author
    NAMED = "named"         # authors researched into side["work"], with source


class Status(Enum):
    """What the two clocks say about a side, as written into the manifest."""
    CLEAR = "CLEAR"                 # both clocks have run: in the library
    HELD = "HELD"                   # a clock is known not to have run yet
    UNRESOLVED = "UNRESOLVED"       # a clock cannot be read: author unnamed or undated


# work-block keys whose people are all authors on the s.6 clock
WORK_ROLES = ("composers", "lyricists", "arrangers")


# Performers whose recorded repertoire is their own writing. The memory that
# staged round 3 records the fact for La Bolduc; nobody else is assumed.
AUTHORS = {"Bolduc, Édouard, Mme"}

# Library folder per basis: the folder is the tag ErsatzTV derives.
FOLDER = {Basis.OWN: "chanson", Basis.TRAD: "reel", Basis.CHANT: "chant",
          Basis.NAMED: "chanson"}

# Display names where "Given Surname" is not how the performer is known.
DISPLAY = {"Bolduc, Édouard, Mme": "La Bolduc",
           "Saint-Benoît-du-Lac (Abbey : Québec)": "Abbaye de Saint-Benoît-du-Lac"}


class RightsError(Exception):
    def __init__(self, clock, msg, status=Status.UNRESOLVED):
        super().__init__("%s %s: %s" % (clock.name, clock.value, msg))
        self.clock = clock
        self.status = status


class EnvelopeError(Exception):
    pass


class LayoutError(Exception):
    pass


# ═══ rights ═════════════════════════════════════════════════════════════════

def death_year(person):
    """'Bolduc, Édouard, Mme, 1894-1941' -> 1941. None when not stated."""
    m = _YEARS.search(person)
    if m and m.group(2):
        return int(m.group(2))

    m = _DIED_ONLY.search(person)
    return int(m.group(1)) if m else None


def is_corporate(person):
    """An ensemble or an abbey has no personal clock to age out."""
    return not re.search(r"\d{4}", person) and bool(_CORPORATE.search(person))


def person_name(person):
    """'Bolduc, Édouard, Mme, 1894-1941' -> 'Bolduc, Édouard, Mme'."""
    return _DIED_ONLY.sub("", _YEARS.sub("", person)).strip().rstrip(",").strip()


def authors_of(side, basis):
    """The people the s.6 clock runs on: the performers for own material,
    the researched work block otherwise (arrangers of a trad tune included)."""
    if basis is Basis.OWN:
        return [p for p in side["persons"] if not is_corporate(p)]

    work = side.get("work") or {}
    return [p for role in WORK_ROLES for p in work.get(role, [])]


def clear(side):
    """Both clocks, or raise. Never guesses a missing year or an author."""
    year = side.get("year")
    if year is not None and year > RECORDING_LAST_FIXED:
        raise RightsError(Clock.RECORDING, "fixed %d > %d" % (year, RECORDING_LAST_FIXED),
                          Status.HELD)

    if year is None and VG_SPAN[1] > RECORDING_LAST_FIXED:
        raise RightsError(Clock.RECORDING, "collection span exceeds the clock")

    basis = side.get("basis")
    if basis is None:
        raise RightsError(Clock.WORK, "composer not named in the record")

    basis = Basis(basis)
    work = side.get("work") or {}
    if work.get("unresolved"):
        raise RightsError(Clock.WORK, "unresolved, " + work["unresolved"])

    if basis is Basis.NAMED and not work.get("composers"):
        raise RightsError(Clock.WORK, "no composer in the work block")

    dated = []
    for person in authors_of(side, basis):
        died = death_year(person)
        if died is None:
            raise RightsError(Clock.WORK, "no death year for %r" % person)

        if died > WORK_LAST_DEATH:
            raise RightsError(Clock.WORK, "%r died %d > %d; work runs to %d"
                              % (person, died, WORK_LAST_DEATH, died + 71), Status.HELD)

        dated.append(died)

    if basis is Basis.OWN and not dated:
        raise RightsError(Clock.WORK, "own material claimed with no dated author")

    recording = ("fixed %d" % year if year is not None
                 else "fixed %d-%d" % VG_SPAN) + "  <= %d" % RECORDING_LAST_FIXED
    authors = ", ".join("d.%d" % d for d in dated) + "  <= %d" % WORK_LAST_DEATH
    work = {Basis.OWN: "author " + authors,
            Basis.NAMED: "authors " + authors,
            Basis.TRAD: "traditional tune, no author",
            Basis.CHANT: "plainchant, no author"}[basis]
    if basis in (Basis.TRAD, Basis.CHANT) and dated:
        work = work.replace("no author", "arr. " + authors)

    return {Clock.RECORDING: recording, Clock.WORK: work}


def status(side):
    """(Status, verdict-or-RightsError) for one side."""
    try:
        return Status.CLEAR, clear(side)
    except RightsError as e:
        return e.status, e


def load_sides(path=SIDES):
    with open(path) as fh:
        return json.load(fh)


def load_side(side_id, path=SIDES):
    for side in load_sides(path):
        if side["id"] == side_id:
            return side

    raise KeyError(side_id)


def cleared(sides):
    """(side, verdict) for every side both clocks pass."""
    out = []
    for side in sides:
        try:
            out.append((side, clear(side)))
        except RightsError:
            continue

    return out


# ═══ manifest ═══════════════════════════════════════════════════════════════

def basis_for(entry):
    """Round 3's repertoire class + the title decide what the record proves."""
    rep = entry.get("repertoire", "")
    if rep.startswith("latin-chant"):
        return Basis.CHANT.value

    if rep.startswith("instrumental trad") or _TRAD_FORM.search(entry["title"]):
        return Basis.TRAD.value

    if any(person_name(p) in AUTHORS for p in entry["artist"].split(";")):
        return Basis.OWN.value

    return None


def id3_year(src):
    """The disc's own date as LAC stamped it, or None."""
    out = subprocess.check_output(FFPROBE + ["-v", "error", "-show_entries",
                                             "format_tags=date", "-of",
                                             "default=nw=1:nk=1", src])
    m = re.search(r"\b(1[89]\d{2}|19[0-6]\d)\b", out.decode(errors="replace"))
    return int(m.group(1)) if m else None


def display_name(person):
    name = person_name(person)
    if name in DISPLAY:
        return DISPLAY[name]

    parts = [p.strip() for p in name.split(",")]
    if len(parts) < 2:
        return parts[0]

    given = re.sub(r"\s*\(.*?\)", "", parts[1]).strip()
    return ("%s %s" % (given, parts[0])).strip()


def select(stage, src_dir):
    """Every LAC side of round 3, with the facts the clocks read."""
    sides = []
    for entry in stage:
        if "bytes" not in entry:
            continue                    # not fetched from the LAC host: out of scope

        side_id = entry["id"].replace(".mp3", "")
        persons = [p.strip() for p in entry["artist"].split(";") if p.strip()]
        src = os.path.join(src_dir, side_id + ".mp3")
        sides.append({
            "id": side_id,
            "title": entry["title"].strip(),
            "performer": " & ".join(display_name(p) for p in persons),
            "persons": persons,
            "repertoire": entry["repertoire"],
            "basis": basis_for(entry),
            "year": id3_year(src) if os.path.exists(src) else None,
            "url": entry["url"],
            "bytes": entry["bytes"],
        })

    return sorted(sides, key=lambda s: (s["performer"], s["title"]))


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def stem(side):
    """Library file stem: `Performer - Title (Year) [lac-ID]`, SMB-safe."""
    title = _UNSAFE.sub(" ", side["title"].split(" = ")[0])
    title = re.sub(r"\s+", " ", title).strip(" .")[:80].strip()
    year = " (%d)" % side["year"] if side.get("year") else ""
    return "%s - %s%s [lac-%s]" % (side["performer"], title, year, side["id"])


def rel_path(side):
    return "gramophone/%s/%s.mp4" % (FOLDER[Basis(side["basis"])], stem(side))


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
    # Named after the source: build.sh measures several sides at once in
    # one work dir, and a shared file interleaves two passes' lines.
    txt = os.path.join(workdir, os.path.basename(src) + ".rms.txt")
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
    d.ellipse((c - R_LABEL + 3, c - R_LABEL + 3, c + R_LABEL - 3, c + R_LABEL - 3),
              outline=MARIGOLD, width=2)

    f_small, f_title = fonts["label_small"], fonts["label_title"]
    lines = [("CH 0", f_small), ("GRAMOPHONE", f_small),
             (fit_text(d, side["title"], f_title, 2 * R_LABEL - 20), f_title),
             ("%d RPM" % RPM, f_small)]
    ys = [c - 42, c - 30, c + 8, c + 26]
    for (text, font), y in zip(lines, ys):
        w = d.textlength(text, font=font)
        d.text((c - w / 2, y), text, font=font, fill=SHELLAC)

    d.ellipse((c - R_HOLE, c - R_HOLE, c + R_HOLE, c + R_HOLE), fill=BG)
    return img


def fit_text(d, text, font, width):
    """Shrink a line with an ellipsis until it fits. The label is small and
    the full title lives in the panel, so truncation is fine."""
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
        "title": ImageFont.truetype(SERIF % "Bold", 18),
        "label_small": ImageFont.truetype(SERIF % "Bold", 10),
        "label_title": ImageFont.truetype(SERIF % "Bold", 12),
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
    rows = [(line, "ink") for line in wrap(side["performer"])]
    for line in wrap(" · ".join(side["persons"])):
        rows.append((line, "label"))

    rows += [
        ("", "gap"),
        ("%d RPM · SHELLAC · MONO · %d:%02d" % (RPM, seconds // 60, seconds % 60), "ink"),
        ("LIBRARY AND ARCHIVES CANADA", "ink"),
        ("VIRTUAL GRAMOPHONE  obj/m2/f7/%s" % side["id"], "label"),
        ("", "rule"),
        ("RECORDING  %s" % Clock.RECORDING.value, "ink"),
        ("  %s" % verdict[Clock.RECORDING], "label"),
        ("  PUBLIC DOMAIN, PERMANENTLY", "bold"),
        ("WORK       %s" % Clock.WORK.value, "ink"),
    ]
    rows += [("  " + line, "label") for line in wrap(verdict[Clock.WORK], COLS - 2)]
    rows += [
        ("  PUBLIC DOMAIN, PERMANENTLY", "bold"),
        ("", "gap"),
    ]
    for line in wrap("Both clocks have to run out. A public-domain "
                     "recording of a living work is still an infringement."):
        rows.append((line, "label"))

    check_cols([r[0] for r in rows])
    return rows


def panel_static(side, verdict, seconds, fonts):
    """The unchanging right-hand panel, drawn once."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((ART_W, 0, W - 1, H - 1), fill=PANEL_BG)
    for y in (10, 60, 440):
        d.line((PANEL_X, y, PANEL_R, y), fill=RULE)

    d.text((PANEL_X, 15), "CH 0  GRAMOPHONE", font=fonts["small"], fill=LABEL)
    title = fit_text(d, side["title"], fonts["title"], PANEL_W)
    d.text((PANEL_X, 32), title, font=fonts["title"], fill=IVORY)

    colour = {"label": LABEL, "ink": INK, "bold": MARIGOLD}
    font = {"label": fonts["small"], "ink": fonts["code"], "bold": fonts["bold"]}
    y = PANEL_TOP
    for text, style in panel_lines(side, verdict, seconds):
        if style == "gap":
            y += 8
            continue

        if style == "rule":
            d.line((PANEL_X, y + 4, PANEL_R, y + 4), fill=RULE)
            y += 12
            continue

        d.text((PANEL_X, y), text, font=font[style], fill=colour[style])
        y += ROW

    # The clock and the VU live below the static rows; text running into
    # them would be the same silent clipping check_cols refuses.
    if y > PANEL_FLOOR:
        raise LayoutError("panel rows end at %d > %d" % (y, PANEL_FLOOR))

    # Bottom strip: provenance of the renderer itself, like the L-systems'
    # `src sha1`. What is on screen is what is in the repo.
    sha = hashlib.sha1(open(__file__, "rb").read()).hexdigest()[:12]
    d.text((PANEL_X, 448), "z0-gramo/gramo.py  sha1 %s" % sha,
           font=fonts["small"], fill=LABEL)
    d.text((PANEL_X, 462), "groove = RMS per frame, rim first",
           font=fonts["small"], fill=LABEL)
    return img


# VU meter: an open arc with a needle. An arc plus a needle is a dial; a ring
# plus crossed lines would be a gunsight, which is why there is no ring.
VU_CX, VU_CY, VU_R = 596, 412, 26
VU_MIN_DB, VU_MAX_DB = -40.0, 0.0
VU_LEFT_DEG, VU_RIGHT_DEG = 160, 20       # y-up angles of the scale ends
CLOCK_Y = 404


def vu_angle(db):
    f = min(1.0, max(0.0, (db - VU_MIN_DB) / (VU_MAX_DB - VU_MIN_DB)))
    return math.radians(VU_LEFT_DEG - (VU_LEFT_DEG - VU_RIGHT_DEG) * f)


def draw_vu(d, db, fonts):
    box = (VU_CX - VU_R, VU_CY - VU_R, VU_CX + VU_R, VU_CY + VU_R)
    d.arc(box, start=-VU_LEFT_DEG, end=-VU_RIGHT_DEG, fill=INK, width=2)
    for k in range(5):
        a = math.radians(VU_LEFT_DEG - (VU_LEFT_DEG - VU_RIGHT_DEG) * k / 4)
        x0, y0 = VU_CX + (VU_R - 5) * math.cos(a), VU_CY - (VU_R - 5) * math.sin(a)
        x1, y1 = VU_CX + VU_R * math.cos(a), VU_CY - VU_R * math.sin(a)
        d.line((x0, y0, x1, y1), fill=INK, width=1)

    a = vu_angle(db)
    d.line((VU_CX, VU_CY, VU_CX + (VU_R - 2) * math.cos(a),
            VU_CY - (VU_R - 2) * math.sin(a)), fill=MARIGOLD, width=2)
    d.text((VU_CX - VU_R - 22, VU_CY - 8), "VU", font=fonts["small"], fill=LABEL)


def draw_arm(d, t, seconds):
    """Tonearm from a top-right pivot to the stylus on the groove."""
    cx, cy = ART_W / 2, H / 2
    px, py = ART_W - 22, 30
    r = stylus_radius(t, seconds)
    ang = math.atan2(py - cy, px - cx)
    sx, sy = cx + r * math.cos(ang), cy + r * math.sin(ang)

    d.line((px, py, sx, sy), fill=INK, width=3)
    d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=INK)
    d.rectangle((sx - 3, sy - 3, sx + 3, sy + 3), fill=MARIGOLD)


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
        d.text((PANEL_X, CLOCK_Y), clock_text(int(t), int(seconds)),
               font=fonts["bold"], fill=IVORY)
        yield img


def encode_cmd(src, out, seconds):
    """Raw RGB on stdin + the side's audio -> house-spec MP4.

    CRF 23 like the assembler; ErsatzTV re-encodes on air, what matters is
    that the groove edges survive. Audio is transcoded once, mono -> stereo
    AAC 48 kHz, and NOT processed: this is the disc as LAC published it.
    `-shortest` is not used: the picture runs the full audio length by
    construction, and `z0-video-tail.sh scan` proves it afterwards."""
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
    """The whole side. A side the lunch pool bound would exclude is refused
    here rather than cut: the pool is `minutes:[0 TO 9]` and a cut song is
    worse than a missing one."""
    seconds = duration(src)
    if seconds > MAX_MINUTES * 60:
        raise RuntimeError("%.0f s side exceeds the %d min pool bound" % (seconds, MAX_MINUTES))

    fonts = load_fonts()
    proc = subprocess.Popen(encode_cmd(src, out, seconds), stdin=subprocess.PIPE)
    for img in frames(side, env, seconds, fonts):
        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")


# ═══ docs ═══════════════════════════════════════════════════════════════════

def tex_escape(s):
    s = s.replace("\\", "\\textbackslash{}")
    for ch in "&%$#_{}":
        s = s.replace(ch, "\\" + ch)
    s = s.replace("~", "\\textasciitilde{}").replace("^", "\\textasciicircum{}")
    return s.replace("<=", "\\ensuremath{\\leq}")


def tex_rows(sides):
    """One `ripmdlongtable` row per side: TITLE & SOURCE & CLOCKS, in the
    shape of the Canadian film tables in docs/programming-library.tex."""
    rows = []
    for side in sides:
        st, v = status(side)
        if st is Status.CLEAR:
            clocks = "s.23 %s; s.6 %s. CLEAR." % (v[Clock.RECORDING].replace("  ", ", "),
                                                v[Clock.WORK].replace("  ", ", "))
        else:
            clocks = "%s (%s): %s." % (st.value, v.clock.value, str(v).split(": ", 1)[1])

        work = side.get("work") or {}
        credits = "; ".join("%s %s" % (role[:-1], ", ".join(work[role]))
                            for role in WORK_ROLES if work.get(role))
        if credits:
            clocks = "%s %s" % (credits + ".", clocks)

        title = "%s — %s" % (side["performer"], side["title"])
        if side.get("year"):
            title += " (%d)" % side["year"]
        src = "\\ripmono{obj/\\allowbreak{}m2/\\allowbreak{}f7/\\allowbreak{}%s.mp3}" % side["id"]
        record = re.search(r"idNumber=(\d+)", work.get("source", ""))
        if record:
            src += "; LAC record \\ripmono{%s}" % record.group(1)
        rows.append("%s & %s & %s \\\\" % (tex_escape(title), src, tex_escape(clocks)))

    return rows


# ═══ CLI ════════════════════════════════════════════════════════════════════

def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "select":
        with open(argv[2]) as fh:
            stage = json.load(fh)
        sides = select(stage, argv[3])
        with open(argv[4], "w") as fh:
            json.dump(sides, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("%d LAC sides, %d clear" % (len(sides), len(cleared(sides))))
        return 0

    if cmd == "check":
        sides = [load_side(argv[2])] if len(argv) > 2 else load_sides()
        counts = {st: 0 for st in Status}
        for side in sides:
            st, v = status(side)
            counts[st] += 1
            if st is not Status.CLEAR:
                print("%-6s %-10s %s" % (side["id"], st.value, v))
                continue

            print("%-6s %-10s %s | %s" % (side["id"], st.value, v[Clock.RECORDING], v[Clock.WORK]))

        print("  ".join("%s %d" % (st.value, n) for st, n in counts.items()))
        return 0

    if cmd == "stamp":
        sides = load_sides()
        for side in sides:
            side["status"] = status(side)[0].value
        with open(SIDES, "w") as fh:
            json.dump(sides, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("  ".join("%s %d" % (st.value, sum(s["status"] == st.value for s in sides))
                        for st in Status))
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

    if cmd == "stem":
        print(rel_path(load_side(argv[2])))
        return 0

    if cmd == "tex":
        print("\n".join(tex_rows(load_sides())))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
