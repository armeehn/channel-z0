# 2026-08-19 — L-system station intervals, drawn and glitched by their own source

## Task
"create glitchy animations for in between segments on channel zero ... use ffglitch and
create some sort of generative art and algorithm to showcase those as small clips. it
would show the code as well", refined mid-task to: "you can use lindenmayer systems and
show the code used to generate it as part of the art. kind of like a quine".

## Outcome
Done, then extended on the same day after "keep making more". **Sixteen** 55.0 s clips
at 854x480 installed in `/mnt/main-data/channelz0/generative/` on vile
(`z0-lsys-*.mp4` + `.nfo`), taking that pool to 46. Tools in `tools/z0-lsys/`, docs in
`docs/lsystems.md`. Worktree `/home/user/z0-lsys-wt` in LXC 111.

- **PR #37** (first eight) — squash-merged as `c827c2e` while I was still working.
- **PR #40** (eight more: peano, gosper, moore, tree, snowflake, terdragon, seaweed,
  board) — open, `feat/lsystem-more-specimens`, commit `eb977e9`.
- `feat/lsystem-intervals` is stale and superseded; its `5220fee` carries a wrong
  message (see Traps) and `caf12d9` annotates that. Both are re-landed properly in #40.

**Not yet on air** — see Open.

## Traps
- **numpy in LXC 111 is broken.** `import numpy` dies with
  `/usr/lib/libm.so.6: version 'GLIBC_2.44' not found` — it is built against a newer
  glibc than the container has. PIL 12.3.0 is fine. Anything rendering in 111 must use
  PIL. (This is why the tool does its own raster work rather than reusing Glitchsheet.)
- **Comparing the input and output bitstreams does NOT prove ffedit did anything.** My
  first guard sha1'd `seed.mpg` against `art.mpg`. It passed with `--trim 0`, which sets
  every vector to zero: ffedit re-codes a vector it was handed even when the value is
  unchanged, so the file differs while the picture stands perfectly still. The guard that
  works decodes the untouched carrier alongside the glitched one and compares *pictures*
  (`--min-motion`, default 1.0). Real clips measure 5.2–21.1; `--trim 0` measures 0.010
  and is refused.
- **A second, subtler version of the same mistake:** I first measured motion only in the
  post-growth phase, where the ink canvas is frozen. A real fern scored 0.02 against the
  dead clip's 0.010 — indistinguishable. The cause was that the end-of-clip "bloom" was
  itself a no-op: `s = 0.18 * push 30 / 10 = 0.54` half-pels, and `Math.round()` of a unit
  vector times 0.54 is almost always 0. **Motion vectors are integers; anything under ~1
  half-pel rounds away to nothing.** A knob can look wired up and do nothing.
- **`make-specimens.py` validated line width AFTER writing the files.** The over-wide
  file sat on disk next to the complaint about it and the renderer used it anyway — two
  renders shipped from source the panel could not display. Now it checks all eight and
  writes none if any fails.
- **argparse (py3.14) raises `ValueError: badly formed help string` at `add_argument`
  time** if a help string contains a bare `%`. Must be `%%`.
- **Motion vectors that fetch from outside the frame decode as flat saturated green** —
  visible as green corners in the first spike. Every specimen fades its field out over
  the last 3 macroblocks at each edge; that code is on screen and is not decoration.
- **The classifier refuses `UPDATE LibraryPath SET LastScan = NULL` on the live ErsatzTV
  sqlite**, same as it refuses playout-table deletes. Plain `SELECT`s still worked
  afterward this time. There is no non-DB, non-restart way to force a scan from the CLI.
- **vile has no `ffmpeg`/`ffprobe` on PATH** (`zsh: command not found`). Probe media in
  LXC 111 instead.
- `pct exec 111 -- git ...` as root fails with *dubious ownership*; run as user `user`.
- A shell heredoc mangled a UTF-8 middot (`·` → `ยท`). Write non-ASCII with python, not
  `cat <<EOF`.
