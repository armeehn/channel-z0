#!/usr/bin/env python3
"""Channel Z0 — bounce ErsatzTV when its HLS session starts starving the uplink.

ErsatzTV v26.7.1 keeps a work-ahead chunk of the next item so hand-offs never
starve the live edge. After days in one session it stops working ahead; every
item hand-off then stalls the channel for 10-30 s, Owncast (hardcoded 10 s read
deadline) drops the RTMP session, and z0-leader restarts the uplink. Seen
2026-09-11: 19 -> 21 -> 57 -> 174 uplink restarts/day over four days; a
container restart cleared it at once. This guard counts uplink restarts in the
last hour (the symptom, logged locally by z0-uplink) and restarts ErsatzTV when
the storm is on. It does not read the segmenter's playlist: the on-disk
live.m3u8 is rewritten by concurrent encoders and its lead swings between
~0 and ~60 s within one item, so it is not a usable signal.

Cron (midclt cronjob, root, every 10 min):
  z0-lead-guard.py >> /mnt/main-data/channelz0/.z0-station/lead-guard.log 2>&1

Flags:
  --dry-run   decide and log, never restart
  --status    print restarts in the window, then exit
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

CONTAINER = "z0-ersatztv"
UPLINK = "z0-uplink"
WINDOW = "60m"           # docker logs --since window
STORM = 6                # uplink restarts within WINDOW = the session is starving
COOLDOWN = 2 * 3600      # seconds between ErsatzTV restarts
STATE = "/mnt/main-data/channelz0/.z0-station/lead-guard.json"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def uplink_restarts():
    """How many times z0-leader started the uplink within WINDOW."""
    r = subprocess.run(["docker", "logs", "--since", WINDOW, UPLINK],
                       capture_output=True, text=True)
    return sum(1 for line in (r.stdout + r.stderr).splitlines()
               if "uplink started" in line)


def load_state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {"last_restart": 0}


def save_state(state):
    tmp = STATE + ".tmp"
    json.dump(state, open(tmp, "w"))
    os.replace(tmp, STATE)


def main():
    dry = "--dry-run" in sys.argv
    restarts = uplink_restarts()

    if "--status" in sys.argv:
        print(f"{now()} uplink restarts/{WINDOW} {restarts}")
        return 0

    state = load_state()
    if restarts < STORM:
        if restarts:
            print(f"{now()} ok: {restarts} uplink restarts/{WINDOW} < {STORM}")
        return 0

    since = time.time() - state["last_restart"]
    if since < COOLDOWN:
        print(f"{now()} hold: storm ({restarts} restarts/{WINDOW}) but {CONTAINER} "
              f"restarted {since/60:.0f} min ago, cooldown {COOLDOWN//60} min")
        return 0

    if dry:
        print(f"{now()} DRY RUN: storm ({restarts} restarts/{WINDOW}) "
              f"— would docker restart {CONTAINER}")
        return 0

    r = subprocess.run(["docker", "restart", CONTAINER], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{now()} FAIL: docker restart rc={r.returncode}: {r.stderr.strip()}")
        return 1

    state["last_restart"] = time.time()
    save_state(state)
    print(f"{now()} restarted {CONTAINER}: {restarts} uplink restarts/{WINDOW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
