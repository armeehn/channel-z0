#!/usr/bin/env python3
"""Channel Z0 — generative station bumps.

A bump is 8–15 seconds of computed picture with a Z0 tagline on the end: the
thing that plays between two cartoons so the join reads as an advert break
and not a playlist. Everything here is drawn from a formula — no footage, no
stock, no AI — so the pool can be topped up forever without clearing rights.

    z0_bumps.py list                              every genre, family, tagline
    z0_bumps.py render --out DIR --family math --count 20 [--seed 7]
    z0_bumps.py render --out DIR --genre julia --count 3 --secs 10
    z0_bumps.py still  --genre lorenz --out frame.png [--t 6]

Three families, three folders, three collections (lists/z0-lists.yml):

    math    a formula drawn clean: attractors, Julia sets, Chladni plates,
            reaction-diffusion, epicycles, Ulam's spiral, Lorenz, life…
    glitch  a math genre run through a treatment: pixel sort, datamosh-style
            block bleed, VHS tracking, slit-scan, analogue feedback, bitcrush.
    lsys    L-systems grown stroke by stroke and NEVER glitched — the user's
            standing instruction; the ffedit L-system intervals are a separate
            family in tools/z0-lsys/.

Output is the house spec for station furniture: 854x480, 30 fps, H.264 under
3000 kbps, AAC 48 kHz, one .nfo sidecar per clip so the tags are explicit
(an NFO that omits a tag deletes it — see tools/z0-nfo.py). Needs numpy, PIL
and an ffmpeg with libx264: that is forge, not LXC 111 (numpy is broken there).

Every clip is deterministic in (genre, seed): re-rendering the same seed gives
the same file, so a bad clip can be reproduced and a good one regenerated.

Adding a genre: subclass Genre, set NAME / FACT / PALETTE, implement frame(),
register in GENRES. Nothing else changes; the CLI, the families, the audio and
the NFO all key off the registry. Standing constraints for every genre: NO
CROSSHAIRS (no reticles, no targets), nothing that reads as violence, no
subtitle-style strip at the bottom edge (the rails own the gutters).
"""

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── House spec ──────────────────────────────────────────────────────────────
W, H = 854, 480
FPS = 30
DEFAULT_SECS = 12
MIN_SECS, MAX_SECS = 6, 30
CARD_SECS = 3.2          # the tagline card at the end
CAPTION_AT = 1.2         # when the genre fact fades in
CAPTION_FADE = 0.5
CARD_FADE = 0.3          # video fade-out at the very end
BITRATE_CAP = "3000k"    # assembler gate for intervals; same ceiling here
AUDIO_RATE = 48000
SUPER = 2                # vector genres draw at 2x and downsample for AA

# ── Brand ───────────────────────────────────────────────────────────────────
# Tokens from api.hq /v1/brand/colors; Z0 red is the wordmark red the idents
# use (tools/z0-lib.sh). Radius 0 everywhere, mono type, bone on ink.
INK = (29, 26, 23)
INK_RAISED = (36, 31, 27)
INK_LINE = (92, 85, 76)
BONE = (246, 241, 231)
BONE_DIM = (234, 228, 214)
PINK = (240, 71, 125)
PINK_DEEP = (216, 17, 80)
MARIGOLD = (254, 154, 13)
MARIGOLD_DEEP = (161, 94, 1)
TEAL = (18, 183, 149)
TEAL_DEEP = (12, 122, 99)
Z0_RED = (224, 42, 27)

PALETTES = {
    "station": [INK, TEAL_DEEP, TEAL, BONE],
    "ember": [INK, PINK_DEEP, MARIGOLD, BONE],
    "signal": [INK, PINK_DEEP, PINK, BONE],
    "mono": [INK, INK_LINE, BONE],
    "cold": [INK, (34, 52, 78), TEAL, BONE],
    "heat": [INK, MARIGOLD_DEEP, MARIGOLD, BONE],
}

FONT_CANDIDATES = [
    "docs/tex/fonts/JetBrainsMono-Bold.ttf",
    "/mnt/main-data/channelz0/branding/fonts/NotoSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
]

# ── Copy ────────────────────────────────────────────────────────────────────
# The station voice: short, deadpan, a local channel for locals. Nothing that
# targets, threatens or sells anyone out. "a local channel, for locals" is the
# canonical line (station.env TAGLINE); the rest riff on it.
TAGLINES = [
    "a local channel, for locals",
    "one signal. always on.",
    "always on, somewhere in the Okanagan",
    "we are not the algorithm.",
    "nothing here was recommended to you.",
    "the schedule is the feature.",
    "public domain. private joy.",
    "these cartoons are older than your grandparents.",
    "you can't skip this. that's the point.",
    "no autoplay. no next episode. just next.",
    "we found this in the public domain and we liked it.",
    "one channel is enough.",
    "television, before it knew your name.",
    "broadcasting from a hillside in Kelowna.",
    "you are watching. thank you.",
    "the only ads are ours.",
    "sign-off is at midnight. sleep is a feature.",
    "parry. riposte. recycle. repeat.",
    "this bump was drawn by a formula.",
    "made of math. served by a very small computer.",
    "the weather desk is real. the desk is not.",
    "we lost the remote in 1962.",
    "if the picture rolls, that's the picture.",
    "channel zero. the one before the others.",
    "counting from zero, like a computer.",
    "the ground floor of television.",
    "still here. still on.",
    "thank you for not changing the channel.",
    "you could be doing anything. you chose this.",
    "there is no next button. there is midnight.",
    "programmed by hand. rendered by numbers.",
    "we don't know what you like. we have cartoons.",
    "everything here is free. the shirts are not.",
    "Kelowna's least-watched channel. proudly.",
    "local. linear. loud enough.",
    "somewhere, this is prime time.",
    "a transmission from Riposte Laboratories.",
    "no feed. no login. no idea who you are.",
    "every frame here was computed. some were worth it.",
    "the tower is a small computer. don't tell the tower.",
]


