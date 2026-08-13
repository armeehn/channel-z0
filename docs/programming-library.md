# The Channel Z0 programming library

How the channel decides what to play, and how to change it.

There are three layers, and they are edited in three different places:

| Layer | Lives in | Applied by |
|---|---|---|
| **Metadata** — what each file *is* | `.nfo` sidecars next to the media | `tools/z0-nfo.py`, then a rescan |
| **Lists** — named pools and rundowns | `lists/z0-lists.yml` | `tools/z0-lists.py` |
| **Schedules** — what plays when | `playout/schedule/*.yml` | `tools/z0-build-schedule.py`, then a playout reset |

Each layer only knows about the one above it. A schedule asks for `noir`; the
list layer decides that means `tag:noir`; the metadata layer decides which files
carry that tag. Change the bottom and the top follows automatically.

---

## 1. Metadata — `tools/z0-nfo.py`

ErsatzTV gives an **Other Video** almost nothing: the title is the raw file
stem, and Year, Genre, Studio, Director and Plot are all empty. Channel Z0's
library is one Other Videos library path, so before this existed the guide read

```
Betty Boop Barnacle Bill (1930) [BettyBoopBarnacleBill1930]
```

and no query could ask for "a 1930s cartoon", because nothing knew what year it
was.

ErsatzTV *does* read an NFO sidecar for Other Videos, so `z0-nfo.py` writes one
`<file>.nfo` per media file with a cleaned title, a year, genres, studios,
directors, tags, a content rating and a short outline.

```sh
# after any download run
python3 z0-nfo.py --inventory inventory.json --scan-fs \
                  --media-root /mnt/main-data/channelz0
```

`--inventory` is a JSON export of the current library (see the header of the
script); `--scan-fs` additionally walks the filesystem so files that have never
been scanned are covered too. Use both.

### ⚠️ The trap: folder tags and NFO tags are the same field, and the NFO wins

With no sidecar, ErsatzTV tags an Other Video with the folder names above it, so
`movies/noir/x.mp4` carries `media`, `movies`, `noir`. **The moment a sidecar
appears, `LocalMetadataProvider.ApplyMetadataUpdate` calls
`UpdateMetadataCollections`, which removes every existing tag the incoming
metadata does not list.** The folder-derived fallback (`RefreshFallbackMetadata`)
only runs when there is *no* `.nfo` at all.

So a sidecar that forgets `<tag>noir</tag>` silently deletes the tag the whole
schedule is built on. `tag:noir` then matches nothing, the pool is empty, and an
empty pool is skipped in silence — a hole in the playout, not an error.

`z0-nfo.py` reads the current tags out of the database and re-emits every one of
them verbatim before adding its own, and **refuses to run** if any file would
lose a tag. Never hand-write these files.

### What it derives

- **Title** — brackets and archive.org identifiers stripped, `Arctic Giant, The`
  flipped to `The Arctic Giant`.
- **Year** — from a parenthesised year in the file name, which beats the false
  positives (`Chapter 10`, `DVD-6605`, `#5530`). ~217 of 349 files resolve; the
  rest are left blank rather than guessed.
- **Sort title** — for serials, a zero-padded chapter number, so
  `order: chronological` plays Chapter 3 before Chapter 10 instead of after it.
- **Series** — Betty Boop, Bosko, Felix, Popeye, Superman, Merrie Melodies, Ub
  Iwerks, Private Snafu, Why We Fight, the newsreel series, and thirteen serials.
- **Studio** — only where the file name states it or the attribution is
  unambiguous for the whole run. Popeye and Superman both moved from Fleischer to
  Famous Studios in 1942, so **no studio is claimed for either** — a wrong credit
  on screen is worse than a missing one.
- **Content rating** — used purely as a daypart gate, not as a ratings board:
  - `Z0-GENERAL` — anything, any time.
  - `Z0-LATE` — 23:00 and later only. The four burlesque reels and the
    exploitation "square-up" features. **Before the sidecars existed these were
    indistinguishable from any other short and were airing inside the 06:30 and
    16:00 daytime blocks.**
  - `Z0-STATION` — idents, bars, test card, the weather segment.
  - `Z0-REVIEW` — nothing schedules this. See below.

