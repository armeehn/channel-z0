# L-system intervals — the picture, and the program that made it

A second family of station intervals, alongside the Glitchsheet ones in
[intervals.md](intervals.md). Each clip is a **Lindenmayer system**: a handful
of rewriting rules, expanded, read back as turtle orders, and drawn — with its
own source code set beside it on screen.

The two halves of the frame cannot disagree, because they are the same file.

---

## One file, three jobs

Every specimen in `tools/z0-lsys/specimens/` is a self-contained JavaScript
file, used three times over:

| Used by | As | What it does |
|---|---|---|
| `qjs lsys-emit.js` | an ES module | walks the turtle; the renderer draws those strokes as the ink |
| `ffedit -f mv -s <file>` | an FFglitch script | replaces **every motion vector** with the heading of the branch crossing that macroblock |
| the renderer | text | prints it, verbatim, into the panel on the right |

So the code on screen is not an illustration of the algorithm. It is the
algorithm — the same bytes that `ffedit` ran, with the sha1 shown in the
footer alongside the exact command and its `-sp` payload.

**Nothing is hidden behind an import.** That is the whole claim, and it is why
the machinery is duplicated into all eight files rather than shared. The files
are therefore **output**: edit `specimen.template.js` or the `SYSTEMS` table in
`make-specimens.py` and regenerate. Hand-edits to `specimens/*.js` are lost.

```sh
tools/z0-lsys/make-specimens.py
```

The generator enforces a **52-column limit** and refuses to write anything if a
single line is over it. That is not style: the panel is 406 px wide and the
listing is set at 12 px, so a longer line is a line nobody can read. It checks
every file before writing any of them — validating on the way out once left the
over-wide file on disk next to the complaint about it, and the render used it
regardless.

---

## What is on screen

```
+---------------------------+-------------------------+
|                           | CH 0  STATION INTERVAL  |
|   448 x 480               | FERN                    |
|   the L-system, drawn      | six rewrites of one     |
|   stroke by stroke and     | ------------------------|
|   smeared by its own       | export const SYS = {    |
|   motion vectors           |   axiom: "X",           |
|                           |   rules: { X: "F+[[X..  |
|                           |   ...                   |
|                           | ------------------------|
|                           | F+[[X]-X]-F[-FX]+X ...  |  <- the live string
|                           | $ ffedit -f mv -s ...   |
|                           | gen 6  25,159 symbols   |
+---------------------------+-------------------------+
        854 x 480, the channel's own frame — nothing is pillarboxed
```

The clip has an arc, because an interval is cut at an arbitrary boundary and
has to be worth joining at any point:

| Share of clip | What happens |
|---|---|
| 0–3% | the specimen card: name, rules, an empty frame |
| 3–85% | the turtle draws, and a **wave of motion travels the branches in the order they were drawn** |
| 85–100% | the drawing is finished and drifts, smearing along its own tangents |

The source pages through itself **exactly once per clip**, however long the
file is: the renderer takes the fewest pages that hold it and then spreads the
lines evenly, so the last page is not two lines and eight seconds of empty
panel.

The strip under the listing is the real expanded L-string, windowed at the
turtle's current position — 147 lines of program above, and the 25,159 symbols
it produced running past below.

---

## The specimens

| Slug | Name | Rules | Angle | Gens | Push | Phosphor |
|---|---|---|---|---|---|---|
| `fern` | FERN | `X→F+[[X]-X]-F[-FX]+X`, `F→FF` | 25° | 6 | 30 | amber |
| `dragon` | DRAGON | `X→X+YF+`, `Y→-FX-Y` | 90° | 12 | 15 | green |
| `hilbert` | HILBERT | `A→+BF-AFA-FB+`, `B→-AF+BFB+FA-` | 90° | 6 | 10 | bone |
| `koch` | KOCH ISLAND | `F→F+F-F-FF+F+F-F` | 90° | 3 | 16 | red |
| `sierpinski` | SIERPINSKI | `F→F-G+F+G-F`, `G→GG` | 120° | 6 | 30 | amber |
| `levy` | LEVY C | `F→+F--F+` | 45° | 14 | 15 | green |
| `bush` | BUSH | `F→FF-[-F+F+F]+[+F-F-F]` | 22.5° | 5 | 28 | amber |
| `crystal` | CRYSTAL | `F→FF+F+F+F+FF` | 90° | 4 | 22 | bone |

`push` is per specimen and lives in `SYS`, on screen, because it has to be:
**a space-filling curve fills every macroblock, so the shove that animates a
fern turns a Hilbert curve to mud.** Hilbert takes a third of the fern's.

