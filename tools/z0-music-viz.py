#!/usr/bin/env python3
"""Channel Z0 — turn a LUNCH LOOPS music card into a real audio visualiser.

The 73 music items are a still card muxed against a stream-copied audio track.
This replaces the still with an animation driven by the track's OWN spectrum,
without touching the audio: `-c:a copy` throughout, because these are the only
surviving digital transfers of the 78s and they have already been through one
encode.

How it works, and why it is not an ffmpeg one-liner:

  1. ffmpeg does the DSP. N `bandpass` chains, each followed by
     `asetnsamples=n=1600` (= exactly one 30fps video frame at 48kHz) and
     `astats=reset=1`, print one RMS figure per band per frame. That is the
     whole spectrum measurement, done in C, in one pass, at ~85x realtime.
     Doing an FFT in Python here would be minutes per track; numpy is not
     importable in LXC 111 (glibc), so this is not a style preference.
  2. Python does the drawing only — no DSP. It turns those numbers into
     bar heights and paints them into a raw RGBA buffer, which is piped
     straight back into ffmpeg and `overlay`ed onto the card.

The overlay is RGBA with a transparent background, which is what lets the bars
sit on the card's radial gradient without having to reconstruct it.

`astats` prints its figures at INFO level. Running the measurement pass at
`-v error` yields a silently EMPTY result set, not an error.
"""
import argparse, os, shlex, shutil, subprocess, sys, tempfile

# vile has the media but no host ffmpeg, so there it runs
#   FFMPEG='docker run --rm -i --entrypoint /usr/local/bin/ffmpeg -v <tree>:<tree> linuxserver/ffmpeg'
# with the tree bind-mounted at the SAME path inside the container, so every
# path this script builds is valid on both sides and nothing needs rewriting.
FFMPEG  = shlex.split(os.environ.get('FFMPEG',  'ffmpeg'))
FFPROBE = shlex.split(os.environ.get('FFPROBE', 'ffprobe'))

FPS = 30
SR = 48000
NS = SR // FPS            # 1600 samples == one video frame
CARD_W, CARD_H = 640, 480

# Brand palette (BRAND.md). Hard edges, no blur, no fade — station house style.
INK    = (0x0b, 0x0f, 0x14)
BONE   = (0xf6, 0xf1, 0xe7)
LINE   = (0x5c, 0x55, 0x4c)
PINK   = (0xf0, 0x47, 0x7d)
ORANGE = (0xfe, 0x9a, 0x0d)
TEAL   = (0x12, 0xb7, 0x95)

SILENT_DB = -120.0


# ---------------------------------------------------------------- measurement

def log_bands(n, lo, hi):
    """n log-spaced centre frequencies from lo to hi."""
    if n == 1:
        return [lo]
    r = (hi / lo) ** (1.0 / (n - 1))
    return [lo * (r ** i) for i in range(n)]


def measure(src, freqs, workdir, verbose=False):
    """Per-frame RMS (dB) for each band. Returns list-of-lists, band-major."""
    files = [os.path.join(workdir, 'band%02d.txt' % i) for i in range(len(freqs))]
    parts = ['[0:a]aformat=sample_fmts=fltp:sample_rates=%d:channel_layouts=mono,'
             'asplit=%d%s' % (SR, len(freqs),
                              ''.join('[c%d]' % i for i in range(len(freqs))))]
    for i, (f, path) in enumerate(zip(freqs, files)):
        # width_type=o:w=1.5 -> 1.5-octave bandpass. Narrower reads as noisy and
        # twitchy on 78s (which are mostly broadband surface noise up top);
        # wider smears the bands into each other and the bars move as one.
        chain = ('[c%d]bandpass=f=%.1f:width_type=o:w=1.5,'
                 'asetnsamples=n=%d:p=0,'
                 'astats=metadata=1:reset=1,'
                 'ametadata=print:key=lavfi.astats.Overall.RMS_level:file=%s'
                 % (i, f, NS, _esc(path)))
        # A filtergraph must have at least one output, so the last chain is
        # mapped to the null muxer and the rest are dead-ended.
        parts.append(chain + ('[out]' if i == len(freqs) - 1 else ',anullsink'))
    cmd = FFMPEG + ['-v', 'info', '-nostdin', '-y', '-i', src,
           '-filter_complex', ';'.join(parts), '-map', '[out]', '-f', 'null', '-']
    run(cmd, verbose)

    series = []
    for path in files:
        vals = []
        with open(path) as fh:
            for ln in fh:
                if ln.startswith('lavfi.'):
                    raw = ln.strip().split('=', 1)[1]
                    try:
                        v = float(raw)
                    except ValueError:
                        v = SILENT_DB          # -inf / nan on digital silence
                    vals.append(SILENT_DB if v != v or v < SILENT_DB else v)
        series.append(vals)
    n = min(len(s) for s in series)
    return [s[:n] for s in series]


