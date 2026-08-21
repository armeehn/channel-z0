#!/usr/bin/env python3
"""The GROUND ZERO opening soundtrack, synthesised as an SPC700.

The 8-bit pass was a 2A03: two pulses, a triangle with no volume control, and
one noise channel doing every drum.  A 16-bit console is a *sampler* — eight
voices, each playing a short waveform with its own ADSR envelope, stereo pan,
pitch modulation, and a hardware echo unit with feedback and a filter in the
loop.  That echo is most of why this era sounds the way it does, and it is the
single biggest audible difference between the two passes.

So: wavetables instead of duty cycles, envelopes instead of decay ramps, a
stereo bus, a detuned second voice on the leads for chorus, and a real delay
line at the end.

Pure Python and the stdlib `wave` module — numpy is broken in the container
this renders on.  Wavetable lookup is a table index and an add, which is
exactly what makes that affordable.

Usage:  gzaudio.py OUT.wav
"""
import math
import sys
import wave
from array import array

RATE = 48000
LENGTH = 60.0
N = int(RATE * LENGTH)

TBL = 1024
MASK = TBL - 1

L = array("d", bytes(8 * N))
R = array("d", bytes(8 * N))
ECHO_L = array("d", bytes(8 * N))     # the echo send bus
ECHO_R = array("d", bytes(8 * N))


# ── note table ────────────────────────────────────────────────────────────
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def hz(name):
    if name == "R":
        return 0.0
    i = 1
    semis = _STEP[name[0]]
    while i < len(name) and name[i] in "#b":
        semis += 1 if name[i] == "#" else -1
        i += 1
    return 440.0 * (2.0 ** ((semis - 9) / 12.0 + (int(name[i:]) - 4)))


# ── wavetables ────────────────────────────────────────────────────────────
def _harm(amps):
    t = [0.0] * TBL
    for k, a in enumerate(amps, start=1):
        if not a:
            continue
        for i in range(TBL):
            t[i] += a * math.sin(2 * math.pi * k * i / TBL)
    peak = max(abs(v) for v in t) or 1.0
    return array("d", [v / peak for v in t])


WAVES = {
    # A slap bass: strong second and third, dead by the fifth.
    "bass":   _harm([1.0, 0.62, 0.40, 0.34, 0.20, 0.14, 0.09]),
    # The lead: bright enough to cut over drums without being a buzzsaw.
    "lead":   _harm([1.0, 0.70, 0.45, 0.30, 0.22, 0.15, 0.10, 0.07]),
    # Brass for the fanfare — even and odd, with bite.
    "brass":  _harm([1.0, 0.82, 0.62, 0.50, 0.40, 0.30, 0.22, 0.16, 0.12, 0.08]),
    # Strings: many low-amplitude partials, soft attack, used as a bed.
    "string": _harm([1.0, 0.50, 0.33, 0.25, 0.20, 0.16, 0.14, 0.12, 0.10, 0.08]),
    # A bell for the sting and the crawl arpeggio: sparse, odd-weighted.
    "bell":   _harm([1.0, 0.0, 0.55, 0.0, 0.32, 0.10, 0.0, 0.16]),
}