### The review queue

`Z0-REVIEW` / `tag:review-nonpd` is how material stays in the library without
being airable:

- **~22 modern fan-animation files** (Warrior Cats "MAP"/"PMV" edits and
  friends) that arrived in a bulk download. Not public domain, not vintage.
- **The five NFB shorts** (`tag:nfb`). As a federal agency, Crown copyright
  (s.12, 50 years) should make everything the NFB published before 1976 public
  domain in Canada — but no court has ruled and the NFB actively asserts and
  licenses that exact catalogue. **The question is open with the user.** Every
  Canadian pool also carries an explicit `NOT tag:nfb`, so the exclusion holds
  even if someone forgets one of the two mechanisms.

Neither is deleted. The decision stays the operator's.

---

## 2. Lists — `lists/z0-lists.yml`

ErsatzTV has **no management API** (`/api/*` and `/swagger` answer only through
the Blazor SPA catch-all, and a POST to an unrouted path returns 400, so a 400
from `/graphql` proves nothing). `tools/z0-lists.py` therefore writes the rows
directly.

```sh
python3 z0-lists.py --db /mnt/solid-state/ersatztv/ersatztv.sqlite3 \
                    --manifest z0-lists.yml --check
```

It is idempotent, matches on name, and only touches rows prefixed `Z0 `.
**Take a database backup first** — there is no undo.

`--check` evaluates every smart-collection query against the database and
reports the match count, failing if any pool is empty. This is worth running
every time: an empty pool is the single most common way to break this channel
and it fails silently on air.

### What's in it

- **57 smart collections** — the pools. Genre, era, series, studio, subject,
  season, duration band, and the daypart gates.
- **13 collections** — hand-picked and, where it matters, hand-ordered
  (`custom_order: true`): the sign-on and sign-off packages, the Vancouver reel
  in chronological order, Why We Fight in order.
- **5 multi-collections** — pools of pools.
- **12 playlists** in 3 groups — small rundowns with their own per-item counts,
  ordering and guide flags.
- **11 filler presets** — pre-roll, mid-roll, post-roll, tail and fallback.
- **3 watermarks** and **3 decos** with a deco template.

### Query notes

- The title analyser **does not split on hyphens**: `title:colorbars` will never
  match `colorbars-60m`. Quote the whole title.
- `minutes` / `seconds` / `chapters` / `height` / `width` are numeric and only
  work in range syntax — `minutes:[10 TO 30]`. Written bare they parse as terms
  and match nothing.
- Smart collections **can reference each other** — `smart_collection:"Z0 Cartoons"`
  — with cycle detection. **Quotes are required**; without them the substitution
  silently does not happen and the query means something else.
- Names are `varchar(50)`.

### ⚠️ Two shapes that kill the entire playout build

Both of these produce a database that looks perfectly fine, and a channel that
quietly falls back. The only symptom is one line in the ErsatzTV log:
`[WRN] Unable to build playout 1: ...`.

1. **A playlist may not name the same collection twice.** `PlaylistEnumerator`
   keys its map on `(ContentKey, CollectionKey)`, so a repeat throws
   *"An item with the same key has already been added"*.
2. **A multi-collection member with `group: true` must be `chronological` or
   `season_episode`.** `MultiCollectionGroup`'s constructor throws
   `NotSupportedException: Unsupported MultiCollection PlaybackOrder: Shuffle`.
   Shuffle the *groups* instead, via the `multi_collection` content key's own
   `order`.

`z0-lists.py` now refuses to apply either, with an explanation.

---

## 3. Schedules — `playout/schedule/`

```
_content.yml                  content keys      (import fragment)
_sequences.yml                reusable sequences (import fragment)
channel-z0.yml                the week          — GENERATED
channel-z0-halloween.yml      seasonal
channel-z0-christmas.yml      seasonal
channel-z0-canada-day.yml     seasonal
channel-z0-marathon.yml       special
channel-z0-testpattern.yml    engineering
```

Imports are resolved relative to the importing file's directory, and **the
importing file wins on any key collision** — which is how a seasonal schedule
overrides a single strand without copying the week.

### The week is generated

