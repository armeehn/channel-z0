#!/usr/bin/env python3
"""
z0-build-schedule.py — emit playout/schedule/channel-z0.yml.

  ── WHY THIS IS GENERATED AND NOT HAND-WRITTEN ─────────────────────────────
  ErsatzTV's sequential scheduler has NO day-of-week primitive. The seven day
  blocks in the schedule simply run in order and `repeat: true` returns to the
  first; which block lands on which weekday is decided entirely by the day the
  playout is built or reset on. (Day-of-week and seasonal switching do exist in
  ErsatzTV — as PlayoutTemplate rows — but only for BLOCK playouts, not
  sequential ones.)

  So the file has to be rotated by hand every time the playout is reset on a
  different weekday, and nothing detects it and nothing reports it: the channel
  simply airs Monday Night Noir on a Wednesday while the storefront promises
  Workbench Theatre. That rotation is now a flag:

      z0-build-schedule.py --start-day thursday

  Build it for the day you are going to reset on. Build EARLY in that day, too:
  a playout built mid-afternoon starts at instruction one with every morning
  `pad_until` already in the past, so they collapse to nothing and the evening
  stretches to cover the day.
  ───────────────────────────────────────────────────────────────────────────

Usage:
    z0-build-schedule.py --start-day wednesday --out channel-z0.yml
    z0-build-schedule.py --start-day today --out channel-z0.yml
"""

import argparse
import datetime
import sys

import z0_intervals

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday"]

# ── The week ─────────────────────────────────────────────────────────────────
# One entry per weekday, Monday first. `matinee` is the 14:00 picture, `evening`
# the 20:00 one, `second` the 22:00 strand. Everything else is common to every
# day and lives in day_plan() below.
#
# Keys refer to _content.yml. A key that resolves to an empty pool is a silent
# hole, so never add one here without running z0-lists.py --check first.
# The 20:00 and 23:00 identities are the ONLY things that change between days.
# That is the whole trick: it is the cheapest possible way to make seven
# identical loops feel like seven different evenings, and it is what the
# storefront grid and docs/programming.md both promise. Titles and themes here
# are taken from docs/programming.md — if you change one, change all three or
# the guide-on-the-wall and the guide disagree.
WEEK = {
    "monday": dict(
        lunch=("LUNCH LOOPS — WALTZ HOUR", "pl_lunch_waltz"),
        matinee=("THE AFTERNOON PICTURE SHOW", "docs"),
        prime=("MONDAY NIGHT NOIR", "noir"),
        late=("AFTER HOURS", "soundies"),
    ),
    "tuesday": dict(
        lunch=("LUNCH LOOPS — POLKA HOUR", "pl_lunch_polka"),
        matinee=("THE AFTERNOON PICTURE SHOW", "features_short"),
        prime=("ATOMIC TUESDAY", "scifi"),
        late=("THE LATE TRANSMISSION", "science"),
    ),
    "wednesday": dict(
        lunch=("LUNCH LOOPS — SONGS AND CHORUSES", "pl_lunch_song"),
        matinee=("THE AFTERNOON PICTURE SHOW", "classics"),
        prime=("WORKBENCH THEATRE", "docs"),
        late=("NIGHT PATTERN", "industrial"),
    ),
    "thursday": dict(
        lunch=("LUNCH LOOPS — KOLOMYIKA HOUR", "pl_lunch_kolomyika"),
        matinee=("CHAPTER PLAY MATINEE", "serials"),
        prime=("SERIAL NIGHT", "serials"),
        late=("CHAPTER'S END", "cult"),
    ),
    "friday": dict(
        lunch=("LUNCH LOOPS — POLKA PARTY", "pl_lunch_party"),
        matinee=("THE AFTERNOON PICTURE SHOW", "classics"),
        prime=("FRIDAY NIGHT FEATURE", "cult"),
        # The one slot the Z0-LATE material is scheduled into. Everything rated
        # Z0-LATE by tools/z0-nfo.py — the burlesque reels and the exploitation
        # "square-up" features — reaches air here and nowhere else. Every
        # daytime pool carries `NOT mpaa:Z0-LATE`.
        late=("THE LATE LATE SHOW", "late_show"),
    ),
    "saturday": dict(
        lunch=("LUNCH LOOPS — WEDDING PARTY", "pl_lunch_wedding"),
        morning="pl_saturday_morning",
        matinee=("SERIAL MATINEE", "pl_serial_matinee"),
        prime=("SATURDAY DOUBLE BILL", "classics"),
        # Saturday takes a second feature instead of the encore, per the bible.
        second_feature=("SATURDAY DOUBLE BILL — SECOND FEATURE", "scifi"),
        # No `late`: the second feature holds the night and signs off when it
        # ends. See the pad_to_next note in day_plan().
    ),
    "sunday": dict(
        lunch=("LUNCH LOOPS — PRAIRIE MIXED", "pl_lunch_mixed"),
        matinee=("THE VANCOUVER REEL", "vancouver_reel"),
        prime=("SUNDAY CINEMA", "classics"),
        late=("NIGHT PATTERN", "slowtv"),
        neighbourhood=("CANADA NIGHT", "pl_vancouver_night"),
    ),
}


