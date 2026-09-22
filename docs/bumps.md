# Bumps and house promos

Since 2026-09-15 an advert break on Channel Z0 is a bump, a house promo and,
sometimes, a vintage commercial. Bumps are 8–15 s of generated picture with a
station line on the end. Promos are the station's own adverts: one spot per
product on the shop, one per Riposte programme. Both are drawn from formulas
and data, never from footage, so the pool grows without clearing rights.

## Where breaks happen

| Place | Mechanism | Rundown |
|---|---|---|
| Around every scheduled programme | `feature_break` pre/post-roll | ident, math bump, merch promo, commercial |
| Inside `short_subjects` | `advert_break` | glitch bump, projects promo, commercial |
| CARTOON BLOCK / CARNIVAL | playlist `Cartoon Hour` | break after every 2 cartoons |
| CARTOON BLOCK II | playlist `Cartoon Block II` | break after every 2 cartoons |
| SHORT SUBJECTS strands | playlist `Short Subjects Hour` | break after 2, then after 1 |
| PRELINGER THEATRE | playlist `Prelinger Theatre Hour` | break after every film |

`pad_until` never emits pre-roll or post-roll, so the padded strands pad from
a playlist whose rundown carries the breaks. Every item in a playlist must
name a different source, which is why there are three bump collections and
two promo collections rather than one of each.

## Files

```
tools/z0_bumps.py        engine + CLI: 26 genres, 8 treatments, cards, audio
tools/z0-promos.py       merch + projects spots; imports z0_bumps
tools/z0-promos-extra.yml      public projects api.hq does not list yet
lists/z0-lists.yml       Z0 Bumps {Math,Glitch,L-System}, Z0 Promos {Merch,Projects}
                         + the four rundown playlists (matched on PATH)
playout/_content.yml     bumps_*, promos_*, pl_short_subjects, pl_prelinger,
                         pl_cartoon_block_ii
playout/_sequences.yml   feature_break, advert_break
```

Media on the node:

```
/mnt/main-data/channelz0/bumps/{math,glitch,lsys}/z0-bump-<family>-<genre>-<seed>.mp4 + .nfo
/mnt/main-data/channelz0/promos/{merch,projects}/z0-promo-<kind>-<handle>.mp4 + .nfo
```

## Families

- **math** — a formula drawn clean: Clifford and de Jong attractors,
  Gray–Scott reaction-diffusion, Chladni plates, Fourier epicycles (the Z and
  0 of the wordmark as sums of circles), flow fields, harmonographs,
  elementary automata, Life, moiré, Julia sets, phyllotaxis, Voronoi, times
  tables on a circle, double pendulums, Lorenz, Truchet tiles, the wave
  equation, spirographs, Ulam's spiral, hex grids, a Mandelbrot zoom, the
  abelian sandpile, boids, metaballs, diffusion-limited aggregation.
- **glitch** — a math genre through a treatment: pixel sort, analogue
  feedback, slit-scan, VHS tracking, block bleed (the datamosh look without
  breaking a bitstream), bitcrush, wobble, vertical roll. Bursty envelopes,
  and the audio breaks with the picture.
- **lsys** — L-systems grown stroke by stroke. Never glitched, by
  instruction. The ffedit L-system intervals in `tools/z0-lsys/` are a
  different thing and stay as they are.

Every clip carries a one-line caption under the picture (what the formula
is) and an end card in the ident's grammar: ink field, bone mono,
`CHANNEL Z0` with the red Z0. `card` cuts hard to the field; `band` keeps
the art running under it.

The card carries **no copy**. The wordmark is the whole card, standing rule
since 2026-09-22. `--copy tagline` brings back a line from `TAGLINES` for a
one-off batch, and `--tagline "..."` sets one by hand; neither is what the
timer renders.

## Rendering

Needs numpy, PIL, an ffmpeg with libx264. That is forge, not LXC 111. From x:

```
z0 bumps render 24            # 8 math, 8 glitch, 8 lsys on forge, new seeds
z0 bumps ship                 # forge → x → node, scan, collections refreshed
z0 promos refresh             # store + api.hq → forge → node; folder is a mirror
z0 pool                       # what the node holds per family
```

`z0-promos.timer` refreshes the promos weekly; `z0-bumps.timer` tops up the
bump pool monthly. Both are on x. A clip is deterministic in (genre, seed);
`z0_bumps.py still --genre G --seed S` gives one frame for a look.

## Adding a genre

Subclass `Genre` in `tools/z0_bumps.py`, set `NAME`, `FACT`, `PALETTE`,
implement `frame(i, t, u)` returning an (H, W, 3) uint8 array, add the class
to `GENRES`. Raster genres compute at half or quarter size and call `up()`;
vector genres draw with PIL at 2x and call `down()`. Nothing else changes.

Standing constraints: no crosshairs or reticles, nothing that reads as
violence, no full-width strip at the bottom edge (the rails own the gutters),
no footage, no AI-generated picture.

## Shipping

Path-matched collections are filled by `z0-lists.py` from `MediaItem` rows,
so a new folder needs, in order: files on the node, a library scan
(`POST /api/libraries/4/scan`, the UI button), then `z0-lists.py` from the
node's tool copy. No Lucene rebuild: nothing here queries by a new tag. The
schedule change reaches air through the usual path — merge, `z0-tools-sync`,
the 05:05 day-align repairs at the 06:00 seam. Copy `_content.yml` and
`_sequences.yml` into `/mnt/solid-state/ersatztv/` before that runs, or the
regenerated week names keys the deployed fragments do not have.
