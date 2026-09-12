# 2026-08-24 — Spawning the station on another machine, in one command

**Branch:** `agent/z0-spawn-automation` · **Worktree:** `/home/user/wt-z0-spawn`

The ask was "how quickly could we automate spawning Channel Z0 on another
machine, assuming all the servers need to be set up", then: make it happen.

`bootstrap-node.sh` already covered maybe two thirds of the plumbing. What it
did *not* do was the part that decides whether the new box is a television
station or just a machine running ErsatzTV — and it ended by printing a 7-step
manual GUI checklist, which is the honest admission that the hard part was never
automated.

## What was actually wrong, found by looking rather than reading the docs

1. **`/iptv/channel/1.ts` is a 404 on this station.** The channel is number 0.
   `.env.example` and the generated `.env` both hardcoded 1, so a bootstrapped
   node would answer every health check and publish nothing. This is the worst
   kind of bug the estate produces: a green light over silence.

2. **The image tags the script chose are abandoned upstream.** It picked
   `latest-nvidia` / `latest-vaapi`; there has been no `-nvidia` build since
   v25.2.0. Live runs `ghcr.io/ersatztv/legacy:v26.7.1`. A fresh bootstrap would
   have landed on a frozen image with no graphics engine — the gutter rails, the
   whole current on-air look, would silently not render. The tag was never the
   right knob: one image serves every accelerator, and hardware is chosen by
   `runtime: nvidia` + a GPU UUID, or `/dev/dri`. That cannot be expressed by a
   variable inside one compose file, hence the generated `compose.hwaccel.yml`.

3. **`playout/ersatztv.sh` pointed at `ghcr.io/ersatztv/ersatztv`,** which is not
   where the image lives, and hardcoded `--device /dev/dri` so it could never
   work on the NVENC box the station actually runs on.

4. **There is no ErsatzTV config API.** `/api/channels` returning 400 to an empty
   POST looked promising for about a minute; `/api/ffmpeg_profiles` returns the
   SPA HTML, and there is no swagger. The SPA router answers everything. The
   database *is* the station, so the only faithful spawn is to carry it.

## The three traps the restore has to handle, or it produces a subtly wrong station

- **The playout anchor stores an instruction INDEX** into the flattened
  schedule. Carry it to a new box and it still looks valid and still points
  somewhere — just at a different instruction. The week does not fail; it
  resumes mid-block. Same failure #38 was written to prevent. Restore clears all
  playout tables so the week re-enters from the top.
- **The search index is a separate store from the database.** Delete items (we
  strip the source's Jellyfin libraries) and the index still lists them; queries
  resolve to things that are gone, and an empty pool schedules nothing and
  leaves a hole in the guide with no error anywhere. Restore drops the index and
  lets it rebuild.
- **The profile NAME carries the encoder** ("854x480 h264_nvenc aac"). Re-point
  the hwaccel and leave the name and the UI cheerfully advertises nvenc on a
  VAAPI box forever.

Stripping the remote sources is safe here because all 74 smart collections are
`type:other_video` against the local library — checked, not assumed. It takes
the DB from 3278 media items to 789.

## Why `fetch-archive.sh` cannot stand in for copying the library

It runs *search queries*. A rebuild returns different titles with different
tags, and its manifest only ever **skips** what is already down — there is no
replay mode. Roughly a fifth of the 155 GB (schoolroom, the Canadian and BC
sets, the 73 music cards, everything generated) has no recipe at all. So
`z0-media-sync.sh` mirrors a peer, and **excludes `.z0-cluster`** — that
directory is the lease, and copying it gives the new node the belief that it is
already on air, which is precisely the double-publish the whole locking design
exists to prevent.

## Testing notes, including one that failed in exactly the documented way

`tools/test-spawn.sh` builds a synthetic station in a scratch SQLite DB — no
station, no media, no GPU, ~5 seconds, in the spirit of `test-failover.sh`.
19 assertions.

- **The suite was mutation-tested.** Removing the lease exclusion, the anchor
  clearing, and the encoder re-point each produced the expected failures, and
  the clean tree returns to 19/19. A suite nobody has watched fail is not
  evidence.
- **It passed 19/19 on x and 18/19 in LXC 111**, which is the whole reason to
  run it in both. sqlite 3.53 no longer honours the double-quoted-string
  misfeature, so `COALESCE(VaapiDevice,"none")` resolved `"none"` as an
  identifier, errored, and the assertion compared against an empty string. The
  *behaviour* was correct the whole time; the test was lying. Single-quote SQL
  string literals.
- **A dry run reported `ERR cannot create /mnt/z0`** because the media sync
  mkdir'd before checking `DRY`. The script's own `ok_real` comment already says
  a preview that claims something untrue is worse than no preview.

## What is still not automated, and why

**The tower cannot be provisioned on Oracle's free tier today.** Verified live:
both Always Free micro slots are in use (`z0-tower`, `rpp-01`), and the A1
ladder returned "Out of host capacity" on every rung as recently as 05:54 this
morning. That is a purchase decision, not a coding problem. `ocipost.sh` already
launches instances when there is capacity to launch into.

**No Cloudflare credential exists on x** (`/etc/rl-secrets/` has anthropic,
tailscale, vastai). `z0-tower-config.sh --dns-a` is written and takes
`CF_API_TOKEN` + `CF_ZONE`; it refuses cleanly with the exact token scope needed
rather than half-doing it.

**No container bring-up was proven end to end.** Nothing on x, 111, 114 or 117
has Docker, and the only Docker host is vile — the live station, with two other
jobs already poking at Z0. Everything short of `docker compose up` is proven
against real data: the capture ran read-only against the live station, and the
restore was verified by querying the resulting database.

The live station was not modified. The only write anywhere near it was a
`/tmp` probe copy on vile, since removed; it is still streaming 1.5 MB per 6 s
on channel 0.
