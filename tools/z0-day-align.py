#!/usr/bin/env python3
"""
z0-day-align.py — keep the day block that AIRS on the day the storefront promises.

  ── THE FAILURE THIS EXISTS TO CATCH ───────────────────────────────────────
  ErsatzTV's sequential scheduler has no day-of-week primitive. The seven day
  blocks in channel-z0.yml run in order and `repeat: true` returns to the
  first; which block lands on which weekday is decided *entirely* by the day
  the playout was last built or reset on. Reset the playout on a Saturday with
  a file rotated to start on FRIDAY and the channel airs Friday's programming
  on Saturday, Saturday's on Sunday, for ever — and nothing reports it. The
  guide is self-consistent, the DB is healthy, every status check is green,
  and the only symptom is that ch0.ripostelabs.xyz promises WORKBENCH THEATRE
  while the transmitter is showing ATOMIC TUESDAY.

  That is exactly what happened on 2026-08-15: tools/z0-presignon-reset.sh was
  run at 05:15 on a Saturday against the FRIDAY-rotated file, and the channel
  spent the next four days one day behind its own published schedule.

  So: this checks, and if asked, repairs.
  ───────────────────────────────────────────────────────────────────────────

WHAT IT CHECKS
  Each broadcast day (06:00 local → 06:00 local, which is exactly one day
  block: the file's first instruction is the 06:00 sign-on interval and its
  last is COLOUR BARS padding to 06:00 tomorrow) carries a 20:00 tentpole whose
  title is unique to its weekday — MONDAY NIGHT NOIR, ATOMIC TUESDAY, … Those
  names come from z0-build-schedule.py's own WEEK table, which is the same
  table the storefront grid in site/index.html and docs/programming.tex are
  written from. So "the tentpole that is built for Wednesday is the one the
  Wednesday tab shows" is a complete alignment test, stated in the terms the
  viewer sees.

HOW IT REPAIRS  (--apply)
  NOT with a playout reset. A reset re-enters the week at instruction one at
  whatever time it is run, which collapses every `pad_until` already in the
  past and — measured across four resets — costs the FOLLOWING day its entire
  morning. Instead this cuts at a 06:00 block boundary, the one seam in the
  week where "start of a day block" and "start of a day" are the same instant:

    1. regenerate channel-z0.yml with --start-day <weekday of that boundary>
    2. stop ErsatzTV
    3. delete the playout items and history at/after the boundary
       (everything airing between now and the boundary is left alone)
    4. point the playout anchor at the boundary, instruction index 0
    5. start ErsatzTV, let it rebuild forward, restart the uplink

  The seam is the LAST 06:00 inside what has already been built, not the first
  one after now — see cut_boundary() for why that distinction is the whole
  difference between repairing the week and breaking a morning. It means the
  repair lands one broadcast day later than you might expect, and that is
  deliberate. Nothing already scheduled before the seam is touched, and the
  cost is a ~1 minute stop of the ErsatzTV container.

DEPLOYING A NEW SCHEDULE  (--redeploy)
  There is no safe way to swap channel-z0.yml under a running playout by hand.
  The anchor stores an instruction INDEX into the deployed file (and the index
  is into the flattened list, with `sequence:` expanded, so you cannot even
  compute it). Deploy a file with a different number of instructions and the
  next build resumes at that index in the NEW file — which is now a different
  instruction. The week does not fail; it lands somewhere else, mid-block, and
  the only symptom is a day that looks subtly wrong.

  `--redeploy` is the supported way: it does the full repair — regenerate for
  the seam's weekday, deploy, cut, re-enter at instruction 0 — whether or not
  anything is misaligned. Use it after any change to the generator.

USAGE
    z0-day-align.py                 # check, print a table, exit 1 if misaligned
    z0-day-align.py --apply         # check, and repair at the next 06:00 seam
    z0-day-align.py --redeploy      # deploy the current generator's week, aligned
    z0-day-align.py --apply --quiet-when-ok    # for cron

EXIT CODES
    0  aligned (or repaired successfully)
    1  misaligned and --apply was not given
    2  something went wrong (repair failed, or the state is unreadable)
"""

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

