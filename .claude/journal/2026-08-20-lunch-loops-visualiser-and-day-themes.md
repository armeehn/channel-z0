# 2026-08-20 — LUNCH LOOPS: a real audio visualiser, and a different form each day

## Task
"i want a audio visualizer for the music segments on channel z0", then "create
playlists for the music being played so that we have different kinds of music on
different days during the lunch loops".

## Outcome
Both live. Branch `agent/music-visualizer`, PR **#41** (5 commits, unmerged).
Worktree `/home/user/wt-music-viz` in LXC 111.

- Visualiser: all 73 `/media/music/*.mp4` re-rendered and swapped in place.
- Day themes: tags corrected, 7 playlists applied, schedule redeployed. The
  themed week enters at the seam **Sat 2026-08-22 06:00**, not today.
- New: `tools/z0-music-viz.py`, `tools/z0-viz-extent.py`, `docs/music-cards.md`.
- Scratch on vile: `/mnt/main-data/channelz0/.z0viz/` (cards, backups, deploy script).

## Traps
- **`astats` only prints at INFO level.** The measurement pass at `-v error`
  returns an EMPTY result set and no error. Every bar sits at zero and the render
  reports success. If the bars do not move, check verbosity before anything else.
- **`sqlite3 <path>` CREATES an empty database.** The ErsatzTV DB is
  `/mnt/solid-state/ersatztv/ersatztv.sqlite3`, **not** `ersatztv.db`. Querying
  the wrong name silently made a 0-byte `ersatztv.db` in `/config` and answered
  "no such table: MediaVersion", which reads like a schema change. Moved to
  `.z0-backup-20260814/stray-empty-*`. Always `ls` the file before believing an
  empty schema.
- **Do not render on vile.** No host ffmpeg; driving the containerised one is
  **~0.7x realtime** because every raw RGBA frame crosses docker's stdin proxy
  (~5 h for 73 tracks) vs **4.2x** native in LXC 111 (~45 min). vile is also the
  live playout box. `jellyfin-ffmpeg` cannot be lifted out of its container to
  fix this — it needs system libs it does not bundle (`libopenmpt`).
- **A containerised ffmpeg's work dir must be inside the bind mount.** `astats`
  writes its band files *with ffmpeg*, so a host `/tmp` workdir fails at graph
  init with `Could not open .../band00.txt`. Reads like permissions, is mounts.
- **`z0-nfo.py` matched dance forms against the whole `Artist - Title` stem.**
  Every record by a band with a form in its NAME got that form: `tag:polka` held
  20 records of which 14 were polkas, "Original Polka Kings — Chownyk *Waltz*"
  was tagged both, "The Polka Drifters — A Soldier's *Lament*" was a polka. The
  pre-existing `Polka Party` playlist was serving laments. Fixed to read the work
  title. Regenerating all 73 sidecars changed exactly `+12 wedding, +8 song,
  +8 kolomyika, -6 polka` and nothing else — diff all 73 before deploying tags.
- **Nulling `LibraryPath.LastScan` does NOT force a scan.**
  `scanner.library_refresh_interval` is 6 (hours) and the worker did not pick it
  up in 9 minutes of polling. A `docker restart z0-ersatztv` triggers it; tags
  landed ~20 s after restart.
- **A playlist may not name the same source twice** — `PlaylistEnumerator` keys
  on `(ContentKey, CollectionKey)` and a repeat fails the **whole** playout
  build. This is why each themed day has a distinct *second* form rather than
  drawing its lead pool twice. Already documented at `Cartoon Hour` in
  `lists/z0-lists.yml`; it applies to every new playlist.
- **`minutes` only works in range syntax** (`minutes:[0 TO 9]`). Bare, it parses
  as a term and matches nothing — which here would silently *un-bound* every pool
  rather than fail.
- **The music library is not all 78rpm singles.** Four sides run 18–23 min
  (Peter Picklyk's two LP sides; "Marriage & Married Life" Parts 1+2, a 45-min
  narration). Two are wedding-tagged, i.e. Saturday's lead. One in a slot sized
  for a polka eats a third of the block, on top of the film the block already
  schedules.
