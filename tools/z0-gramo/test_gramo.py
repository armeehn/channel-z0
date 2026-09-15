#!/usr/bin/env python3
"""Tests for the GRAMOPHONE sides. Plain unittest: LXC 111 has no pytest.

Every check carries a negative control. An agent cannot hear or see the
output, so the claims are measured: the rights clocks refuse what they
should, the envelope parser fails loudly when ffmpeg said nothing, and a
loud side draws a different disc from a silent one."""
import hashlib
import json
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
    "id": "0", "title": "Test side", "performer": "Nobody",
    "persons": ["Nobody, 1890-1940"], "basis": "own", "year": 1930,
}


class Rights(unittest.TestCase):
    def test_death_year(self):
        self.assertEqual(gramo.death_year("Bolduc, Édouard, Mme, 1894-1941"), 1941)
        self.assertEqual(gramo.death_year("Desmarteaux, Alexandre, m. 1926"), 1926)
        self.assertEqual(gramo.death_year("Hartmann, Georges, d. 1900"), 1900)
        self.assertEqual(gramo.death_year("Lamberti, Augustin, 1832?-1893"), 1893)
        self.assertIsNone(gramo.death_year("Soucy, Isidore, 1899-"))
        self.assertIsNone(gramo.death_year("Déroulède, Paul, 1846-1914?"))
        self.assertIsNone(gramo.death_year("Anonymous"))

    def test_corporate_has_no_clock(self):
        self.assertTrue(gramo.is_corporate("Saint-Benoît-du-Lac (Abbey : Québec)"))
        self.assertTrue(gramo.is_corporate("Trio de la rue St. Timothée"))
        self.assertFalse(gramo.is_corporate("Isidore Soucy"))      # a person, undated
        self.assertFalse(gramo.is_corporate("Miro, Henri, 1879-1950"))

    def test_clear_both_clocks(self):
        v = gramo.clear(SIDE)
        self.assertEqual(v[gramo.Clock.RECORDING], "fixed 1930  <= 1964")
        self.assertEqual(v[gramo.Clock.WORK], "author d.1940  <= 1971")

    def test_refuses_late_recording(self):
        with self.assertRaises(gramo.RightsError) as cm:
            gramo.clear(dict(SIDE, year=1965))
        self.assertIs(cm.exception.clock, gramo.Clock.RECORDING)

    def test_undated_disc_falls_back_to_the_span(self):
        v = gramo.clear(dict(SIDE, year=None))
        self.assertEqual(v[gramo.Clock.RECORDING], "fixed 1900-1950  <= 1964")

    def test_refuses_late_death(self):
        # Andy De Jarlis d.1975: recording PD, his own compositions are not.
        with self.assertRaises(gramo.RightsError) as cm:
            gramo.clear(dict(SIDE, persons=["De Jarlis, Andy, 1914-1975"]))
        self.assertIs(cm.exception.clock, gramo.Clock.WORK)

    def test_refuses_missing_year(self):
        with self.assertRaises(gramo.RightsError):
            gramo.clear(dict(SIDE, persons=["Nobody, 1890-1940", "Someone"]))

    def test_refuses_unnamed_composer(self):
        # A dead tenor singing a song the record does not attribute: the work
        # clock cannot be read, however long ago the singer died.
        with self.assertRaises(gramo.RightsError) as cm:
            gramo.clear(dict(SIDE, basis=None))
        self.assertIs(cm.exception.clock, gramo.Clock.WORK)

    def test_named_work_reads_the_work_block(self):
        named = dict(SIDE, basis="named", persons=["Singer, 1900-1980"],
                     work={"composers": ["Adam, Adolphe, 1803-1856"],
                           "lyricists": ["Cappeau, Placide, 1808-1877"],
                           "source": "https://www.bac-lac.gc.ca/x"})
        self.assertEqual(gramo.status(named)[0], gramo.Status.CLEAR)
        self.assertEqual(gramo.clear(named)[gramo.Clock.WORK], "authors d.1856, d.1877  <= 1971")

        late = dict(named, work=dict(named["work"], lyricists=["Living, 1900-1990"]))
        self.assertEqual(gramo.status(late)[0], gramo.Status.HELD)
        undated = dict(named, work=dict(named["work"], lyricists=["Someone"]))
        self.assertEqual(gramo.status(undated)[0], gramo.Status.UNRESOLVED)
        silent = dict(named, work={"composers": [], "unresolved": "sources disagree"})
        st, err = gramo.status(silent)
        self.assertEqual(st, gramo.Status.UNRESOLVED)
        self.assertIn("sources disagree", str(err))
        nobody = dict(named, work={"composers": []})
        self.assertEqual(gramo.status(nobody)[0], gramo.Status.UNRESOLVED)

    def test_arranger_of_a_trad_tune_is_clocked(self):
        trad = dict(SIDE, basis="trad", work={"arrangers": ["Arr, Anne, 1880-1950"]})
        self.assertEqual(gramo.clear(trad)[gramo.Clock.WORK],
                         "traditional tune, arr. d.1950  <= 1971")
        late = dict(SIDE, basis="trad", work={"arrangers": ["Arr, Anne, 1900-1980"]})
        self.assertEqual(gramo.status(late)[0], gramo.Status.HELD)

    def test_late_recording_is_held_not_unresolved(self):
        self.assertEqual(gramo.status(dict(SIDE, year=1965))[0], gramo.Status.HELD)
        self.assertEqual(gramo.status(dict(SIDE, basis=None))[0], gramo.Status.UNRESOLVED)

    def test_anonymous_work_needs_no_author(self):
        chant = dict(SIDE, basis="chant", persons=["Saint-Benoît-du-Lac (Abbey : Québec)"])
        self.assertEqual(gramo.clear(chant)[gramo.Clock.WORK], "plainchant, no author")
        trad = dict(SIDE, basis="trad")
        self.assertEqual(gramo.clear(trad)[gramo.Clock.WORK], "traditional tune, no author")

    def test_basis_from_the_record(self):
        self.assertEqual(gramo.basis_for({"repertoire": "latin-chant (Quebec abbey)",
                                          "title": "Agnus Dei", "artist": "x"}), "chant")
        self.assertEqual(gramo.basis_for({"repertoire": "salon/concert", "title": "Reel des matelots",
                                          "artist": "Boulay, A. J., 1883-1948"}), "trad")
        self.assertEqual(gramo.basis_for({"repertoire": "francophone song/monologue",
                                          "title": "Les cinq jumelles",
                                          "artist": "Bolduc, Édouard, Mme, 1894-1941"}), "own")
        # The tenor and the pianist: performer named, composer not.
        self.assertIsNone(gramo.basis_for({"repertoire": "salon/concert", "title": "Je t'aime",
                                           "artist": "Saucier, Joseph, 1869-1941"}))

    def test_shipped_sides(self):
        sides = gramo.load_sides()
        placed = gramo.cleared(sides)
        self.assertGreater(len(placed), 0)
        self.assertLess(len(placed), len(sides), "the manifest must carry the rejects too")
        stems = set()
        for side in sides:
            self.assertTrue(side["url"].startswith("https://www.collectionscanada.gc.ca/"),
                            "the feed's own host does not resolve; use .gc.ca")
            self.assertEqual(side.get("status"), gramo.status(side)[0].value,
                             "%s: stamped status is stale; run gramo.py stamp" % side["id"])
            work = side.get("work") or {}
            if side["basis"] == "named" or work:
                self.assertTrue(work.get("source", "").startswith("https://"),
                                "%s: a researched work needs its source URL" % side["id"])
        for side, verdict in placed:
            gramo.panel_lines(side, verdict, 240)               # fits the panel
            stems.add(gramo.rel_path(side))
        self.assertEqual(len(stems), len(placed), "two sides would share a file")