# The container runs on this timezone, and every time in the schedule file is
# local to it. cron does not necessarily agree, so pin it rather than inherit.
DEFAULT_TZ = "America/Vancouver"

CONFIG_DIR = "/mnt/solid-state/ersatztv"
SCHEDULE_NAME = "channel-z0.yml"
CONTAINER = "z0-ersatztv"
UPLINK = "z0-uplink"

# The day block runs 06:00 → 06:00. This is not a preference: it is where the
# generated file's block boundary actually falls (instruction 0 is the 8-second
# station interval that lands at 06:00:00, and the block's last instruction is
# COLOUR BARS with `pad_until: '06:00'` + `tomorrow: true`).
DAY_START_HOUR = 6

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday"]


def log(msg):
    print(msg, flush=True)


def die(msg, code=2):
    print(f"z0-day-align: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ── the week, read from the generator so there is ONE copy of it ─────────────
def load_primes(tools_dir):
    """{'monday': 'MONDAY NIGHT NOIR', …} straight out of z0-build-schedule.py.

    Imported rather than copied: a second hand-maintained table of the same
    names is a lie waiting to happen, and this check is only worth anything if
    it is testing against what the generator (and therefore the storefront
    grid) actually says.
    """
    import importlib.util
    path = os.path.join(tools_dir, "z0-build-schedule.py")
    if not os.path.exists(path):
        die(f"generator not found at {path}")
    # The generator imports z0_intervals as a sibling module.
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    spec = importlib.util.spec_from_file_location("z0_build_schedule", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    primes = {}
    for day, plan in mod.WEEK.items():
        primes[day] = plan["prime"][0]
    missing = [d for d in WEEKDAYS if d not in primes]
    if missing:
        die(f"generator WEEK is missing {missing}")
    if len(set(primes.values())) != 7:
        die("the seven 20:00 tentpole titles are not unique; this check "
            "cannot identify a day block by its tentpole any more")
    return primes


# ── time helpers ─────────────────────────────────────────────────────────────
def to_utc_text(local_dt):
    """The DB stores UTC as 'YYYY-MM-DD HH:MM:SS.fffffff' — a SPACE, not a T.

    Comparisons against these strings only work if the other side has the same
    shape, which is why this returns text and not a datetime.
    """
    return local_dt.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def local_naive(y, m, d, hour=0):
    return dt.datetime(y, m, d, hour).astimezone()


def broadcast_date(local_dt):
    """Which broadcast day a wall-clock moment belongs to (06:00 → 06:00)."""
    d = local_dt.date()
    if local_dt.hour < DAY_START_HOUR:
        d -= dt.timedelta(days=1)
    return d


def next_boundary(now_local):
    """The next 06:00 strictly in the future."""
    today6 = dt.datetime.combine(now_local.date(),
                                 dt.time(DAY_START_HOUR)).astimezone()
    if now_local < today6:
        return today6
    return today6 + dt.timedelta(days=1)


def cut_boundary(now_local, frontier_local):
    """Where to cut: the LAST 06:00 that is still inside what has already been
    built, not the first one after now.

    This is the difference between a repair and a new fault. ErsatzTV builds
    the playout out to `playout.days_to_build` (2) ahead of the wall clock and
    then extends it a little at a time. Cut at tomorrow's 06:00 and the next
    build has to lay down a day and a half in a single pass — and the overnight
    `pad_until` in that pass does not stop at 05:26. It runs until the build
    frontier: measured three times on a screener replica at 09:16, 10:15 and
    11:27, each time swallowing the morning behind it (no sign-on, no cartoon
    block, straight from THE ALL-NIGHT SHOW to PRELINGER at 09:20). Only the
    FIRST night after the cut does it; the six nights after that were correct
    in a seven-day build, which is why this is worth working around rather than
    fixing in the schedule. Nothing in ErsatzTV logs it.

    Cutting at the last boundary inside the frontier instead means the rebuild
    is a few hours long and every night after it is laid down by the same
    ordinary incremental extension that has been getting them right all along.
    The cost is that the repair lands one broadcast day later.
    """
    latest = dt.datetime.combine(frontier_local.date(),
                                 dt.time(DAY_START_HOUR)).astimezone()
    if latest > frontier_local:
        latest -= dt.timedelta(days=1)
    first = next_boundary(now_local)
    return max(latest, first)


def frontier(conn):
    """How far the playout has been built — the anchor's next start."""
    row = conn.execute("select NextStart from PlayoutAnchor limit 1").fetchone()
    if not row:
        die("no playout anchor; the playout has never been built")
    stamp = dt.datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
    return stamp.replace(tzinfo=dt.timezone.utc).astimezone()


# ── reading the playout ──────────────────────────────────────────────────────
def open_db(db_path, readonly=True):
    if readonly:
        # mode=ro so a check can never be the thing that corrupts the channel.
        uri = f"file:{db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=15)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def built_days(conn, primes):
    """[(broadcast_date, aired_prime_title, start_local)] for every day block
    that has its 20:00 tentpole built."""
    names = tuple(primes.values())
    q = ("select CustomTitle, Start from PlayoutItem "
         f"where CustomTitle in ({','.join('?' * len(names))}) order by Start")
    out = []
    for title, start in conn.execute(q, names):
        # Start is UTC text; make it local.
        stamp = dt.datetime.strptime(start[:19], "%Y-%m-%d %H:%M:%S")
        local = stamp.replace(tzinfo=dt.timezone.utc).astimezone()
        out.append((broadcast_date(local), title, local))
    return out


def over_all(conn, hours=6):
    """Contiguous runs of one title longer than `hours` — the fingerprint of a
    pad that has eaten a day.

    `pad_until` names a time on the day the instruction is reached and does not
    roll forward, so an instruction reached at 00:03 and targeting 23:00 pads
    for 23 hours. It fills it, silently, and everything after it slides a day
    late. Nothing else in a healthy day comes close to six hours — the longest
    real block is the overnight variety strand at about five and a half.
    """
    rows = conn.execute(
        "select datetime(Start,'localtime'), datetime(Finish,'localtime'), "
        "CustomTitle from PlayoutItem order by Start").fetchall()
    out = []
    run_title, run_start, run_end = None, None, None
    for start, finish, title in rows:
        if title != run_title:
            if run_title and run_start:
                span = (dt.datetime.fromisoformat(run_end)
                        - dt.datetime.fromisoformat(run_start))
                if span >= dt.timedelta(hours=hours):
                    out.append((run_start, run_end, run_title, span))
            run_title, run_start = title, start
        run_end = finish
    if run_title and run_start and run_end:
        span = (dt.datetime.fromisoformat(run_end)
                - dt.datetime.fromisoformat(run_start))
        if span >= dt.timedelta(hours=hours):
            out.append((run_start, run_end, run_title, span))
    return out


def check(conn, primes, since=None):
    """Returns (rows, misaligned_dates). rows = (date, expected, aired, ok).

    `since` drops broadcast days that belong to the phase BEFORE the last cut.
    A cut only moves the week from its seam forward, so the days built before
    it stay on the old rotation for ever; judging them again would make every
    later run think the channel is still broken and cut it a second time.
    """
    rows = []
    bad = []
    for date, title, _local in built_days(conn, primes):
        if since and date < since:
            continue
        expected = primes[WEEKDAYS[date.weekday()]]
        ok = (title == expected)
        rows.append((date, expected, title, ok))
        if not ok:
            bad.append(date)
    return rows, bad


def state_path(config):
    return os.path.join(config, ".z0-day-align.json")


def load_cut(config):
    """The seam of the last repair, as a local date (or None)."""
    try:
        with open(state_path(config)) as fh:
            return dt.date.fromisoformat(json.load(fh)["cut_boundary"][:10])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_cut(config, boundary):
    with open(state_path(config), "w") as fh:
        json.dump({"cut_boundary": boundary.isoformat(),
                   "written": dt.datetime.now().astimezone().isoformat()}, fh)


def report(rows, now_local):
    if not rows:
        log("  (no day tentpoles built — nothing to compare)")
        return
    log(f"  {'BROADCAST DAY':<22}  {'STOREFRONT PROMISES':<24}  "
        f"{'PLAYOUT BUILT':<24}")
    for date, expected, aired, ok in rows:
        when = "today" if date == broadcast_date(now_local) else ""
        mark = "ok " if ok else "OFF"
        log(f"  {date:%a %Y-%m-%d} {when:<7} {expected:<24}  "
            f"{aired:<24}  {mark}")


# ── the repair ───────────────────────────────────────────────────────────────
def run(cmd, **kw):
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kw)


def regenerate(tools_dir, start_day, dry_path):
    gen = os.path.join(tools_dir, "z0-build-schedule.py")
    r = run([sys.executable, gen, "--start-day", start_day, "--out", dry_path],
            cwd=tools_dir)
    if r.returncode != 0:
        die(f"generator failed: {r.stderr.strip() or r.stdout.strip()}")
    log(f"  generated {dry_path}: {r.stdout.strip()}")


def apply_repair(args, primes, now_local, boundary):
    db_path = os.path.join(args.config, "ersatztv.sqlite3")
    schedule = os.path.join(args.config, SCHEDULE_NAME)
    start_day = WEEKDAYS[boundary.weekday()]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(args.config, f".z0-backup-align-{stamp}")
    os.makedirs(backup, exist_ok=True)

    log(f"\nREPAIR — cutting in at {boundary:%Y-%m-%d %H:%M %Z} "
        f"({start_day.upper()})")

    # 1. the file, rotated for the day the channel will resume on
    staged = os.path.join(backup, "channel-z0.new.yml")
    regenerate(args.tools, start_day, staged)
    shutil.copy2(schedule, os.path.join(backup, "channel-z0.old.yml"))

    # 2. stop the channel. Everything after this point has an EXIT path that
    #    starts it again — "the repair didn't happen" is an acceptable outcome,
    #    "the channel is off air" is not.
    try:
        _stop_edit_start(args, db_path, schedule, staged, backup, boundary)
    finally:
        if not _running(args.container):
            log(f"  starting {args.container} (recovery path)")
            run(["docker", "start", args.container])

    # 3. let it rebuild, then re-check
    log("  waiting for the rebuild")
    boundary_utc = to_utc_text(boundary)
    for _ in range(60):
        time.sleep(5)
        try:
            conn = open_db(db_path)
            n = conn.execute(
                "select count(*) from PlayoutItem where Start >= ?",
                (boundary_utc,)).fetchone()[0]
            conn.close()
        except sqlite3.Error:
            continue
        if n > 20:
            log(f"  rebuilt: {n} items at/after the boundary")
            break
    else:
        die("the playout did not rebuild past the boundary; the channel is "
            "running but the week beyond tomorrow's sign-on is EMPTY")

    # Record the seam. Everything built before it stays on the old rotation
    # for ever, so without this the next run reads those days, calls the
    # channel broken and cuts it again — every night, on a timer.
    save_cut(args.config, boundary)

    # 4. the uplink does not survive an ErsatzTV restart: it keeps a frozen
    #    RTMP session and Owncast keeps reporting online with the old title.
    if args.uplink:
        log(f"  restarting {args.uplink}")
        run(["docker", "restart", args.uplink])


def _running(name):
    r = run(["docker", "ps", "--format", "{{.Names}}"])
    return name in r.stdout.split()


def _stop_edit_start(args, db_path, schedule, staged, backup, boundary):
    log(f"  stopping {args.container}")
    r = run(["docker", "stop", "-t", "30", args.container])
    if r.returncode != 0 and _running(args.container):
        die(f"could not stop {args.container}: {r.stderr.strip()}")

    # back the DB up only once the app has let go of it
    conn = open_db(db_path, readonly=False)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copy2(db_path, os.path.join(backup, "ersatztv.sqlite3"))
    log(f"  backup -> {backup}")

    shutil.copy2(staged, schedule)
    log(f"  deployed {schedule} (rotated to start "
        f"{WEEKDAYS[boundary.weekday()].upper()})")

    boundary_utc = to_utc_text(boundary)
    conn = open_db(db_path, readonly=False)
    cur = conn.cursor()
    # The last item that still airs before the seam decides what the anchor's
    # guide group carries over; the first instruction of a block opens a new
    # group with `epg_group: true`, so hand it the group as it stands, unlocked.
    row = cur.execute(
        "select GuideGroup, datetime(Start,'localtime'), CustomTitle "
        "from PlayoutItem where Start < ? order by Start desc limit 1",
        (boundary_utc,)).fetchone()
    if not row:
        die("no playout items before the boundary — refusing to cut a playout "
            "that has nothing to keep")
    guide_group, last_local, last_title = row
    log(f"  last item kept: {last_local}  {last_title}  (guide group {guide_group})")

    cur.execute("delete from PlayoutItem where Start >= ?", (boundary_utc,))
    n_items = cur.rowcount
    cur.execute('delete from PlayoutHistory where "When" >= ?', (boundary_utc,))
    n_hist = cur.rowcount
    # PlayoutItemGraphicsElement cascades, but only with foreign_keys ON — and
    # an orphan there silently un-decorates a programme, so make sure.
    cur.execute("delete from PlayoutItemGraphicsElement where PlayoutItemId "
                "not in (select Id from PlayoutItem)")

    context = json.dumps({
        "InstructionIndex": 0,
        "GuideGroup": guide_group,
        "GuideGroupLocked": False,
        "ChannelWatermarkIds": [],
        "ScheduleIndices": {"": 0},
    })
    cur.execute(
        "update PlayoutAnchor set NextStart = ?, NextInstructionIndex = 0, "
        "DurationFinish = NULL, InDurationFiller = 0, InFlood = 0, "
        "MultipleRemaining = NULL, Context = ? where PlayoutId = "
        "(select PlayoutId from PlayoutAnchor limit 1)",
        (boundary_utc + ".0000000", context))
    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        die(f"expected exactly one playout anchor, updated {cur.rowcount}")
    conn.commit()
    ok = cur.execute("PRAGMA quick_check").fetchone()[0]
    conn.close()
    log(f"  cut: {n_items} items removed at/after the seam, "
        f"{n_hist} history rows, quick_check={ok}")

    log(f"  starting {args.container}")
    r = run(["docker", "start", args.container])
    if r.returncode != 0:
        die(f"could not start {args.container}: {r.stderr.strip()}")


def main():
    ap = argparse.ArgumentParser(
        description="Check (and optionally repair) which weekday Channel Z0's "
                    "day blocks are airing on.")
    ap.add_argument("--config", default=CONFIG_DIR,
                    help="ErsatzTV config dir (holds the DB and the schedule)")
    ap.add_argument("--tools", default=os.path.dirname(os.path.abspath(__file__)),
                    help="directory holding z0-build-schedule.py")
    ap.add_argument("--container", default=CONTAINER)
    ap.add_argument("--uplink", default=UPLINK,
                    help="restarted after a repair; '' to skip")
    ap.add_argument("--tz", default=DEFAULT_TZ)
    ap.add_argument("--apply", action="store_true",
                    help="repair a misalignment at the next 06:00 boundary")
    ap.add_argument("--redeploy", action="store_true",
                    help="deploy the current generator's schedule and re-enter "
                         "the week at the seam even if nothing is misaligned "
                         "(the only safe way to change the schedule file)")
    ap.add_argument("--quiet-when-ok", action="store_true",
                    help="print nothing when the channel is already aligned")
    args = ap.parse_args()

    os.environ["TZ"] = args.tz
    time.tzset()

    db_path = os.path.join(args.config, "ersatztv.sqlite3")
    if not os.path.exists(db_path):
        die(f"no database at {db_path}")

    primes = load_primes(args.tools)
    now_local = dt.datetime.now().astimezone()
    since = load_cut(args.config)
    conn = open_db(db_path)
    rows, bad = check(conn, primes, since)
    over = [o for o in over_all(conn)
            if not since or dt.date.fromisoformat(o[1][:10]) >= since]
    built_to = frontier(conn)
    conn.close()

    boundary = cut_boundary(now_local, built_to)
    over_ahead = [o for o in over
                  if dt.datetime.fromisoformat(o[1]) > boundary.replace(tzinfo=None)]

    if args.redeploy:
        log(f"Channel Z0 day alignment — {now_local:%Y-%m-%d %H:%M %Z}")
        report(rows, now_local)
        if boundary <= now_local:
            die("no usable seam ahead; re-run after the next sign-on")
        log("  REDEPLOY requested — cutting the week in at the seam so the new "
            "schedule is entered at instruction 0.")
        apply_repair(args, primes, now_local, boundary)
        conn = open_db(db_path)
        signon = conn.execute(
            "select datetime(Start,'localtime') from PlayoutItem "
            "where Start >= ? and CustomTitle = 'SIGN-ON' order by Start limit 1",
            (to_utc_text(boundary),)).fetchone()
        conn.close()
        if not signon:
            die("no SIGN-ON was built after the cut — the block did not restart "
                "at instruction 0")
        log(f"  block restarted: SIGN-ON at {signon[0]} "
            f"(expected {boundary:%Y-%m-%d} 06:00)")
        return 0

    if since and not rows:
        if not args.quiet_when_ok:
            log(f"Channel Z0 day alignment — {now_local:%Y-%m-%d %H:%M %Z}")
            log(f"  the week was cut back onto the calendar at {since} and "
                f"nothing past that seam carries a day tentpole yet; "
                f"re-check once the playout has built past 20:00.")
        return 0

    if not bad and not over:
        if not args.quiet_when_ok:
            log(f"Channel Z0 day alignment — {now_local:%Y-%m-%d %H:%M %Z}")
            report(rows, now_local)
            log("  ALIGNED: every built day block matches the weekday the "
                "storefront publishes.")
        return 0

    log(f"Channel Z0 day alignment — {now_local:%Y-%m-%d %H:%M %Z}")
    report(rows, now_local)
    if bad:
        log(f"  MISALIGNED: {len(bad)} built day(s) do not match the "
            f"published grid.")
    for start, end, title, span in over:
        log(f"  OVERRUN: {title} runs {span} — {start} → {end}. A pad has "
            f"eaten a day; everything after it airs late.")

    if not args.apply:
        log("  (run again with --apply to cut the week back onto the calendar "
            "at the next 06:00 sign-on)")
        return 1

    if boundary <= now_local:
        log("  no usable seam ahead; re-run after the next sign-on.")
        return 1

    apply_repair(args, primes, now_local, boundary)

    conn = open_db(db_path)
    now2 = dt.datetime.now().astimezone()
    rows, bad = check(conn, primes, boundary.date())
    over = over_all(conn)
    over = [o for o in over
            if dt.date.fromisoformat(o[1][:10]) >= boundary.date()]
    conn.close()
    log("\nafter the repair:")
    report(rows, now2)

    # The day tentpole is at 20:00 and the rebuild only reaches the old build
    # frontier, so it usually is not built yet and the table above cannot
    # confirm the day. What CAN be confirmed now is that the block restarted
    # where it was told to: instruction 0 is an 8-second interval landing on
    # 06:00:00 and instruction 5 is the sign-on.
    conn = open_db(db_path)
    signon = conn.execute(
        "select datetime(Start,'localtime'), CustomTitle from PlayoutItem "
        "where Start >= ? and CustomTitle = 'SIGN-ON' order by Start limit 1",
        (to_utc_text(boundary),)).fetchone()
    conn.close()
    if not signon:
        die("no SIGN-ON was built after the cut — the block did not restart "
            "at instruction 0")
    log(f"  block restarted: SIGN-ON at {signon[0]} "
        f"(expected {boundary:%Y-%m-%d} 06:00)")
    still = list(bad)
    for start, end, title, span in over:
        log(f"  OVERRUN REMAINS: {title} {span} — {start} → {end}")
    if still:
        die(f"still misaligned after the repair: {still}")
    if over:
        die("the week rebuilt with a block that runs over; the schedule "
            "itself is at fault, not the alignment")
    log("  ALIGNED from the next sign-on onward.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