def lerp_ramp(v, palette):
    """Map values in 0..1 onto a palette ramp. v is any-shape float array;
    returns uint8 (..., 3)."""
    v = np.clip(v, 0.0, 1.0)
    n = len(palette)
    xs = np.linspace(0.0, 1.0, n)
    out = np.empty(v.shape + (3,), dtype=np.float32)
    pal = np.array(palette, dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(v, xs, pal[:, c])
    return out.astype(np.uint8)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def find_font(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("Z0_FONT")
    if env and os.path.isfile(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in FONT_CANDIDATES:
        for base in (os.path.join(here, ".."), "."):
            p = cand if cand.startswith("/") else os.path.join(base, cand)
            if os.path.isfile(p):
                return p
    return None


class Fonts:
    """One place that loads the mono face at the sizes the layouts use."""

    def __init__(self, path):
        self.path = path
        self._cache = {}

    def at(self, size):
        if size not in self._cache:
            if self.path:
                self._cache[size] = ImageFont.truetype(self.path, size)
            else:
                self._cache[size] = ImageFont.load_default()
        return self._cache[size]


# ══ Genres ══════════════════════════════════════════════════════════════════
# Each genre owns its own state and returns one uint8 (H, W, 3) frame per
# call. `t` is seconds into the ART portion (before the card), `u` is 0..1
# progress through it. Raster genres compute at half or quarter size and
# upscale; vector genres draw with PIL at 2x and downsample for anti-aliasing.


class Genre:
    NAME = "genre"
    FACT = ""                 # the one-line caption under the picture
    PALETTE = "station"
    FAMILIES = ("math", "glitch")   # where this genre may be used
    LIVE_CAPTION = False      # caption text depends on the frame

    def __init__(self, rng, art_secs, palette=None):
        self.rng = rng
        self.art_secs = art_secs
        self.n_frames = int(round(art_secs * FPS))
        self.pal = PALETTES[palette or self.PALETTE]

    def frame(self, i, t, u):
        raise NotImplementedError

    def caption(self, i, t, u):
        return self.FACT

    # helpers -------------------------------------------------------------
    def canvas2x(self):
        return Image.new("RGB", (W * SUPER, H * SUPER), INK)

    @staticmethod
    def down(img):
        return np.asarray(img.resize((W, H), Image.LANCZOS))

    @staticmethod
    def up(arr, factor, smooth=True):
        img = Image.fromarray(arr)
        method = Image.BILINEAR if smooth else Image.NEAREST
        return np.asarray(img.resize((W, H), method))

    def colour_at(self, v):
        """One RGB tuple from the ramp for a scalar in 0..1."""
        return tuple(int(c) for c in lerp_ramp(np.array([v]), self.pal)[0])


# ── L-systems (the clean family) ─────────────────────────────────────────────
LSYS_SPECIMENS = {
    # name: (axiom, rules, angle_deg, iterations, upright)
    "plant": ("X", {"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"}, 25.0, 5, True),
    "dragon": ("FX", {"X": "X+YF+", "Y": "-FX-Y"}, 90.0, 12, False),
    "hilbert": ("A", {"A": "-BF+AFA+FB-", "B": "+AF-BFB-FA+"}, 90.0, 6, False),
    "koch": ("F--F--F", {"F": "F+F--F+F"}, 60.0, 4, False),
    "sierpinski": ("A", {"A": "B-A-B", "B": "A+B+A"}, 60.0, 7, False),
    "gosper": ("A", {"A": "A-B--B+A++AA+B-", "B": "+A-BB--B-A++A+B"}, 60.0, 4, False),
    "levy": ("F", {"F": "+F--F+"}, 45.0, 12, False),
    "bush": ("F", {"F": "FF+[+F-F-F]-[-F+F+F]"}, 22.5, 4, True),
    "terdragon": ("F", {"F": "F+F-F"}, 120.0, 8, False),
    "peano": ("X", {"X": "XFYFX+F+YFXFY-F-XFYFX", "Y": "YFXFY-F-XFYFX+F+YFXFY"}, 90.0, 3, False),
}


def lsys_segments(axiom, rules, angle_deg, iters, upright):
    """Expand and walk the turtle. Returns (N, 4) float array of segments in
    an unnormalised plane, y up."""
    s = axiom
    for _ in range(iters):
        s = "".join(rules.get(ch, ch) for ch in s)
    ang = math.radians(90.0 if upright else 0.0)
    step = math.radians(angle_deg)
    x = y = 0.0
    stack = []
    segs = []
    for ch in s:
        if ch in "FAB":
            nx, ny = x + math.cos(ang), y + math.sin(ang)
            segs.append((x, y, nx, ny))
            x, y = nx, ny
        elif ch == "+":
            ang += step
        elif ch == "-":
            ang -= step
        elif ch == "[":
            stack.append((x, y, ang))
        elif ch == "]":
            x, y, ang = stack.pop()
    return np.array(segs, dtype=np.float64)


class LSystem(Genre):
    NAME = "lsys"
    FACT = "a plant, spelled out in five letters"
    PALETTE = "station"
    FAMILIES = ("lsys",)

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        name = rng.choice(list(LSYS_SPECIMENS))
        self.specimen = name
        axiom, rules, angle, iters, upright = LSYS_SPECIMENS[name]
        segs = lsys_segments(axiom, rules, angle, iters, upright)
        # Fit into 86% of the frame, preserving aspect.
        lo = np.minimum(segs[:, 0:2].min(0), segs[:, 2:4].min(0))
        hi = np.maximum(segs[:, 0:2].max(0), segs[:, 2:4].max(0))
        span = np.maximum(hi - lo, 1e-9)
        scale = min(W * SUPER * 0.86 / span[0], H * SUPER * 0.86 / span[1])
        off = (np.array([W * SUPER, H * SUPER]) - span * scale) / 2 - lo * scale
        pts = segs.reshape(-1, 2) * scale + off
        pts[:, 1] = H * SUPER - pts[:, 1]        # y down for PIL
        self.segs = pts.reshape(-1, 4)
        self.drawn = 0
        self.img = self.canvas2x()
        self.draw = ImageDraw.Draw(self.img)
        self.width = 3 if len(self.segs) < 3000 else 2
        facts = {
            "plant": "a plant, spelled out in five letters",
            "dragon": "the dragon curve. fold a strip of paper 12 times.",
            "hilbert": "Hilbert's curve. one line, every pixel.",
            "koch": "Koch's snowflake. finite area, infinite edge.",
            "sierpinski": "Sierpinski's arrowhead. a triangle of triangles.",
            "gosper": "the Gosper curve. a hexagon that fills itself.",
            "levy": "the Lévy C curve. 45 degrees, forever.",
            "bush": "a bush. four rewrite rules and a stack.",
            "terdragon": "the terdragon. three turns, 6561 steps.",
            "peano": "Peano's curve, 1890. the first space-filler.",
        }
        self.FACT = facts[name]

    def frame(self, i, t, u):
        target = int(ease_in_out(u / 0.92) * len(self.segs))
        n = len(self.segs)
        for k in range(self.drawn, min(target, n)):
            x0, y0, x1, y1 = self.segs[k]
            col = self.colour_at(0.35 + 0.65 * k / max(n - 1, 1))
            self.draw.line((x0, y0, x1, y1), fill=col, width=self.width)
        self.drawn = max(self.drawn, min(target, n))
        return self.down(self.img)


# ── Strange attractors ───────────────────────────────────────────────────────
CLIFFORD_SETS = [(-1.4, 1.6, 1.0, 0.7), (1.7, 1.7, 0.6, 1.2),
                 (-1.7, 1.3, -0.1, -1.2), (1.5, -1.8, 1.6, 0.9),
                 (-1.8, -2.0, -0.5, -0.9)]
DEJONG_SETS = [(1.4, -2.3, 2.4, -2.1), (-2.7, -0.09, -0.86, -2.2),
               (-0.827, -1.637, 1.659, -0.943), (2.01, -2.53, 1.61, -0.33)]


class Attractor(Genre):
    NAME = "attractor"
    FACT = "x' = sin(ay) + c·cos(ax). a million points, one rule."
    PALETTE = "ember"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.kind = rng.choice(["clifford", "dejong"])
        sets = CLIFFORD_SETS if self.kind == "clifford" else DEJONG_SETS
        self.p = np.array(sets[rng.integers(len(sets))], dtype=np.float64)
        self.drift = rng.normal(0, 0.08, 4)
        self.pts = rng.uniform(-1, 1, (24000, 2))
        self.hw, self.hh = W // 2, H // 2
        self.acc = np.zeros((self.hh, self.hw), dtype=np.float32)
        if self.kind == "dejong":
            self.FACT = "de Jong's attractor. chaos with a fixed address."

    def frame(self, i, t, u):
        a, b, c, d = self.p + self.drift * np.sin(2 * np.pi * t / 9.0)
        x, y = self.pts[:, 0], self.pts[:, 1]
        for _ in range(10):
            if self.kind == "clifford":
                x, y = np.sin(a * y) + c * np.cos(a * x), np.sin(b * x) + d * np.cos(b * y)
            else:
                x, y = np.sin(a * y) - np.cos(b * x), np.sin(c * x) - np.cos(d * y)
            px = ((x + 2.3) / 4.6 * self.hw).astype(np.int32)
            py = ((y + 2.3) / 4.6 * self.hh).astype(np.int32)
            ok = (px >= 0) & (px < self.hw) & (py >= 0) & (py < self.hh)
            np.add.at(self.acc, (py[ok], px[ok]), 1.0)
        self.pts[:, 0], self.pts[:, 1] = x, y
        self.acc *= 0.93
        v = np.log1p(self.acc)
        v = v / max(v.max(), 1e-6)
        return self.up(lerp_ramp(v ** 0.7, self.pal), 2)


# ── Reaction-diffusion ───────────────────────────────────────────────────────
GRAY_SCOTT = {
    "coral": (0.0545, 0.062), "mitosis": (0.0367, 0.0649),
    "holes": (0.039, 0.058),
}   # "spots" (0.035, 0.065) and "worms" (0.078, 0.061) die out at this grid size


class ReactionDiffusion(Genre):
    NAME = "rd"
    FACT = "two chemicals, one rule, every animal's coat."
    PALETTE = "cold"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.name = rng.choice(list(GRAY_SCOTT))
        self.f, self.k = GRAY_SCOTT[self.name]
        self.gw, self.gh = W // 4, H // 4
        self.A = np.ones((self.gh, self.gw), dtype=np.float32)
        self.B = np.zeros((self.gh, self.gw), dtype=np.float32)
        for _ in range(int(rng.integers(3, 8))):
            y, x = rng.integers(0, self.gh - 6), rng.integers(0, self.gw - 6)
            self.B[y:y + 6, x:x + 6] = 1.0
        self.B += rng.uniform(0, 0.02, self.B.shape).astype(np.float32)
        self.steps = 24
        for _ in range(300):
            self.step()
        self.FACT = f"Gray–Scott reaction-diffusion, the “{self.name}” regime."

    def lap(self, Z):
        return (0.2 * (np.roll(Z, 1, 0) + np.roll(Z, -1, 0) + np.roll(Z, 1, 1) + np.roll(Z, -1, 1))
                + 0.05 * (np.roll(np.roll(Z, 1, 0), 1, 1) + np.roll(np.roll(Z, 1, 0), -1, 1)
                          + np.roll(np.roll(Z, -1, 0), 1, 1) + np.roll(np.roll(Z, -1, 0), -1, 1))
                - Z)

    def step(self):
        A, B = self.A, self.B
        ABB = A * B * B
        # Clipped to the physical range: a seed square at B=1 overshoots to
        # ~1.9 on step one and, left alone, B² runs away to NaN within the
        # warm-up (seen with 5+ seed squares).
        self.A = np.clip(A + (1.0 * self.lap(A) - ABB + self.f * (1 - A)), 0, 1)
        self.B = np.clip(B + (0.5 * self.lap(B) + ABB - (self.k + self.f) * B), 0, 1)

    def frame(self, i, t, u):
        for _ in range(self.steps):
            self.step()
        v = np.clip(self.B * 2.2, 0, 1)
        return self.up(lerp_ramp(v, self.pal), 4)


# ── Chladni plate ────────────────────────────────────────────────────────────
class Chladni(Genre):
    NAME = "chladni"
    FACT = "sand on a vibrating plate. the lines are where it stays still."
    PALETTE = "mono"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        ys, xs = np.mgrid[0:H, 0:W]
        self.x = (xs / W * 2 - 1).astype(np.float32)
        self.y = (ys / H * 2 - 1).astype(np.float32) * (H / W)
        n_modes = int(art_secs / 2.5) + 2
        self.modes = [(int(rng.integers(1, 8)), int(rng.integers(1, 8))) for _ in range(n_modes)]
        self.grain = rng.uniform(0.85, 1.0, (H, W)).astype(np.float32)

    def frame(self, i, t, u):
        pos = u * (len(self.modes) - 1)
        k = min(int(pos), len(self.modes) - 2)
        s = smoothstep(0.15, 0.85, np.array([pos - k]))[0]
        (n0, m0), (n1, m1) = self.modes[k], self.modes[k + 1]
        n = n0 + (n1 - n0) * s
        m = m0 + (m1 - m0) * s
        pi = np.float32(math.pi)
        f = (np.cos(n * pi * self.x) * np.cos(m * pi * self.y)
             - np.cos(m * pi * self.x) * np.cos(n * pi * self.y))
        sand = np.exp(-(f / 0.07) ** 2) * self.grain
        v = 0.08 + 0.92 * sand
        return lerp_ramp(v, self.pal)


# ── Fourier epicycles ────────────────────────────────────────────────────────
def glyph_outline(text, font_path, size=420):
    """Ordered boundary of a glyph, as complex points. Outer contour only."""
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    img = Image.new("L", (size * 2, size * 2), 0)
    d = ImageDraw.Draw(img)
    d.text((size // 2, size // 4), text, font=font, fill=255)
    m = np.asarray(img) > 127
    inner = m & np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1)
    edge = m & ~inner
    ys, xs = np.nonzero(edge)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    # Nearest-neighbour walk from the leftmost point; stops at the first
    # contour, which for a simply connected glyph is the outer one.
    order = [int(np.argmin(pts[:, 0]))]
    used = np.zeros(len(pts), dtype=bool)
    used[order[0]] = True
    cur = pts[order[0]]
    for _ in range(len(pts) - 1):
        d2 = ((pts - cur) ** 2).sum(1)
        d2[used] = np.inf
        j = int(np.argmin(d2))
        if d2[j] > 25.0:          # jumped to another contour: stop
            break
        used[j] = True
        order.append(j)
        cur = pts[j]
    p = pts[order]
    return p[:, 0] + 1j * p[:, 1]


def parametric_outline(kind, rng, n=600):
    s = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if kind == "heart":
        x = 16 * np.sin(s) ** 3
        y = -(13 * np.cos(s) - 5 * np.cos(2 * s) - 2 * np.cos(3 * s) - np.cos(4 * s))
    elif kind == "star":
        k = int(rng.integers(5, 8))
        r = 1 + 0.45 * np.cos(k * s)
        x, y = r * np.cos(s), r * np.sin(s)
    elif kind == "lissajous":
        a, b = int(rng.integers(2, 5)), int(rng.integers(3, 6))
        x, y = np.sin(a * s + 0.5), np.sin(b * s)
    else:  # blob: a few random harmonics
        r = 1 + sum(rng.uniform(0.05, 0.25) * np.cos(h * s + rng.uniform(0, 6.3))
                    for h in range(2, 6))
        x, y = r * np.cos(s), r * np.sin(s)
    return x + 1j * y


class Epicycles(Genre):
    NAME = "epicycles"
    FACT = "any shape is a sum of circles."
    PALETTE = "signal"
    N_TERMS = 60

    def __init__(self, rng, art_secs, palette=None, font_path=None):
        super().__init__(rng, art_secs, palette)
        choice = rng.choice(["Z", "0", "heart", "star", "lissajous", "blob"])
        if choice in ("Z", "0") and font_path:
            z = glyph_outline(choice, font_path)
            self.FACT = f"the “{choice}” of Z0, as a sum of {self.N_TERMS} circles."
        else:
            if choice in ("Z", "0"):
                choice = "blob"
            z = parametric_outline(choice, rng)
        # Resample by arc length to N points, centre, scale to the frame.
        seg = np.abs(np.diff(np.append(z, z[0])))
        cum = np.concatenate([[0], np.cumsum(seg)])
        N = 720
        tt = np.linspace(0, cum[-1], N, endpoint=False)
        zz = np.append(z, z[0])
        z = np.interp(tt, cum, zz.real) + 1j * np.interp(tt, cum, zz.imag)
        z -= z.mean()
        span = max(np.abs(z.real).max(), np.abs(z.imag).max() * W / H)
        z *= (W * SUPER * 0.34) / span
        # DFT, keep the strongest terms.
        k = np.arange(N)
        coef = np.fft.fft(z) / N
        freqs = np.where(k <= N // 2, k, k - N)
        idx = np.argsort(-np.abs(coef))[: self.N_TERMS]
        self.c = coef[idx]
        self.f = freqs[idx]
        self.centre = np.array([W * SUPER / 2, H * SUPER / 2])
        self.trace = []
        self.loops = 1.15

    def frame(self, i, t, u):
        img = self.canvas2x()
        d = ImageDraw.Draw(img)
        phase = 2 * np.pi * u * self.loops
        terms = self.c * np.exp(1j * self.f * phase)
        pos = np.concatenate([[0j], np.cumsum(terms)])
        pts = np.stack([pos.real, pos.imag], 1) + self.centre
        # Circles and arms, faint.
        circle_col = self.colour_at(0.42)
        arm_col = self.colour_at(0.55)
        for k in range(len(terms)):
            r = abs(terms[k])
            if r < 1.5:
                continue
            cx, cy = pts[k]
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=circle_col, width=1)
        d.line([tuple(p) for p in pts], fill=arm_col, width=2)
        # The trace.
        self.trace.append(tuple(pts[-1]))
        if len(self.trace) > 1:
            d.line(self.trace, fill=self.colour_at(0.95), width=5)
        tip = pts[-1]
        d.ellipse((tip[0] - 6, tip[1] - 6, tip[0] + 6, tip[1] + 6), fill=BONE)
        return self.down(img)


# ── Flow field ───────────────────────────────────────────────────────────────
def smooth_noise(rng, cells_x, cells_y, slices):
    """Value noise as a stack of bicubic-upsampled random grids, one per time
    slice; the caller blends between slices."""
    out = []
    for _ in range(slices):
        coarse = Image.fromarray((rng.uniform(0, 255, (cells_y, cells_x))).astype(np.uint8))
        out.append(np.asarray(coarse.resize((W, H), Image.BICUBIC)).astype(np.float32) / 255.0)
    return out


class Flow(Genre):
    NAME = "flow"
    FACT = "particles following noise. nobody drew these lines."
    PALETTE = "station"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.slices = smooth_noise(rng, 7, 4, 5)
        n = 3500
        self.pos = rng.uniform(0, 1, (n, 2)) * np.array([W, H])
        self.hue = rng.uniform(0.3, 1.0, n)
        self.canvas = np.zeros((H, W, 3), dtype=np.float32)
        self.speed = 2.2
        self.turns = rng.uniform(2.0, 4.5)

    def frame(self, i, t, u):
        s = u * (len(self.slices) - 1)
        k = min(int(s), len(self.slices) - 2)
        a = s - k
        noise = self.slices[k] * (1 - a) + self.slices[k + 1] * a
        xi = np.clip(self.pos[:, 0].astype(np.int32), 0, W - 1)
        yi = np.clip(self.pos[:, 1].astype(np.int32), 0, H - 1)
        ang = noise[yi, xi] * 2 * np.pi * self.turns
        self.pos[:, 0] += np.cos(ang) * self.speed
        self.pos[:, 1] += np.sin(ang) * self.speed
        # Wrap, and respawn a few so the field never empties.
        self.pos[:, 0] %= W
        self.pos[:, 1] %= H
        respawn = self.rng.random(len(self.pos)) < 0.004
        self.pos[respawn] = self.rng.uniform(0, 1, (respawn.sum(), 2)) * np.array([W, H])
        self.canvas *= 0.965
        cols = lerp_ramp(self.hue, self.pal).astype(np.float32)
        xi = self.pos[:, 0].astype(np.int32)
        yi = self.pos[:, 1].astype(np.int32)
        self.canvas[yi, xi] = np.maximum(self.canvas[yi, xi], cols)
        return np.clip(self.canvas, 0, 255).astype(np.uint8)


# ── Harmonograph ─────────────────────────────────────────────────────────────
class Harmonograph(Genre):
    NAME = "harmonograph"
    FACT = "two pendulums and a pen. 1844."
    PALETTE = "ember"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        base = rng.integers(2, 5)
        self.fx = [base + rng.normal(0, 0.012), base * 1.5 + rng.normal(0, 0.012)]
        self.fy = [base + rng.normal(0, 0.012), base * 0.5 + 2 + rng.normal(0, 0.012)]
        self.ph = rng.uniform(0, 2 * np.pi, 4)
        self.damp = rng.uniform(0.008, 0.02, 4)
        self.total_t = 70.0
        self.img = self.canvas2x()
        self.draw = ImageDraw.Draw(self.img)
        self.last = None
        self.tt = 0.0
        self.dt = 0.02

    def point(self, s):
        A = W * SUPER * 0.21
        B = H * SUPER * 0.42
        x = (A * math.sin(self.fx[0] * s + self.ph[0]) * math.exp(-self.damp[0] * s)
             + A * math.sin(self.fx[1] * s + self.ph[1]) * math.exp(-self.damp[1] * s))
        y = (B * math.sin(self.fy[0] * s + self.ph[2]) * math.exp(-self.damp[2] * s)
             + B * math.sin(self.fy[1] * s + self.ph[3]) * math.exp(-self.damp[3] * s))
        return (W * SUPER / 2 + x, H * SUPER / 2 + y)

    def frame(self, i, t, u):
        target = ease_in_out(u / 0.95) * self.total_t
        while self.tt < target:
            p = self.point(self.tt)
            if self.last is not None:
                self.draw.line((self.last, p), fill=self.colour_at(0.3 + 0.7 * self.tt / self.total_t), width=2)
            self.last = p
            self.tt += self.dt
        return self.down(self.img)


# ── Elementary cellular automaton ───────────────────────────────────────────
class Automaton(Genre):
    NAME = "automaton"
    FACT = "rule 30. one line at a time."
    PALETTE = "mono"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.rule = int(rng.choice([30, 45, 73, 90, 105, 110, 150, 135, 149]))
        self.FACT = f"rule {self.rule}. one line at a time."
        self.px = 4
        self.cw, self.ch = W // self.px, H // self.px
        self.rows = np.zeros((self.ch, self.cw), dtype=np.uint8)
        row = np.zeros(self.cw, dtype=np.uint8)
        if rng.random() < 0.6:
            row[self.cw // 2] = 1
        else:
            row[:] = rng.random(self.cw) < 0.5
        self.row = row
        self.rows[-1] = row
        self.rows_per_frame = 2
        self.table = np.array([(self.rule >> k) & 1 for k in range(8)], dtype=np.uint8)

    def step(self):
        l = np.roll(self.row, 1)
        r = np.roll(self.row, -1)
        idx = (l << 2) | (self.row << 1) | r
        self.row = self.table[idx]

    def frame(self, i, t, u):
        for _ in range(self.rows_per_frame):
            self.step()
            self.rows = np.roll(self.rows, -1, 0)
            self.rows[-1] = self.row
        v = self.rows.astype(np.float32)
        age = np.linspace(0.55, 1.0, self.ch, dtype=np.float32)[:, None]
        img = lerp_ramp(v * age, self.pal)
        return self.up(img, self.px, smooth=False)


# ── Game of Life ─────────────────────────────────────────────────────────────
class Life(Genre):
    NAME = "life"
    FACT = "four rules. no player."
    PALETTE = "station"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.px = 8
        self.cw, self.ch = W // self.px, H // self.px
        self.g = np.zeros((self.ch, self.cw), dtype=np.uint8)
        y0, x0 = self.ch // 4, self.cw // 4
        self.g[y0:3 * y0, x0:3 * x0] = rng.random((2 * y0, 2 * x0)) < 0.38
        self.age = np.zeros_like(self.g, dtype=np.float32)
        self.glow = np.zeros_like(self.age)

    def frame(self, i, t, u):
        if i % 2 == 0:
            g = self.g
            n = sum(np.roll(np.roll(g, dy, 0), dx, 1)
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))
            born = (g == 0) & (n == 3)
            live = (g == 1) & ((n == 2) | (n == 3))
            self.g = (born | live).astype(np.uint8)
            self.age = np.where(self.g == 1, self.age + 1, 0)
        alive = self.g == 1
        self.glow *= 0.9
        self.glow[alive] = 1.0
        v = np.where(alive, 0.55 + 0.45 * np.exp(-self.age / 12.0), self.glow * 0.35)
        cell = lerp_ramp(v, self.pal)
        big = np.kron(cell, np.ones((self.px, self.px, 1), dtype=np.uint8))
        big[self.px - 1::self.px, :, :] = INK      # 1 px grid gap
        big[:, self.px - 1::self.px, :] = INK
        return big[:H, :W]


# ── Moiré ────────────────────────────────────────────────────────────────────
class Moire(Genre):
    NAME = "moire"
    FACT = "two patterns disagreeing."
    PALETTE = "mono"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        ys, xs = np.mgrid[0:H, 0:W]
        self.xs = xs.astype(np.float32)
        self.ys = ys.astype(np.float32)
        self.k = rng.uniform(0.35, 0.6)
        self.kind = rng.choice(["rings", "lines"])
        self.w = rng.uniform(0.3, 0.6, 4)
        if self.kind == "lines":
            self.FACT = "two gratings, a few degrees apart."

    def frame(self, i, t, u):
        if self.kind == "rings":
            c1 = (W / 2 + 90 * math.sin(self.w[0] * t), H / 2 + 60 * math.cos(self.w[1] * t))
            c2 = (W / 2 + 90 * math.cos(self.w[2] * t + 1), H / 2 - 60 * math.sin(self.w[3] * t))
            r1 = np.hypot(self.xs - c1[0], self.ys - c1[1])
            r2 = np.hypot(self.xs - c2[0], self.ys - c2[1])
            v = np.cos(self.k * r1) + np.cos(self.k * r2)
        else:
            a1 = 0.05 * t
            a2 = -0.03 * t + 0.08
            p1 = self.xs * math.cos(a1) + self.ys * math.sin(a1)
            p2 = self.xs * math.cos(a2) + self.ys * math.sin(a2)
            v = np.cos(self.k * p1) + np.cos(self.k * 1.02 * p2)
        v = smoothstep(-0.4, 0.4, v / 2)
        return lerp_ramp(v * 0.9, self.pal)


# ── Julia set ────────────────────────────────────────────────────────────────
class Julia(Genre):
    NAME = "julia"
    FACT = "z → z² + c. that's it. that's the whole picture."
    PALETTE = "cold"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.hw, self.hh = W // 2, H // 2
        ys, xs = np.mgrid[0:self.hh, 0:self.hw]
        self.z0 = ((xs / self.hw * 3.4 - 1.7) + 1j * (ys / self.hh * 1.9 - 0.95)).astype(np.complex64)
        self.theta = rng.uniform(0, 2 * np.pi)
        self.rate = rng.choice([-1, 1]) * rng.uniform(0.5, 0.9) / art_secs
        self.iters = 56
        self.r = 0.7885

    def frame(self, i, t, u):
        c = np.complex64(self.r * np.exp(1j * (self.theta + 2 * np.pi * self.rate * t)))
        z = self.z0.copy()
        n = np.zeros(z.shape, dtype=np.float32)
        alive = np.ones(z.shape, dtype=bool)
        for k in range(self.iters):
            z[alive] = z[alive] * z[alive] + c
            esc = alive & (np.abs(z) > 4.0)
            n[esc] = k + 1 - np.log2(np.maximum(np.log(np.abs(z[esc])), 1e-9))
            alive &= ~esc
        v = np.where(alive, 0.0, (n / self.iters) ** 0.6)
        v = np.where(alive, 0.0, 0.15 + 0.85 * (0.5 + 0.5 * np.sin(v * 9.0 + t * 0.6)))
        return self.up(lerp_ramp(v, self.pal), 2)


# ── Phyllotaxis ──────────────────────────────────────────────────────────────
class Phyllotaxis(Genre):
    NAME = "phyllotaxis"
    FACT = "137.5°. the angle sunflowers use."
    PALETTE = "heat"
    LIVE_CAPTION = True

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.golden = 137.50776
        self.drift = rng.choice([-1, 1]) * rng.uniform(0.25, 0.6)
        self.n_max = 2400
        self.dot = 4.5 * SUPER

    def angle(self, u):
        if u < 0.55:
            return self.golden
        return self.golden + self.drift * ease_in_out((u - 0.55) / 0.45)

    def caption(self, i, t, u):
        return f"{self.angle(u):.2f}°. the angle sunflowers use."

    def frame(self, i, t, u):
        img = self.canvas2x()
        d = ImageDraw.Draw(img)
        n = int(min(1.0, u / 0.6) * self.n_max)
        ang = math.radians(self.angle(u))
        c = (H * SUPER * 0.47) / math.sqrt(self.n_max)
        ks = np.arange(n)
        r = c * np.sqrt(ks)
        th = ks * ang
        xs = W * SUPER / 2 + r * np.cos(th)
        ys = H * SUPER / 2 + r * np.sin(th)
        cols = lerp_ramp(0.35 + 0.65 * (ks % 89) / 89.0, self.pal)
        rad = self.dot * (0.5 + 0.5 * np.sqrt(ks / max(n, 1)))
        for x, y, col, rr in zip(xs, ys, cols, rad):
            d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=tuple(int(v) for v in col))
        return self.down(img)


# ── Voronoi ──────────────────────────────────────────────────────────────────
class Voronoi(Genre):
    NAME = "voronoi"
    FACT = "every point, its nearest seed."
    PALETTE = "station"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.hw, self.hh = W // 2, H // 2
        n = 26
        self.centre = rng.uniform(0, 1, (n, 2)) * np.array([self.hw, self.hh])
        self.amp = rng.uniform(20, 70, (n, 2))
        self.w = rng.uniform(0.15, 0.5, (n, 2))
        self.ph = rng.uniform(0, 6.3, (n, 2))
        self.tint = rng.uniform(0.25, 0.8, n)
        ys, xs = np.mgrid[0:self.hh, 0:self.hw]
        self.xs = xs.astype(np.float32)
        self.ys = ys.astype(np.float32)

    def frame(self, i, t, u):
        p = self.centre + self.amp * np.sin(self.w * t + self.ph)
        d = np.stack([np.hypot(self.xs - px, self.ys - py) for px, py in p])
        idx = np.argsort(d, axis=0)[:2]
        d1 = np.take_along_axis(d, idx[:1], 0)[0]
        d2 = np.take_along_axis(d, idx[1:2], 0)[0]
        cell = self.tint[idx[0]]
        edge = smoothstep(0.0, 3.0, d2 - d1)
        v = cell * (0.35 + 0.65 * edge) * (1 - 0.35 * np.clip(d1 / 90.0, 0, 1))
        return self.up(lerp_ramp(v, self.pal), 2)


# ── Times tables on a circle ────────────────────────────────────────────────
class TimesTable(Genre):
    NAME = "timestable"
    FACT = "multiplication, mod 180, on a circle."
    PALETTE = "signal"
    LIVE_CAPTION = True

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.N = 180
        self.k0 = rng.uniform(1.5, 2.5)
        self.k1 = self.k0 + rng.uniform(5, 9)
        self.R = H * SUPER * 0.44

    def k_at(self, u):
        return self.k0 + (self.k1 - self.k0) * u

    def caption(self, i, t, u):
        return f"×{self.k_at(u):.2f}, mod {self.N}, on a circle."

    def frame(self, i, t, u):
        img = self.canvas2x()
        d = ImageDraw.Draw(img)
        k = self.k_at(u)
        cx, cy = W * SUPER / 2, H * SUPER / 2
        js = np.arange(self.N)
        a0 = 2 * np.pi * js / self.N
        a1 = 2 * np.pi * (k * js % self.N) / self.N
        d.ellipse((cx - self.R, cy - self.R, cx + self.R, cy + self.R), outline=INK_LINE, width=2)
        for j in range(self.N):
            col = self.colour_at(0.45 + 0.55 * j / self.N)
            d.line((cx + self.R * math.cos(a0[j]), cy + self.R * math.sin(a0[j]),
                    cx + self.R * math.cos(a1[j]), cy + self.R * math.sin(a1[j])), fill=col, width=1)
        return self.down(img)


# ── Double pendulum ──────────────────────────────────────────────────────────
class Pendulum(Genre):
    NAME = "pendulum"
    FACT = "same start, three outcomes."
    PALETTE = "ember"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        th1 = rng.uniform(1.8, 2.8)
        th2 = rng.uniform(1.5, 3.0)
        self.state = np.array([[th1, th2 + 1e-4 * k, 0.0, 0.0] for k in range(3)])
        self.cols = [PINK, TEAL, MARIGOLD]
        self.L = H * SUPER * 0.22
        self.trail = np.zeros((H * SUPER, W * SUPER, 3), dtype=np.float32)
        self.img = self.canvas2x()
        self.last = [None] * 3
        self.dt = 1.0 / 240

    def deriv(self, s):
        g = 9.81
        t1, t2, w1, w2 = s
        d = t1 - t2
        den = 3 - math.cos(2 * d)
        a1 = (-g * 3 * math.sin(t1) - g * math.sin(t1 - 2 * t2)
              - 2 * math.sin(d) * (w2 * w2 + w1 * w1 * math.cos(d))) / den
        a2 = (2 * math.sin(d) * (w1 * w1 * 2 + g * 2 * math.cos(t1) + w2 * w2 * math.cos(d))) / den
        return np.array([w1, w2, a1, a2])

    def rk4(self, s):
        h = self.dt
        k1 = self.deriv(s)
        k2 = self.deriv(s + h / 2 * k1)
        k3 = self.deriv(s + h / 2 * k2)
        k4 = self.deriv(s + h * k3)
        return s + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

    def frame(self, i, t, u):
        d = ImageDraw.Draw(self.img)
        # Fade the trail canvas toward ink.
        arr = np.asarray(self.img).astype(np.float32)
        arr = arr * 0.985 + np.array(INK, dtype=np.float32) * 0.015
        self.img = Image.fromarray(arr.astype(np.uint8))
        d = ImageDraw.Draw(self.img)
        cx, cy = W * SUPER / 2, H * SUPER * 0.42
        rods = []
        for k in range(3):
            for _ in range(8):
                self.state[k] = self.rk4(self.state[k])
            t1, t2 = self.state[k][0], self.state[k][1]
            x1, y1 = cx + self.L * math.sin(t1), cy + self.L * math.cos(t1)
            x2, y2 = x1 + self.L * math.sin(t2), y1 + self.L * math.cos(t2)
            if self.last[k] is not None:
                d.line((self.last[k], (x2, y2)), fill=self.cols[k], width=3)
            self.last[k] = (x2, y2)
            rods.append(((cx, cy), (x1, y1), (x2, y2)))
        out = self.img.copy()
        d2 = ImageDraw.Draw(out)
        for (p0, p1, p2), col in zip(rods, self.cols):
            d2.line((p0, p1, p2), fill=BONE_DIM, width=2)
            d2.ellipse((p2[0] - 6, p2[1] - 6, p2[0] + 6, p2[1] + 6), fill=col)
        d2.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=BONE)
        return self.down(out)


# ── Lorenz ───────────────────────────────────────────────────────────────────
class Lorenz(Genre):
    NAME = "lorenz"
    FACT = "weather, simplified to three numbers."
    PALETTE = "station"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.s = np.array([rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(15, 30)])
        self.dt = 0.008
        self.steps = 18
        self.pts = []
        self.max_pts = 2600
        self.spin = rng.uniform(0.15, 0.3) * rng.choice([-1, 1])
        self.tilt = rng.uniform(0.3, 0.9)

    def frame(self, i, t, u):
        sig, rho, beta = 10.0, 28.0, 8.0 / 3
        for _ in range(self.steps):
            x, y, z = self.s
            self.s = self.s + self.dt * np.array([sig * (y - x), x * (rho - z) - y, x * y - beta * z])
            self.pts.append(self.s.copy())
        self.pts = self.pts[-self.max_pts:]
        P = np.array(self.pts)
        a = self.spin * t
        xr = P[:, 0] * math.cos(a) - P[:, 1] * math.sin(a)
        yr = P[:, 0] * math.sin(a) + P[:, 1] * math.cos(a)
        zr = P[:, 2] - 25
        sx = W * SUPER / 2 + xr * (H * SUPER / 60)
        sy = H * SUPER / 2 - (zr * math.cos(self.tilt) + yr * math.sin(self.tilt)) * (H * SUPER / 60)
        img = self.canvas2x()
        d = ImageDraw.Draw(img)
        n = len(sx)
        step = 6
        for k in range(0, n - step, step):
            col = self.colour_at(0.25 + 0.75 * k / n)
            d.line([(sx[j], sy[j]) for j in range(k, k + step + 1)], fill=col, width=2)
        d.ellipse((sx[-1] - 5, sy[-1] - 5, sx[-1] + 5, sy[-1] + 5), fill=BONE)
        return self.down(img)


# ── Truchet tiles ────────────────────────────────────────────────────────────
class Truchet(Genre):
    NAME = "truchet"
    FACT = "one tile, two ways round."
    PALETTE = "mono"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.size = int(rng.choice([48, 60, 72]))
        self.nx, self.ny = W // self.size + 2, H // self.size + 2
        self.o = rng.integers(0, 2, (self.ny, self.nx))
        self.flip_prob = 0.9
        self.wave_dir = rng.uniform(0, 2 * np.pi)
        self.invert = rng.random() < 0.3
        self.line_col = [TEAL, BONE, MARIGOLD, PINK][int(rng.integers(4))] if not self.invert else INK
        self.bg = INK if not self.invert else BONE
        self.last_wave = -1
        self.wave_period = 2.2

    def frame(self, i, t, u):
        # A wave sweeps across; tiles flip when it passes.
        phase = (t / self.wave_period) % 1.0
        ys, xs = np.mgrid[0:self.ny, 0:self.nx]
        proj = (xs * math.cos(self.wave_dir) + ys * math.sin(self.wave_dir))
        proj = (proj - proj.min()) / (proj.max() - proj.min() + 1e-9)
        band = np.abs(proj - phase) < (1.0 / (FPS * self.wave_period))
        flips = band & (self.rng.random(band.shape) < self.flip_prob)
        self.o[flips] ^= 1
        img = Image.new("RGB", (W * SUPER, H * SUPER), self.bg)
        d = ImageDraw.Draw(img)
        s = self.size * SUPER
        wdt = max(4, s // 9)
        for gy in range(self.ny):
            for gx in range(self.nx):
                x0, y0 = gx * s - s // 2, gy * s - s // 2
                if self.o[gy, gx] == 0:
                    d.arc((x0 - s / 2, y0 - s / 2, x0 + s / 2, y0 + s / 2), 0, 90, fill=self.line_col, width=wdt)
                    d.arc((x0 + s / 2, y0 + s / 2, x0 + 3 * s / 2, y0 + 3 * s / 2), 180, 270, fill=self.line_col, width=wdt)
                else:
                    d.arc((x0 + s / 2, y0 - s / 2, x0 + 3 * s / 2, y0 + s / 2), 90, 180, fill=self.line_col, width=wdt)
                    d.arc((x0 - s / 2, y0 + s / 2, x0 + s / 2, y0 + 3 * s / 2), 270, 360, fill=self.line_col, width=wdt)
        return self.down(img)


# ── Ripple (2D wave equation) ────────────────────────────────────────────────
class Ripple(Genre):
    NAME = "ripple"
    FACT = "the wave equation, with drops."
    PALETTE = "cold"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.hw, self.hh = W // 2, H // 2
        self.u0 = np.zeros((self.hh, self.hw), dtype=np.float32)
        self.u1 = np.zeros_like(self.u0)
        self.c2 = 0.24
        self.damp = 0.9975
        ys, xs = np.mgrid[0:self.hh, 0:self.hw]
        self.xs, self.ys = xs, ys
        self.next_drop = 0.0

    def frame(self, i, t, u):
        if t >= self.next_drop and u < 0.85:
            cx, cy = self.rng.uniform(0.1, 0.9) * self.hw, self.rng.uniform(0.1, 0.9) * self.hh
            r2 = (self.xs - cx) ** 2 + (self.ys - cy) ** 2
            self.u1 += (self.rng.uniform(1.5, 3.5) * np.exp(-r2 / 12.0)).astype(np.float32)
            self.next_drop = t + self.rng.uniform(0.25, 1.1)
        for _ in range(3):
            lap = (np.roll(self.u1, 1, 0) + np.roll(self.u1, -1, 0)
                   + np.roll(self.u1, 1, 1) + np.roll(self.u1, -1, 1) - 4 * self.u1)
            u2 = (2 * self.u1 - self.u0 + self.c2 * lap) * self.damp
            self.u0, self.u1 = self.u1, u2
        gx = np.roll(self.u1, -1, 1) - self.u1
        gy = np.roll(self.u1, -1, 0) - self.u1
        v = 0.42 + 0.9 * (gx * 0.8 + gy * 0.6)
        return self.up(lerp_ramp(v, self.pal), 2)


# ── Spirograph ───────────────────────────────────────────────────────────────
class Spiro(Genre):
    NAME = "spiro"
    FACT = "a hypotrochoid. the toy was patented in 1965."
    PALETTE = "signal"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        pairs = [(5, 3), (7, 4), (8, 5), (9, 4), (11, 7), (13, 5), (7, 3)]
        self.R, self.r = pairs[rng.integers(len(pairs))]
        self.d = rng.uniform(0.4, 1.4) * self.r
        self.turns = self.r          # closes after r turns of the big circle
        self.img = self.canvas2x()
        self.draw = ImageDraw.Draw(self.img)
        self.tt = 0.0
        self.dt = 0.01
        self.total = 2 * math.pi * self.turns
        scale = H * SUPER * 0.45 / (self.R - self.r + self.d)
        self.scale = scale
        self.last = None

    def point(self, s):
        R, r, d = self.R, self.r, self.d
        x = (R - r) * math.cos(s) + d * math.cos((R - r) / r * s)
        y = (R - r) * math.sin(s) - d * math.sin((R - r) / r * s)
        return (W * SUPER / 2 + x * self.scale, H * SUPER / 2 + y * self.scale)

    def frame(self, i, t, u):
        target = ease_in_out(u / 0.95) * self.total
        while self.tt < target:
            p = self.point(self.tt)
            if self.last is not None:
                self.draw.line((self.last, p), fill=self.colour_at(0.35 + 0.65 * self.tt / self.total), width=3)
            self.last = p
            self.tt += self.dt
        return self.down(self.img)


# ── Ulam spiral ──────────────────────────────────────────────────────────────
def sieve(n):
    s = np.ones(n + 1, dtype=bool)
    s[:2] = False
    for k in range(2, int(n ** 0.5) + 1):
        if s[k]:
            s[k * k::k] = False
    return s


class Ulam(Genre):
    NAME = "ulam"
    FACT = "prime numbers on a spiral. nobody knows why the lines."
    PALETTE = "heat"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.px = 4
        self.cw, self.ch = W // self.px, H // self.px
        self.n_cells = self.cw * self.ch
        self.grid = np.zeros((self.ch, self.cw), dtype=np.float32)
        self.path = self.spiral_path()
        # The walk runs past the frame's corners, so sieve the whole path.
        self.primes = sieve(len(self.path) + 2)
        self.k = 0
        self.per_frame = max(1, int(self.n_cells / (self.n_frames * 0.9)))

    def spiral_path(self):
        # Walk out from the centre: R1 U1 L2 D2 R3 U3 ...
        cx, cy = self.cw // 2, self.ch // 2
        x, y = cx, cy
        out = [(x, y)]
        step = 1
        dirs = [(1, 0), (0, -1), (-1, 0), (0, 1)]
        di = 0
        while len(out) < self.n_cells * 2:
            for _ in range(2):
                dx, dy = dirs[di % 4]
                for _ in range(step):
                    x += dx
                    y += dy
                    out.append((x, y))
                di += 1
            step += 1
        return out

    def frame(self, i, t, u):
        end = min(self.k + self.per_frame, len(self.path))
        for n in range(self.k, end):
            x, y = self.path[n]
            if 0 <= x < self.cw and 0 <= y < self.ch:
                self.grid[y, x] = 1.0 if self.primes[n + 1] else 0.12
        self.k = end
        img = lerp_ramp(self.grid, self.pal)
        if self.k < len(self.path):
            x, y = self.path[min(self.k, len(self.path) - 1)]
            if 0 <= x < self.cw and 0 <= y < self.ch:
                img[y, x] = PINK
        return self.up(img, self.px, smooth=False)


# ── Hex grid ─────────────────────────────────────────────────────────────────
class HexGrid(Genre):
    NAME = "hexgrid"
    FACT = "cells in a hex. each one carries the next."
    PALETTE = "heat"

    def __init__(self, rng, art_secs, palette=None):
        super().__init__(rng, art_secs, palette)
        self.size = 26 * SUPER
        w = math.sqrt(3) * self.size
        self.cells = []
        cols = int(W * SUPER / w) + 2
        rows = int(H * SUPER / (1.5 * self.size)) + 2
        for r in range(rows):
            for c in range(cols):
                x = c * w + (w / 2 if r % 2 else 0)
                y = r * 1.5 * self.size
                self.cells.append((x, y))
        self.cells = np.array(self.cells)
        self.sources = []
        self.next_src = 0.0
        self.level = np.zeros(len(self.cells))

    def frame(self, i, t, u):
        if t >= self.next_src and u < 0.8:
            k = int(self.rng.integers(len(self.cells)))
            self.sources.append((t, self.cells[k]))
            self.next_src = t + self.rng.uniform(0.6, 1.6)
        self.level *= 0.94
        for t0, (sx, sy) in self.sources:
            age = t - t0
            d = np.hypot(self.cells[:, 0] - sx, self.cells[:, 1] - sy)
            ring = np.exp(-((d - age * 260 * SUPER / 2) / (30 * SUPER)) ** 2)
            self.level = np.maximum(self.level, ring * max(0.0, 1 - age / 4.0))
        img = self.canvas2x()
        d = ImageDraw.Draw(img)
        s = self.size * 0.92
        ang = [math.radians(60 * k + 30) for k in range(6)]
        for (x, y), lv in zip(self.cells, self.level):
            col = self.colour_at(0.12 + 0.88 * lv)
            poly = [(x + s * math.cos(a), y + s * math.sin(a)) for a in ang]
            d.polygon(poly, fill=col, outline=INK_RAISED)
        return self.down(img)


GENRES = {g.NAME: g for g in [
    LSystem, Attractor, ReactionDiffusion, Chladni, Epicycles, Flow, Harmonograph,
    Automaton, Life, Moire, Julia, Phyllotaxis, Voronoi, TimesTable, Pendulum,
    Lorenz, Truchet, Ripple, Spiro, Ulam, HexGrid,
]}
FAMILIES = ("math", "glitch", "lsys")


def genres_for(family):
    return [n for n, g in GENRES.items() if family in g.FAMILIES]


# ══ Treatments (the glitch family) ══════════════════════════════════════════
# Each treatment is stateful and takes the intensity envelope `e` in 0..1 for
# this frame. Bursty treatments get a bursty envelope; smearing ones get a
# slow swell. None of these change the picture's bounds, so the rails still
# own the gutters.


class Treatment:
    NAME = "treatment"
    BURSTY = True

    def __init__(self, rng):
        self.rng = rng

    def apply(self, frame, e, i, t):
        raise NotImplementedError


class PixelSort(Treatment):
    NAME = "pixelsort"

    def __init__(self, rng):
        super().__init__(rng)
        self.lo, self.hi = rng.uniform(0.15, 0.35), rng.uniform(0.6, 0.9)
        self.vertical = rng.random() < 0.3

    def apply(self, frame, e, i, t):
        if e < 0.05:
            return frame
        f = frame.transpose(1, 0, 2) if self.vertical else frame
        out = f.copy()
        lum = f.astype(np.float32).mean(2) / 255.0
        rows = np.arange(f.shape[0])
        band = int(f.shape[0] * e)
        y0 = int(self.rng.integers(0, max(1, f.shape[0] - band)))
        for y in rows[y0:y0 + band]:
            m = (lum[y] > self.lo) & (lum[y] < self.hi)
            if not m.any():
                continue
            edges = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
            starts, ends = np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]
            for s, en in zip(starts, ends):
                if en - s < 8:
                    continue
                order = np.argsort(lum[y, s:en])
                out[y, s:en] = f[y, s:en][order]
        return out.transpose(1, 0, 2) if self.vertical else out


class Feedback(Treatment):
    NAME = "feedback"
    BURSTY = False

    def __init__(self, rng):
        super().__init__(rng)
        self.prev = None
        self.zoom = rng.uniform(1.015, 1.045)
        self.rot = rng.uniform(-2.0, 2.0)

    def apply(self, frame, e, i, t):
        if self.prev is None:
            self.prev = frame.astype(np.float32)
            return frame
        img = Image.fromarray(self.prev.astype(np.uint8))
        img = img.rotate(self.rot, resample=Image.BILINEAR, center=(W / 2, H / 2))
        zw, zh = int(W * self.zoom), int(H * self.zoom)
        img = img.resize((zw, zh), Image.BILINEAR).crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
        fb = np.asarray(img).astype(np.float32)
        # A true blend, not a max: a max blooms a bright field to white in
        # two seconds. The 0.97 keeps the tunnel from ever saturating.
        mix = 0.45 + 0.4 * e
        out = frame.astype(np.float32) * (1 - mix) + fb * 0.97 * mix
        self.prev = out
        return np.clip(out, 0, 255).astype(np.uint8)


class SlitScan(Treatment):
    NAME = "slitscan"
    BURSTY = False
    DEPTH = 40

    def __init__(self, rng):
        super().__init__(rng)
        self.buf = []
        self.vertical = rng.random() < 0.5

    def apply(self, frame, e, i, t):
        self.buf.append(frame)
        self.buf = self.buf[-self.DEPTH:]
        n = len(self.buf)
        if n < 2:
            return frame
        stack = np.stack(self.buf)             # (n, H, W, 3)
        depth = int((n - 1) * e)
        if self.vertical:
            idx = (n - 1 - (np.arange(H) / H * depth)).astype(np.int32)
            return stack[idx[:, None], np.arange(H)[:, None], np.arange(W)[None, :]]
        idx = (n - 1 - (np.arange(W) / W * depth)).astype(np.int32)
        return stack[idx[None, :], np.arange(H)[:, None], np.arange(W)[None, :]]


class VHS(Treatment):
    NAME = "vhs"

    def __init__(self, rng):
        super().__init__(rng)
        self.band_y = rng.uniform(0.2, 0.8)

    def apply(self, frame, e, i, t):
        k = int(2 + 8 * e)
        out = frame.copy()
        out[..., 0] = np.roll(frame[..., 0], -k, axis=1)
        out[..., 2] = np.roll(frame[..., 2], k, axis=1)
        # Tracking band: a strip of rows sheared sideways.
        by = int(((self.band_y + 0.08 * t) % 1.0) * H)
        bh = int(12 + 40 * e)
        rows = np.arange(by, min(H, by + bh))
        for y in rows:
            out[y] = np.roll(out[y], int(30 * e * math.sin(y * 0.3 + t * 9)), axis=0)
        out[1::2] = (out[1::2].astype(np.float32) * (0.82 - 0.1 * e)).astype(np.uint8)
        noise = self.rng.normal(0, 6 + 24 * e, (H, W, 1)).astype(np.float32)
        return np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)


class Bleed(Treatment):
    """Datamosh look without a datamosh: macroblocks that stop refreshing and
    keep dragging their last motion vector."""
    NAME = "bleed"
    BS = 16

    def __init__(self, rng):
        super().__init__(rng)
        self.prev = None
        self.mv = None

    def apply(self, frame, e, i, t):
        bs = self.BS
        by, bx = H // bs, W // bs
        if self.prev is None or e < 0.03:
            self.prev = frame.copy()
            self.mv = self.rng.integers(-3, 4, (by, bx, 2))
            return frame
        # Motion vectors drift slowly so the smear has a direction.
        self.mv = np.clip(self.mv + self.rng.integers(-1, 2, self.mv.shape), -8, 8)
        stale = self.rng.random((by, bx)) < (0.55 + 0.4 * e)
        out = frame.copy()
        for gy in range(by):
            for gx in range(bx):
                if not stale[gy, gx]:
                    continue
                dy, dx = int(self.mv[gy, gx, 0]), int(self.mv[gy, gx, 1])
                y0, x0 = gy * bs, gx * bs
                sy0, sx0 = min(max(y0 + dy, 0), H - bs), min(max(x0 + dx, 0), W - bs)
                out[y0:y0 + bs, x0:x0 + bs] = self.prev[sy0:sy0 + bs, sx0:sx0 + bs]
        self.prev = out
        return out


class Bitcrush(Treatment):
    NAME = "bitcrush"
    BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0

    def apply(self, frame, e, i, t):
        p = int(2 + 6 * e)
        small = frame[::p, ::p].astype(np.float32)
        levels = max(2, int(8 - 6 * e))
        h, w = small.shape[:2]
        dither = np.tile(self.BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w, None]
        q = np.floor(small / 255.0 * (levels - 1) + dither) / (levels - 1) * 255.0
        big = np.kron(q.astype(np.uint8), np.ones((p, p, 1), dtype=np.uint8))
        return big[:H, :W]


class Wobble(Treatment):
    NAME = "wobble"

    def __init__(self, rng):
        super().__init__(rng)
        self.lam = rng.uniform(40, 120)
        self.w = rng.uniform(4, 9)

    def apply(self, frame, e, i, t):
        ys = np.arange(H)
        shift = (e * 28 * np.sin(2 * np.pi * ys / self.lam + self.w * t)).astype(np.int32)
        idx = (np.arange(W)[None, :] - shift[:, None]) % W
        out = np.take_along_axis(frame, idx[..., None].repeat(3, 2), axis=1)
        k = int(3 * e)
        if k:
            out[..., 0] = np.roll(out[..., 0], k, axis=1)
            out[..., 2] = np.roll(out[..., 2], -k, axis=1)
        return out


class Roll(Treatment):
    """The lost vertical hold."""
    NAME = "roll"

    def __init__(self, rng):
        super().__init__(rng)
        self.off = 0.0

    def apply(self, frame, e, i, t):
        self.off = (self.off + e * 22) % H
        if e < 0.05:
            self.off *= 0.85
        o = int(self.off)
        out = np.roll(frame, o, axis=0)
        bar = slice(max(0, o - 6), o + 2)
        out[bar] = (out[bar].astype(np.float32) * 0.25).astype(np.uint8)
        return out


TREATMENTS = {t.NAME: t for t in [PixelSort, Feedback, SlitScan, VHS, Bleed, Bitcrush, Wobble, Roll]}


def burst_envelope(rng, n_frames, bursty):
    """Per-frame intensity. Bursty: mostly a little, sometimes a lot, in
    bursts of 0.2–0.9 s. Smooth: a slow swell."""
    if not bursty:
        ph = rng.uniform(0, 6.3)
        return 0.35 + 0.35 * np.sin(np.linspace(0, 2.5 * np.pi, n_frames) + ph)
    env = np.full(n_frames, 0.08)
    i = int(rng.integers(5, 25))
    while i < n_frames:
        length = int(rng.uniform(0.2, 0.9) * FPS)
        peak = rng.uniform(0.45, 1.0)
        env[i:i + length] = np.maximum(env[i:i + length], peak)
        i += length + int(rng.uniform(0.5, 1.8) * FPS)
    # A touch of attack/decay so bursts do not click on and off.
    k = np.array([0.2, 0.6, 1.0, 0.6, 0.2])
    env = np.convolve(env, k / k.sum(), mode="same")
    return np.clip(env, 0, 1)


# ══ Text ═════════════════════════════════════════════════════════════════════

def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def blend(base, overlay, alpha):
    """Alpha-blend two RGB uint8 frames."""
    if alpha <= 0:
        return base
    if alpha >= 1:
        return overlay
    return (base.astype(np.float32) * (1 - alpha) + overlay.astype(np.float32) * alpha).astype(np.uint8)


def draw_caption(frame, text, fonts, alpha):
    """The genre fact: a small mono line, lower-left, on an ink underlay. Kept
    inside the 107 px gutters the rails own — never a full-width strip."""
    if alpha <= 0 or not text:
        return frame
    img = Image.fromarray(frame)
    d = ImageDraw.Draw(img)
    text = text.upper()
    size = 20
    font = fonts.at(size)
    tw = d.textlength(text, font=font)
    while tw > W - 2 * 128 and size > 14:
        size -= 1
        font = fonts.at(size)
        tw = d.textlength(text, font=font)
    x, y = 128, H - 62
    pad = 10
    d.rectangle((x - pad, y - pad + 2, x + tw + pad, y + 24 + pad - 2), fill=INK)
    d.rectangle((x - pad, y - pad + 2, x - pad + 4, y + 24 + pad - 2), fill=MARIGOLD)
    d.text((x + 2, y), text, font=font, fill=BONE)
    return blend(frame, np.asarray(img), alpha)


def draw_wordmark(d, fonts, x_right, y, size=26):
    """CHANNEL in bone, Z0 in the ident red, right-aligned at x_right."""
    f = fonts.at(size)
    w_ch = d.textlength("CHANNEL ", font=f)
    w_z0 = d.textlength("Z0", font=f)
    d.text((x_right - w_z0 - w_ch, y), "CHANNEL ", font=f, fill=BONE)
    d.text((x_right - w_z0, y), "Z0", font=f, fill=Z0_RED)


def card_frame(tagline, fonts, style, art=None, dim=0.55):
    """The tagline card. `card`: a hard cut to an ink field with the line
    centred (the Adult Swim grammar, in the station's own type). `band`: the
    art keeps running, dimmed, under a centred ink band."""
    if style == "band" and art is not None:
        base = (art.astype(np.float32) * dim).astype(np.uint8)
        img = Image.fromarray(base)
    else:
        img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    size = 40
    font = fonts.at(size)
    lines = wrap_text(d, tagline, font, W - 260)
    while len(lines) > 2 and size > 26:
        size -= 2
        font = fonts.at(size)
        lines = wrap_text(d, tagline, font, W - 260)
    lh = size + 12
    block_h = lh * len(lines)
    y0 = (H - block_h) // 2
    if style == "band":
        d.rectangle((0, y0 - 28, W, y0 + block_h + 20), fill=INK)
    # Two bone rules echo the ident's checker rule.
    d.rectangle((150, y0 - 44, W - 150, y0 - 41), fill=BONE)
    d.rectangle((150, y0 + block_h + 36, W - 150, y0 + block_h + 39), fill=BONE)
    for k, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y0 + k * lh), line, font=font, fill=BONE)
    draw_wordmark(d, fonts, W - 132, H - 58)
    small = fonts.at(16)
    d.text((132, H - 54), "CH 0 · A LOCAL CHANNEL, FOR LOCALS", font=small, fill=INK_LINE)
    return np.asarray(img)


