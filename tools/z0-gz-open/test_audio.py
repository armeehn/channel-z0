#!/usr/bin/env python3
"""Checks on the synthesised score that do not require ears.

Three things get proved here, because all three have been wrong at some point:
the echo unit actually produces repeats, the pan law actually moves voices, and
the notes that come out are the notes the score asked for.  Each has a negative
control — an assertion that passes only because the thing under test is on.
"""
import math
import sys

import gzaudio as A


def reset():
    for buf in (A.L, A.R, A.ECHO_L, A.ECHO_R):
        for i in range(len(buf)):
            buf[i] = 0.0


def rms(buf, t0, t1):
    i0, i1 = int(t0 * A.RATE), int(t1 * A.RATE)
    seg = buf[i0:i1]
    return math.sqrt(sum(v * v for v in seg) / max(1, len(seg)))


def test_echo():
    """One short note with a full echo send must reappear at 0.30 s intervals,
    each repeat quieter than the last — and must NOT reappear with echo off."""
    reset()
    A.voice(0.10, 0.12, "A4", "lead", 0.5, echo=1.0)
    A.mixdown()
    taps = [rms(A.L, 0.10 + 0.30 * k, 0.10 + 0.30 * k + 0.12) for k in range(4)]

    reset()
    A.voice(0.10, 0.12, "A4", "lead", 0.5, echo=0.0)
    A.mixdown()
    dry = [rms(A.L, 0.10 + 0.30 * k, 0.10 + 0.30 * k + 0.12) for k in range(4)]

    print("  echo on : " + " ".join("%.4f" % v for v in taps))
    print("  echo off: " + " ".join("%.4f" % v for v in dry))
    assert taps[1] > 0.02 * taps[0], "no first repeat — echo unit is dead"
    assert taps[1] > taps[2] > taps[3], "repeats are not decaying"
    assert dry[1] < 0.01 * dry[0], "negative control failed: repeats with echo off"
    print("  PASS  repeats at 0.30 s, decaying, and absent when the send is 0")


def test_pan():
    """Hard left must be much louder in L than R, and vice versa."""
    reset()
    A.voice(0.1, 0.4, "A4", "lead", 0.4, pan=-1.0)
    l, r = rms(A.L, 0.1, 0.5), rms(A.R, 0.1, 0.5)
    print("  pan -1.0 -> L %.4f  R %.4f  ratio %.1f" % (l, r, l / max(r, 1e-9)))
    assert l > 20 * r, "left pan does not reach left"
    reset()
    A.voice(0.1, 0.4, "A4", "lead", 0.4, pan=1.0)
    l, r = rms(A.L, 0.1, 0.5), rms(A.R, 0.1, 0.5)
    print("  pan +1.0 -> L %.4f  R %.4f  ratio %.1f" % (l, r, r / max(l, 1e-9)))
    assert r > 20 * l, "right pan does not reach right"
    reset()
    A.voice(0.1, 0.4, "A4", "lead", 0.4, pan=0.0)
    l, r = rms(A.L, 0.1, 0.5), rms(A.R, 0.1, 0.5)
    assert abs(l - r) < 0.02 * l, "centre is not centred"
    print("  PASS  equal-power pan reaches both extremes and centres")


def goertzel(seg, f, rate):
    k = 2 * math.cos(2 * math.pi * f / rate)
    s1 = s2 = 0.0
    for x in seg:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(abs(s1 * s1 + s2 * s2 - k * s1 * s2)) / len(seg)


def test_pitch():
    """A voice asked for a note must put its energy at that note's frequency
    and not at its neighbours a semitone either side."""
    reset()
    for name in ("D2", "A3", "D5", "Bb5"):
        A.voice(0.1, 1.0, name, "lead", 0.4)
        f = A.hz(name)
        # The window has to be long enough to RESOLVE a semitone at this
        # frequency, or the test fails on the bass for arithmetic reasons and
        # not musical ones: at D2 a semitone is 4.4 Hz and a fixed 8192-sample
        # window only resolves 5.9 Hz.
        win = min(int(0.85 * A.RATE), max(8192, int(34 * A.RATE / f)))
        i0 = int(0.15 * A.RATE)
        seg = A.L[i0:i0 + win]
        on = goertzel(seg, f, A.RATE)
        lo = goertzel(seg, f * 2 ** (-1 / 12), A.RATE)
        hi = goertzel(seg, f * 2 ** (1 / 12), A.RATE)
        print("  %-4s %7.2f Hz  on %.5f  -1st %.5f  +1st %.5f" % (name, f, on, lo, hi))
        assert on > 4 * max(lo, hi), f"{name} is not where it should be"
        reset()
    print("  PASS  every voice lands on the note it was given")


def test_ending():
    """The cue must end on an OPEN FIFTH — A and E, and no third at all.

    It used to end on a Picardy third and the claim in the docs was "A major".
    Both the claim and its opposite are one interval apart, so the check is
    the interval: neither C natural nor C# may be anywhere near the level of
    the A and the E."""
    reset()
    A.build()
    A.mixdown()
    rate = A.RATE
    i0 = int(58.4 * rate)
    win = min(int(1.2 * rate), max(8192, int(34 * rate / 440.0)))
    seg = A.L[i0:i0 + win]
    lvl = {nm: goertzel(seg, A.hz(nm), rate)
           for nm in ("A5", "E6", "C6", "C#6")}
    for nm, v in lvl.items():
        print("  %-4s %.5f" % (nm, v))
    root = max(lvl["A5"], lvl["E6"])
    third = max(lvl["C6"], lvl["C#6"])
    print("  root/third ratio %.1f" % (root / max(third, 1e-9)))
    assert root > 6 * third, "there is a third in the final chord"
    print("  PASS  final chord is an open fifth, no third")


if __name__ == "__main__":
    print("echo unit:")
    test_echo()
    print("pan law:")
    test_pan()
    print("pitch:")
    test_pitch()
    print("ending:")
    test_ending()
    print("\nall audio checks passed")
