#!/usr/bin/env python3
# Channel Z0 — the now-playing bridge.
#
# ErsatzTV knows what's on the air; Owncast doesn't. This closes the gap: it
# reads ErsatzTV's XMLTV guide, works out what's airing *right now*, and writes
# that into Owncast's stream title. The storefront polls Owncast's /api/status
# and shows the title live, so the "NOW SHOWING" line on the site is the real
# program, not the hand-typed schedule.
#
# Runs forever, polling every Z0_NOWPLAYING_POLL seconds. Only pushes when the
# title actually changes, so Owncast isn't spammed. Pure stdlib — no pip.
#
# Config (from /etc/channel-z0.env or the compose .env):
#   Z0_CHANNEL_XMLTV   ErsatzTV guide URL (default http://127.0.0.1:8409/iptv/xmltv.xml)
#   Z0_CHANNEL_ID      XMLTV channel id to follow (optional; default: the only/first one)
#   Z0_WATCH_DOMAIN    Owncast host, e.g. watch.ch0.ripostelabs.xyz  (required)
#   Z0_OWNCAST_TOKEN   Owncast access token with the "set stream title" scope (required)
#   Z0_NOWPLAYING_POLL seconds between checks (default 60)
#   Z0_NOWPLAYING_PREFIX  optional prefix, e.g. "CH0 · " (default none)

import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# The watch host sits behind a CDN whose bot check refuses the stock
# "Python-urllib" agent (docs/scaling.tex, tier 2). Say who is calling.
USER_AGENT = "channel-z0-nowplaying/1"

XMLTV = os.environ.get("Z0_CHANNEL_XMLTV", "http://127.0.0.1:8409/iptv/xmltv.xml")
CHANNEL_ID = os.environ.get("Z0_CHANNEL_ID", "").strip()
WATCH = os.environ.get("Z0_WATCH_DOMAIN", "").strip()
TOKEN = os.environ.get("Z0_OWNCAST_TOKEN", "").strip()
POLL = int(os.environ.get("Z0_NOWPLAYING_POLL", "60"))
PREFIX = os.environ.get("Z0_NOWPLAYING_PREFIX", "")


def log(msg):
    print(f"nowplaying: {msg}", flush=True)


def parse_xmltv_time(raw):
    # XMLTV stamps look like "20260725190000 +0000" (offset optional).
    raw = (raw or "").strip()
    if not raw:
        return None
    stamp, _, offset = raw.partition(" ")
    try:
        dt = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    offset = offset.strip()
    if offset and offset[0] in "+-" and len(offset) >= 5:
        sign = 1 if offset[0] == "+" else -1
        hours, mins = int(offset[1:3]), int(offset[3:5])
        from datetime import timedelta
        return dt.replace(tzinfo=timezone(sign * timedelta(hours=hours, minutes=mins)))
    return dt.replace(tzinfo=timezone.utc)


def current_program():
    with urllib.request.urlopen(XMLTV, timeout=15) as r:
        tree = ET.parse(r)
    now = datetime.now(timezone.utc)
    best = None
    for prog in tree.getroot().findall("programme"):
        if CHANNEL_ID and CHANNEL_ID not in (prog.get("channel") or ""):
            continue
        start = parse_xmltv_time(prog.get("start"))
        stop = parse_xmltv_time(prog.get("stop"))
        if not start or not stop:
            continue
        if start <= now < stop:
            title = (prog.findtext("title") or "").strip()
            sub = (prog.findtext("sub-title") or "").strip()
            if title:
                best = f"{title} — {sub}" if sub and sub != title else title
            break
    return best


def push_title(value):
    body = json.dumps({"value": value}).encode()
    req = urllib.request.Request(
        f"https://{WATCH}/api/integrations/streamtitle",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    if not WATCH or not TOKEN:
        log("Z0_WATCH_DOMAIN and Z0_OWNCAST_TOKEN are required — see .env.example. Idle.")
        # Don't crash-loop the container; just wait so logs stay readable.
        while True:
            time.sleep(3600)
    log(f"following {XMLTV} -> https://{WATCH} every {POLL}s")
    last = None
    while True:
        try:
            title = current_program()
            if title:
                marquee = f"{PREFIX}{title}"
                if marquee != last:
                    push_title(marquee)
                    log(f"now showing: {marquee}")
                    last = marquee
        except Exception as e:  # keep the bridge alive through any hiccup
            log(f"skip: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