```sh
python3 z0-build-schedule.py --start-day thursday --out channel-z0.yml
```

ErsatzTV's sequential scheduler has **no day-of-week primitive**. The seven day
blocks run in order and `repeat: true` returns to the first; which block lands on
which weekday is decided entirely by the day the playout is built or **reset**
on. Nothing detects a mismatch and nothing reports it — the channel simply airs
Monday Night Noir on a Wednesday while the storefront promises Workbench Theatre.

So rotation is a flag. **Build for the day you are going to reset on**, and build
*early* in that day: a playout built mid-afternoon starts at instruction one with
every morning `pad_until` already in the past, so they collapse to nothing and
the evening stretches to cover the day. It rights itself at the next sign-on.

(Day-of-week and seasonal switching *do* exist in ErsatzTV, as `PlayoutTemplate`
rows with `DaysOfWeek` / `MonthsOfYear` / date ranges — but only **block**
playouts read them. Channel Z0 runs a sequential playout, which is what buys the
graphics control, the pre-roll sequences and everything else in `_sequences.yml`.)

### Validate before you deploy

```sh
python3 z0-validate-schedule.py channel-z0.yml \
        --graphics-root /mnt/solid-state/ersatztv/templates/graphics-elements
```

Runs ErsatzTV's own JSON schema (the same validation the app runs — when it
fails, `SequentialPlayoutBuilder` returns `None` and the playout does not build
**at all**), then the Z0 trap list:

- `search:` used as a human label — the schema declares it `{"type": "null"}`;
  a value there fails validation and the playout silently does not build.
- `pad_until` without an explicit `tomorrow:` — 26.x changed `Tomorrow` from
  bool to string so it can hold an expression, and the handler evaluates it with
  no null check, so NCalc throws and the build dies. Dormant until the first
  rebuild later in the day than the earliest morning block.
- Unbalanced `epg_group` — `LockGuideGroup` is a no-op while already locked, so
  two `true` in a row merge two programmes into one guide row.
- A content key referenced but not defined.
- Padding from a pool of seconds-long items (~300 items, four stings on a loop).
- A `graphics_on` target that does not exist on disk.

`jsonschema` is installed on **vile**, not on x, so run the validator on vile or
the schema layer is skipped (it says so when it skips).

### The vocabulary actually in use

`import`, `sequence`, `shuffle_sequence`, `pre_roll`, `post_roll`, `mid_roll`,
`watermark`, `graphics_on`/`graphics_off`, `epg_group`, `all`, `count`,
`duration`, `pad_until`, `pad_to_next`, `filler_kind`, `trim`,
`discard_attempts`, `offline_tail`, `repeat`, and the `collection`,
`smart_collection`, `multi_collection`, `playlist` and `search` content types.

Three things are deliberately **not** used:

- **`marathon:`** — groups by show / season / artist / album, none of which an
  Other Video has. Every item would land in one degenerate group. `all:` over an
  ordered collection is the honest version, and is what `channel-z0-marathon.yml`
  does. (The C# enum also has a Director option the YAML schema doesn't expose,
  which would have worked for the Harman-Ising shorts.)
- **`rewind:`** — a handler and a model exist, but the instruction is not in the
  schema's `oneOf` list for either `playout` or `sequence`, so it cannot be used.
- **`skip_to_item:`** — requires season and episode numbers.

`mid_roll` *is* wired up but will almost never fire: a mid-roll sequence is
inserted at an item's **chapter markers**, and only 7 files in this library have
two or more chapters.

### pre_roll / post_roll only wrap some instructions

The roll handlers are invoked from the `all`, `count` and `duration` handlers
**only** — `pad_until` and `pad_to_next` do not emit them. That is why features
are scheduled with `count:` and why the day still calls `sequence: station_break`
explicitly in a few places.

Because the roll handlers push a `FillerKind`, everything inside a roll sequence
is automatically dropped from the programme guide. A sequence invoked *directly*
is plain content and **will** appear in the guide unless you set `filler_kind`
on it — which is why `station_break` carries `filler_kind: preroll`.

---

## Deploying a change

Order matters, and every step here has bitten someone.