def programme(title, content, count=1, rolls=True):
    """A single scheduled programme, bracketed the way a broadcast day
    brackets one: an ident and two adverts either side.

    This used to bracket every feature with `strip_down` / `strip_up` as well,
    because the bottom strip was a subtitle element costing roughly 4x realtime
    at 1080p and dropping it bought back headroom on exactly the items that
    needed it most. The strip is gone — its content lives in the side rails,
    which are image elements and effectively free — so there is nothing to drop
    and every programme now carries the full set of on-air furniture.

    pre_roll / post_roll are only emitted by the `all`, `count` and `duration`
    handlers, which is why this uses `count:` and not `pad_until:`."""
    out = []
    if rolls:
        out.append({"pre_roll": True, "sequence": "feature_break"})
        out.append({"post_roll": True, "sequence": "feature_break"})
    out.append({"epg_group": True})
    out.append({"count": count, "content": content, "custom_title": title})
    out.append({"epg_group": False})
    if rolls:
        # Clear them again, or every later count/duration block in the day
        # picks up the same pre-roll and the guide fills with idents.
        out.append({"pre_roll": False})
        out.append({"post_roll": False})
    return out


def strand(title, content, until, tomorrow=False, discard=6, trim=False):
    """A block padded out to a clock time. `discard_attempts` matters: without
    it, `pad_until` gives up on the first item that does not FIT the remaining
    gap rather than trying the next one, and a single unlucky shuffle empties
    the whole block."""
    item = {
        "pad_until": until,
        "tomorrow": tomorrow,
        "content": content,
        "custom_title": title,
        "discard_attempts": discard,
    }
    if trim:
        item["trim"] = True
    return [{"epg_group": True}, item, {"epg_group": False}]


def strand_to_next(title, content, minutes, discard=6):
    """A block padded out to the next multiple of `minutes` past the hour.

    The difference from strand() is not cosmetic. `pad_until` names a time on
    the day the instruction is REACHED and does not roll forward if that time
    has already gone by, so an instruction reached at 00:03 and targeting
    23:00 pads for twenty-three hours and eats the following day whole.
    `pad_to_next` is relative, so it is bounded by `minutes` no matter what
    the clock says — the only safe way to pad after something that may run
    past midnight."""
    return [{"epg_group": True},
            {"pad_to_next": minutes, "content": content,
             "custom_title": title, "discard_attempts": discard},
            {"epg_group": False}]


def coming_soon(title, card, until, discard=6):
    """A slot that is reserved but has no programme yet: the card HOLDS the
    whole block. Nothing else airs in it.

    This is the second attempt and the history matters, because the first one
    looked more sophisticated and was wrong. It played the card ONCE and then
    padded the rest of the hour from a themed pool (schoolroom / newsreels),
    with both under one guide title. The reasoning was that an hour of static
    slate is dead air and a themed pool is better television.

    What that actually produced: you tuned to LAB HOUR at 11:00 and saw a
    Prelinger classroom film, because the card was 60 seconds of a 60-minute
    hour — and the guide labelled the whole hour COMING SOON, so the films were
    also mislabelled. The instruction was to *block off* the slot. A slot that
    still airs an hour of other programming is not blocked off; it is a slot
    with a 60-second caption in front of it.

    So the card now fills the block:

    - `pad_until` FROM THE CARD POOL, not from content. The pool holds one
      5-minute card, so an hour tiles in ~12 plays — the same order as an
      ordinary SHORT SUBJECTS block. A 60-second card would have been booked
      ~60 times, which is the documented "never pad_until with short items"
      trap.
    - `trim: true` cuts the last play so the block lands exactly on the clock
      instead of stopping early and dropping into fallback filler.
    - One `epg_group`, so the hour is a single honest guide entry that says
      COMING SOON and means it.
    - Still no `pre_roll`/`post_roll` and no strip: bracketing a slate with
      idents and adverts would advertise a programme that does not exist yet.

    The card carries a slow sliding accent marker for exactly one reason: an
    hour of a genuinely static frame reads as a frozen channel rather than a
    held slot."""
    return [
        {"epg_group": True},
        {
            "pad_until": until,
            "tomorrow": False,
            "content": card,
            "custom_title": title,
            "discard_attempts": discard,
            "trim": True,
        },
        {"epg_group": False},
    ]


