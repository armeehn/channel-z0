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
    # A bell: sparse, odd-weighted.
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


# ── the score ─────────────────────────────────────────────────────────────
# Slow and grave.  There is no tempo: a drone on A, a pulse once a second
# while the signal is leaving, strings that swell as the ring opens, one low
# impact, and an open fifth to close — A and E, no third, because the story
# does not resolve sweetly.  The 168 BPM chip score this replaces is in the
# repository's history; nothing of it is used except the instruments.
CHORDS = {"Am": ["A4", "C5", "E5", "A5"], "F": ["F4", "A4", "C5", "F5"],
          "C": ["C4", "E4", "G4", "C5"], "G": ["G4", "B4", "D5", "G5"],
          "Dm": ["D4", "F4", "A4", "D5"], "E": ["E4", "G#4", "B4", "E5"],
          "A5": ["A4", "E5", "A5", "E6"]}
ROOTS = {"Am": "A2", "F": "F2", "C": "C3", "G": "G2", "Dm": "D3", "E": "E2",
         "A5": "A2"}
PADS = {"Am": ["A4", "C5", "E5"], "F": ["F4", "A4", "C5"],
        "C": ["C4", "E4", "G4"], "G": ["G4", "B4", "D5"],
        "Dm": ["D4", "F4", "A4"], "E": ["E4", "G#4", "B4"],
        "A5": ["A4", "E5", "A5"]}

# Frame times the picture and the cue share (make_frames.py timeline).
T_SIGNAL, T_FIELD, T_RING, T_LAND, T_CLAIM, T_LOCKUP = 3.0, 15.0, 25.0, 33.0, 44.0, 52.0
T_IMPACT = T_LAND + 80 / 30.0


def pad(t, dur, chord, vol=0.045, atk=1.5, rel=1.5):
    for i, nm in enumerate(PADS[chord]):
        voice(t, dur, nm, "string", vol, pan=(-0.62, 0.0, 0.62)[i],
              atk=atk, dec=0.4, sus=0.9, rel=rel, detune=6.0)


def bell(t, note, vol=0.05, pan=0.0, dur=0.9):
    voice(t, dur, note, "bell", vol, pan, atk=0.004, dec=0.25, sus=0.35,
          rel=0.6, echo=0.45)


def pulse(t, vol=0.16):
    voice(t, 0.10, "A1", "bass", vol, atk=0.002, dec=0.08, sus=0.3, rel=0.10,
          echo=0.18)


def build():
    # ── the drone, under everything ───────────────────────────────────────
    voice(0.0, 57.0, "A1", "bass", 0.10, atk=4.0, dec=0.5, sus=1.0, rel=2.5)
    voice(0.0, 57.0, "E2", "string", 0.045, pan=0.2, atk=7.0, dec=0.5, sus=1.0,
          rel=2.5, detune=5.0)
    voice(0.0, 57.0, "A2", "string", 0.035, pan=-0.2, atk=9.0, dec=0.5, sus=1.0,
          rel=2.5, detune=4.0)

    # ── 3.0 – 15.0  the signal leaving: a pulse once a second ─────────────
    t = T_SIGNAL
    while t < T_FIELD - 0.5:
        pulse(t, 0.16 * max(0.35, 1 - (t - T_SIGNAL) / 14.0))
        t += 1.0
    pad(T_SIGNAL + 0.5, T_FIELD - T_SIGNAL - 1.0, "Am", 0.040, atk=2.5)
    bell(7.0, "E5", 0.045, -0.2)
    bell(11.0, "C5", 0.045, 0.2)

    # ── 15.0 – 25.0  the field: unanswered, then answered ─────────────────
    pad(T_FIELD, 10.0, "F", 0.042, atk=3.0)
    bell(19.0, "E5", 0.040, -0.3)
    bell(22.5, "A5", 0.050, 0.3, dur=1.4)
    voice(20.4, 5.0, "E6", "bell", 0.028, atk=2.5, dec=0.5, sus=0.8, rel=1.5, echo=0.5)

    # ── 25.0 – 33.0  the ring: strings swell ──────────────────────────────
    for nm, pn, v in (("A4", -0.4, 0.075), ("C5", 0.0, 0.065), ("E5", 0.4, 0.070)):
        voice(T_RING, 7.2, nm, "string", v, pn, atk=4.5, dec=0.5, sus=0.95,
              rel=1.2, vib=0.06, vibd=3.0, detune=6.0)
    voice(T_RING + 1.0, 6.0, "G3", "bass", 0.09, atk=3.0, dec=0.5, sus=0.9, rel=1.0)
    for i, tt in enumerate((29.0, 30.4, 31.6)):
        bell(tt, ("E6", "A6", "E6")[i], 0.032, (-0.3, 0.3, 0.0)[i], dur=1.2)

    # ── 33.0 – 44.0  the descent and the impact ───────────────────────────
    voice(T_LAND, T_IMPACT - T_LAND - 0.2, "E2", "string", 0.05, atk=1.0, dec=0.2,
          sus=0.9, rel=0.2, detune=7.0)
    kick(T_IMPACT, 0.55)
    _sweep(T_IMPACT, 1.8, 72.0, 24.0, 0.55, curve=1.8)
    _burst(T_IMPACT, 0.9, 0.10, 2.0, step=5, echo=0.4, off=32749)
    # after it: almost nothing.  The drone, and one bell a long way off.
    bell(40.5, "A5", 0.030, 0.0, dur=1.6)

    # ── 44.0 – 52.0  the claim ────────────────────────────────────────────
    pad(T_CLAIM, 7.5, "Am", 0.045, atk=2.0)
    bell(T_CLAIM + 0.6, "A5", 0.055, -0.2, dur=1.4)
    bell(T_CLAIM + 2.6, "C6", 0.050, 0.2, dur=1.4)
    bell(T_CLAIM + 4.6, "B5", 0.045, 0.0, dur=1.6)

    # ── 52.0 – 60.0  the lockup, on an open fifth ─────────────────────────
    voice(T_LOCKUP, 7.4, "A2", "bass", 0.13, atk=0.8, dec=0.5, sus=0.9, rel=1.2)
    for nm, pn, v in (("A3", -0.3, 0.085), ("E4", 0.3, 0.070), ("A4", 0.0, 0.055),
                      ("E5", -0.15, 0.040), ("A5", 0.15, 0.040)):
        voice(T_LOCKUP, 7.2, nm, "string", v, pn, atk=1.6, dec=0.5, sus=0.9,
              rel=1.4, vib=0.05, vibd=2.5, detune=6.0)
    bell(T_LOCKUP + 2.8, "A5", 0.045, -0.2, dur=1.6)
    bell(T_LOCKUP + 4.4, "E6", 0.040, 0.2, dur=1.8)


# ── mix ───────────────────────────────────────────────────────────────────
def mixdown():
    # The echo unit: one delay line, feedback, and a one-pole lowpass in the
    # loop so repeats get darker rather than just quieter.  Three hundred
    # milliseconds and dark repeats: a room, not a rhythm.
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