# ══ Audio ════════════════════════════════════════════════════════════════════

def synth_audio(rng, secs, card_at, env=None, family="math"):
    """A quiet drone with a soft cut at the card. Glitch clips add noise
    bursts gated by the video envelope so the picture and the sound break
    together. Returns int16 stereo (n, 2)."""
    n = int(secs * AUDIO_RATE)
    t = np.arange(n) / AUDIO_RATE
    f0 = float(rng.choice([55.0, 65.41, 73.42, 82.41]))
    detune = 1.0 + rng.uniform(0.002, 0.005)
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * 0.18 * t + rng.uniform(0, 6))
    def drone(mult):
        return (np.sin(2 * np.pi * f0 * mult * t) * 0.55
                + np.sin(2 * np.pi * f0 * 2 * mult * t) * 0.25
                + np.sin(2 * np.pi * f0 * 3 * mult * t + 0.5) * 0.12) * trem
    left = drone(1.0)
    right = drone(detune)
    floor = rng.normal(0, 1, n).astype(np.float32)
    floor = np.convolve(floor, np.ones(24) / 24, mode="same") * 0.5
    left = left * 0.09 + floor * 0.01     # lands near -24 LUFS integrated
    right = right * 0.09 + floor * 0.01
    if family == "glitch" and env is not None:
        e = np.interp(t, np.arange(len(env)) / FPS, env)
        gate = np.clip((e - 0.3) / 0.7, 0, 1)
        burst = rng.normal(0, 1, n).astype(np.float32)
        hold = int(rng.integers(6, 40))
        burst = np.repeat(burst[::hold], hold)[:n]           # sample-and-hold crunch
        burst = np.round(burst * 3) / 3                        # bit reduction
        left += burst * gate * 0.14
        right += np.roll(burst, 250) * gate * 0.14
    # The cut: a click and a low thump, then the drone sits back 6 dB.
    k0 = int(card_at * AUDIO_RATE)
    if 0 < k0 < n:
        click = rng.normal(0, 1, 240) * np.linspace(1, 0, 240) * 0.25
        thump_t = np.arange(int(0.18 * AUDIO_RATE)) / AUDIO_RATE
        thump = np.sin(2 * np.pi * 70 * thump_t) * np.exp(-thump_t * 22) * 0.35
        left[k0:k0 + 240] += click
        right[k0:k0 + 240] += click
        left[k0:k0 + len(thump)] += thump
        right[k0:k0 + len(thump)] += thump
        left[k0:] *= 0.5
        right[k0:] *= 0.5
    fade_in = np.clip(t / 0.4, 0, 1)
    fade_out = np.clip((secs - t) / 0.35, 0, 1)
    left *= fade_in * fade_out
    right *= fade_in * fade_out
    out = np.stack([left, right], 1)
    out = np.clip(out, -0.9, 0.9)
    return (out * 32767).astype(np.int16)


