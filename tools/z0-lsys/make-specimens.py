#!/usr/bin/env python3
"""Generate the L-system specimen files from one template.

Each specimen is a SELF-CONTAINED JavaScript file, and that is the whole
point: it is the program `qjs` runs to draw the ink, the program `ffedit`
runs to bend the motion vectors, AND the text shown on screen beside the
picture it made. Nothing it does is hidden behind an import.

Being self-contained means the machinery is duplicated eight times, so the
files are OUTPUT, not source. Edit `specimen.template.js` (or the SYSTEMS
table below) and regenerate; hand-edits to `specimens/*.js` are lost.

    tools/z0-lsys/make-specimens.py

The 52-column limit is not style: the code panel is 406 px wide and the
listing is set at 12 px, so a longer line is a line the viewer cannot read.
It is asserted rather than wrapped, because silently truncated source would
break the one claim this whole piece makes.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = 52

# heading is in degrees, clockwise from east, because the frame's y axis
# points down: -90 is straight up the screen.
SYSTEMS = [
    dict(slug="fern", push=30, name="FERN", ink="#ffb000",
         caption="six rewrites of a single letter",
         note=["Barnsley's fern. X is never drawn -- it is",
               "only a promise to grow something later."],
         axiom="X", rules={"X": "F+[[X]-X]-F[-FX]+X", "F": "FF"},
         angle=25, gens=6, heading=-90),
    dict(slug="dragon", push=15, name="DRAGON", ink="#33ff66",
         caption="a strip of paper folded twelve times",
         note=["The Heighway dragon: fold a strip in half",
               "twelve times, then open every crease to 90."],
         axiom="FX", rules={"X": "X+YF+", "Y": "-FX-Y"},
         angle=90, gens=12, heading=0),
    dict(slug="hilbert", push=10, name="HILBERT", ink="#cfcabc",
         caption="one line that reaches every square",
         note=["A space-filling curve. Given enough",
               "generations it passes through every point."],
         axiom="A", rules={"A": "+BF-AFA-FB+", "B": "-AF+BFB+FA-"},
         angle=90, gens=6, heading=0),
    dict(slug="koch", push=16, name="KOCH ISLAND", ink="#ff2d2d",
         caption="a coastline of finite area",
         note=["Every edge grows a smaller copy of the",
               "whole coast. The perimeter never settles."],
         axiom="F+F+F+F", rules={"F": "F+F-F-FF+F+F-F"},
         angle=90, gens=3, heading=0),
    dict(slug="sierpinski", push=30, name="SIERPINSKI", ink="#ffb000",
         caption="a triangle that eats its own middle",
         note=["Two letters, both drawing, one doubling.",
               "The holes are what is left over."],
         axiom="F-G-G", rules={"F": "F-G+F+G-F", "G": "GG"},
         angle=120, gens=6, heading=0),
    dict(slug="levy", push=15, name="LEVY C", ink="#33ff66",
         caption="one rule, fourteen times over",
         note=["The whole curve is +F--F+ applied to",
               "itself. Nothing else is specified."],
         axiom="F", rules={"F": "+F--F+"},
         angle=45, gens=14, heading=0),
    dict(slug="bush", push=28, name="BUSH", ink="#ffb000",
         caption="a weed grown from one stem",
         note=["Brackets are a stack: the turtle remembers",
               "where a branch began and returns to it."],
         axiom="F", rules={"F": "FF-[-F+F+F]+[+F-F-F]"},
         angle=22.5, gens=5, heading=-90),
    dict(slug="crystal", push=22, name="CRYSTAL", ink="#cfcabc",
         caption="a snowflake cut with right angles",
         note=["The quadratic Koch island. Right angles",
               "only, and it still comes out as frost."],
         axiom="F+F+F+F", rules={"F": "FF+F+F+F+FF"},
         angle=90, gens=4, heading=0),
    dict(slug="peano", push=10, name="PEANO", ink="#ffb000",
         caption="one line that fills a square",
         note=["Nine copies of itself per generation,",
               "and it reaches every point of the square."],
         axiom="F", rules={"F": "F+F-F-F-F+F+F+F-F"},
         angle=90, gens=4, heading=0),
    dict(slug="gosper", push=14, name="GOSPER", ink="#33ff66",
         caption="the flowsnake, a hexagon that tiles",
         note=["Two letters, both drawing, at sixty",
               "degrees. The curve tiles the plane."],
         axiom="F", rules={"F": "F-G--G+F++FF+G-",
                           "G": "+F-GG--G-F++F+G"},
         angle=60, gens=4, heading=0),
    dict(slug="moore", push=10, name="MOORE", ink="#cfcabc",
         caption="a closed curve that fills its square",
         note=["Hilbert's curve joined end to end, so",
               "the turtle finishes where it began."],
         axiom="LFL+F+LFL", rules={"L": "-RF+LFL+FR-",
                                   "R": "+LF-RFR-FL+"},
         angle=90, gens=5, heading=0),
    dict(slug="tree", push=26, name="TREE", ink="#ffb000",
         caption="a stem that keeps three ways open",
         note=["Every segment sprouts left, right and",
               "straight on, and the brackets remember."],
         axiom="F", rules={"F": "F[+F]F[-F][F]"},
         angle=20, gens=5, heading=-90),
    dict(slug="snowflake", push=18, name="SNOWFLAKE", ink="#ff2d2d",
         caption="the Koch snowflake, at sixty degrees",
         note=["Three Koch curves nose to tail. The",
               "area settles; the edge never does."],
         axiom="F++F++F", rules={"F": "F-F++F-F"},
         angle=60, gens=5, heading=0),
    dict(slug="terdragon", push=16, name="TERDRAGON", ink="#33ff66",
         caption="one rule, three ways, nine times",
         note=["F becomes F+F-F at a hundred and",
               "twenty degrees. Nothing else is said."],
         axiom="F", rules={"F": "F+F-F"},
         angle=120, gens=9, heading=0),
    dict(slug="seaweed", push=28, name="SEAWEED", ink="#ffb000",
         caption="a weed that leans as it grows",
         note=["Two bracketed pairs per segment, at an",
               "angle just tight enough to curl."],
         axiom="F", rules={"F": "FF-[-F+F]+[+F-F]"},
         angle=22, gens=5, heading=-90),
    dict(slug="board", push=18, name="BOARD", ink="#cfcabc",
         caption="a square that grows square teeth",
         note=["Right angles only, eight to a side,",
               "and the outline never repeats itself."],
         axiom="F+F+F+F", rules={"F": "FF+F+F+F+F+F-F"},
         angle=90, gens=3, heading=0),
]


def rules_lines(rules):
    """Render the rule table, one production per line where it fits."""
    items = ['%s: "%s"' % (k, v) for k, v in rules.items()]
    one = "  rules:   { " + ", ".join(items) + " },"
    if len(one) <= COLS:
        return [one]
    out = ["  rules:   {"]
    for it in items:
        out.append("    " + it + ",")
    out.append("  },")
    return out


def header(sys_def, index):
    n = sys_def
    L = []
    L.append("// %s  ·  CH 0 L-SYSTEM SPECIMEN %02d"
             % (n["name"], index))
    for line in n["note"]:
        L.append("// " + line)
    L.append("//")
    L.append("// This file is the whole program. qjs runs it")
    L.append("// to draw the ink; ffedit runs it again to")
    L.append("// bend the motion vectors that smear it. You")
    L.append("// are reading what made the picture beside it.")
    L.append("")
    L.append("export const SYS = {")
    L.append('  name:    "%s",' % n["name"])
    L.append('  caption: "%s",' % n["caption"])
    L.append('  ink:     "%s",' % n["ink"])
    L.append('  axiom:   "%s",' % n["axiom"])
    L += rules_lines(n["rules"])
    L.append("  angle:   %-5s// degrees per + or -"
             % (str(n["angle"]) + ","))
    L.append("  gens:    %-5s// rewrites" % ("%d," % n["gens"]))
    L.append("  heading: %-5s// where the turtle starts"
             % ("%d," % n["heading"]))
    L.append("  push:    %-5s// how hard ffedit shoves it"
             % ("%d," % n["push"]))
    L.append("};")
    return "\n".join(L)


def main():
    with open(os.path.join(HERE, "specimen.template.js")) as f:
        template = f.read()
    outdir = os.path.join(HERE, "specimens")
    os.makedirs(outdir, exist_ok=True)
    # Check every specimen BEFORE writing any of them. Validating on the way
    # out left the over-wide file on disk next to the complaint about it, and
    # the render picked it up regardless -- a guard that reports a problem
    # after shipping it is not a guard.
    built, bad = [], 0
    for i, s in enumerate(SYSTEMS, 1):
        text = template.replace("__HEADER__", header(s, i))
        for n, line in enumerate(text.splitlines(), 1):
            if len(line) > COLS:
                print("%s:%d is %d columns: %s"
                      % (s["slug"], n, len(line), line), file=sys.stderr)
                bad += 1
        built.append((s, text))
    if bad:
        print("\n%d line(s) over %d columns -- nothing written, fix the "
              "template" % (bad, COLS), file=sys.stderr)
        return 1
    for s, text in built:
        with open(os.path.join(outdir, s["slug"] + ".js"), "w") as f:
            f.write(text)
        print("%-12s %3d lines  %s" % (s["slug"], len(text.splitlines()),
                                       s["caption"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