# ── the voice ─────────────────────────────────────────────────────────────
def voice(t, dur, note, wave_name="lead", vol=0.16, pan=0.0,
          atk=0.006, dec=0.10, sus=0.70, rel=0.14,
          vib=0.0, vibf=6.2, vibd=0.25, slide=0.0, echo=0.0, detune=0.0):
    """One sampler voice: table, ADSR, pan, vibrato, portamento, echo send.

    Modulation is recomputed every 64 samples rather than every sample.  At
    6 Hz vibrato that is inaudible and it is the difference between this
    rendering in seconds and rendering in minutes.
    """
    f0 = hz(note)
    if f0 <= 0:
        return
    if detune:
        voice(t, dur, note, wave_name, vol * 0.5, pan + 0.18, atk, dec, sus,
              rel, vib, vibf, vibd, slide, echo, 0.0)
        vol *= 0.62
        f0 *= 2.0 ** (detune / 1200.0)

    tbl = WAVES[wave_name]
    i0 = int(t * RATE)
    n = int((dur + rel) * RATE)
    if i0 + n > N:
        n = N - i0
    if n <= 0:
        return

    na = max(1, int(atk * RATE))
    nd = max(1, int(dec * RATE))
    nr = max(1, int(rel * RATE))
    nsus_end = max(na + nd, n - nr)

    # Equal-power pan.  The first version was `min(1, 1 +/- pan) ** 0.5`,
    # which clamps to 1.0 on the near side and so could never move a voice
    # more than about 2 dB — the whole mix measured 0.04 wide, i.e. mono.
    _a = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    gl = vol * math.cos(_a) * 1.414
    gr = vol * math.sin(_a) * 1.414
    phase = 0.0
    inc = f0 * TBL / RATE
    blk = 64
    i = 0
    while i < n:
        # per-block modulation
        tt = i / RATE
        f = f0 * (2.0 ** ((slide * (i / n)) / 12.0))
        if vib and tt > vibd:
            f *= 2.0 ** (vib * math.sin((tt - vibd) * 2 * math.pi * vibf) / 12.0)
        inc = f * TBL / RATE
        end = min(n, i + blk)
        for j in range(i, end):
            if j < na:
                e = j / na
            elif j < na + nd:
                e = 1.0 - (1.0 - sus) * (j - na) / nd
            elif j < nsus_end:
                e = sus
            else:
                e = sus * max(0.0, 1.0 - (j - nsus_end) / nr)
            v = tbl[int(phase) & MASK] * e
            phase += inc
            k = i0 + j
            L[k] += v * gl
            R[k] += v * gr
            if echo:
                ECHO_L[k] += v * gl * echo
                ECHO_R[k] += v * gr * echo
        i = end


# ── the kit ───────────────────────────────────────────────────────────────
_NOISE = None


def _noise_tbl():
    global _NOISE
    if _NOISE is None:
        reg = 0x7FFF
        out = array("d", bytes(8 * 65536))
        for i in range(65536):
            bit = (reg ^ (reg >> 1)) & 1
            reg = (reg >> 1) | (bit << 14)
            out[i] = 1.0 if (reg & 1) else -1.0
        _NOISE = out
    return _NOISE


def _burst(t, dur, vol, curve, pan=0.0, step=1, echo=0.0, off=0):
    nz = _noise_tbl()
    i0 = int(t * RATE)
    n = min(int(dur * RATE), N - i0)
    _a = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    gl = vol * math.cos(_a) * 1.414
    gr = vol * math.sin(_a) * 1.414
    for i in range(n):
        e = (1.0 - i / n) ** curve
        v = nz[(off + i * step) & 0xFFFF] * e
        L[i0 + i] += v * gl
        R[i0 + i] += v * gr
        if echo:
            ECHO_L[i0 + i] += v * gl * echo
            ECHO_R[i0 + i] += v * gr * echo


def _sweep(t, dur, f_from, f_to, vol, curve=2.5, wave_name="bass"):
    tbl = WAVES[wave_name]
    i0 = int(t * RATE)
    n = min(int(dur * RATE), N - i0)
    phase = 0.0
    for i in range(n):
        k = i / n
        f = f_from * (f_to / f_from) ** k
        phase += f * TBL / RATE
        v = tbl[int(phase) & MASK] * (1.0 - k) ** curve * vol
        L[i0 + i] += v
        R[i0 + i] += v


def kick(t, vol=0.42):
    _sweep(t, 0.13, 128.0, 44.0, vol)
    _burst(t, 0.012, vol * 0.35, 1.0, step=7)


def snare(t, vol=0.26):
    _burst(t, 0.13, vol, 2.2, step=3, echo=0.35, off=7919)
    _sweep(t, 0.07, 240.0, 170.0, vol * 0.45, curve=2.0)


def hat(t, vol=0.075, open_=False):
    _burst(t, 0.09 if open_ else 0.028, vol, 3.0, step=11, pan=0.38, off=104729)


def crash(t, vol=0.30):
    _burst(t, 1.6, vol, 1.5, step=5, echo=0.5, off=32749)


def stab(t, vol=0.30, note="D4"):
    """The orchestra hit.  Nothing says 16-bit faster."""
    for i, nm in enumerate((note, "A4", "F5", "D5")):
        voice(t, 0.28, nm, "brass", vol * (0.9 ** i), pan=(-0.45 + 0.30 * i),
              atk=0.002, dec=0.09, sus=0.30, rel=0.20, echo=0.30)
    _burst(t, 0.16, vol * 0.5, 2.0, step=2, echo=0.3, off=15485)


