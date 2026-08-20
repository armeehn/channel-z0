#!/usr/bin/env python3
"""The GROUND ZERO opening soundtrack, synthesised as a 2A03.

Four voices, the same four an NES has and no others: two pulse channels with
selectable duty, one triangle that is quantised to 16 steps (the chip has no
volume control on it, which is why the bass here is always the same loudness),
and one LFSR noise channel doing every drum.  No samples, no filters, no reverb
— an echo is a second quieter note placed later on the same voice, because that
is how these scores actually did it.

Pure Python and the stdlib `wave` module: numpy is broken in the container this
renders on, and the whole track is under three minutes of arithmetic anyway.

Usage:  gzaudio.py OUT.wav
"""
import math
import struct
import sys
import wave
from array import array

RATE = 48000
LENGTH = 60.0
N = int(RATE * LENGTH)

# ── note table ────────────────────────────────────────────────────────────
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def hz(name):
    """'A4' -> 440.0, 'C#5', 'Bb3' also accepted.  'R' is a rest."""
    if name == "R":
        return 0.0
    i = 1
    semis = _STEP[name[0]]
    while i < len(name) and name[i] in "#b":
        semis += 1 if name[i] == "#" else -1
        i += 1
    octv = int(name[i:])
    return 440.0 * (2.0 ** ((semis - 9) / 12.0 + (octv - 4)))


BUF = array("d", bytes(8 * N))

# ── voices ────────────────────────────────────────────────────────────────
# Every voice writes straight into one accumulation buffer.  Notes are allowed
# to overlap and simply sum, which is not what a 2A03 does — but the alternative
# is voice-stealing, and the only place it would be audible is the echo tail on
# the sting, where the doubling is the point.


def pulse(t, dur, note, vol=0.16, duty=0.5, decay=1.0, vib=0.0, slide=0.0):
    """Square wave.  `decay` is the fraction of `vol` left at the end of the
    note; `vib` is vibrato depth in semitones; `slide` bends over the note."""
    f0 = hz(note)
    if f0 <= 0:
        return
    i0 = int(t * RATE)
    n = int(dur * RATE)
    if i0 + n > N:
        n = N - i0
    phase = 0.0
    for i in range(n):
        k = i / n
        f = f0 * (2.0 ** ((slide * k) / 12.0))
        if vib:
            f *= 2.0 ** (vib * math.sin(i / RATE * 2 * math.pi * 6.5) / 12.0)
        phase += f / RATE
        v = vol * (1.0 + (decay - 1.0) * k)
        BUF[i0 + i] += v if (phase % 1.0) < duty else -v


_TRI = [abs(((s + 8) % 32) - 16) / 16.0 * 2.0 - 1.0 for s in range(32)]


def tri(t, dur, note, vol=0.20):
    """The triangle: 16 quantised steps up and 16 down, fixed volume."""
    f0 = hz(note)
    if f0 <= 0:
        return
    i0 = int(t * RATE)
    n = min(int(dur * RATE), N - i0)
    phase = 0.0
    for i in range(n):
        phase += f0 / RATE
        BUF[i0 + i] += vol * _TRI[int(phase * 32) & 31]


def noise(t, dur, vol=0.12, period=40, decay=0.0, tonal=False):
    """15-bit LFSR noise.  `tonal` flips the feedback tap, the chip's short
    mode — which is the difference between a snare and a hi-hat here."""
    i0 = int(t * RATE)
    n = min(int(dur * RATE), N - i0)
    reg = 0x7FFF
    acc = 0
    out = 1.0
    for i in range(n):
        acc += 1
        if acc >= period:
            acc = 0
            bit = (reg ^ (reg >> (6 if tonal else 1))) & 1
            reg = (reg >> 1) | (bit << 14)
            out = 1.0 if (reg & 1) else -1.0
        k = i / n
        BUF[i0 + i] += vol * (1.0 + (decay - 1.0) * k) * out


