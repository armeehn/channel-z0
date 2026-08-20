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
BPM = 150.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
SIX = BEAT / 4

CHORDS = {
    "Dm": ["D3", "F3", "A3", "D4"], "Bb": ["Bb2", "D3", "F3", "Bb3"],
    "F": ["F2", "A2", "C3", "F3"], "C": ["C3", "E3", "G3", "C4"],
    "A": ["A2", "C#3", "E3", "A3"], "Gm": ["G2", "Bb2", "D3", "G3"],
}
ROOTS = {"Dm": "D2", "Bb": "Bb1", "F": "F2", "C": "C2", "A": "A1", "Gm": "G1"}
PADS = {"Dm": ["D4", "F4", "A4"], "Bb": ["Bb3", "D4", "F4"],
        "F": ["F3", "A3", "C4"], "C": ["C4", "E4", "G4"],
        "A": ["A3", "C#4", "E4"], "Gm": ["G3", "Bb3", "D4"]}


def arp(t, bars, chord, vol=0.05, step=None, wave_name="bell", echo=0.4):
    step = step or SIX
    seq = CHORDS[chord]
    for i in range(int(round(bars * BAR / step))):
        voice(t + i * step, step * 0.9, seq[i % len(seq)], wave_name, vol,
              pan=-0.55 + 0.30 * (i % 4), atk=0.002, dec=0.09, sus=0.25,
              rel=0.10, echo=echo)


def pad(t, dur, chord, vol=0.045):
    for i, nm in enumerate(PADS[chord]):
        voice(t, dur, nm, "string", vol, pan=(-0.62, 0.0, 0.62)[i],
              atk=0.35, dec=0.4, sus=0.85, rel=0.5, detune=7.0)


def line(t, notes, vol=0.15, wave_name="lead", pan=0.0, sus=0.75, echo=0.25,
         vib=0.0, detune=0.0, atk=0.008, rel=0.12):
    for name, sixteenths in notes:
        d = sixteenths * SIX
        if name != "R":
            voice(t, d * 0.92, name, wave_name, vol, pan, atk=atk, dec=0.10,
                  sus=sus, rel=rel, vib=vib, echo=echo, detune=detune)
        t += d
    return t


