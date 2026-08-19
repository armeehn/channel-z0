#!/usr/bin/env python3
"""Render the L-system station intervals: the picture, and the program that made it.

Each clip is one specimen from `specimens/`, and that specimen file is used
three times over:

  1. `qjs lsys-emit.js` imports it and walks the turtle, which is what draws
     the ink -- a still frame per video frame, growing stroke by stroke.
  2. `ffedit -f mv -s <specimen>` runs the SAME file over the encoded
     bitstream, where its `glitch_frame` replaces every motion vector with the
     heading of the branch that crosses that macroblock. The picture is then
     smeared along its own growth by the MPEG-2 decoder.
  3. The renderer prints it, verbatim, into the panel on the right.

So the code on screen is not an illustration of the algorithm. It is the
algorithm, and the two halves of the frame cannot disagree.

Why this can all run on one host, unlike tools/z0-generative.py: nothing here
needs numpy or Glitchsheet. LXC 111 has ffgac, ffedit and qjs at /opt/ffglitch
AND a real ffmpeg with libx264, so the render, the glitch and the H.264 encode
happen in one place. (numpy in LXC 111 is in fact broken -- it is built against
a newer glibc than the container has -- so PIL does all the raster work here.)

Load-bearing details, each of which cost something to find:

  * The carrier is encoded `+nopimb+forcemv`, `-qscale:v 1`, one enormous GOP,
    `-sc_threshold max`. forcemv writes a motion vector for every macroblock
    even where the encoder wants none, nopimb keeps intra blocks out of P
    frames, and the single I frame at the top means damage propagates for the
    whole clip instead of being scrubbed a few frames later.

  * The art viewport is 448x480 -- 28x30 whole macroblocks. An unaligned size
    leaves a partial block column at the edge and the block grid is the entire
    aesthetic.

  * Motion vectors that fetch from outside the frame decode as flat saturated
    green. The specimens fade their field out over the last three macroblocks
    at each edge for exactly that reason; it is not a taste decision.

  * `-sp` takes integers only. ffedit's JSON parser rejects a float outright
    and then writes no output file, which reads like a crash. Fractions travel
    percent-scaled and are divided inside the script.

  * The ink frames are written into ffgac over a pipe, and the glitched frames
    are read back over another. A 55-second clip is 1650 frames; as PNGs that
    is a gigabyte of temporary files per specimen, for no gain.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
FFGAC = os.environ.get("Z0_FFGAC", "/opt/ffglitch/ffgac")
FFEDIT = os.environ.get("Z0_FFEDIT", "/opt/ffglitch/ffedit")
QJS = os.environ.get("Z0_QJS", "/opt/ffglitch/qjs")
MONO = "/usr/share/fonts/liberation/LiberationMono-%s.ttf"

FRAME_W, FRAME_H = 854, 480     # the channel's own frame, so nothing is padded
ART_W = 448                     # 28 x 30 macroblocks
PANEL_W = FRAME_W - ART_W       # 406
PAD = 14

# The phosphor palette, per BRAND.md: anything that represents the broadcast
# gets the CRT treatment, not the Riposte brand.
BG = (13, 13, 13)
RULE = (74, 58, 16)
LABEL = (154, 108, 20)
CODE = (201, 139, 22)
COMMENT = (112, 84, 30)

LIST_TOP = 72
LIST_LINES = 24        # the most that fit above the footer
LEAD = 14


def hex2rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def geometry(spec_path, work):
    """Walk the specimen's turtle by running the specimen itself under qjs."""
    shutil.copy(spec_path, os.path.join(work, "_specimen.js"))
    shutil.copy(os.path.join(HERE, "lsys-emit.js"),
                os.path.join(work, "lsys-emit.js"))
    p = run([QJS, "lsys-emit.js", str(ART_W), str(FRAME_H)], cwd=work)
    if p.returncode != 0 or not p.stdout.strip():
        raise SystemExit("qjs failed on %s:\n%s" % (spec_path, p.stderr[-800:]))
    return json.loads(p.stdout)


# ---------------------------------------------------------------------------
# the left half: ink
# ---------------------------------------------------------------------------