- **A card safe-area comment went stale and nearly cost a redesign.**
  `music-card.html` reserved "nothing below y 375" for the crawl; #35 (2026-08-19)
  deleted the bottom strip and moved everything into the pillarbox rails. The
  band is now free.
- **`y=268` for the analyser is measured, not chosen.** `render-music.mjs`
  shrinks the *title* to fit but not the artist credit; exactly one of 73 wraps
  it to a second line reaching y=257.5, so y=250 cleared 72 and clipped one.
  `tools/z0-viz-extent.py` measures it — and a **full-width** scan is misleading,
  reporting y=367 for every card, which is the decorative `.corner.bl` bracket at
  x 18–31 that the analyser never reaches.
- **An exact duration comparison rejects good files.** Three renders differ from
  source by ~**21 microseconds** (122.427021 → 122.427000) — mp4 container
  rounding, not a lost frame. The deploy guard correctly refused and aborted;
  the fix is a 50 ms tolerance, not removing the guard.
- **`z0-day-align.py --redeploy` is blocked by the auto-mode classifier**
  (it does `DELETE FROM PlayoutItem/PlayoutAnchor/PlayoutHistory`). It needs an
  explicit permission grant from the user; there is no substitute — the anchor
  stores an instruction *index* into the flattened deployed file, so a hand-swap
  resumes at a different instruction and the week silently lands mid-block.

## Decisions
- **`tall` style** (analyser fills the lower half, datum strip to the bottom)
  over `mark` (animate the existing 5-bar mark) and `analyser` (bottom band) —
  user's pick from three rendered previews; a corner mark is small for a 2 h block
  and removing the static mark leaves a hole only `tall` fills.
- **ffmpeg does the DSP, Python only draws.** N `bandpass` + `asetnsamples=1600`
  + `astats reset=1` = one RMS per band per frame, ~85x realtime. A Python FFT
  would be minutes per track and `numpy` does not import in LXC 111 (glibc).
- **RGBA overlay with a transparent background**, so hard-edged bars sit on the
  card's radial gradient without reconstructing it.
- **Hard tri-band colour segments**, not an interpolated ramp: orange→teal passes
  through olive and the analyser came out a rainbow containing two colours the
  station does not own.
- **19 sides left unclassified** rather than guessed from transliterated titles
  ("Side 1", "Julayda", "Once More"). They stay in the general pool.
- **Long sides bounded out of the music pools** but not dropped — Saturday spends
  its *film* slot on them, so the wedding day is built around the narration.

## Verified / unverified
Verified: 73/73 rendered, 0 failed; worst duration delta **0.000021 s**; all
640x480 / aac 48000 / 2ch. After swap+rescan all 73 `MediaItem.State=0`,
dimensions/SAR/DAR unchanged (640|480|1:1|4:3), and the 12:02:30 item still
scheduled. Pools resolve: Polkas 14, Waltzes 13, Kolomyiky 8, Weddings 10,
Songs 8, Fiddle 3, Short Sides 69, Long Sides 4, Fast 25. Deployed
`channel-z0.yml` carries all 7 themed strands. Redeploy cut at Sat 06:00 —
42 items removed, 47 rebuilt, SIGN-ON at 06:00:08. New tag terms present in
`search-index`. On-air frame extracted from the live file shows the analyser.

Unverified: **the Saturday 12:00 themed block had not been built yet** when this
was written (playout frontier Sat 09:59) — nobody has seen a themed lunch block
actually drawn from its pool. The transcode benchmark (22x vs 33x realtime) was
libx264 in LXC 111, **not** vile's NVENC.

## Open
- Confirm the Sat 2026-08-22 12:00 block draws wedding-tagged music and no pool
  came out empty. If empty: `rm -rf /mnt/solid-state/ersatztv/search-index`,
  restart, redeploy.
- PR #41 unmerged.
- Left alone deliberately: the ~2296 `MediaItem.State=3` rows (pre-existing, not
  music — all 73 music items are State=0), and the unbounded `Z0 Prairie Music`
  pool, because Canada Night and the Neighbourhood Desk draw on it.
- `/mnt/main-data/channelz0/.z0viz/` and `/home/user/z0viz/` are scratch; the
  ZFS snapshot `main-data/channelz0@pre-music-viz-20260820` is the rollback.
