# On-air graphics — the bug, the weather desk, the crawl

Everything the channel puts on top of the picture. Four overlays and one
full-screen segment, all fed by one script on a timer; nothing here needs a
human once it is running.

| What | Where it comes from | Refresh |
|---|---|---|
| Channel bug (bottom right) | `branding/z0-bug.png`, made by `tools/make-bug.sh` | static |
| Weather card (top right) | `branding/z0-weather-card.png` | every 15 min |
| Crawl (bottom strip) | `branding/z0-crawl.ass` — forecast + the next programmes off the EPG | every 15 min |
| "NEXT ·" lower third | ErsatzTV's own guide, via `epg_entries` | per programme |
| The Weather Desk (full screen) | `weather/z0-local-forecast.mp4`, 2 min, 4×/day | hourly |

## Requires ErsatzTV ≥ 25.5.0

The graphics engine does not exist before that. On 25.2 the only overlay
available is a single static `ChannelWatermark` image — no text, no templating,
no crawl. The station runs **26.7.1** (`ghcr.io/ersatztv/legacy`).

Note the image moved: `ghcr.io/ersatztv/ersatztv` published no `-nvidia` build
after v25.2.0 and the line now lives at `ghcr.io/ersatztv/legacy`, one unified
image containing NVENC/VAAPI/QSV. `latest-nvidia` is not stale-but-current, it
is abandoned — pinning to it silently freezes you on June 2025.

## The weather desk

`tools/z0-weather.sh` fetches from **Open-Meteo** (no key, no account, so
nothing to rotate or expire), renders with the ffmpeg inside the ErsatzTV image,
and installs each asset atomically. `tools/z0-weather.py` does the fetching and
lays out the drawtext calls; the shell script drives ffmpeg.

```bash
tools/z0-weather.sh              # card + crawl + full-screen segment
tools/z0-weather.sh --card-only  # skip the segment (the slow part)
```

Location comes from the environment, defaulting to Kelowna, BC:

```bash
Z0_WX_LAT=49.88307 Z0_WX_LON=-119.48568 Z0_WX_CITY=KELOWNA Z0_WX_REGION=BC \
Z0_WX_TZ=America/Vancouver tools/z0-weather.sh
```

Two cron entries on the playout host, because the two halves have very
different costs — the card is seconds, the segment is most of a minute of
encoding that competes with the live transcode:

```
*/15 * * * *   tools/z0-weather.sh --card-only
5    * * * *   tools/z0-weather.sh
```

### A music bed

The segment ships with a quiet low drone. Drop any audio file into
`weather/bed/` and the next render uses it instead, looped and faded.
`Z0_SILENT=1` gives silence.

## Things that will bite you

**Write atomically or the overlay disappears for a whole programme.** ErsatzTV
opens these files while streaming. If it catches a half-written PNG,
`ImageElement` logs `Failed to initialize image element; will disable for this
content` and the graphic is gone until the next item — a silent, self-healing
failure that looks like a config mistake. Every install here is write-temp +
`rename(2)`.

**The segment's duration must never change.** ErsatzTV scheduled it from the
duration it saw at scan time. The script pins the output to
`Z0_WX_SEGMENT_SECS` and *refuses to install* a file of the wrong length, so the
library row stays valid and no rescan is ever needed. Keep one filename.

**Overlays refresh per programme, not per frame.** ErsatzTV re-reads an image or
text template when each item's ffmpeg process starts. During a 90-minute film
the card is whatever was on disk when that film began — which is why the card
carries an `AS OF` stamp instead of pretending to be live. The segmenter also
works ahead, so what is on air is a little behind the file on disk.

**Skia does not use fontconfig.** Text elements render through
SkiaSharp/RichTextKit, which ignores fontconfig entirely — `fc-list` and
`fc-match` finding a face inside the container proves nothing. Without
`include_fonts_from` the log says `Could not find font ...; using default` and
the lower third quietly renders in the wrong face. The two faces we need are
staged in `branding/fonts/`.

**`drawtext` is missing from some ErsatzTV images.** The old 25.2 `-nvidia`
image was built without it despite advertising freetype and fontconfig, so the
`make-*.sh` generators could not run against it. The 26.7.1 image has it.

**A crawl over a feature film is what makes people switch off.** The schedule
turns the crawl off around each feature and overnight during colour bars, and
turns the weather card off during the weather segment itself (it repeats the
segment and collides with its header).

## Wiring it into the schedule

`tools/wire-graphics.py` rewrites `playout/channel-z0.yml`, inserting the
`graphics_on`/`graphics_off` instructions and the four daily forecast slots
across all seven day blocks. It is idempotent — re-run it after editing the
schedule.

```bash
tools/wire-graphics.py playout/channel-z0.yml playout/channel-z0.yml
```

It also repairs two things that stop the playout building on 26.x, both of
which fail **silently**:

- **`search:` must be null.** This file used to write `search: Cartoons`, using
  the slot as a label. From 25.4 the schedule is validated against a JSON
  schema where `search` is `{"type": "null"}` and every object is
  `additionalProperties: false`. A failed validation means
  `SequentialPlayoutBuilder` returns `None` and the playout does not build at
  all. The label now lives in a comment, where it always belonged.
- **Every `pad_until` needs an explicit `tomorrow:`.** 26.x changed
  `Tomorrow` from `bool` to `string` so it can hold an expression, and
  `YamlPlayoutPadUntilHandler` does `new Expression(padUntil.Tomorrow)` with no
  null check. NCalc throws `ExpressionString cannot be null or empty` and the
  whole build dies. The branch only runs when the pad target is already in the
  past, so a bare `pad_until` is a landmine that detonates the first time the
  playout is rebuilt later in the day than its earliest morning block.

After changing the schedule, the playout must be **reset** — graphics elements
are attached to playout *items* as they are built, so existing items never gain
them. Delete `PlayoutItem`, `PlayoutAnchor` and `PlayoutHistory` for the playout
and restart. Reset on a **Wednesday** (see the header of `channel-z0.yml`).

Element definitions must exist and be *registered* before the build that
references them. ErsatzTV refreshes them at startup, hourly, and when a stream
session starts — but at startup it builds playouts *before* refreshing, so a
brand-new element file needs one restart to register and a second build to be
attached.

## Performance

Compositing is CPU work (SkiaSharp), and the blend is a GPU `overlay_cuda`.
Adding four elements on top of a software x264 encode pushed some items below
real time (one hit **0.253x**, which is a stutter, not a warning). The channel
now encodes with **NVENC** (`HardwareAcceleration=2` on the ffmpeg profile) —
the GTX 1650 was sitting completely idle while the CPU did all of it.

One title still runs near the line: an interlaced 480p print that gets
deinterlaced and upscaled 3× (~1.26x). That is the source, not the overlays.