def _esc(path):
    """Escape a path for use INSIDE an ffmpeg filter argument."""
    return path.replace('\\', '\\\\').replace(':', '\\:').replace("'", r"\'")


# ---------------------------------------------------------------- shaping

def pct(sorted_vals, q):
    if not sorted_vals:
        return SILENT_DB
    i = int(len(sorted_vals) * q)
    return sorted_vals[min(i, len(sorted_vals) - 1)]


def shape(series, attack=0.55, decay=0.045, peak_decay=0.011):
    """dB series -> (levels, peaks) in 0..1, band-major.

    Normalised PER BAND but with a SHARED span. Per-band floors are essential:
    these transfers roll off hard at both ends, so a globally-scaled bass band
    would sit at zero for the whole track and the bar would look broken. A
    shared span is what stops the opposite failure — independently scaling each
    band makes quiet bands as tall as loud ones and the display stops meaning
    anything.
    """
    floors, spans = [], []
    for vals in series:
        live = sorted(v for v in vals if v > SILENT_DB + 1)
        if len(live) < FPS:                     # essentially silent band
            floors.append(0.0); spans.append(1.0); continue
        lo, hi = pct(live, 0.10), pct(live, 0.98)
        floors.append(lo)
        spans.append(max(hi - lo, 6.0))         # never divide by a tiny range
    span = sorted(spans)[len(spans) // 2]       # median span, shared

    levels, peaks = [], []
    for vals, floor in zip(series, floors):
        lv, pk = [], []
        cur = 0.0
        cap = 0.0
        for v in vals:
            x = 0.0 if v <= SILENT_DB + 1 else (v - floor) / span
            x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
            # fast attack, slow decay: a bar that fell as fast as it rose reads
            # as flicker rather than as level
            cur = cur + (x - cur) * attack if x > cur else max(x, cur - decay)
            cap = cur if cur >= cap else max(cur, cap - peak_decay)
            lv.append(cur); pk.append(cap)
        levels.append(lv); peaks.append(pk)
    return levels, peaks


# ---------------------------------------------------------------- drawing

class Region:
    """A raw RGBA overlay plane, drawn per frame and piped to ffmpeg."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.blank = bytes(w * h * 4)

    def frame(self, bars, peaks, colours, geom, peak_h=3):
        """bars/peaks: 0..1 per band. geom: (x0, bar_w, gap)."""
        buf = bytearray(self.blank)
        x0, bw, gap = geom
        w, h = self.w, self.h
        for i, lvl in enumerate(bars):
            bx = x0 + i * (bw + gap)
            if bx + bw > w:
                break
            r, g, b = colours[i]
            row = bytes((r, g, b, 255)) * bw
            bh = int(lvl * h + 0.5)
            if bh > h:
                bh = h
            for y in range(h - bh, h):
                off = (y * w + bx) * 4
                buf[off:off + bw * 4] = row
            # peak cap — a bone tick that falls slower than the bar, so the
            # loudest moment of the last couple of seconds stays legible
            py = h - int(peaks[i] * h + 0.5)
            if 0 <= py < h:
                cap = bytes(BONE + (255,)) * bw
                for y in range(py, min(py + peak_h, h)):
                    off = (y * w + bx) * 4
                    buf[off:off + bw * 4] = cap
        return bytes(buf)


# ---------------------------------------------------------------- styles
#
# Geometry is in 640x480 card space.
#
# The card was laid out on 2026-08-14, when the crawl was still burnt over the
# bottom of the PICTURE and its comment reserves "nothing below y 375". PR #35
# (2026-08-19) moved every on-air element into the 854x480 pillarbox rails, so
# that band is now dead space rather than reserved space, and `analyser` is what
# puts it back to work. Do not re-tighten this to the old safe area without
# checking where the furniture actually lives.

STYLES = {
    # The card already draws a five-bar equaliser as a static MARK. This makes
    # that same mark real: identical position, width, gap and colours, only the
    # heights now come from the audio.
    'mark': dict(x=481, y=120, w=103, h=120, n=5, bar=15, gap=7,
                 lo=80.0, hi=5000.0, peak=3,
                 colours=[LINE, ORANGE, LINE, LINE, TEAL]),

    # A wide analyser across the band the crawl used to occupy, aligned to the
    # card's own 40px text margin.
    'analyser': dict(x=40, y=408, w=560, h=60, n=20, bar=21, gap=7,
                     lo=70.0, hi=6000.0, peak=3,
                     colours=None),              # tri-band segments, see below

    # The whole lower half, with the datum strip moved to the very bottom
    # (card `data-viz="tall"`). The card's middle band is otherwise empty once
    # the static mark is gone, so this is the version that does not leave a
    # hole where the mark used to be.
    #
    # y=268 is MEASURED, not chosen. render-music.mjs shrinks the TITLE to fit
    # but not the artist credit, and one of the 73 ("Freddy Chetyrbok with
    # Johnny & The Nite-Lighters - You Old Miser-Teah Stawray Kawlawbieyou")
    # wraps that credit onto a second line reaching y=257.5. An earlier y=250
    # cleared 72 cards and clipped that one. Re-measure with tools/z0-viz-extent.py
    # before moving this up, and note that a full-width scan is misleading: the
    # decorative .corner.bl bracket sits at y 355-368, but at x 18-31, which the
    # analyser never reaches.
    'tall': dict(x=40, y=268, w=560, h=172, n=20, bar=21, gap=7,
                 lo=70.0, hi=6000.0, peak=4,
                 colours=None),
}


def triband_ramp(n):
    """Pink / orange / teal across n bars, matching the card's top triband.

    HARD SEGMENTS, cut at the same 36% and 64% stops as the triband in the
    card CSS. The first version of this interpolated between the three brand
    colours, which looks reasonable in a swatch and wrong on air: orange->teal
    passes through olive and the analyser came out a rainbow containing two
    colours the station does not own. Everything else in Z0's furniture is
    hard-edged and unblended; this matches it.
    """
    out = []
    for i in range(n):
        t = (i + 0.5) / n
        out.append(PINK if t < 0.36 else (ORANGE if t < 0.64 else TEAL))
    return out


# ---------------------------------------------------------------- encode

def run(cmd, verbose=False):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode('utf8', 'replace')[-4000:])
        raise SystemExit('ffmpeg failed: %s' % cmd[0])
    if verbose:
        sys.stderr.write(p.stderr.decode('utf8', 'replace')[-2000:])
    return p


def duration(path):
    out = subprocess.run(FFPROBE + ['-v', 'error', '-show_entries',
                                    'format=duration', '-of', 'csv=p=0', path],
                         stdout=subprocess.PIPE).stdout.decode().strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def render(src, card, out, style, workdir, limit=None, verbose=False):
    cfg = STYLES[style]
    freqs = log_bands(cfg['n'], cfg['lo'], cfg['hi'])
    series = measure(src, freqs, workdir, verbose)
    levels, peaks = shape(series)
    nframes = len(levels[0])
    if limit:
        nframes = min(nframes, int(limit * FPS))
    colours = cfg['colours'] or triband_ramp(cfg['n'])

    reg = Region(cfg['w'], cfg['h'])
    geom = (0, cfg['bar'], cfg['gap'])

    # NOTE: no -nostdin here. remux-music.sh needs it because ffmpeg would
    # otherwise eat the shell loop's stdin; this encode is FED on stdin (the
    # raw RGBA overlay), so suppressing it would break the thing it protects.
    cmd = FFMPEG + [
        '-hide_banner', '-loglevel', 'error', '-y',
        '-loop', '1', '-framerate', str(FPS), '-i', card,
        '-f', 'rawvideo', '-pix_fmt', 'rgba', '-video_size',
        '%dx%d' % (cfg['w'], cfg['h']), '-framerate', str(FPS), '-i', '-',
        '-i', src,
        '-filter_complex',
        '[0:v]scale=%d:%d:flags=lanczos,setsar=1[card];'
        '[card][1:v]overlay=x=%d:y=%d:format=auto:shortest=1,format=yuv420p[v]'
        % (CARD_W, CARD_H, cfg['x'], cfg['y']),
        '-map', '[v]', '-map', '2:a:0',
        '-c:a', 'copy',
        '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
        '-b:v', '1200k', '-maxrate', '1500k', '-bufsize', '2400k',
        '-preset', 'veryfast', '-r', str(FPS), '-g', '60',
        '-shortest', '-movflags', '+faststart', out,
    ]
    if limit:
        cmd[-1:-1] = ['-t', str(limit)]

    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for f in range(nframes):
            p.stdin.write(reg.frame([levels[b][f] for b in range(cfg['n'])],
                                    [peaks[b][f] for b in range(cfg['n'])],
                                    colours, geom, cfg['peak']))
    except BrokenPipeError:
        pass
    finally:
        try:
            p.stdin.close()
        except BrokenPipeError:
            pass
    err = p.stderr.read().decode('utf8', 'replace')
    if p.wait() != 0:
        sys.stderr.write(err[-4000:])
        raise SystemExit('encode failed for %s' % out)
    return nframes



# ---------------------------------------------------------------- batch

def batch(args):
    """Render a whole track list.

    The safety rails are inherited from remux-music.sh and are not optional:

      * Output is built in a dot-DIRECTORY under the media tree. ErsatzTV's
        scanner skips dot-DIRECTORIES but happily indexes dot-FILES, so a
        temp written in place as ".name.tmp.mp4" becomes a real media item and
        then a permanent State=1 ghost the moment it is renamed away. There is
        already one such ghost row in the DB from the last music render.
      * The temp is renamed ONTO the original path. Same path = an update, not
        a rename, so no ghost row is created and the playout stays valid.
      * A duration guard refuses to replace a good file with a shorter one.
        Duration must be preserved exactly or the built schedule goes stale:
        every item after it in the block would shift.
    """
    stems = [ln.strip() for ln in open(args.list) if ln.strip()]
    tmpdir = os.path.join(args.media, '.z0-convtmp')
    os.makedirs(tmpdir, exist_ok=True)
    if args.stage:
        os.makedirs(args.stage, exist_ok=True)

    ok = fail = skip = 0
    for i, stem in enumerate(stems, 1):
        src = os.path.join(args.media, 'music', stem + '.mp4')
        card = os.path.join(args.cards, stem + '.png')
        if not os.path.exists(src):
            print('MISS-SRC   %s' % stem); fail += 1; continue
        if not os.path.exists(card):
            print('MISS-CARD  %s' % stem); fail += 1; continue

        tmp = os.path.join(tmpdir, 'viz_%03d.mp4' % i)
        work = tempfile.mkdtemp(prefix='z0viz.', dir=tmpdir)
        try:
            render(src, card, tmp, args.style, work, None, False)
        except SystemExit as e:
            print('FAIL       %s (%s)' % (stem, e)); fail += 1
            if os.path.exists(tmp):
                os.remove(tmp)
            continue
        finally:
            shutil.rmtree(work, ignore_errors=True)

        ds, dt = duration(src), duration(tmp)
        if abs(ds - dt) > 2.0:
            print('FAIL       %s duration %.1fs -> %.1fs, refusing' % (stem, ds, dt))
            os.remove(tmp); fail += 1; continue

        dest = os.path.join(args.stage, stem + '.mp4') if args.stage else src
        shutil.move(tmp, dest)
        print('OK    %3d/%d  %s (%.1fs)' % (i, len(stems), stem, dt))
        ok += 1

    print('=== music viz done: %d ok, %d failed, %d skipped ===' % (ok, fail, skip))
    return 1 if fail else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', help='source item (audio is stream-copied from it)')
    ap.add_argument('--card', help='640x480 card PNG (or 2x, it is scaled)')
    ap.add_argument('--out')
    ap.add_argument('--batch', action='store_true', help='render a whole track list')
    ap.add_argument('--list', help='batch: newline-separated stems')
    ap.add_argument('--media', help='batch: media root (contains music/)')
    ap.add_argument('--cards', help='batch: directory of <stem>.png backplates')
    ap.add_argument('--stage', help='batch: write here instead of replacing in place')
    ap.add_argument('--style', default='mark', choices=sorted(STYLES))
    ap.add_argument('--limit', type=float, help='seconds, for previews')
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()

    if a.batch:
        for req in ('list', 'media', 'cards'):
            if not getattr(a, req):
                ap.error('--batch needs --%s' % req)
        raise SystemExit(batch(a))

    if not (a.src and a.card and a.out):
        ap.error('--src, --card and --out are required without --batch')

    # Alongside the OUTPUT, never /tmp. The measurement pass writes its band
    # files with ffmpeg, and when ffmpeg is containerised (vile) a host /tmp
    # path does not exist inside the container -- the graph then fails at init
    # with "Could not open .../band00.txt", which reads like a permissions bug
    # and is really a mount bug. The output directory is writable and mounted
    # by definition, so it is the one safe default.
    work = tempfile.mkdtemp(prefix='z0viz.',
                            dir=os.path.dirname(os.path.abspath(a.out)) or '.')
    try:
        n = render(a.src, a.card, a.out, a.style, work, a.limit, a.verbose)
        print('%s  %s  %d frames  %.1fs' % (a.style, os.path.basename(a.out),
                                            n, duration(a.out)))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