def day_plan(name, spec):
    """The common shape of a Z0 day, with the themed slots filled in."""
    P = []

    # ── Sign-on and morning ───────────────────────────────────────────────────
    # The weekends are NOT the weekday spine with different films in it — they
    # restructure the morning, and both docs/programming.md and the storefront
    # grid say so in the same words. The generator used to apply the weekday
    # shape to all seven days, which put LAB HOUR on Sunday (the guide promises
    # PRELINGER THEATRE) and pushed Saturday's matinee an hour late.
    #
    # Keep these three branches in step with docs/programming.md § Weekends and
    # `WEEK` in site/index.html, or the guide and the guide-on-the-wall disagree.
    P.append({"sequence": "sign_on"})
    morning = spec.get("morning", "pl_cartoon_hour")

    if name == "saturday":
        # Cartoons come forward and run long; no STRETCH AND COFFEE.
        P += strand("SHORT SUBJECTS", "pad_short", "07:00")
        P += strand("CARTOON CARNIVAL", morning, "10:00")
        P += strand("PRELINGER THEATRE", "prelinger", "11:00")
        P += coming_soon("LAB HOUR — COMING SOON", "coming_soon_lab", "12:00")
    elif name == "sunday":
        # The quiet one: a slower morning, and NO LAB HOUR — 11:00 is
        # PRELINGER THEATRE, which is why this branch has no card at all.
        P += strand("SHORT SUBJECTS", "pad_short", "06:30")
        P += strand("SUNDAY SERVICE", "slowtv", "09:00", discard=4)
        P += strand("CARTOON CARNIVAL", morning, "11:00")
        P += strand("PRELINGER THEATRE", "prelinger", "12:00")
    else:
        P += strand("SHORT SUBJECTS", "pad_short", "06:30")
        P += strand("STRETCH AND COFFEE", "slowtv", "07:00", discard=4)
        P += strand("CARTOON BLOCK", morning, "09:00")
        P += strand("PRELINGER THEATRE", "prelinger", "11:00")
        P += coming_soon("LAB HOUR — COMING SOON", "coming_soon_lab", "12:00")

    # ── Midday ────────────────────────────────────────────────────────────────
    P.append({"sequence": "weather_break"})
    # docs/programming.md has always defined noon as "Music + the community
    # bulletin board", but the deployed schedule padded it from `prelinger` —
    # which is the bug behind "there isn't music even though it's noon, it's
    # still showing old clips".
    #
    # It pads from the Lunch Loops PLAYLIST rather than from the music pool
    # directly: the tracks are 2–3 minutes, and padding two hours from a pool
    # that short schedules ~40 items and buries the guide. The playlist
    # interleaves music with one 10–30 minute film per cycle.
    #
    # The community bulletin board is the bottom crawl, which is up for the
    # whole block — this is one of the few places it is deliberately NOT taken
    # down, so the strip's cost is real here. It is affordable because the
    # music cards are 640x480 and cheap to decode.
    # Saturday's matinee is an hour earlier (13:00 MATINEE DOUBLE), so lunch is
    # an hour shorter. Every other day runs 12:00-14:00.
    # Each weekday leads with a different form -- waltzes, polkas, songs,
    # kolomyiky, the fast pool, the wedding sides -- and Sunday is the whole
    # library shuffled. The playlists are in lists/z0-lists.yml; the titles are
    # here because they are what the guide shows, and a viewer only ever learns
    # the day has a theme from the guide.
    lunch_title, lunch_content = spec.get(
        "lunch", ("LUNCH LOOPS", "pl_lunch_loops"))
    P += strand(lunch_title, lunch_content,
                "13:00" if name == "saturday" else "14:00")

    # ── Afternoon ─────────────────────────────────────────────────────────────
    P += programme(*spec["matinee"])
    P += strand("SHORT SUBJECTS", "pad_short", "16:00")
    P += strand("CARTOON BLOCK II", "animation_blocks", "18:00")

    # ── Early evening ─────────────────────────────────────────────────────────
    # 19:00 GROUND ZERO and 00:00 SIGN-OFF are the two fixed points that never
    # move — the station's heartbeat. GROUND ZERO has no footage yet, so the
    # slot is held at the right time: it opens on the programme's COMING SOON
    # card and is then filled from the newsreel pool. The shape of the day is
    # the point, and the card is what tells a viewer the slot is reserved
    # rather than broken.
    P.append({"sequence": "weather_break"})
    nb_title, nb_content = spec.get(
        "neighbourhood", ("THE NEIGHBOURHOOD DESK", "pl_neighbourhood"))
    P += strand(nb_title, nb_content, "19:00")
    P += coming_soon("GROUND ZERO — COMING SOON", "coming_soon_gnd", "20:00")

    # ── Prime ─────────────────────────────────────────────────────────────────
    P += programme(*spec["prime"])

    # What follows prime is the third place the weekends diverge, and the
    # published grid is specific about it:
    #   Mon-Fri  22:00 GROUND ZERO — ENCORE, 23:00 the late block
    #   Saturday 22:30 the second feature (no encore — it takes the picture)
    #   Sunday   22:30 NIGHT PATTERN, and NO encore at all
    # Sunday is the one that was actually wrong: it was getting a 22:00 encore
    # the guide never promised, which after the cards started holding slots
    # meant an hour of COMING SOON on a night with no Ground Zero on the grid.
    if name == "saturday":
        P += strand("SHORT SUBJECTS", "pad_short", "22:30")
        P += programme(*spec["second_feature"])
        P.append({"sequence": "station_break"})
        # ── This one is `pad_to_next`, and it HAS to be. ────────────────────
        # Saturday is the only night whose picture is *designed* to run past
        # midnight: the grid says feature two at 22:30 and sign-off at 00:30.
        # A `pad_until` cannot express that. Its target is a time on the
        # CURRENT day and it does not roll forward, so a second feature that
        # ends at 00:03 leaves the next instruction padding to "23:00 today"
        # — 23 hours away. It fills it, too: 251 items of SHORT SUBJECTS
        # swallowing the whole of Sunday, after which Sunday's block airs on
        # Monday and every day of the week is one day late for ever. That is
        # not hypothetical; it is what a screener build did on 2026-08-19,
        # and it is the mechanism behind "channel zero is a day behind".
        # `pad_to_next: 30` pads to the next half hour whatever the clock
        # says, so it is bounded by construction: at 00:03 it lands on 00:30,
        # which is exactly the sign-off the storefront promises.
        P += strand_to_next("SHORT SUBJECTS", "pad_short", 30)
    elif name == "sunday":
        P += strand("SHORT SUBJECTS", "pad_short", "22:30")
        P.append({"sequence": "station_break"})
    else:
        P += strand("SHORT SUBJECTS", "pad_short", "22:00")
        P += coming_soon("GROUND ZERO ENCORE — COMING SOON",
                         "coming_soon_gnd", "23:00")
        P.append({"sequence": "station_break"})
        P += strand("SHORT SUBJECTS", "pad_short", "23:00")

    # ── The late block ────────────────────────────────────────────────────────
    # Themed per night.
    #
    # This used to raise a `ChannelWatermark` called "Z0 Bug Late Night" for the
    # duration — a second, dimmer bug at 45% opacity, bottom-LEFT, the only
    # place the channel used a watermark rather than a graphics element. It was
    # a survivor of ErsatzTV 25.2, where a single static watermark was the only
    # overlay that existed at all.
    #
    # It is gone because it is now both redundant and wrong. Redundant: the bug
    # is permanently in the right rail, so late night was drawing a second copy
    # of a mark that never leaves. Wrong: a watermark is composited over the
    # PICTURE, and the whole point of the rails is that nothing is. It was the
    # last thing the channel put on top of the programme.
    #
    # The three ChannelWatermark rows are left in the database. Nothing
    # references them now, and they are the only worked example of how to put a
    # per-block overlay on this channel if one is ever wanted again.
    #
    # Saturday has no late block, and the grid never promised one: the double
    # bill's second picture IS the late block, and it is still running at
    # midnight. (It used to get one anyway, which is the other half of the pad
    # problem above — a late block padded to 00:00 after a feature that ended
    # at 00:03 is another 24-hour target.)
    if spec.get("late"):
        P += strand(spec["late"][0], spec["late"][1], "00:00",
                    tomorrow=True, discard=8)

    # ── Sign-off ──────────────────────────────────────────────────────────────
    P.append({"sequence": "weather_break"})
    P.append({"sequence": "sign_off"})

    # ── Overnight ─────────────────────────────────────────────────────────────
    # This used to be `pad_until 06:00 trim: true content: colorbars` — one
    # hour-long file, trimmed, covering roughly six hours of every night. The
    # sign-off ritual is kept, but the six hours are now programmed. Put the
    # colorbars line back here if you want the old behaviour.
    #
    # `offline_tail` marks the block as the tail of the broadcast day so the
    # guide does not advertise it as a programme strand.
    P.append({"sequence": "overnight_variety"})
    P.append({"shuffle_sequence": "overnight_variety"})
    P += strand("THE ALL-NIGHT SHOW", "overnight", "05:30",
                tomorrow=True, discard=8)
    P += strand("COLOUR BARS", "colorbars", "06:00", tomorrow=True, trim=True)
    return P