# ── drum kit, such as it is ───────────────────────────────────────────────
def kick(t, vol=0.30):
    tri(t, 0.09, "D2", vol)
    noise(t, 0.035, vol * 0.5, period=180, decay=0.0)


def snare(t, vol=0.20):
    noise(t, 0.115, vol, period=28, decay=0.0)
    noise(t, 0.05, vol * 0.6, period=90, decay=0.0)


def hat(t, vol=0.055):
    noise(t, 0.032, vol, period=8, decay=0.0, tonal=True)


def crash(t, vol=0.24):
    noise(t, 1.2, vol, period=12, decay=0.02, tonal=False)


# ── the score ─────────────────────────────────────────────────────────────
BPM = 150.0
BEAT = 60.0 / BPM          # 0.4 s
BAR = 4 * BEAT             # 1.6 s
SIX = BEAT / 4             # one sixteenth

CHORDS = {
    "Dm":  ["D3", "F3", "A3", "D4"],
    "Bb":  ["Bb2", "D3", "F3", "Bb3"],
    "F":   ["F2", "A2", "C3", "F3"],
    "C":   ["C3", "E3", "G3", "C4"],
    "A":   ["A2", "C#3", "E3", "A3"],
    "Gm":  ["G2", "Bb2", "D3", "G3"],
}
ROOTS = {"Dm": "D2", "Bb": "Bb1", "F": "F2", "C": "C2", "A": "A1", "Gm": "G1"}


def arp(t, bars, chord, vol=0.055, duty=0.125, step=None):
    """A chord played as a stream of sixteenths — the chiptune way to hold one."""
    step = step or SIX
    seq = CHORDS[chord]
    n = int(round(bars * BAR / step))
    for i in range(n):
        pulse(t + i * step, step * 0.92, seq[i % len(seq)], vol, duty, decay=0.55)


def line(t, notes, vol=0.15, duty=0.5, decay=0.75, vib=0.0, gap=0.94):
    """notes: [(name, sixteenths), ...].  Returns the time it ends."""
    for name, sixteenths in notes:
        d = sixteenths * SIX
        if name != "R":
            pulse(t, d * gap, name, vol, duty, decay=decay, vib=vib)
        t += d
    return t