# ── the score ─────────────────────────────────────────────────────────────
# Upbeat, in the Mega Man register: 168 BPM, A minor, eighth-note bass under a
# hook that keeps climbing, and a Picardy third at the very end — the last
# chord is A MAJOR, because the story resolves with somebody arriving to help.
# The 8-bit pass was a D-minor dirge at 150 and it made the whole thing feel
# like a warning.
BPM = 168.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
SIX = BEAT / 4

CHORDS = {
    "Am": ["A3", "C4", "E4", "A4"], "F": ["F3", "A3", "C4", "F4"],
    "C": ["C4", "E4", "G4", "C5"], "G": ["G3", "B3", "D4", "G4"],
    "Dm": ["D3", "F3", "A3", "D4"], "E": ["E3", "G#3", "B3", "E4"],
    "A": ["A3", "C#4", "E4", "A4"],
}
ROOTS = {"Am": "A2", "F": "F2", "C": "C3", "G": "G2", "Dm": "D3", "E": "E2",
         "A": "A2"}
PADS = {"Am": ["A4", "C5", "E5"], "F": ["F4", "A4", "C5"],
        "C": ["G4", "C5", "E5"], "G": ["G4", "B4", "D5"],
        "Dm": ["D4", "F4", "A4"], "E": ["E4", "G#4", "B4"],
        "A": ["A4", "C#5", "E5"]}

LOOP = ["Am", "F", "C", "G"]


def arp(t, bars, chord, vol=0.05, step=None, wave_name="bell", echo=0.4):
    step = step or SIX
    seq = CHORDS[chord]
    for i in range(int(round(bars * BAR / step))):
        voice(t + i * step, step * 0.9, seq[i % len(seq)], wave_name, vol,
              pan=-0.55 + 0.30 * (i % 4), atk=0.002, dec=0.08, sus=0.22,
              rel=0.09, echo=echo)


def pad(t, dur, chord, vol=0.045):
    for i, nm in enumerate(PADS[chord]):
        voice(t, dur, nm, "string", vol, pan=(-0.62, 0.0, 0.62)[i],
              atk=0.30, dec=0.4, sus=0.85, rel=0.5, detune=7.0)


def line(t, notes, vol=0.15, wave_name="lead", pan=0.0, sus=0.75, echo=0.25,
         vib=0.0, detune=0.0, atk=0.006, rel=0.10):
    for name, sixteenths in notes:
        d = sixteenths * SIX
        if name != "R":
            voice(t, d * 0.94, name, wave_name, vol, pan, atk=atk, dec=0.08,
                  sus=sus, rel=rel, vib=vib, echo=echo, detune=detune)
        t += d
    return t


def bassline(t, bars, chord, vol=0.185, eighths=True):
    """Driving eighths with an octave lift on the fourth beat.  This is the
    engine of the whole cue."""
    r = ROOTS[chord]
    up = r[:-1] + str(int(r[-1]) + 1)
    n = int(bars * 8) if eighths else int(bars * 16)
    step = BEAT / 2 if eighths else BEAT / 4
    for j in range(n):
        nm = up if (j % 8) in (6, 7) else r
        voice(t + j * step, step * 0.80, nm, "bass", vol,
              atk=0.002, dec=0.06, sus=0.40, rel=0.05)


def drums(t, beats, fill_at=None, double=False):
    for b in range(beats):
        tb = t + b * BEAT
        if b % 4 in (0, 2):
            kick(tb)
        if b % 4 == 2:
            kick(tb + BEAT * 0.75, 0.30)
        if b % 4 in (1, 3):
            snare(tb)
        hat(tb)
        hat(tb + BEAT / 2, 0.055, open_=(b % 8 == 7))
        if double:
            hat(tb + BEAT / 4, 0.04)
            hat(tb + BEAT * 0.75, 0.04)
        if fill_at is not None and b == fill_at:
            for i in range(4):
                snare(tb + i * BEAT / 4, 0.16 + i * 0.02)


# The hook.  Four bars, and it climbs every bar until the last one lets go.
HOOK = [("A5", 2), ("B5", 2), ("C6", 4), ("B5", 2), ("A5", 2), ("G5", 4),
        ("A5", 2), ("C6", 2), ("F6", 4), ("E6", 2), ("D6", 2), ("C6", 4),
        ("E6", 2), ("D6", 2), ("C6", 4), ("B5", 2), ("C6", 2), ("D6", 4),
        ("B5", 4), ("D6", 4), ("G5", 8)]
