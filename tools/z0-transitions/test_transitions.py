#!/usr/bin/env python3
"""Checks on the segment transition cards.  Picture checks for the two TTF
grammars skip where no monospace TTF is installed (CI); the manifest, the
16-bit grammar, the sidecars and the sound are checked everywhere."""
import os
import sys
import tempfile
import wave

from PIL import ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transitions as T

FAILS = []
SKIPS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _ttf():
    try:
        T.font("xb", 20)
        return True
    except T.FontMissing:
        return False


def test_manifest():
    try:
        T.check_manifest()
    except AssertionError as e:
        FAILS.append("manifest: %s" % (e,))
    names = [T.clip_name(k, s) for k, s in T.cards()]
    check(len(names) == len(set(names)), "clip names collide")
    check(all(len(n) <= 40 for n in names), "a clip name is over 40 chars")
    check(len(names) >= 20, "only %d cards" % len(names))


def test_gz_frames():
    a = T.frame("groundzero", "interview", 84)
    b = T.frame("groundzero", "interview", 84)
    check(a.size == (640, 480) and a.mode == "RGB", "gz frame is %r %s" % (a.size, a.mode))
    check(a.tobytes() == b.tobytes(), "gz frame is not deterministic")
    check(a.tobytes() != T.frame("groundzero", "interview", 0).tobytes(),
          "gz frame 0 and 84 are identical")
    last = T.frame("groundzero", "interview", T.FRAMES - 1)
    mean = ImageStat.Stat(last.convert("L")).mean[0]
    check(mean < 30, "gz card does not dip to ink at the end (mean %.1f)" % mean)


def test_ttf_frames():
    if not _ttf():
        SKIPS.append("ttf frames (no monospace TTF)")
        return
    for show, slug in (("labhour", "bench"), ("desk", "lost-found")):
        a = T.frame(show, slug, 84)
        check(a.size == (640, 480), "%s frame is %r" % (show, a.size))
        check(a.tobytes() == T.frame(show, slug, 84).tobytes(),
              "%s frame is not deterministic" % show)
        check(a.tobytes() != T.frame(show, slug, 2).tobytes(),
              "%s frame 2 and 84 are identical" % show)
    # the desk card leaves the frame: the last frame is ink again
    last = T.frame("desk", "lost-found", T.FRAMES - 1)
    mean = ImageStat.Stat(last.convert("L")).mean[0]
    check(mean < 30, "desk card does not leave (mean %.1f)" % mean)


def test_nfo():
    n = T.nfo("desk", "lost-found")
    for tag in ("<tag>media</tag>", "<tag>transitions</tag>", "<tag>desk</tag>"):
        check(tag in n, "nfo lacks %s" % tag)
    check("generative" not in n, "nfo carries the interval pool tag")
    check("LOST &amp; FOUND" in n, "ampersand not escaped in the nfo")


def test_audio():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "a.wav")
        T.audio("groundzero", "contact", path)
        with wave.open(path) as w:
            check(w.getnchannels() == 2 and w.getframerate() == 48000, "wav format")
            check(w.getnframes() == int(T.SECONDS * 48000), "wav length %d" % w.getnframes())
            head = w.readframes(24000)
        loud = max(abs(int.from_bytes(head[i:i + 2], "little", signed=True))
                   for i in range(0, len(head), 2))
        check(loud > 3000, "sting is silent in the first half second (peak %d)" % loud)
        check(loud <= int(0.82 * 32767) + 1, "sting exceeds the headroom rule")
    # nothing scheduled past the end of the card
    T._clear()
    T.desk_sting(T.find("desk", "casserole")[1])
    tail = int(T.SECONDS * T.A.RATE)
    check(max(abs(v) for v in T.A.L[tail:tail + 4800]) < 1e-6, "desk sting runs past the card")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    for s in SKIPS:
        print("SKIP", s)
    for f in FAILS:
        print("FAIL", f)
    print("%d tests, %d failures, %d skipped" % (len(tests), len(FAILS), len(SKIPS)))
    sys.exit(1 if FAILS else 0)
