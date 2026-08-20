# LUNCH LOOPS music cards and the audio visualiser

The 73 items in `Music Loops` are audio records, not films. Each one is a
**still card muxed against a stream-copied audio track** — the picture is
generated, the sound is the original transfer and is never re-encoded.

This document covers how a card is built, how the visualiser drives it from the
track's own spectrum, and the several ways this pipeline has silently produced a
plausible-looking wrong result.

- Source audio: `/media/.z0music/<stem>.mp3` (73 prairie Ukrainian-Canadian 78s,
  archive.org `ukrainiancanadianvinyl`, CC PD Mark 1.0)
- On-air items: `/media/music/<stem>.mp4`, 640x480, pillarboxed into the
  channel's 854x480 by the live transcode
- Card template: `playout/cards/music-card.html`
- Card renderer: `playout/cards/render-music.mjs` (Playwright)
- Visualiser: `tools/z0-music-viz.py`

`<stem>` is `Artist - Title`, and the renderer splits on the first ` - `.

## Why the audio is never touched

`-c:a copy`, everywhere, without exception. These are the only surviving digital
transfers of these records and they have already been through one lossy encode.
Re-running them through AAC to change a *picture* would be generation loss for
nothing. Every duration in the built schedule also depends on it: an item whose
length changes shifts every item after it in the block.

## The visualiser

`tools/z0-music-viz.py` replaces the still with an animation driven by the
track's own spectrum. Two stages, and the split matters:

1. **ffmpeg does the DSP.** N `bandpass` chains, each followed by
   `asetnsamples=n=1600` — exactly one 30fps video frame at 48kHz — and
   `astats=metadata=1:reset=1`, print one RMS figure per band per frame. One
   pass, in C, at ~85x realtime.
2. **Python does the drawing only.** It turns those numbers into bar heights and
   paints them into a raw RGBA buffer piped back into ffmpeg and `overlay`ed
   onto the card. The overlay carries **alpha**, which is what lets hard-edged
   bars sit on the card's radial gradient without reconstructing it.

Doing the FFT in Python instead would be minutes per track, and `numpy` is not
importable in LXC 111 (built against a newer glibc than the container has).
That is a constraint, not a preference.

### Shaping

Per band: a floor from that band's own 10th percentile, a **shared** span (the
median of all bands' p10..p98). Both halves are load-bearing. These transfers
roll off hard at both ends, so a globally-scaled bass band sits at zero for the
whole track and reads as a broken bar; but scaling each band independently makes
quiet bands as tall as loud ones and the display stops meaning anything.

Then fast attack / slow decay, plus a peak cap that falls slower still. A bar
that fell as fast as it rose reads as flicker, not as level.

### Styles

| style | region (640x480 space) | bands | notes |
|---|---|---|---|
| `tall` | x40 y268 560x172 | 20 | **shipped.** Lower half; card needs `data-viz="tall"` |
| `analyser` | x40 y408 560x60 | 20 | bottom band only; leaves the mid-right empty |
| `mark` | x481 y120 103x120 | 5 | the existing 5-bar mark, made real |

`mark` is the conservative one: the card already *draws* a five-bar equaliser as
a static mark, and this style replaces it at identical position, width, gap and
colours. `tall` was chosen because LUNCH LOOPS is a two-hour block and a corner
mark is small to watch for that long — and because removing the static mark
leaves a hole that only `tall` fills.

Colours are **hard tri-band segments**, cut at the same 36% / 64% stops as the
triband in the card CSS. The first version interpolated between the three brand
colours, which looks fine in a swatch and wrong on air: orange→teal passes
through olive, and the analyser came out a rainbow containing two colours the
station does not own.

## Traps

**`astats` prints at INFO level.** Running the measurement pass at `-v error`
produces an EMPTY result set and no error at all — every bar sits at zero and
the render "succeeds". If the bars do not move, check the verbosity first.

**The card's safe area moved on 2026-08-19 and the comment did not.**
`music-card.html` used to reserve "nothing below y 375, nothing right of x 420
above y 90" because the crawl was burnt over the bottom of the picture for the
whole block. PR #35 moved every on-air element into the 854x480 pillarbox rails
and deleted the bottom strip, so the picture is now unobscured and the whole
640x480 is available. `tall` uses the band the crawl used to occupy.