HOOK_LOW = [("C5", 2), ("D5", 2), ("E5", 4), ("D5", 2), ("C5", 2), ("B4", 4),
            ("C5", 2), ("E5", 2), ("A5", 4), ("G5", 2), ("F5", 2), ("E5", 4),
            ("G5", 2), ("F5", 2), ("E5", 4), ("D5", 2), ("E5", 2), ("F5", 4),
            ("D5", 4), ("G5", 4), ("B4", 8)]


def build():
    # ── 0.00 – 4.50  publisher sting ──────────────────────────────────────
    for i in range(25):
        _burst((6 + 1.05 * i) / 30.0, 0.010, 0.05, 3.0, step=13, off=i * 733)

    t = 44 / 30.0
    for i, nm in enumerate(("A4", "C5", "E5", "A5")):
        voice(t + i * 0.070, 0.16, nm, "bell", 0.17, pan=-0.6 + 0.40 * i,
              atk=0.002, dec=0.10, sus=0.35, rel=0.22, echo=0.55)
    t += 0.29
    stab(t, 0.26, "C3")
    for nm, v, pn in (("C4", 0.13, -0.3), ("E4", 0.10, 0.0), ("G4", 0.09, 0.3)):
        voice(t, 1.5, nm, "brass", v, pn, atk=0.008, dec=0.35, sus=0.42,
              rel=0.55, vib=0.10, echo=0.45, detune=6.0)
    voice(t, 1.7, "A2", "bass", 0.20, atk=0.003, dec=0.30, sus=0.55, rel=0.5)
    pad(t, 1.9, "Am", 0.05)

    # ── 4.50 – 18.50  the prologue bed ────────────────────────────────────
    # Bouncy rather than solemn: a sixteenth arpeggio from the first bar, and
    # hats from the fifth, so the crawl already has a pulse under it.
    t0 = 4.5
    bars = 9.8
    t = t0
    i = 0
    while t < t0 + bars * BAR:
        chord = LOOP[i % 4]
        pad(t, BAR * 0.96, chord, 0.040)
        arp(t, 1, chord, vol=0.044)
        for j in range(4):
            voice(t + j * BEAT, BEAT * 0.7, ROOTS[chord], "bass", 0.15,
                  atk=0.004, dec=0.12, sus=0.5, rel=0.08)
        t += BAR
        i += 1
    for b in range(int(5 * BAR / BEAT), int(bars * BAR / BEAT)):
        hat(t0 + b * BEAT, 0.045)
        if b % 4 == 2:
            snare(t0 + b * BEAT, 0.10)

    # the hook, previewed quietly on the bell while the crawl is still running
    line(t0 + 5 * BAR, HOOK, vol=0.070, wave_name="bell", pan=-0.15, sus=0.45,
         echo=0.45)
    # a lift into the launch
    line(t0 + 9 * BAR, [("A4", 2), ("B4", 2), ("C5", 2), ("D5", 2),
                        ("E5", 2), ("F5", 2), ("G5", 2), ("G#5", 2)],
         vol=0.10, wave_name="brass", sus=0.6, echo=0.3)

    # ── 18.50 – 25.50  deep space ─────────────────────────────────────────
    t0 = 18.5
    crash(t0, 0.20)
    drums(t0, int(7.0 / BEAT))
    t = t0
    i = 0
    while t < t0 + 7.0:
        chord = LOOP[i % 4]
        bassline(t, 1, chord)
        pad(t, BAR * 0.95, chord, 0.036)
        t += BAR
        i += 1
    line(t0, HOOK, vol=0.135, wave_name="lead", pan=-0.1, sus=0.66, echo=0.28,
         vib=0.05, detune=8.0)
    line(t0 + 2 * SIX, HOOK_LOW, vol=0.055, wave_name="bell", pan=0.42,
         sus=0.45, echo=0.4)

    # ── 25.50 – 31.50  the wormhole ───────────────────────────────────────
    # Double time, and the bass goes to sixteenths.  Everything climbs.
    t0 = 25.5
    drums(t0, int(6.0 / BEAT), double=True)
    t = t0
    i = 0
    while t < t0 + 6.0:
        chord = ("Am", "F", "G", "Am", "F", "E")[i % 6]
        bassline(t, 1, chord, vol=0.17, eighths=False)
        pad(t, BAR * 0.95, chord, 0.040)
        t += BAR
        i += 1
    steps = ["A4", "B4", "C5", "E5", "A5", "B5", "C6", "E6",
             "A5", "C6", "E6", "A6", "G5", "B5", "D6", "G6"]
    for i, nm in enumerate(steps):
        voice(t0 + i * (6.0 / len(steps)), 6.0 / len(steps) * 0.9, nm, "brass",
              0.085 + i * 0.0035, pan=-0.7 + 1.4 * i / (len(steps) - 1),
              atk=0.004, dec=0.06, sus=0.65, rel=0.06, echo=0.35)
    rt, gapn = t0 + 3.6, 0.18
    while rt < t0 + 5.9:
        snare(rt, 0.12 + (rt - t0 - 3.6) * 0.03)
        rt += gapn
        gapn = max(0.05, gapn * 0.85)

    # ── 31.50 – 39.50  the landing ────────────────────────────────────────
    # The hook, full, and the biggest statement in the cue.
    t0 = 31.5
    crash(t0, 0.30)
    stab(t0, 0.30, "A3")
    drums(t0, int(8.0 / BEAT), fill_at=int(8.0 / BEAT) - 2)
    t = t0
    i = 0
    while t < t0 + 8.0:
        chord = LOOP[i % 4]
        bassline(t, 1, chord, vol=0.20)
        pad(t, BAR * 0.95, chord, 0.045)
        t += BAR
        i += 1
    line(t0, HOOK, vol=0.150, wave_name="brass", pan=-0.12, sus=0.70,
         echo=0.30, detune=9.0)
    line(t0 + 4 * BAR, HOOK, vol=0.140, wave_name="lead", pan=0.12, sus=0.68,
         echo=0.30, vib=0.06, detune=8.0)
    line(t0 + 4 * BAR + 2 * SIX, HOOK_LOW, vol=0.060, wave_name="bell",
         pan=-0.45, sus=0.45, echo=0.4)

    # ── 39.50 – 43.50  her face ───────────────────────────────────────────
    # Everything stops except a pad and a bell.  It is the only quiet bar in
    # the cue and it is where the sequence stops being about a spaceship.
    t0 = 39.5
    for i, chord in enumerate(("F", "C", "G", "Am")):
        pad(t0 + i * BAR * 0.7, BAR * 0.72, chord, 0.055)
        voice(t0 + i * BAR * 0.7, BAR * 0.66, ROOTS[chord], "bass", 0.13,
              atk=0.02, dec=0.3, sus=0.6, rel=0.3)
    line(t0 + 0.10, [("E5", 4), ("F5", 4), ("G5", 8),
                     ("E5", 4), ("D5", 4), ("C5", 8),
                     ("D5", 4), ("E5", 4), ("A5", 8)],
         vol=0.095, wave_name="bell", pan=0.0, sus=0.5, echo=0.5, vib=0.04,
         atk=0.02)

    # ── 43.50 – 48.50  the name card ──────────────────────────────────────
    t0 = 43.5
    stab(t0, 0.28, "A3")
    drums(t0, int(5.0 / BEAT))
    t = t0
    i = 0
    while t < t0 + 5.0:
        chord = ("Am", "G", "F", "G")[i % 4]
        bassline(t, 1, chord, vol=0.19)
        pad(t, BAR * 0.95, chord, 0.042)
        t += BAR
        i += 1
    line(t0, [("A5", 4), ("C6", 4), ("B5", 4), ("G5", 4),
              ("A5", 4), ("B5", 4), ("C6", 8),
              ("D6", 4), ("C6", 4), ("B5", 4), ("A5", 4)],
         vol=0.140, wave_name="lead", pan=-0.1, sus=0.68, echo=0.30,
         detune=8.0)

    # ── 48.50 – 55.50  the logo ───────────────────────────────────────────
    t0 = 48.5
    crash(t0, 0.30)
    kick(t0, 0.46)
    stab(t0, 0.32, "A3")
    for off, chord in ((0.0, "Am"), (0.72, "F"), (1.44, "G"), (2.16, "Am")):
        tb = t0 + off
        kick(tb)
        snare(tb + BEAT)
        voice(tb, 0.70, ROOTS[chord], "bass", 0.20, atk=0.003, dec=0.15,
              sus=0.55, rel=0.15)
        pad(tb, 0.75, chord, 0.05)

    line(t0 + 0.08, [("A5", 2), ("R", 2), ("A5", 2), ("R", 2),
                     ("C6", 4), ("E6", 4),
                     ("F6", 8), ("E6", 8),
                     ("D6", 4), ("E6", 4), ("F6", 4), ("G6", 4)],
         vol=0.145, wave_name="brass", pan=-0.12, sus=0.72, echo=0.32,
         detune=9.0)
    line(t0 + 0.08, [("C5", 2), ("R", 2), ("C5", 2), ("R", 2),
                     ("E5", 4), ("A5", 4),
                     ("A5", 8), ("C6", 8),
                     ("B5", 4), ("C6", 4), ("D6", 4), ("E6", 4)],
         vol=0.062, wave_name="lead", pan=0.38, sus=0.7, echo=0.3)

    hold = t0 + 3 * 0.72 + 0.72
    for nm, v, pn in (("A6", 0.125, -0.15), ("E6", 0.085, 0.15),
                      ("C6", 0.070, 0.35)):
        voice(hold, 3.4, nm, "brass", v, pn, atk=0.015, dec=0.8, sus=0.55,
              rel=1.0, vib=0.14, vibd=0.4, echo=0.35, detune=8.0)
    voice(hold, 3.6, "A2", "bass", 0.20, atk=0.008, dec=0.7, sus=0.6, rel=0.9)
    pad(hold, 3.6, "Am", 0.055)
    crash(hold, 0.24)
    drums(hold, int(3.2 / BEAT))

    # ── 55.50 – 60.00  attract, ending on A MAJOR ─────────────────────────
    t0 = 55.5
    for i, chord in enumerate(("F", "G", "A")):
        dur = BAR if i < 2 else 2.2
        voice(t0 + i * BAR, dur * 0.94, ROOTS[chord], "bass", 0.14,
              atk=0.01, dec=0.3, sus=0.6, rel=0.4)
        pad(t0 + i * BAR, dur * 0.94, chord, 0.048)
        if i < 2:
            arp(t0 + i * BAR, 1, chord, vol=0.034)
    line(t0, [("C6", 4), ("B5", 4), ("A5", 8),
              ("B5", 4), ("C#6", 4), ("E6", 8)],
         vol=0.100, wave_name="bell", pan=-0.1, sus=0.55, echo=0.45, vib=0.05)
    # the final chord, major, held
    for nm, v, pn in (("A5", 0.10, -0.3), ("C#6", 0.075, 0.0),
                      ("E6", 0.070, 0.3)):
        voice(t0 + 2 * BAR, 2.4, nm, "brass", v, pn, atk=0.02, dec=0.7,
              sus=0.6, rel=0.9, vib=0.10, echo=0.4, detune=7.0)
    for b in range(6):
        hat(t0 + b * BEAT, 0.030)
    kick(t0 + 2 * BAR, 0.34)


