# GRAMOPHONE listening intervals

A fourth interval family, alongside the Glitchsheet pieces (`intervals`), the
L-systems (`lsystems`) and the anime interstitials. One Library and Archives
Canada *Virtual Gramophone* 78 side, played whole, with the picture generated
from the sound. Tools in `tools/z0-gramo/`.

## The picture

The record's groove is the side's own loudness map, cut the way a lathe cuts
it: rim first, one turn per 1/78 minute, label last. ffmpeg measures one RMS
figure per video frame (`asetnsamples=1600` + `astats`, the recipe from
`z0-music-viz.py`; numpy does not import in LXC 111, so ffmpeg is the DSP)
and Python lays those figures down in polar coordinates. The disc turns at
78 rpm. A tonearm tracks playback inward, and the groove behind the stylus is
station marigold, the groove ahead of it grey.

The panel is the L-system panel, measured: art viewport x 0..447, panel
462..840, rules at y 10, 68 and 408, 52 columns of 12 px mono. It carries the
title, the credited people with dates, the LAC object id, both copyright
clocks with their verdicts, and a VU needle. The bottom strip names the
renderer and its sha1, as the L-systems name their source.

No crosshair: the spindle is a plain hole and the VU scale is an open arc. No
subtitle element: the text is in the picture. The clip is 854x480 native and
fills the frame, because the gutter rails go down for intervals.

## Rights: two clocks, both must run out

    s.23  sound recording   fixed <= 1964        permanently PD (2015 ext. non-retroactive)
    s.6   musical work      author d. <= 1971    permanently PD (2022 ext. non-retroactive)

The Virtual Gramophone digitised discs cut 1900-1950, so every side clears
the first clock by construction. The second is proven per credited person
from the feed's own `Surname, Given, 1894-1941` string. `gramo.clear()`
refuses a person with no death year or one after 1971; it never guesses.
The first side is La Bolduc, who wrote her own songs, so performer and
composer are one person.

`sides.json` is the manifest: id, feed title, credited persons, byte count
(the fetch is verified against it, because archive hosts answer 5xx with an
HTML body that ffprobe will call an mp3), and `why_clear` in prose. New sides
come from `/root/z0/content/canada-round3-stage.json` on x.

## Build

    tools/z0-gramo/build.sh 14397 z0-gramo-00     # -> /var/tmp/z0-gramo/

Tests first, then the rights check, fetch, envelope, render, and an ffprobe
gate: h264 854x480 30 fps yuv420p, AAC 48 kHz stereo, <= 3000 kbps. About a
minute per side in LXC 111. Deterministic: no clock, no seed.

## Staging and air

The clip is staged in `/mnt/main-data/channelz0/generative/` on vile with an
NFO whose tags are `media` + `gramophone` and NOT `generative`. The NFO
replaces the folder tags, so the file sits in the interval directory without
joining the interval pool. Nothing airs until the schedule names it.

To put it on air:

1. `tag:gramophone` is a NEW tag. Rebuild the search index (`rm -rf
   /config/search-index` + restart, off-hours); a rescan alone leaves the
   pool empty and an empty pool is skipped in silence.
2. Add a `gramophone` search key to `playout/_content.yml`
   (`type:other_video AND tag:gramophone`, `order: shuffle`).
3. Give it a junction: a whole side needs the 4:00 interval that the
   two-hour blocks book, or its own LISTENING INTERVAL slot. `trim: true`
   would cut the song; prefer `count: 1` at a 4:00 junction.
4. Regenerate with `z0-build-schedule.py`, then `z0-day-align.py --redeploy`
   on vile.