def write_wav(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(AUDIO_RATE)
        w.writeframes(pcm.tobytes())


# ══ Encode ═══════════════════════════════════════════════════════════════════

def ffmpeg_cmd(out_path, wav_path):
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
        "-i", wav_path,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-maxrate", BITRATE_CAP, "-bufsize", "6000k",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "60",
        "-c:a", "aac", "-b:a", "96k", "-ar", str(AUDIO_RATE),
        "-shortest", "-movflags", "+faststart",
        out_path,
    ]


def nfo_xml(title, outline, tags):
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    tag_lines = "\n".join(f"  <tag>{esc(t)}</tag>" for t in tags)
    return (
        '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        "<movie>\n"
        f"  <title>{esc(title)}</title>\n"
        f"  <sorttitle>{esc(title)}</sorttitle>\n"
        "  <mpaa>Z0-STATION</mpaa>\n"
        f"  <outline>{esc(outline)}</outline>\n"
        f"  <plot>{esc(outline)}</plot>\n"
        "  <genre>Station</genre>\n"
        f"{tag_lines}\n"
        "</movie>\n"
    )


# ══ One clip ═════════════════════════════════════════════════════════════════

def make_genre(name, rng, art_secs, font_path=None, palette=None):
    cls = GENRES[name]
    if cls is Epicycles:
        return cls(rng, art_secs, palette, font_path=font_path)
    return cls(rng, art_secs, palette)