def build():
    # ── 0.00 – 4.50  publisher sting ──────────────────────────────────────
    for i in range(25):
        _burst((6 + 1.05 * i) / 30.0, 0.010, 0.05, 3.0, step=13, off=i * 733)

    t = 44 / 30.0
    for i, nm in enumerate(("A4", "D5", "F5", "A5")):
        voice(t + i * 0.075, 0.16, nm, "bell", 0.17, pan=-0.6 + 0.40 * i,
              atk=0.002, dec=0.10, sus=0.35, rel=0.22, echo=0.55)
    t += 0.30
    stab(t, 0.26, "D3")
    for nm, v, pn in (("D4", 0.13, -0.3), ("A4", 0.10, 0.0), ("F5", 0.09, 0.3)):
        voice(t, 1.5, nm, "brass", v, pn, atk=0.01, dec=0.35, sus=0.42,
              rel=0.55, vib=0.10, echo=0.45, detune=6.0)
    voice(t, 1.7, "D2", "bass", 0.20, atk=0.004, dec=0.30, sus=0.55, rel=0.5)
    pad(t, 1.9, "Dm", 0.05)

    # ── 4.50 – 26.50  the prologue bed ────────────────────────────────────
    t0 = 4.5
    prog = [("Dm", 2), ("Bb", 2), ("F", 2), ("C", 2), ("Dm", 2), ("Gm", 2),
            ("A", 1.75)]
    t = t0
    for chord, bars in prog:
        voice(t, bars * BAR * 0.96, ROOTS[chord], "bass", 0.15,
              atk=0.02, dec=0.5, sus=0.60, rel=0.4)
        pad(t, bars * BAR * 0.96, chord, 0.042)
        arp(t, bars, chord, vol=0.042)
        t += bars * BAR

    lead_in = t0 + 6 * BAR
    line(lead_in, [("D5", 8), ("F5", 4), ("E5", 4),
                   ("D5", 8), ("C5", 4), ("D5", 4),
                   ("F5", 12), ("R", 4),
                   ("A4", 8), ("D5", 8)],
         vol=0.085, wave_name="bell", pan=-0.15, sus=0.5, echo=0.45, vib=0.05)
    line(t0 + 10 * BAR, [("A5", 8), ("G5", 4), ("F5", 4), ("E5", 12), ("R", 4)],
         vol=0.095, wave_name="lead", pan=0.15, sus=0.55, echo=0.4, vib=0.07,
         atk=0.05)
    line(t0 + 12.25 * BAR, [("D5", 2), ("E5", 2), ("F5", 2), ("G5", 2),
                            ("A5", 2), ("Bb5", 2), ("C6", 2), ("C#6", 2)],
         vol=0.11, wave_name="brass", sus=0.6, echo=0.3)

    # ── 26.50 – 36.50  the rooftop ────────────────────────────────────────
    t0 = 26.5
    for b in range(int(10.0 / BEAT)):
        tb = t0 + b * BEAT
        if b % 4 in (0, 2):
            kick(tb)
        if b % 4 in (1, 3):
            snare(tb)
        hat(tb)
        hat(tb + BEAT / 2, 0.055, open_=(b % 8 == 7))

    for i, chord in enumerate(["Dm", "Dm", "Bb", "Bb", "F", "C"]):
        tb = t0 + i * BAR
        r = ROOTS[chord]
        for j in range(8):
            nm = r if j % 4 != 3 else r[:-1] + str(int(r[-1]) + 1)
            voice(tb + j * BEAT / 2, BEAT * 0.42, nm, "bass", 0.185,
                  atk=0.003, dec=0.07, sus=0.45, rel=0.06)
        pad(tb, BAR * 0.95, chord, 0.036)

    line(t0, [("A4", 4), ("D5", 4), ("F5", 4), ("A5", 4),
              ("G5", 6), ("F5", 2), ("D5", 8),
              ("D5", 4), ("F5", 4), ("Bb5", 4), ("A5", 4),
              ("F5", 6), ("D5", 2), ("Bb4", 8),
              ("C5", 4), ("F5", 4), ("A5", 4), ("G5", 4),
              ("E5", 6), ("G5", 2), ("C5", 4), ("E5", 4)],
         vol=0.135, wave_name="lead", pan=-0.1, sus=0.68, echo=0.28, vib=0.05,
         detune=8.0)
    line(t0 + 2 * SIX, [("F4", 4), ("A4", 4), ("D5", 4), ("F5", 4),
                        ("E5", 6), ("D5", 2), ("A4", 8),
                        ("Bb4", 4), ("D5", 4), ("F5", 4), ("F5", 4),
                        ("D5", 6), ("Bb4", 2), ("F4", 8),
                        ("A4", 4), ("C5", 4), ("F5", 4), ("E5", 4),
                        ("C5", 6), ("E5", 2), ("G4", 8)],
         vol=0.055, wave_name="bell", pan=0.4, sus=0.5, echo=0.4)

    # ── 36.50 – 41.50  the push-in ────────────────────────────────────────
    t0 = 36.5
    riser = ["D4", "E4", "F4", "G4", "A4", "Bb4", "C5", "D5",
             "E5", "F5", "G5", "A5", "Bb5", "C6", "D6", "E6"]
    for i, nm in enumerate(riser):
        voice(t0 + i * 0.20, 0.20, nm, "brass", 0.075 + i * 0.0042,
              pan=-0.75 + 1.5 * i / 15.0, atk=0.01, dec=0.06, sus=0.8, rel=0.05,
              echo=0.3)
    voice(t0, 3.3, "D2", "bass", 0.17, atk=0.05, dec=0.6, sus=0.7, rel=0.3)
    voice(t0 + 3.2, 0.9, "A1", "bass", 0.18, atk=0.01, dec=0.3, sus=0.7)
    pad(t0, 4.0, "Dm", 0.05)
    rt, gapn = t0, 0.20
    while rt < t0 + 4.0:
        snare(rt, 0.11 + (rt - t0) * 0.022)
        rt += gapn
        gapn = max(0.055, gapn * 0.86)
    crash(t0 + 4.0, 0.24)
    for i, nm in enumerate(("D6", "A5", "F5", "D5")):
        voice(t0 + 4.05 + i * 0.06, 0.10, nm, "brass", 0.13, atk=0.002,
              dec=0.05, sus=0.4, rel=0.08, echo=0.4)

    # ── 41.50 – 52.00  the logo ───────────────────────────────────────────
    t0 = 41.5
    crash(t0, 0.30)
    kick(t0, 0.46)
    stab(t0, 0.30, "D3")
    voice(t0, 0.7, "D2", "bass", 0.21, atk=0.003, dec=0.2, sus=0.6, rel=0.2)

    for off, chord in ((0.0, "Dm"), (0.8, "Dm"), (1.6, "Bb"), (2.4, "C")):
        tb = t0 + off
        kick(tb)
        snare(tb + 0.4)
        voice(tb, 0.78, ROOTS[chord], "bass", 0.20, atk=0.003, dec=0.15,
              sus=0.55, rel=0.15)
        pad(tb, 0.8, chord, 0.05)

    line(t0 + 0.10, [("D5", 2), ("R", 2), ("D5", 2), ("R", 2),
                     ("F5", 4), ("A5", 4),
                     ("Bb5", 8), ("A5", 8),
                     ("G5", 4), ("A5", 4), ("Bb5", 4), ("C6", 4)],
         vol=0.145, wave_name="brass", pan=-0.12, sus=0.72, echo=0.32,
         detune=9.0)
    line(t0 + 0.10, [("F4", 2), ("R", 2), ("F4", 2), ("R", 2),
                     ("A4", 4), ("D5", 4),
                     ("D5", 8), ("F5", 8),
                     ("E5", 4), ("F5", 4), ("G5", 4), ("A5", 4)],
         vol=0.065, wave_name="lead", pan=0.35, sus=0.7, echo=0.3)

    hold = t0 + 4 * BEAT * 3
    for nm, v, pn in (("D6", 0.13, -0.15), ("A5", 0.085, 0.15),
                      ("F5", 0.07, 0.35)):
        voice(hold, 5.4, nm, "brass", v, pn, atk=0.02, dec=0.9, sus=0.55,
              rel=1.2, vib=0.14, vibd=0.5, echo=0.35, detune=8.0)
    voice(hold, 5.6, "D2", "bass", 0.20, atk=0.01, dec=0.8, sus=0.6, rel=1.0)
    pad(hold, 5.6, "Dm", 0.055)
    crash(hold, 0.24)
    for b in range(9):
        tb = hold + b * BEAT
        kick(tb) if b % 2 == 0 else snare(tb, 0.20)
        hat(tb + BEAT / 2, 0.05)

    # ── 52.00 – 60.00  attract ────────────────────────────────────────────
    t0 = 52.0
    for i, chord in enumerate(("Dm", "Bb", "F", "A", "Dm")):
        voice(t0 + i * BAR, BAR * 0.92, ROOTS[chord], "bass", 0.13,
              atk=0.01, dec=0.3, sus=0.55, rel=0.25)
        pad(t0 + i * BAR, BAR * 0.92, chord, 0.04)
        arp(t0 + i * BAR, 1, chord, vol=0.032)
    line(t0, [("A4", 4), ("D5", 4), ("F5", 4), ("A5", 4),
              ("G5", 8), ("F5", 8),
              ("C5", 4), ("F5", 4), ("A5", 4), ("G5", 4),
              ("E5", 8), ("C#5", 8),
              ("D5", 16)],
         vol=0.095, wave_name="bell", pan=-0.1, sus=0.55, echo=0.45, vib=0.05)
    for b in range(10):
        hat(t0 + b * BEAT, 0.032)


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