BANNER = "  # {} {}"


def emit(days, start_day):
    """Render to YAML by hand rather than through yaml.dump, so the day banners
    and the running commentary survive. A generated schedule nobody can read is
    not an improvement on a hand-written one."""
    i = WEEKDAYS.index(start_day)
    order = WEEKDAYS[i:] + WEEKDAYS[:i]

    L = []
    L.append("# " + "─" * 77)
    L.append("# CHANNEL Z0 — the broadcast week.")
    L.append("#")
    L.append("# GENERATED by tools/z0-build-schedule.py. Do not edit by hand;")
    L.append("# edit the generator and re-run, or your change is lost the next")
    L.append("# time the week is rotated.")
    L.append("#")
    L.append(f"# Rotated to start on {start_day.upper()}.")
    L.append("#")
    L.append("# The seven day blocks below run in order and `repeat: true`")
    L.append("# returns to the first. There is no day-of-week primitive: which")
    L.append("# block lands on which weekday is decided entirely by the day the")
    L.append("# playout is built or RESET on. If you reset this playout on any")
    L.append("# day other than " + start_day.upper() + ", re-run the generator")
    L.append("# with --start-day for that day first, or the channel airs the")
    L.append("# wrong day's programming and nothing reports it.")
    L.append("#")
    L.append("# Content keys come from _content.yml, sequences from")
    L.append("# _sequences.yml. Both are imported below; the importing file")
    L.append("# wins on any key collision, which is how the seasonal variants")
    L.append("# override a single strand without copying the week.")
    L.append("# " + "─" * 77)
    L.append("")
    L.append("import:")
    L.append("  - _content.yml")
    L.append("  - _sequences.yml")
    L.append("")
    L.append("playout:")

    for n, day in enumerate(order):
        L.append("")
        L.append("  # " + "═" * 73)
        L.append(f"  # {day.upper()}  (block {n + 1} of 7)")
        L.append("  # " + "═" * 73)
        for instr in days[day]:
            L += render(instr)

    L.append("")
    L.append("  # Back to block 1. Without this the playout runs out of")
    L.append("  # instructions and the channel stops after seven days.")
    L.append("  - repeat: true")
    L.append("")
    return "\n".join(L)