The palette is the phosphor set from [BRAND.md](../BRAND.md) — amber `#ffb000`,
phosphor red `#ff2d2d`, green `#33ff66`, bone `#cfcabc` on `#0d0d0d`. An
interval represents the broadcast, so it gets the CRT treatment, not the
Riposte brand.

---

## The pipeline — one host, unlike the Glitchsheet intervals

```
LXC 111 (claude)
  qjs      -> the turtle, as geometry
  PIL      -> the ink, frame by frame, over a pipe
  ffgac    -> MPEG-2 carrier          +nopimb +forcemv, one GOP
  ffedit   -> the same specimen file, over the motion vectors
  ffgac    -> decode
  PIL      -> the source panel beside it
  ffmpeg   -> H.264 854x480, silent stereo AAC
```

```sh
pct exec 111 -- su - user -c \
  'cd ~/channel-z0/tools/z0-lsys && python3 z0-lsys-render.py --out-dir /tmp/z0lsys/out'
```

Eight 55-second clips in about **40 seconds**, all told.

`tools/z0-generative.py` needs three hosts because Glitchsheet's engine and
numpy live in LXC 114, which has no ffmpeg at all. Nothing here needs either:
LXC 111 has `ffgac`, `ffedit` and `qjs` under `/opt/ffglitch` **and** a real
ffmpeg with libx264. (numpy in LXC 111 is in fact broken — built against a
newer glibc than the container has — so PIL does all the raster work.)

---

## Why the picture moves at all

The carrier is a **still** as far as the encoder is concerned. New strokes
appear, so those macroblocks get a residual; everything already drawn is
predicted from the previous frame with a zero residual. A block with no
residual is *whatever its motion vector fetched* — and the motion vectors are
the L-system. So the decoder becomes the paint engine.

That only works because of the encode flags:

| Flag | Why |
|---|---|
| `+forcemv` | writes a vector for every macroblock even where the encoder wants none |
| `+nopimb` | keeps intra blocks out of P frames, so nothing scrubs itself clean |
| `-qscale:v 1`, `-g <all>`, `-sc_threshold max` | one I frame at the top; damage propagates for the whole clip |
| 448x480 | 28x30 **whole** macroblocks — a partial block column at the edge breaks the grid, and the grid is the aesthetic |

---

## Traps

* **A motion vector that fetches from outside the frame decodes as flat
  saturated green.** The specimens fade their field out over the last three
  macroblocks at every edge for that reason alone. It is in the code on
  screen, and it is not a taste decision.

* **`-sp` takes integers only.** ffedit's JSON parser rejects a float outright
  and then writes no output file at all, which reads exactly like a crash.
  Fractions travel percent-scaled and are divided inside the script.

* **Comparing the two bitstreams proves nothing.** ffedit re-codes a vector it
  was handed even when the value is unchanged, so a script that sets every
  vector to zero still writes a *different file* while the picture stands
  perfectly still. The render guards on the real thing instead: it decodes the
  untouched carrier alongside the glitched one and refuses a clip whose
  pictures differ by less than `--min-motion`. Same encoder, same quantiser,
  so with the vectors left alone the measure is exactly zero. `--trim 0` is
  the negative test, and it is refused.

* **Watching the glitched clip on its own says little more**, because the
  drawing is moving anyway — the turtle is still drawing it.

* Every clip is checked for length within a second of 55.0 s before it is
  installed, in the spirit of `tools/z0-weather.sh`.

---

## Getting them on air

The clips carry the `generative` tag in their `.nfo`, so they join the
existing interval pool and **need no schedule change**. Drop them in and let
the library refresh:

```sh
scp z0-lsys-*.mp4 z0-lsys-*.nfo root@10.0.1.222:/mnt/main-data/channelz0/generative/
```

**The NFO's tags replace the folder's tags**, so `<tag>generative</tag>` has to
be in the file — that is what the renderer writes, alongside `media`.

The library refreshes on `scanner.library_refresh_interval` (6 hours), so they
join the shuffle on their own. To have them sooner, scan the library from the
ErsatzTV UI. A **new** tag would need more — the pool is a `search:` key
answered by Lucene, and an unindexed tag silently yields an empty pool — but
`generative` already exists and is already indexed.

---

## Tuning

| Want | Change |
|---|---|
| A different system | `SYSTEMS` in `make-specimens.py`, then regenerate |
| Calmer or wilder | that specimen's `push` (it is per specimen for a reason) |
| Everything calmer | `--trim`, a global percentage over every `push` |
| More or less drift at the end | `--bloom` |
| A narrower travelling wave | `--win`, in % of the string |
| Longer clips | `--seconds`; the source still pages through exactly once |
