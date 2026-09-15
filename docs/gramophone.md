# GRAMOPHONE sides in LUNCH LOOPS

Library and Archives Canada's *Virtual Gramophone* 78s (1900-1950), played
whole in the noon music block, with the picture generated from the sound.
Tools in `tools/z0-gramo/`; the manifest `sides.json` is the rights record;
the docs table is in `docs/programming-library.tex`.

Two pools, two days: `Z0 Gramophone Songs` (La Bolduc, the Saint-Benoît-du-Lac
chant) sits in Wednesday's SONGS AND CHORUSES, `Z0 Gramophone Reels` (Soucy,
Allard, Montmarquette) in Friday's POLKA PARTY. Nothing else in the week
draws on them: the sides are not tagged `canada`, so `Z0 Prairie Music`, the
Neighbourhood Desk and Canada Night are unchanged. The schedule file does not
change either; the two playlists gain one item each in the database.

## The picture

The record's groove is the side's own loudness map, cut the way a lathe cuts
it: rim first, one turn per 1/78 minute, label last. ffmpeg measures one RMS
figure per video frame (`asetnsamples=1600` + `astats`, the recipe from
`z0-music-viz.py`; numpy does not import in LXC 111, so ffmpeg is the DSP)
and Python lays those figures down in polar coordinates. The disc turns at
78 rpm. A tonearm tracks playback inward, and the groove behind the stylus is
station marigold, the groove ahead of it grey.

The card is **640x480, 4:3**, like every other LUNCH LOOPS card. The block
airs with the gutter rails up, and a 16:9 item puts its edges under the rails
(`docs/intervals.tex`), so the panel is the L-system panel's proportions at
4:3: 40 columns of 12 px mono, title, performer, credited people with dates,
the LAC object id, both clocks with their verdicts, a VU needle and a clock.
No crosshair, no subtitle element: the text is in the picture.

## Rights: two clocks, both must run out

    s.23  sound recording   fixed <= 1964        permanently PD (2015 ext. non-retroactive)
    s.6   musical work      author d. <= 1971    permanently PD (2022 ext. non-retroactive)

The recording year is the disc's own ID3 `date` as LAC stamped it (the
collection span 1900-1950 is the fallback for an undated file). The work
clock is the trap: the feeds credit *performers*, and a public-domain
recording of a song by someone still in copyright is still an infringement.
`gramo.clear()` therefore reads the work clock only where the record itself
supports it, and refuses the rest:

| `basis` | who the record proves the author is | sides |
|---|---|---|
| `own` | the credited performer wrote the material (La Bolduc) | every credit d. <= 1971 |
| `trad` | a reel, gigue or quadrille: traditional, no author | any credit dated is <= 1971 |
| `chant` | plainchant from the abbey: no author | corporate credit, no clock |
| none | a tenor, a pianist, a salon orchestra performing an unnamed composer | **REVIEW** |

The REVIEW pile is the bulk of round 3 (Saucier, Éva Gauthier, Albani,
Dufault, Eckstein, Miro's Band): singers dead for eighty years performing
works the record does not attribute. Most are almost certainly clear and
none can be proven from the feed. Naming the composers per side is the
cheapest way to grow the pool, and it is a research task, not a build step.

`gramo.py check` prints the verdict per side and the counts per clock.
Corporate credits (a trio, a band, the abbey) have no personal clock; an
undated *person* is a refusal, never a guess.

## Build

    tools/z0-gramo/build.sh              # every side both clocks clear
    tools/z0-gramo/build.sh 14397 15964  # just these

Tests, then per side: rights, fetch (verified against the manifest's byte
count, because archive hosts answer 5xx with an HTML body that ffprobe will
call an mp3), envelope, render, and an ffprobe gate: h264 640x480 30 fps
yuv420p, AAC 48 kHz stereo, <= 3000 kbps. Then `z0-video-tail.sh scan` over
the output: the picture must run at least as long as the sound, or the side
airs as seconds of audio over no frames and the tower drifts by exactly that.
About 30 s per side, `$JOBS` at a time. Render on forge (`ml350p run`), not on
x or LXC 111: 94 sides at 4 jobs put x at load 48. forge has Pillow and ffmpeg
but no Liberation fonts; copy them from 111 and point `GRAMO_FONT_DIR` at
them. Deterministic: no clock, no seed. Output under
`$GRAMO_WORK/out/gramophone/<basis>/`.

## Into the library

Files go to `/media/gramophone/<chanson|reel|chant>/` with the stem
`Performer - Title (Year) [lac-ID]`; the folder is the tag, and the LAC id
in the stem is how `z0-nfo.py` finds the side in the manifest and writes the
sidecar (title, year, genre Music, studio LAC, both verdicts in the plot).
Run it with `--inventory` over the new files only, never `--scan-fs` over the
whole root. Then a library scan (`POST /api/libraries/4/scan`); on 26.7.1
the scan indexed the new tags without a restart (2026-09-15: `tag:gramophone`
answered 95 on the search page ten minutes after the scan). Prove it before
trusting it: the search page is the live Lucene index and `--check` is SQL,
and they can disagree. `z0-lists.py --check --dry-run` first, then apply.

`gramo.py select STAGE.json SRC_DIR OUT.json` rebuilds the manifest from
`/root/z0/content/canada-round3-stage.json` on x and the fetched mp3s; it is
committed, so nobody needs to.
