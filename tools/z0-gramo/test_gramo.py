#!/usr/bin/env python3
"""Tests for the GRAMOPHONE interval. Plain unittest: LXC 111 has no pytest.

Every check carries a negative control. An agent cannot hear or see the
output, so the claims are measured: the rights clocks refuse what they
should, the envelope parser fails loudly when ffmpeg said nothing, and a
loud side draws a different disc from a silent one."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gramo  # noqa: E402

HAVE_FFMPEG = shutil.which(gramo.FFMPEG[0]) is not None
HAVE_FONTS = os.path.exists(gramo.MONO % "Regular")

SIDE = {
    "id": "0", "title": "Test side", "short": "Test",
    "performer": "Nobody", "persons": ["Nobody, 1890-1940"],
    "persons_display": "Nobody 1890-1940", "feeds": ["A feed"],
}


class Rights(unittest.TestCase):
    def test_death_year(self):
        self.assertEqual(gramo.death_year("Bolduc, Édouard, Mme, 1894-1941"), 1941)
        self.assertIsNone(gramo.death_year("Soucy, Isidore, 1899-"))
        self.assertIsNone(gramo.death_year("Anonymous"))

    def test_clear_both_clocks(self):
        v = gramo.clear(SIDE)
        self.assertIn("1964", v[gramo.Clock.RECORDING])
        self.assertEqual(v[gramo.Clock.WORK], "d.1940")

    def test_refuses_late_death(self):
        # Andy De Jarlis d.1975: recording PD, his own compositions are not.
        side = dict(SIDE, persons=["De Jarlis, Andy, 1914-1975"])
        with self.assertRaises(gramo.RightsError):
            gramo.clear(side)

    def test_refuses_missing_year(self):
        side = dict(SIDE, persons=["Nobody, 1890-1940", "Someone"])
        with self.assertRaises(gramo.RightsError):
            gramo.clear(side)

    def test_shipped_sides_clear(self):
        with open(gramo.SIDES) as fh:
            sides = __import__("json").load(fh)

        for side in sides:
            gramo.panel_lines(side, gramo.clear(side), 240)   # fits the panel
            self.assertTrue(side["url"].startswith("https://www.collectionscanada.gc.ca/"),
                            "the feed's own host does not resolve; use .gc.ca")


class Envelope(unittest.TestCase):
    def test_parse(self):
        text = ("frame:0 pts:0\nlavfi.astats.Overall.RMS_level=-23.5\n"
                "frame:1\nlavfi.astats.Overall.RMS_level=-inf\n")
        self.assertEqual(gramo.parse_envelope(text), [-23.5, -120.0])

    def test_empty_is_an_error(self):
        # The astats-at-INFO trap: an empty result must not render a dead disc.
        with self.assertRaises(gramo.EnvelopeError):
            gramo.parse_envelope("frame:0 pts:0\n")

    def test_normalise_clamps(self):
        self.assertEqual(gramo.normalise([-200.0, -45.0, -8.0, 0.0]),
                         [0.0, 0.0, 1.0, 1.0])

    @unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg")
    def test_measure_sine_vs_silence(self):
        work = tempfile.mkdtemp()
        try:
            loud = os.path.join(work, "sine.wav")
            quiet = os.path.join(work, "null.wav")
            subprocess.run(gramo.FFMPEG + ["-v", "error", "-y", "-f", "lavfi",
                                           "-i", "sine=f=440:d=1", loud], check=True)
            subprocess.run(gramo.FFMPEG + ["-v", "error", "-y", "-f", "lavfi",
                                           "-i", "anullsrc=d=1", quiet], check=True)
            e_loud = gramo.measure(loud, work)
            e_quiet = gramo.measure(quiet, work)
        finally:
            shutil.rmtree(work)

        self.assertEqual(len(e_loud), gramo.FPS)       # one figure per frame
        self.assertGreater(max(e_loud), -30.0)   # ffmpeg's sine is ~-21 dB RMS
        self.assertLess(max(e_quiet), -100.0)


@unittest.skipUnless(HAVE_FONTS, "needs the Liberation fonts")
class Picture(unittest.TestCase):
    def setUp(self):
        self.fonts = gramo.load_fonts()

    def frame_md5(self, env, i=45):
        seconds = len(env) / gramo.FPS
        for k, img in enumerate(gramo.frames(SIDE, env, seconds, self.fonts)):
            if k == i:
                return hashlib.md5(img.tobytes()).hexdigest()

    def test_loud_side_differs_from_silent(self):
        n = gramo.FPS * 4
        silent = [-120.0] * n
        loud = [-10.0 if (k // 15) % 2 else -120.0 for k in range(n)]
        self.assertNotEqual(self.frame_md5(silent), self.frame_md5(loud))

    def test_deterministic(self):
        env = [-20.0 + (k % 7) for k in range(gramo.FPS * 3)]
        self.assertEqual(self.frame_md5(env), self.frame_md5(env))

    def test_frame_is_house_size(self):
        env = [-30.0] * gramo.FPS
        img = next(gramo.frames(SIDE, env, 1.0, self.fonts))
        self.assertEqual(img.size, (gramo.W, gramo.H))
        self.assertEqual(img.mode, "RGB")

    def test_stylus_travels_rim_to_label(self):
        self.assertEqual(gramo.stylus_radius(0, 10), gramo.R_OUT)
        self.assertEqual(gramo.stylus_radius(10, 10), gramo.R_LABEL)
        self.assertEqual(gramo.stylus_radius(99, 10), gramo.R_LABEL)

    def test_panel_refuses_overlong_line(self):
        side = dict(SIDE, feeds=["x" * (gramo.COLS + 1)])
        with self.assertRaises(gramo.LayoutError):
            gramo.panel_lines(side, gramo.clear(side), 60)

    def test_vu_needle_sweeps(self):
        lo, hi = gramo.vu_angle(-40.0), gramo.vu_angle(0.0)
        self.assertGreater(lo, hi)                       # left to right
        self.assertEqual(gramo.vu_angle(-200.0), lo)     # clamped


class Nfo(unittest.TestCase):
    def test_tags(self):
        text = gramo.nfo(SIDE, "z0-gramo-00")
        self.assertIn("<tag>media</tag>", text)
        self.assertIn("<tag>gramophone</tag>", text)
        # The NFO replaces the folder tags. `generative` would put the clip in
        # the live interval pool on the next rescan; staged means it is absent.
        self.assertNotIn("generative", text)
        self.assertIn("<title>z0-gramo-00</title>", text)

    def test_escapes(self):
        side = dict(SIDE, title="Tom & Jerry <live>")
        self.assertIn("Tom &amp; Jerry &lt;live&gt;", gramo.nfo(side, "x"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