def ink_frames(geo, a, n_frames):
    """The turtle drawing itself, one frame at a time.

    Only the new strokes change between frames, so the encoder spends bits on
    those and codes everything else as a zero-residual prediction -- which is
    the whole trick: a block with no residual is whatever the motion vector
    fetched, and the motion vectors are the L-system.
    """
    seg = geo["seg"]
    ink = hex2rgb(geo["sys"]["ink"])
    head = tuple(min(255, int(c * 0.4 + 165)) for c in ink)
    canvas = Image.new("RGB", (ART_W, FRAME_H), BG)
    d = ImageDraw.Draw(canvas)
    p = 0
    for f in range(n_frames):
        u = (f * 100.0 / n_frames - a.t0) / float(a.t1 - a.t0)
        if u > 0:
            lim = min(1.0, u)
            while p < len(seg) and seg[p][4] <= lim:
                s = seg[p]
                d.line((s[0], s[1], s[2], s[3]), fill=ink, width=a.width)
                p += 1
        # Once the turtle is done the canvas is left alone: a static source
        # means no residual at all, so the bloom at the end is pure motion.
        if u <= 0 or u > 1.0 or p == 0:
            yield canvas
            continue
        img = canvas.copy()
        dd = ImageDraw.Draw(img)
        for q in range(max(0, p - a.head), p):
            s = seg[q]
            dd.line((s[0], s[1], s[2], s[3]), fill=head, width=a.width)
        yield img


# ---------------------------------------------------------------------------
# the right half: the source
# ---------------------------------------------------------------------------

def char_colours(text, ink):
    """One colour per character. Monospace makes this enough to syntax-colour."""
    out = []
    in_str = in_com = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_com:
            out.append(COMMENT)
        elif in_str:
            out.append(ink)
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(ink)
        elif c == "/" and text[i:i + 2] == "//":
            in_com = True
            out.append(COMMENT)
        else:
            out.append(CODE)
        i += 1
    return out