class Manifest(unittest.TestCase):
    def test_display_name(self):
        self.assertEqual(gramo.display_name("Bolduc, Édouard, Mme, 1894-1941"), "La Bolduc")
        self.assertEqual(gramo.display_name("Soucy, Isidore, 1899-1963"), "Isidore Soucy")
        self.assertEqual(gramo.display_name("Boulay, A. J. (Arthur-Joseph), 1883-1948"), "A. J. Boulay")
        self.assertEqual(gramo.display_name("Crescent Trio"), "Crescent Trio")

    def test_stem_is_smb_safe(self):
        side = dict(SIDE, id="13119", performer="Joseph Allard",
                    title="Boules de neige : reel = Snowballs : reel")
        self.assertEqual(gramo.stem(side), "Joseph Allard - Boules de neige reel (1930) [lac-13119]")
        self.assertEqual(gramo.rel_path(side), "gramophone/chanson/" + gramo.stem(side) + ".mp4")

    def test_tex_rows(self):
        rows = gramo.tex_rows([SIDE, dict(SIDE, id="1", basis=None, title="A & B")])
        self.assertIn("CLEAR.", rows[0])
        self.assertIn("UNRESOLVED (s.6)", rows[1])
        named = dict(SIDE, basis="named", work={"composers": ["Adam, Adolphe, 1803-1856"],
                                                "source": "https://x"})
        self.assertIn("composer Adam, Adolphe, 1803-1856. s.23", gramo.tex_rows([named])[0])
        self.assertIn("A \\& B", rows[1])

    def test_build_selects_what_check_prints(self):
        # build.sh selects sides by the status word `check` prints; a rename
        # of that word once made it build zero sides and exit clean.
        out = subprocess.run([sys.executable, gramo.__file__, "check", "14408"],
                             capture_output=True, text=True, check=True).stdout
        word = out.split()[1]
        self.assertEqual(word, gramo.Status.CLEAR.value)
        build = open(os.path.join(os.path.dirname(gramo.__file__), "build.sh")).read()
        self.assertIn('$2=="%s"' % word, build)
        self.assertIn("^$id *%s" % word, build)


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

    def test_frame_is_a_lunch_card(self):
        # 4:3, so the card sits inside the gutter rails like the prairie sides.
        env = [-30.0] * gramo.FPS
        img = next(gramo.frames(SIDE, env, 1.0, self.fonts))
        self.assertEqual(img.size, (640, 480))
        self.assertEqual(img.mode, "RGB")

    def test_stylus_travels_rim_to_label(self):
        self.assertEqual(gramo.stylus_radius(0, 10), gramo.R_OUT)
        self.assertEqual(gramo.stylus_radius(10, 10), gramo.R_LABEL)
        self.assertEqual(gramo.stylus_radius(99, 10), gramo.R_LABEL)

    def test_panel_refuses_overlong_line(self):
        side = dict(SIDE, performer="x" * (gramo.COLS + 1))
        with self.assertRaises(gramo.LayoutError):
            gramo.panel_lines(side, gramo.clear(side), 60)

    def test_panel_refuses_overflow(self):
        # Four ensembles' worth of credits wraps past the clock and the VU.
        side = dict(SIDE, persons=["Nobody %d, 1890-1940" % k for k in range(24)])
        with self.assertRaises(gramo.LayoutError):
            gramo.panel_static(side, gramo.clear(side), 60, self.fonts)

    def test_vu_needle_sweeps(self):
        lo, hi = gramo.vu_angle(-40.0), gramo.vu_angle(0.0)
        self.assertGreater(lo, hi)                       # left to right
        self.assertEqual(gramo.vu_angle(-200.0), lo)     # clamped


if __name__ == "__main__":
    unittest.main(verbosity=1)