def render_clip(spec):
    """spec: dict(genre, family, seed, secs, out_dir, font, treatment?, tagline?)
    Renders one .mp4 + .nfo, returns a manifest row."""
    genre_name = spec["genre"]
    family = spec["family"]
    seed = int(spec["seed"])
    secs = float(spec["secs"])
    rng = np.random.default_rng(seed)
    fonts = Fonts(spec.get("font"))
    art_secs = secs - CARD_SECS
    n_total = int(round(secs * FPS))
    n_art = int(round(art_secs * FPS))

    genre = make_genre(genre_name, rng, art_secs, font_path=fonts.path)
    treatment = None
    env = None
    if family == "glitch":
        t_name = spec.get("treatment") or str(rng.choice(list(TREATMENTS)))
        treatment = TREATMENTS[t_name](rng)
        env = burst_envelope(rng, n_art, treatment.BURSTY)
    tagline = spec.get("tagline") or str(rng.choice(TAGLINES))
    style = spec.get("style") or ("card" if rng.random() < 0.6 else "band")

    clip_id = f"z0-bump-{family}-{genre_name}-{seed:05d}"
    out_dir = spec["out_dir"]
    os.makedirs(out_dir, exist_ok=True)
    mp4 = os.path.join(out_dir, clip_id + ".mp4")
    nfo = os.path.join(out_dir, clip_id + ".nfo")
    wav = os.path.join(out_dir, "." + clip_id + ".wav")

    write_wav(wav, synth_audio(rng, secs, art_secs, env, family))
    proc = subprocess.Popen(ffmpeg_cmd(mp4, wav), stdin=subprocess.PIPE)
    last_art = None
    try:
        for i in range(n_total):
            t = i / FPS
            if i < n_art:
                u = i / max(n_art - 1, 1)
                fr = np.ascontiguousarray(genre.frame(i, t, u))
                if treatment is not None:
                    fr = np.ascontiguousarray(treatment.apply(fr, float(env[i]), i, t))
                a = float(smoothstep(CAPTION_AT, CAPTION_AT + CAPTION_FADE, np.array([t]))[0])
                fr = draw_caption(fr, genre.caption(i, t, u), fonts, a)
                last_art = fr
            else:
                if style == "band":
                    u = 1.0
                    art = np.ascontiguousarray(genre.frame(i, t, u))
                    if treatment is not None:
                        art = np.ascontiguousarray(treatment.apply(art, float(env[-1]) * 0.3, i, t))
                    fr = card_frame(tagline, fonts, "band", art)
                else:
                    fr = card_frame(tagline, fonts, "card")
                remaining = secs - t
                if remaining < CARD_FADE:
                    fr = (fr.astype(np.float32) * (remaining / CARD_FADE)).astype(np.uint8)
            proc.stdin.write(np.ascontiguousarray(fr, dtype=np.uint8).tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()
        if os.path.exists(wav):
            os.remove(wav)
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}) for {clip_id}")

    fact = genre.caption(n_art - 1, art_secs, 1.0)
    tags = ["media", "bumps", "station-furniture", f"bump-{family}", genre_name]
    if treatment is not None:
        tags.append(f"treatment-{treatment.NAME}")
    outline = f"{tagline} — {fact}"
    with open(nfo, "w", encoding="utf-8") as fh:
        fh.write(nfo_xml(clip_id, outline, tags))
    with open(mp4, "rb") as fh:
        md5 = hashlib.md5(fh.read()).hexdigest()
    return {
        "id": clip_id, "genre": genre_name, "family": family, "seed": seed,
        "secs": secs, "treatment": treatment.NAME if treatment else None,
        "style": style, "tagline": tagline, "fact": fact, "md5": md5,
        "bytes": os.path.getsize(mp4),
    }