- **`git commit -F /tmp/<generic-name>` picked up ANOTHER AGENT'S message.** I wrote a
  commit body to `/tmp/msg2.txt` via `pct push`; the write failed
  (`Permission denied` — the path already existed, owned by `user`, left there on
  **15 Aug** by a different job), and `git commit -F` then read that stale file and
  committed my sixteen-specimen change under the title
  *"project-hex: DOC.HEX-200, the three HEX documents as one manual"*. The contents were
  right, the message belonged to another project, and nothing failed loudly: the `pct
  push` error scrolled past inside a chained command and the commit reported success.
  **LXC 111 is shared by several background agents — never stage a commit message, or
  any scratch file, at a generic `/tmp` path there.** Use a job-unique name.
- **A squash-merge strands work you stacked on the branch.** #37 was squash-merged into
  `c827c2e` while I was adding the second eight, so `git log origin/main..branch` still
  listed *all four* of my commits as unmerged — the squash has no ancestry link. Fix was
  a fresh branch off `origin/main` + `git cherry-pick -n`, which applied clean. That also
  meant the bad commit message never had to reach main, and could not have been fixed by
  amending: the branch was already pushed and force-pushing it was not mine to do.
- **Check the PR is still open before editing it.** `gh pr edit 37 --body-file` succeeded
  against an already-MERGED PR; the only reason I noticed was that the follow-up
  `gh pr view --json state` printed `MERGED`.

- `-sp` takes integers only — a float makes ffedit write no output at all. (Known from
  glitzy's `ff.py`; confirmed, not re-learned.)

## Decisions
- **Specimens are self-contained and duplicated, not DRY.** The claim is that the listing
  on screen is the whole program, so nothing may hide behind an import. They are
  therefore *output* of `specimen.template.js` + `make-specimens.py`; hand-edits are lost.
- **Paged listing, not scrolling.** Cheaper to encode (static between page turns) and
  legible at 480p. Page count is derived so the file shows through exactly once per clip,
  however long it is.
- **448x480 art + 406 px panel**, giving a 52-column limit at 12 px — enforced by the
  generator, because a wider line is one nobody can read.
- **Reused the existing `generative` tag** rather than a new one: a new tag needs the
  Lucene search index rebuilt (not just a scan) *and* a schedule change. These join the
  existing shuffle untouched.
- **854x480 native**, unlike the 640x480 Glitchsheet pool, so they fill the channel frame.
- **One host.** Nothing needs numpy or Glitchsheet, so render + glitch + H.264 all happen
  in LXC 111. 8 clips in ~40 s, against ~3 h for a 32-clip Glitchsheet batch.
- `push` lives in each `SYS` block (on screen) because a space-filling curve fills every
  macroblock: Hilbert needs a third of the fern's shove or it turns to mud.

## Verified / unverified
- Verified: 8/8 clips at exactly 55.00 s; glitch measure 5.16–21.11 vs a 1.0 floor;
  `--trim 0` refused. `make-specimens.py` + `git diff --exit-code` clean, so the committed
  specimens match the template. `ffprobe` on a new clip vs `z0-interval-00.mp4`: identical
  h264 / yuv420p / bt709 / 30 fps / aac 48 kHz stereo / 55.000 s, differing only in width.
  8 mp4 + 8 nfo present on vile, NFOs carrying `<tag>media</tag><tag>generative</tag>`.
- Unverified: **nothing has been seen on air.** Judged entirely from extracted still
  frames — I never watched a clip as motion video. The library had not rescanned when I
  stopped.

## Open
- The clips are invisible to ErsatzTV until `/media` is rescanned. `LastScan` was
  **2026-08-19 17:00 UTC** and `scanner.library_refresh_interval` is 6, so the automatic
  pass was due ~16:00 PDT the same day. To force it: scan from the ErsatzTV UI, or grant
  the DB write. Do **not** restart the app casually — that drops the live channel and
  `z0-uplink` does not recover on its own.
- **PR #40 is unmerged** (PR #37 is merged).
- Deliberately left alone: the schedule, `z0_intervals.py` lengths, and the Glitchsheet
  interval family — this pool is additive and changes none of them.