# ── mix ───────────────────────────────────────────────────────────────────
def mixdown():
    # The echo unit: one delay line, feedback, and a one-pole lowpass in the
    # loop so repeats get darker rather than just quieter.  A dotted eighth at
    # 150 BPM, which is why it locks to the drums instead of smearing them.
    delay = int(0.30 * RATE)
    fb = 0.36
    lpf = 0.42
    zl = zr = 0.0
    for i in range(delay, N):
        sl = ECHO_L[i - delay]
        sr = ECHO_R[i - delay]
        zl += lpf * (sl - zl)
        zr += lpf * (sr - zr)
        L[i] += zl
        R[i] += zr
        ECHO_L[i] += zl * fb
        ECHO_R[i] += zr * fb


def write(path):
    build()
    mixdown()
    peak = max(max(abs(v) for v in L), max(abs(v) for v in R)) or 1.0
    # Headroom, not full scale: this plays out next to programme audio and
    # must not be the loudest thing on the channel.
    gain = 0.82 / peak
    tail = int(0.25 * RATE)
    frames = array("h", bytes(4 * N))
    for i in range(N):
        g = gain
        if i > N - tail:
            g *= (N - i) / tail
        a = L[i] * g
        b = R[i] * g
        if a > 1.0:
            a = 1.0
        elif a < -1.0:
            a = -1.0
        if b > 1.0:
            b = 1.0
        elif b < -1.0:
            b = -1.0
        frames[2 * i] = int(a * 32000)
        frames[2 * i + 1] = int(b * 32000)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames.tobytes())
    print(f"wrote {path}: {LENGTH:.1f}s stereo, peak {peak:.3f}, gain {gain:.3f}")


if __name__ == "__main__":
    write(sys.argv[1])