def _worker(spec):
    try:
        row = render_clip(spec)
        return ("ok", row)
    except Exception as exc:  # report, keep the batch going
        return ("err", {"id": f"{spec['genre']}-{spec['seed']}", "error": repr(exc)})


# ══ CLI ══════════════════════════════════════════════════════════════════════

def cmd_list(args):
    print("families:", ", ".join(FAMILIES))
    print("genres:")
    for n, g in GENRES.items():
        print(f"  {n:13s} {'/'.join(g.FAMILIES):11s} {g.FACT}")
    print("treatments:", ", ".join(TREATMENTS))
    print(f"taglines: {len(TAGLINES)}")
    for t in TAGLINES:
        print("  ", t)


def cmd_render(args):
    font = find_font(args.font)
    if font is None:
        print("warning: no mono font found; text will use PIL's bitmap default", file=sys.stderr)
    secs = min(max(args.secs, MIN_SECS), MAX_SECS)
    rng = np.random.default_rng(args.seed)
    families = FAMILIES if args.family == "all" else (args.family,)
    specs = []
    for k in range(args.count):
        family = families[k % len(families)]
        if args.genre:
            genre = args.genre
            if family not in GENRES[genre].FAMILIES:
                family = GENRES[genre].FAMILIES[0]
        else:
            genre = str(rng.choice(genres_for(family)))
        seed = int(args.seed * 1000 + k) if args.seed is not None else int(rng.integers(0, 99999))
        specs.append({
            "genre": genre, "family": family, "seed": seed, "secs": secs,
            "out_dir": os.path.join(args.out, family), "font": font,
            "treatment": args.treatment, "tagline": args.tagline, "style": args.style,
        })
    jobs = args.jobs or max(1, min(len(specs), os.cpu_count() or 1))
    manifest = os.path.join(args.out, "manifest.jsonl")
    os.makedirs(args.out, exist_ok=True)
    ok = err = 0
    with mp.Pool(jobs) as pool, open(manifest, "a", encoding="utf-8") as mf:
        for status, row in pool.imap_unordered(_worker, specs):
            if status == "ok":
                ok += 1
                mf.write(json.dumps(row) + "\n")
                mf.flush()
                kbps = row["bytes"] * 8 / row["secs"] / 1000
                print(f"ok   {row['id']}  {kbps:5.0f} kbps  {row['style']:4s}  “{row['tagline']}”")
            else:
                err += 1
                print(f"FAIL {row['id']}  {row['error']}", file=sys.stderr)
    print(f"{ok} rendered, {err} failed → {args.out}")
    return 1 if err else 0


