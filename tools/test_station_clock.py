#!/usr/bin/env python3
"""The station clock is the station's zone, and a seam cut leaves no overlap.

BC stopped changing its clocks in 2026: America/Vancouver is UTC-7 all year.
The playout node ran on America/Los_Angeles, which fell back to UTC-8 on
2026-11-01, so every `pad_until` in the schedule landed one hour late in
Kelowna (ATOMIC TUESDAY at 20:58). Nothing in the repo named the container's
zone at all; the node's was typed in by hand.

Moving a built playout onto the right clock is a cut at 06:00 in the NEW zone,
and the items already built end their day on the OLD clock. So for once an
item runs across the seam, and it has to end on it.

    python3 tools/test_station_clock.py
"""
import importlib.util
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WRONG_ZONE = "America/Los_Angeles"
fails = []


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


# ── the zone has one source, and every place a node gets it from agrees ──────
zone = None
for line in read("station.env").splitlines():
    if line.startswith("TIMEZONE="):
        zone = line.split("=", 1)[1].strip()
if not zone:
    fails.append("station.env has no TIMEZONE")

if "TZ: ${TZ:-%s}" % zone not in read("playout/compose.yml"):
    fails.append("playout/compose.yml does not hand ErsatzTV TZ, defaulting to %s" % zone)
if "\nTZ=%s\n" % zone not in read(".env.example"):
    fails.append(".env.example does not set TZ=%s" % zone)
if "\nTZ=%s\n" % zone not in read("tools/bootstrap-node.sh"):
    fails.append("tools/bootstrap-node.sh does not write TZ=%s into .env" % zone)

tracked = subprocess.run(["git", "-C", REPO, "grep", "-l", WRONG_ZONE, "--", "playout", "tools",
                          ".env.example"], capture_output=True, text=True).stdout.split()
tracked = [f for f in tracked if f != "tools/test_station_clock.py"]
if tracked:
    fails.append("%s is still named in %s" % (WRONG_ZONE, ", ".join(tracked)))

# ── an item that runs across the seam ends on it ─────────────────────────────
spec = importlib.util.spec_from_file_location("align", os.path.join(HERE, "z0-day-align.py"))
align = importlib.util.module_from_spec(spec)
spec.loader.exec_module(align)

SEAM = "2026-11-12 13:00:00"
ROWS = [
    # Id, Start, Finish, InPoint, OutPoint
    (1, "2026-11-12 12:32:04.7143108", "2026-11-12 12:55:59.6478108", "00:00:00", "00:23:54.9335000"),
    (2, "2026-11-12 12:55:59.6478108", "2026-11-12 13:07:47.0478108", "00:00:00", "00:11:47.4000000"),
    (3, "2026-11-12 13:07:47.0478108", "2026-11-12 13:16:06.7803778", "00:00:00", "00:08:19.7325670"),
]


def playout(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("create table PlayoutItem (Id integer primary key, Start text, Finish text, "
                 "InPoint text, OutPoint text, CustomTitle text)")
    conn.executemany("insert into PlayoutItem values (?,?,?,?,?,'THE ALL-NIGHT SHOW')", rows)
    return conn


if not hasattr(align, "trim_straddler"):
    fails.append("z0-day-align.py has no trim_straddler: an item across the seam overlaps the new block")
else:
    conn = playout(ROWS)
    trimmed = align.trim_straddler(conn.cursor(), SEAM)
    got = {r[0]: r[1:] for r in conn.execute("select Id, Start, Finish, InPoint, OutPoint from PlayoutItem")}

    if not trimmed:
        fails.append("the straddling item was not reported as trimmed")
    if got[2][1] != SEAM:
        fails.append("straddler finishes at %r, not on the seam" % got[2][1])
    # 13:00:00 − 12:55:59.6478108 = 00:04:00.3521892
    if got[2][3] != "00:04:00.3521892":
        fails.append("straddler OutPoint is %r, expected 00:04:00.3521892" % got[2][3])
    if got[1] != ROWS[0][1:] or got[3] != ROWS[2][1:]:
        fails.append("an item that does not cross the seam was changed")

    # The everyday case: COLOUR BARS already ends on the seam. Nothing to do.
    clean = playout([(1, "2026-11-12 12:29:40.5723778", SEAM, "00:00:00", "00:30:19.4276222")])
    if align.trim_straddler(clean.cursor(), SEAM):
        fails.append("an item ending exactly on the seam was trimmed")

    # An item entered part-way keeps its InPoint; OutPoint moves with it.
    late = playout([(1, "2026-11-12 12:59:00", "2026-11-12 13:10:00", "00:05:00", "00:16:00")])
    align.trim_straddler(late.cursor(), SEAM)
    if late.execute("select OutPoint from PlayoutItem").fetchone()[0] != "00:06:00":
        fails.append("OutPoint must be InPoint plus the time left before the seam")

if fails:
    print("FAIL")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok: station zone is %s everywhere a node reads it; a seam cut leaves no overlap" % zone)