def render(instr):
    """One instruction as YAML lines."""
    keys = list(instr)
    first = keys[0]
    out = [f"  - {first}: {fmt(instr[first])}"]
    for k in keys[1:]:
        out.append(f"    {k}: {fmt(instr[k])}")
    return out


def fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if v is None:
        return "null"
    # Everything is single-quoted, so times ('06:30'), bare numbers and
    # true/false/null read as strings rather than as their YAML types. In
    # single-quoted YAML the ONLY escape is a doubled quote — miss it and a
    # title like "CHAPTER'S END" terminates the scalar early and the file will
    # not parse at all.
    return "'" + str(v).replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-day", default="today",
                    help="weekday the first block should land on, or 'today'")
    ap.add_argument("--out", default="-")
    ap.add_argument("--no-intervals", action="store_true",
                    help="omit the generative-art station intervals")
    args = ap.parse_args()

    start = args.start_day.lower()
    if start == "today":
        start = WEEKDAYS[datetime.date.today().weekday()]
    if start not in WEEKDAYS:
        raise SystemExit(f"--start-day must be one of {WEEKDAYS} or 'today'")

    days = {name: day_plan(name, spec) for name, spec in WEEK.items()}
    if not args.no_intervals:
        # Intervals are spliced into the finished instruction list rather than
        # emitted inline by day_plan, because an interval's length depends on
        # BOTH segments it sits between — which is only knowable once the day
        # is complete. See tools/z0_intervals.py and docs/intervals.md.
        days = {name: z0_intervals.splice(P) for name, P in days.items()}
    text = emit(days, start)

    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w") as fh:
            fh.write(text)
        n = sum(len(d) for d in days.values())
        print(f"wrote {args.out}: 7 days, {n} instructions, "
              f"starting {start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