def cmd_still(args):
    font = find_font(args.font)
    rng = np.random.default_rng(args.seed)
    art_secs = args.secs - CARD_SECS
    genre = make_genre(args.genre, rng, art_secs, font_path=font)
    treatment = None
    env = None
    n_art = int(art_secs * FPS)
    if args.treatment:
        treatment = TREATMENTS[args.treatment](rng)
        env = burst_envelope(rng, n_art, treatment.BURSTY)
    n = min(int(args.t * FPS), n_art - 1)
    fr = None
    for i in range(n + 1):
        t = i / FPS
        fr = genre.frame(i, t, i / max(n_art - 1, 1))
        if treatment is not None:
            fr = treatment.apply(np.ascontiguousarray(fr), float(env[i]), i, t)
    fr = draw_caption(np.ascontiguousarray(fr), genre.caption(n, n / FPS, n / n_art), Fonts(font), 1.0)
    Image.fromarray(fr).save(args.out)
    print(args.out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)

    r = sub.add_parser("render")
    r.add_argument("--out", required=True)
    r.add_argument("--family", choices=FAMILIES + ("all",), default="all")
    r.add_argument("--genre", choices=list(GENRES))
    r.add_argument("--treatment", choices=list(TREATMENTS))
    r.add_argument("--count", type=int, default=6)
    r.add_argument("--seed", type=int)
    r.add_argument("--secs", type=float, default=DEFAULT_SECS)
    r.add_argument("--jobs", type=int)
    r.add_argument("--font")
    r.add_argument("--tagline")
    r.add_argument("--style", choices=["card", "band"])
    r.set_defaults(fn=cmd_render)

    s = sub.add_parser("still")
    s.add_argument("--genre", required=True, choices=list(GENRES))
    s.add_argument("--treatment", choices=list(TREATMENTS))
    s.add_argument("--out", required=True)
    s.add_argument("--t", type=float, default=6.0)
    s.add_argument("--secs", type=float, default=DEFAULT_SECS)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--font")
    s.set_defaults(fn=cmd_still)

    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