**`y=268` is measured, not chosen.** `render-music.mjs` shrinks the *title* to
fit but not the artist credit, and one of the 73 ("Freddy Chetyrbok with Johnny
& The Nite-Lighters — You Old Miser-Teah Stawray Kawlawbieyou") wraps that
credit onto a second line reaching y=257.5. An earlier y=250 cleared 72 cards
and clipped exactly one. Re-measure with `tools/z0-viz-extent.py` before moving
it, and note that a **full-width** scan is misleading: it reports y=367 for every
card, which is not text at all but the decorative `.corner.bl` bracket at
x 18–31, which the analyser never reaches.

**Temp files must go in a dot-DIRECTORY, never a dot-FILE.** ErsatzTV's scanner
skips dot-directories but happily indexes dot-files, so a temp written in place
as `.name.tmp.mp4` becomes a real media item and then a permanent `State=1`
ghost the moment it is renamed away. There is already one such row in the DB
from the original music render. The batch mode writes to
`<media>/.z0-convtmp/` and renames **onto the original path** — same path is an
update, not a rename, so no ghost row is created either.

**The work directory must be somewhere ffmpeg can see.** The measurement pass
writes its band files *with ffmpeg*, so when ffmpeg is containerised a host
`/tmp` path does not exist inside the container and the graph fails at init with
`Could not open .../band00.txt`. That reads like a permissions bug and is a
mount bug. The work dir therefore defaults to sitting beside the **output**,
which is writable and mounted by definition.

**No `-nostdin` on the encode.** `remux-music.sh` needs `-nostdin` because
ffmpeg would otherwise eat the shell loop's stdin. This encode is *fed* on
stdin — the raw RGBA overlay — so adding it there breaks the thing it protects.

**Do not render on vile.** vile has the media but no host ffmpeg, and driving a
containerised one is ~0.7x realtime because every raw frame crosses docker's
stdin proxy (~5 hours for 73 tracks). It is also the live playout box. Render in
LXC 111 — native ffmpeg, ~35s per track, ~45 min for all 73 — and move the
results over. `jellyfin-ffmpeg` cannot be lifted out of its container to fix
this; it needs system libs it does not bundle (`libopenmpt`).

## Rebuilding

Cards (LXC 111; ESM ignores `NODE_PATH`, so playwright is reached by symlinking
an existing `node_modules` next to the script):

```sh
node render-music.mjs --html music-card.html --viz=tall tracks.txt cards-tall
```

`--viz` suppresses the static mark; `--viz=tall` additionally drops the datum
strip to the very bottom. Omit it for the plain card.

Visualiser, one track or all of them:

```sh
python3 tools/z0-music-viz.py --src in.mp4 --card card.png --out out.mp4 \
                              --style tall [--limit 30]

python3 tools/z0-music-viz.py --batch --style tall \
        --list tracks.txt --media <root> --cards cards-tall --stage out-tall
```

`--stage` writes beside the originals instead of replacing them. Without it the
batch replaces in place, behind the duration guard.

## Cost

Measured on the channel's own output shape (854x480 @1600k), still card vs
animated, same encoder:

| source | live transcode |
|---|---|
| still card | ~33x realtime |
| `mark` | ~32x |
| `analyser` | ~27x |
| `tall` | ~22x |

The motion costs about 1.5x, and 22x realtime is nowhere near the constraint —
the hard cases on this channel are feature-length films, not cards. On-air file
size does grow (a still compresses to almost nothing): roughly 6 MB → 18 MB per
track, ~500 MB → ~1.3 GB for the pool.

## Rollback

The media tree is a ZFS dataset, so the pre-change state is a snapshot:

```sh
zfs rollback main-data/channelz0@pre-music-viz-20260820   # whole tree
```

Cards are reproducible from `music-card.html` at any time, and because the audio
is stream-copied the visualiser can be re-run against its own output without
generation loss on the sound.