def build():
    # ── 0.00 – 4.50  publisher sting ──────────────────────────────────────
    # Typewriter ticks under the wordmark, one per character, then the chime.
    for i in range(25):
        noise((6 + 1.05 * i) / 30.0, 0.012, 0.05, period=6, decay=0.0, tonal=True)

    t = 44 / 30.0                                   # the flash frame
    for i, nm in enumerate(("A4", "D5", "F5", "A5")):
        pulse(t + i * 0.075, 0.07, nm, 0.17, 0.5, decay=0.4)
    t += 0.30
    for nm, v in (("D5", 0.15), ("A5", 0.11), ("F5", 0.09)):
        pulse(t, 1.15, nm, v, 0.5, decay=0.10, vib=0.10)
    tri(t, 1.30, "D3", 0.20)
    for e, (dl, v) in enumerate(((0.20, 0.06), (0.40, 0.03))):   # the echo
        pulse(t + dl, 0.5, "D5", v, 0.5, decay=0.1)
        pulse(t + dl, 0.5, "A5", v * 0.7, 0.5, decay=0.1)

    # ── 4.50 – 26.50  the prologue bed ────────────────────────────────────
    # Nothing but a bass note and an arpeggio for eleven bars.  The lead does
    # not arrive until the crawl is half read; the text is the event here.
    t0 = 4.5
    prog = [("Dm", 2), ("Bb", 2), ("F", 2), ("C", 2), ("Dm", 2), ("Gm", 2),
            ("A", 1.75)]
    t = t0
    for chord, bars in prog:
        tri(t, bars * BAR * 0.98, ROOTS[chord], 0.17)
        arp(t, bars, chord, vol=0.05)
        t += bars * BAR

    lead_in = t0 + 6 * BAR
    line(lead_in, [("D5", 8), ("F5", 4), ("E5", 4),
                   ("D5", 8), ("C5", 4), ("D5", 4),
                   ("F5", 12), ("R", 4),
                   ("A4", 8), ("D5", 8)],
         vol=0.10, duty=0.25, decay=0.5, vib=0.06)
    line(t0 + 10 * BAR, [("A5", 8), ("G5", 4), ("F5", 4),
                         ("E5", 12), ("R", 4)],
         vol=0.11, duty=0.25, decay=0.5, vib=0.08)
    # the turn into the rooftop: a rising figure over the last bar and a half
    line(t0 + 12.25 * BAR, [("D5", 2), ("E5", 2), ("F5", 2), ("G5", 2),
                            ("A5", 2), ("Bb5", 2), ("C6", 2), ("C#6", 2)],
         vol=0.12, duty=0.25, decay=0.6)

    # ── 26.50 – 36.50  the rooftop ────────────────────────────────────────
    t0 = 26.5
    beats = int(10.0 / BEAT)
    for b in range(beats):
        tb = t0 + b * BEAT
        if b % 4 in (0, 2):
            kick(tb)
        if b % 4 in (1, 3):
            snare(tb)
        hat(tb)
        hat(tb + BEAT / 2)

    bass_prog = ["Dm", "Dm", "Bb", "Bb", "F", "C"]
    for i, chord in enumerate(bass_prog):
        tb = t0 + i * BAR
        r = ROOTS[chord]
        for j in range(8):                          # driving eighths
            tri(tb + j * BEAT / 2, BEAT * 0.44,
                r if j % 4 != 3 else r[:-1] + str(int(r[-1]) + 1), 0.19)

    line(t0, [("A4", 4), ("D5", 4), ("F5", 4), ("A5", 4),
              ("G5", 6), ("F5", 2), ("D5", 8),
              ("D5", 4), ("F5", 4), ("Bb5", 4), ("A5", 4),
              ("F5", 6), ("D5", 2), ("Bb4", 8),
              ("C5", 4), ("F5", 4), ("A5", 4), ("G5", 4),
              ("E5", 6), ("G5", 2), ("C5", 4), ("E5", 4)],
         vol=0.145, duty=0.5, decay=0.65, vib=0.05)
    line(t0 + 2 * SIX, [("F4", 4), ("A4", 4), ("D5", 4), ("F5", 4),
                        ("E5", 6), ("D5", 2), ("A4", 8),
                        ("Bb4", 4), ("D5", 4), ("F5", 4), ("F5", 4),
                        ("D5", 6), ("Bb4", 2), ("F4", 8),
                        ("A4", 4), ("C5", 4), ("F5", 4), ("E5", 4),
                        ("C5", 6), ("E5", 2), ("G4", 8)],
         vol=0.065, duty=0.125, decay=0.6)

    # ── 36.50 – 41.50  the push-in ────────────────────────────────────────
    # Everything narrows to one rising line and an accelerating roll, then a
    # bar of nothing at all so the logo lands in silence.
    t0 = 36.5
    riser = ["D4", "E4", "F4", "G4", "A4", "Bb4", "C5", "D5",
             "E5", "F5", "G5", "A5", "Bb5", "C6", "D6", "E6"]
    for i, nm in enumerate(riser):
        pulse(t0 + i * 0.20, 0.19, nm, 0.09 + i * 0.004, 0.25, decay=0.8)
    tri(t0, 3.2, "D2", 0.18)
    tri(t0 + 3.2, 0.8, "A1", 0.18)
    rt, gapn = t0, 0.20
    while rt < t0 + 4.0:
        snare(rt, 0.10 + (rt - t0) * 0.02)
        rt += gapn
        gapn = max(0.055, gapn * 0.86)
    crash(t0 + 4.0, 0.20)
    for i, nm in enumerate(("D6", "A5", "F5", "D5")):
        pulse(t0 + 4.05 + i * 0.06, 0.055, nm, 0.14, 0.5, decay=0.3)

    # ── 41.50 – 52.00  the logo ───────────────────────────────────────────
    t0 = 41.5
    crash(t0, 0.26)
    kick(t0, 0.34)
    for nm, v in (("D3", 0.14), ("A3", 0.11), ("D4", 0.10)):
        pulse(t0, 0.55, nm, v, 0.5, decay=0.25)
    tri(t0, 0.6, "D2", 0.22)

    hits = [(0.0, "Dm"), (0.8, "Dm"), (1.6, "Bb"), (2.4, "C")]
    for off, chord in hits:
        tb = t0 + off
        kick(tb)
        snare(tb + 0.4)
        tri(tb, 0.75, ROOTS[chord], 0.21)

    line(t0 + 0.10, [("D5", 2), ("R", 2), ("D5", 2), ("R", 2),
                     ("F5", 4), ("A5", 4),
                     ("Bb5", 8), ("A5", 8),
                     ("G5", 4), ("A5", 4), ("Bb5", 4), ("C6", 4)],
         vol=0.16, duty=0.5, decay=0.7)
    line(t0 + 0.10, [("F4", 2), ("R", 2), ("F4", 2), ("R", 2),
                     ("A4", 4), ("D5", 4),
                     ("D5", 8), ("F5", 8),
                     ("E5", 4), ("F5", 4), ("G5", 4), ("A5", 4)],
         vol=0.075, duty=0.125, decay=0.7)

    # the arrival: a held D with vibrato under a slow triad, four bars
    # The hold has to reach all the way to the attract screen.  At 3.6 s it
    # ended at 49.9 and left two seconds of nothing before PRESS START, which
    # does not read as a dramatic pause — it reads as the audio dropping out.
    hold = t0 + 4 * BEAT * 3
    pulse(hold, 5.4, "D6", 0.15, 0.5, decay=0.30, vib=0.16)
    pulse(hold, 5.4, "A5", 0.09, 0.5, decay=0.30, vib=0.16)
    tri(hold, 5.6, "D2", 0.22)
    crash(hold, 0.20)
    for b in range(9):
        tb = hold + b * BEAT
        if b % 2 == 0:
            kick(tb)
        else:
            snare(tb, 0.16)
        hat(tb + BEAT / 2, 0.045)

    # ── 52.00 – 60.00  attract ────────────────────────────────────────────
    # The theme once more, thinner, over a bass that stops walking.  It has to
    # end on the tonic before the picture fades or the cut into the next
    # programme sounds like a dropout.
    t0 = 52.0
    for i, chord in enumerate(("Dm", "Bb", "F", "A", "Dm")):
        tri(t0 + i * BAR, BAR * 0.9, ROOTS[chord], 0.15)
        arp(t0 + i * BAR, 1, chord, vol=0.038)
    line(t0, [("A4", 4), ("D5", 4), ("F5", 4), ("A5", 4),
              ("G5", 8), ("F5", 8),
              ("C5", 4), ("F5", 4), ("A5", 4), ("G5", 4),
              ("E5", 8), ("C#5", 8),
              ("D5", 16)],
         vol=0.105, duty=0.25, decay=0.55, vib=0.05)
    for b in range(10):
        hat(t0 + b * BEAT, 0.030)


def write(path):
    build()
    peak = max(abs(v) for v in BUF) or 1.0
    # Headroom rather than normalising to full scale: this is played out
    # alongside programme audio and must not be the loudest thing on the channel.
    gain = 0.88 / peak
    tail = int(0.25 * RATE)
    frames = array("h", bytes(2 * N))
    for i in range(N):
        v = BUF[i] * gain
        if i > N - tail:                       # avoid a click at the cut
            v *= (N - i) / tail
        if v > 1.0:
            v = 1.0
        elif v < -1.0:
            v = -1.0
        frames[i] = int(v * 32000)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames.tobytes())
    print(f"wrote {path}: {LENGTH:.1f}s, peak {peak:.3f}, gain {gain:.3f}")


if __name__ == "__main__":
    write(sys.argv[1])