class Panel(object):
    """The right-hand column: title, a page of the source, and the counters."""

    def __init__(self, geo, src_lines, spec_name, sha, index, total, adv,
                 fonts, sp):
        self.geo = geo
        self.lines = src_lines
        self.spec = spec_name
        self.sha = sha
        self.index = index
        self.total = total
        self.adv = adv
        self.f_title, self.f_code, self.f_small, self.f_tiny = fonts
        self.ink = hex2rgb(geo["sys"]["ink"])
        self.sp = sp
        self.cols = max(1, int((PANEL_W - 2 * PAD) / adv))
        # Show the whole file exactly once per clip: take the fewest pages
        # that hold it, then spread the lines evenly over them, so the last
        # page is not two lines and eight seconds of empty panel.
        self.pages = max(1, -(-len(src_lines) // LIST_LINES))
        self.per = -(-len(src_lines) // self.pages)
        self.page_cache = {}

    def _chrome(self):
        im = Image.new("RGB", (PANEL_W, FRAME_H), BG)
        d = ImageDraw.Draw(im)
        x = PAD
        d.line((x, 10, PANEL_W - PAD, 10), fill=RULE)
        d.text((x, 15), "CH 0  STATION INTERVAL", font=self.f_small,
               fill=LABEL)
        d.text((x, 31), self.geo["sys"]["name"], font=self.f_title,
               fill=self.ink)
        d.text((x, 52), self.geo["sys"]["caption"][:self.cols],
               font=self.f_small, fill=LABEL)
        d.line((x, 68, PANEL_W - PAD, 68), fill=RULE)
        d.line((x, 408, PANEL_W - PAD, 408), fill=RULE)
        return im

    def page(self, n):
        if n in self.page_cache:
            return self.page_cache[n]
        im = self._chrome()
        d = ImageDraw.Draw(im)
        first = n * self.per
        for k in range(self.per):
            if first + k >= len(self.lines):
                break
            text = self.lines[first + k][:self.cols]
            y = LIST_TOP + k * LEAD
            cols = char_colours(text, self.ink)
            s = 0
            while s < len(text):
                e = s
                while e < len(text) and cols[e] == cols[s]:
                    e += 1
                d.text((PAD + s * self.adv, y), text[s:e], font=self.f_code,
                       fill=cols[s])
                s = e
        self.page_cache[n] = im
        return im

    def frame(self, page, window, frame_no, n_frames):
        im = self.page(page).copy()
        d = ImageDraw.Draw(im)
        x = PAD
        d.text((x, 414), window[:self.cols], font=self.f_code, fill=LABEL)
        # The command really run, over two lines, because the -sp payload
        # does not fit on one and a truncated one would be a lie.
        d.text((x, 430), "$ ffedit -f mv -s %s -o art.mpg -sp \\" % self.spec,
               font=self.f_tiny, fill=COMMENT)
        d.text((x, 441), "  " + self.sp, font=self.f_tiny, fill=COMMENT)
        g = self.geo
        d.text((x, 454), "gen %d   %s symbols   %s drawn"
               % (g["sys"]["gens"], "{:,}".format(g["symbols"]),
                  "{:,}".format(g["drawn"])),
               font=self.f_tiny, fill=LABEL)
        d.text((x, 466), "src %d/%d   sha1 %s   frame %04d/%04d"
               % (page + 1, self.pages, self.sha[:8], frame_no, n_frames),
               font=self.f_tiny, fill=COMMENT)
        return im


# ---------------------------------------------------------------------------
# the pipeline
# ---------------------------------------------------------------------------

def encode_carrier(geo, a, n_frames, out_mpg):
    cmd = [FFGAC, "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (ART_W, FRAME_H), "-framerate", str(a.fps),
           "-i", "-", "-an", "-vcodec", "mpeg2video",
           "-mpv_flags", "+nopimb+forcemv", "-qscale:v", "1",
           "-g", str(n_frames + 16), "-sc_threshold", "max",
           "-f", "rawvideo", "-y", out_mpg]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for img in ink_frames(geo, a, n_frames):
            p.stdin.write(img.tobytes())
    except BrokenPipeError:
        pass
    p.stdin.close()
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0 or not os.path.getsize(out_mpg):
        raise SystemExit("carrier encode failed:\n" + err[-800:])


def sp_params(a, n_frames):
    """ffedit's -sp payload. Every value is an integer: its JSON parser
    rejects a float outright and then writes no output file at all."""
    return json.dumps({"frames": n_frames, "t0": a.t0, "t1": a.t1,
                       "win": a.win, "trim": a.trim, "bloom": a.bloom},
                      separators=(",", ":"))


def glitch(spec_path, in_mpg, out_mpg, sp):
    """Run the specimen over the bitstream, and prove it did something.

    A script that walks the wrong structure -- iterating an object with
    .length, say -- edits nothing and ffedit still exits 0, having written a
    byte-identical stream. The clip then ships as a plain line drawing with a
    code panel claiming a glitch that never happened, and every surface
    downstream reports success. Comparing the two files is the only thing
    between that and air.
    """
    p = run([FFEDIT, "-i", in_mpg, "-f", "mv", "-threads", "1",
             "-s", spec_path, "-sp", sp, "-o", out_mpg, "-y"])
    if p.returncode != 0 or not os.path.exists(out_mpg) \
            or not os.path.getsize(out_mpg):
        raise SystemExit("ffedit failed on %s:\n%s"
                         % (spec_path, p.stderr[-800:]))
    if sha1_file(in_mpg) == sha1_file(out_mpg):
        raise SystemExit(
            "%s changed nothing: ffedit wrote a byte-identical stream, so "
            "the clip would be a drawing with no glitch in it at all."
            % os.path.basename(spec_path))


def compose(art_mpg, seed_mpg, panel, geo, a, n_frames, out_mp4):
    """Decode the glitched art, set the source beside it, encode for air.

    Also measures whether the motion vectors are doing anything at all, by
    decoding the untouched carrier alongside the glitched one and comparing
    them frame by frame. Same encoder, same quantiser, so with the vectors
    left alone the two are identical and the measure is exactly zero: what it
    reports is the glitch and nothing else.

    Neither cheaper check works. Comparing the two BITSTREAMS says nothing --
    ffedit re-codes a vector it was handed even when the value is unchanged,
    so writing zero everywhere still produces a different file while the
    picture stands perfectly still. Watching the glitched clip alone says
    little more: the drawing is moving anyway, because the turtle is still
    drawing it.
    """
    dec = subprocess.Popen(
        [FFGAC, "-hide_banner", "-loglevel", "error", "-i", art_mpg,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ref = subprocess.Popen(
        [FFGAC, "-hide_banner", "-loglevel", "error", "-i", seed_mpg,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    enc = subprocess.Popen(
        [a.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "%dx%d" % (FRAME_W, FRAME_H), "-framerate", str(a.fps),
         "-i", "-", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-shortest", "-c:v", "libx264", "-preset", a.preset,
         "-b:v", a.bitrate, "-pix_fmt", "yuv420p", "-r", str(a.fps),
         "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv",
         "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", out_mp4],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    n_bytes = ART_W * FRAME_H * 3
    # one pass through the source, however long the file is
    page_frames = max(1.0, float(n_frames) / panel.pages)
    string = geo["string"]
    frame = Image.new("RGB", (FRAME_W, FRAME_H), BG)
    seen = 0
    last = None
    moved, moved_n = 0.0, 0
    try:
        while seen < n_frames:
            buf = dec.stdout.read(n_bytes)
            if not buf or len(buf) < n_bytes:
                if last is None:
                    break
                art = last          # pad a short decode rather than truncate
            else:
                art = Image.frombytes("RGB", (ART_W, FRAME_H), buf)
                last = art
            # Keep the reference pipe draining every frame; only pay for
            # the comparison on some of them.
            rbuf = ref.stdout.read(n_bytes)
            if rbuf and len(rbuf) == n_bytes and seen % 3 == 0:
                moved += ImageStat.Stat(ImageChops.difference(
                    art, Image.frombytes("RGB", (ART_W, FRAME_H),
                                         rbuf))).mean[0]
                moved_n += 1
            u = (seen * 100.0 / n_frames - a.t0) / float(a.t1 - a.t0)
            pos = int(min(1.0, max(0.0, u)) * max(0, len(string) - 1))
            half = panel.cols // 2
            lo = max(0, pos - half)
            window = string[lo:lo + panel.cols].ljust(panel.cols)
            page = min(panel.pages - 1, int(seen / page_frames))
            frame.paste(art, (0, 0))
            frame.paste(panel.frame(page, window, seen + 1, n_frames),
                        (ART_W, 0))
            enc.stdin.write(frame.tobytes())
            seen += 1
    except BrokenPipeError:
        pass
    enc.stdin.close()
    try:
        ref.stdout.close()
    except OSError:
        pass
    ref.wait()
    derr = dec.stderr.read().decode("utf-8", "replace")
    eerr = enc.stderr.read().decode("utf-8", "replace")
    dec.wait()
    if enc.wait() != 0:
        raise SystemExit("h264 encode failed:\n%s\n%s" % (derr[-400:],
                                                          eerr[-800:]))
    return seen, (moved / moved_n if moved_n else 0.0)


NFO = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>%s</title>
  <sorttitle>%s</sorttitle>
  <mpaa>Z0-GENERAL</mpaa>
  <outline>%s</outline>
  <plot>%s</plot>
  <tag>media</tag>
  <tag>generative</tag>
</movie>
"""


def probe_duration(path, ffprobe):
    p = run([ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    try:
        return float(p.stdout.strip())
    except ValueError:
        return -1.0


def render_one(spec_path, a, outdir, index, total):
    slug = os.path.basename(spec_path)[:-3]
    src = open(spec_path).read()
    sha = hashlib.sha1(src.encode("utf-8")).hexdigest()
    lines = src.rstrip("\n").split("\n")
    n_frames = int(round(a.seconds * a.fps))

    work = tempfile.mkdtemp(prefix="z0lsys-%s-" % slug, dir=a.workdir)
    try:
        geo = geometry(spec_path, work)
        adv = a.font_adv
        fonts = (ImageFont.truetype(MONO % "Bold", 17),
                 ImageFont.truetype(MONO % "Bold", 12),
                 ImageFont.truetype(MONO % "Regular", 11),
                 ImageFont.truetype(MONO % "Regular", 10))
        sp = sp_params(a, n_frames)
        panel = Panel(geo, lines, os.path.basename(spec_path), sha,
                      index, total, adv, fonts, sp)

        seed = os.path.join(work, "seed.mpg")
        art = os.path.join(work, "art.mpg")
        encode_carrier(geo, a, n_frames, seed)
        glitch(spec_path, seed, art, sp)

        name = "z0-lsys-%s.mp4" % slug
        tmp = os.path.join(outdir, ".%s.tmp.mp4" % slug)
        seen, moved = compose(art, seed, panel, geo, a, n_frames, tmp)

        if moved < a.min_motion:
            os.unlink(tmp)
            raise SystemExit(
                "%s REFUSED: the glitched picture differs from the carrier "
                "by %.3f levels, under the %.2f floor -- the motion vectors "
                "are not moving anything."
                % (slug, moved, a.min_motion))

        dur = probe_duration(tmp, a.ffprobe)
        if abs(dur - a.seconds) > 1.0:
            os.unlink(tmp)
            raise SystemExit("%s REFUSED: %.2fs, expected %.2fs"
                             % (name, dur, a.seconds))
        out = os.path.join(outdir, name)
        os.replace(tmp, out)

        title = "z0-lsys-%s" % slug
        blurb = "%s -- %s. Lindenmayer system drawn and glitched by its own source." \
                % (geo["sys"]["name"], geo["sys"]["caption"])
        with open(os.path.join(outdir, "z0-lsys-%s.nfo" % slug), "w") as f:
            f.write(NFO % (title, title, blurb, blurb))

        size = os.path.getsize(out) / 1048576.0
        print("%-22s %6.2fs %5.1f MiB  %-11s gen %2d  %7s sym  %6s drawn"
              "  glitch %6.2f"
              % (name, dur, size, geo["sys"]["name"], geo["sys"]["gens"],
                 "{:,}".format(geo["symbols"]), "{:,}".format(geo["drawn"]),
                 moved))
        return {"file": name, "specimen": os.path.basename(spec_path),
                "sha1": sha, "seconds": round(dur, 2), "frames": seen,
                "name": geo["sys"]["name"], "caption": geo["sys"]["caption"],
                "axiom": geo["sys"]["axiom"], "rules": geo["sys"]["rules"],
                "angle": geo["sys"]["angle"], "gens": geo["sys"]["gens"],
                "symbols": geo["symbols"], "drawn": geo["drawn"],
                "push": geo["sys"].get("push"),
                "params": {"t0": a.t0, "t1": a.t1, "win": a.win,
                           "trim": a.trim, "bloom": a.bloom, "fps": a.fps}}
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specimens", default=os.path.join(HERE, "specimens"))
    ap.add_argument("--out-dir", default="/tmp/z0lsys/out")
    ap.add_argument("--workdir", default="/tmp/z0lsys")
    ap.add_argument("--only", default="", help="comma-separated slugs")
    ap.add_argument("--seconds", type=float, default=55.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1, help="stroke width")
    ap.add_argument("--head", type=int, default=140,
                    help="strokes lit at the growing tip")
    ap.add_argument("--font-adv", type=float, default=7.2)
    # These four reach the specimen through -sp, so they are integers.
    ap.add_argument("--t0", type=int, default=3, help="growth starts, %% of clip")
    ap.add_argument("--t1", type=int, default=85, help="growth ends, %% of clip")
    ap.add_argument("--win", type=int, default=3,
                    help="width of the moving wave, %% of the string")
    ap.add_argument("--trim", type=int, default=100,
                    help="global scale on every specimen's push, %%")
    ap.add_argument("--bloom", type=int, default=30,
                    help="drift once the turtle is done, %% of full push")
    ap.add_argument("--bitrate", default="3000k")
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--ffprobe", default="ffprobe")
    ap.add_argument("--min-motion", type=float, default=1.0,
                    help="refuse a clip whose picture stands still")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(a.workdir, exist_ok=True)
    specs = sorted(os.path.join(a.specimens, f)
                   for f in os.listdir(a.specimens) if f.endswith(".js"))
    if a.only:
        want = set(s.strip() for s in a.only.split(","))
        specs = [s for s in specs
                 if os.path.basename(s)[:-3] in want]
    if not specs:
        raise SystemExit("no specimens matched")

    index = []
    for i, s in enumerate(specs, 1):
        index.append(render_one(s, a, a.out_dir, i, len(specs)))
    with open(os.path.join(a.out_dir, "lsys.json"), "w") as f:
        json.dump({"clips": index}, f, indent=1)
    print("\n%d clips, %.1f min of material"
          % (len(index), sum(c["seconds"] for c in index) / 60.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
