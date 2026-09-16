#!/usr/bin/env python3
"""Channel Z0 — reset accumulated stream drift, off hours only.

The public stream's PDT falls behind the tower clock whenever a playout item
transcodes below 1.0x on vile (see the 2026-08-26 journal entry on x:
playout under-run — the graphics-engine feed, not passthrough, not the WAN).
Lost seconds are a RATCHET: readrate never claws them back, and only a fresh
uplink session re-baselines the public PDT. This script is that reset, run
from cron at 04:45 — after overnight programming, before z0-day-align at
05:05, when a seconds-long blip has no audience.

Cron (midclt cronjob, root):
  45 4 * * *  .../z0-drift-reset.py >> /mnt/main-data/channelz0/.z0-station/drift-reset.log 2>&1

The threshold is generous on purpose: normal HLS latency measures as 10-20 s
of "drift" and the sentinel's own warn line is 45 s. Below RESET_AT the
restart would buy nothing a viewer can see.

Flags, for humans and tests:
  --force        ignore the off-hours window (NOT the threshold)
  --dry-run      decide, log, but echo instead of restarting
  --simulate N   pretend the measured drift is N seconds (skips the confirm
                 sample; measurement itself still runs, so a dead tower still
                 short-circuits first)
"""

import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

TOWER = "https://watch.ch0.ripostelabs.xyz"
RESET_AT = 60.0          # seconds of drift worth acting on
CONFIRM_WAIT = 30        # both samples must clear RESET_AT
OFF_HOURS = range(3, 6)  # local (America/Vancouver) hours the restart may run
SETTLE = 75              # seconds to let the fresh session produce segments
UPLINK = "z0-uplink"
MASTER = "/hls/stream.m3u8"   # master on the tower; its one variant is wherever it says


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


# Cloudflare in front of the tower answers urllib's default agent with 403
# (since 2026-09-16 01:45Z); every other tower client here already names itself.
USER_AGENT = "channel-z0/1.0 (z0-drift-reset)"


def fetch(path, timeout=15):
    url = path if path.startswith("http") else TOWER + path
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def variant_url(master):
    """First media playlist named by the master, absolute; relative -> tower."""
    for line in master.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line if line.startswith("http") else TOWER + "/" + line.lstrip("/")
    raise ValueError("master playlist names no variant")


def measure():
    """Return drift in seconds, or None with a reason when unmeasurable."""
    try:
        status = json.loads(fetch("/api/status"))
    except Exception as e:
        return None, f"status unreachable ({e})"
    if not status.get("online"):
        return None, "tower reports offline — a reset is z0-leader's job, not ours"

    server = datetime.fromisoformat(status["serverTime"].replace("Z", "+00:00"))
    # Follow the master to the variant: since the R2 offload (2026-09-15) the
    # variant lives on the CDN host, and the old fixed tower path 404s.
    try:
        playlist = fetch(variant_url(fetch(MASTER)))
    except Exception as e:
        return None, f"playlist unreachable ({e})"
    pdts = [l.split(":", 1)[1] for l in playlist.splitlines()
            if l.startswith("#EXT-X-PROGRAM-DATE-TIME:")]
    if not pdts:
        return None, "playlist has no PDT tags"

    newest = datetime.fromisoformat(pdts[-1].replace("Z", "+00:00"))
    return (server - newest).total_seconds(), None


def main():
    args = sys.argv[1:]
    force = "--force" in args
    dry = "--dry-run" in args
    sim = None
    if "--simulate" in args:
        sim = float(args[args.index("--simulate") + 1])

    drift, why = measure()
    if drift is None:
        print(f"{now()} skip: {why}")
        return 0
    if sim is not None:
        print(f"{now()} measured {drift:.0f}s, simulating {sim:.0f}s")
        drift = sim

    if drift < RESET_AT:
        print(f"{now()} ok: drift {drift:.0f}s < {RESET_AT:.0f}s, nothing to do")
        return 0

    hour = time.localtime().tm_hour
    if hour not in OFF_HOURS and not force:
        print(f"{now()} hold: drift {drift:.0f}s but {hour:02d}h is not off "
              f"hours ({OFF_HOURS.start:02d}-{OFF_HOURS.stop - 1:02d}) — "
              f"will act on the night run")
        return 0

    if sim is None:
        # One sample can be a playlist caught mid-write; two 30 s apart
        # cannot, and a genuinely growing drift only reads higher.
        time.sleep(CONFIRM_WAIT)
        second, why = measure()
        if second is None:
            print(f"{now()} skip: confirm sample failed ({why})")
            return 0
        if second < RESET_AT:
            print(f"{now()} ok: drift settled to {second:.0f}s on confirm, "
                  f"nothing to do")
            return 0
        drift = second

    if dry:
        print(f"{now()} DRY RUN: drift {drift:.0f}s — would docker restart "
              f"{UPLINK}")
        return 0

    print(f"{now()} drift {drift:.0f}s — restarting {UPLINK}")
    r = subprocess.run(["docker", "restart", UPLINK],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{now()} FAIL: docker restart rc={r.returncode}: "
              f"{r.stderr.strip()[:200]}")
        return 1

    time.sleep(SETTLE)
    after, why = measure()
    if after is None:
        print(f"{now()} restarted, but post-check unmeasurable: {why}")
    else:
        print(f"{now()} restarted: drift {drift:.0f}s -> {after:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