```sh
# 0. back up
sqlite3 'file:…/ersatztv.sqlite3?mode=ro' ".backup '…/ersatztv.sqlite3.bak'"
cp …/channel-z0.yml …/channel-z0.yml.bak

# 1. metadata, if files changed
python3 z0-nfo.py --inventory inventory.json --scan-fs --media-root …

# 2. lists
python3 z0-lists.py --db … --manifest z0-lists.yml --check

# 3. schedule
python3 z0-build-schedule.py --start-day <today> --out channel-z0.yml
python3 z0-validate-schedule.py channel-z0.yml --graphics-root …
cp _content.yml _sequences.yml channel-z0.yml /mnt/solid-state/ersatztv/

# 4. force a rescan if metadata changed
sqlite3 … "UPDATE LibraryPath SET LastScan=NULL WHERE Path='/media';"

# 5. reset the playout — REQUIRED for element and schedule changes
sqlite3 … "delete from PlayoutItem; delete from PlayoutAnchor; delete from PlayoutHistory;"

# 6. restart BOTH, in this order
docker restart z0-ersatztv
sleep 45
docker restart z0-uplink

# 7. prove it
sqlite3 … "select count(*) from PlayoutItem"          # must be > 0
docker logs --since 3m z0-ersatztv | grep -i 'unable to build'
```

**Why each restart:**

- A stale `PlayoutAnchor` pins the position and every later build does nothing,
  so a failed build stays failed until the anchor is cleared.
- Graphics elements attach to playout **items** at build time; existing items
  never gain them. And at startup ErsatzTV builds playouts *before* refreshing
  graphics elements, so a brand-new element file needs one restart to register
  and a second build to be attached.
- **The uplink does not recover from an ErsatzTV restart.** Its `ffmpeg -c copy`
  holds a frozen RTMP session; Owncast keeps reporting `online: true` with the
  right title and `lastConnectTime` pinned at the old timestamp. Two frames
  grabbed a minute apart being byte-identical is the tell.

### Prove it with a picture, not a status code

`/api/status`, the guide and the database have all reported perfect health while
the channel was transmitting something else. Grab a frame from the **live edge** —
`ffmpeg -i …/stream.m3u8` starts at the *oldest* segment in the playlist and will
happily return minutes-old colour bars:

```sh
B=https://watch.ch0.ripostelabs.xyz
V=$(curl -s $B/hls/stream.m3u8 | grep -v '^#' | head -1)
SEG=$(curl -s $B/hls/$V | grep -v '^#' | tail -1)
ffmpeg -i "$B/hls/$(dirname $V)/$SEG" -frames:v 1 out.png
```

`curl -o /dev/null … && echo ok` proves nothing — curl exits 0 on a 404, and the
tower 404s `/hls/stream.m3u8` entirely while offline.

---

## Swapping in a seasonal schedule

```sh
sqlite3 … "update Playout set ScheduleFile='/config/channel-z0-halloween.yml' where Id=1;"
# then steps 5–7 above
```

and swap it back the same way. There is no calendar in the sequential
scheduler, so this is a manual act on the day.

`channel-z0-testpattern.yml` is the one to reach for during maintenance: no
subtitle element, no rolls, no playlists — the cheapest thing the channel can
transmit, so that what you see is what the encoder did rather than what the
scheduler chose.

---

## Why the channel is 640x480

A **subtitle** graphics element is re-rendered every frame whether or not its
content changed, and costs roughly 4x realtime at 1080p. The bottom strip is a
subtitle element. At 1080p it took the channel off air 27 times in one morning:
items carrying the strip transcoded at 0.254x, ErsatzTV logged
`[FTL] … NOT fast enough to support playback`, abandoned each one and cut to
fallback filler — which carries no graphics at all.

Image and text elements are rasterised once and reused, so they are nearly free.
The cost is proportional to pixel count, which is why the schedule takes the
strip down (`sequence: strip_down`) around every feature.

**If the channel ever goes back to 720p or 1080p, the bottom strip must be
removed.** And judge health by `[FTL]` lines, not `[WRN]` — the warning
threshold is miscalibrated against the `-readrate 1.0` cap and warns constantly
at a perfectly healthy 1.01x.
