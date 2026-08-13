#!/usr/bin/env python3
"""Walk a generated schedule's wall clock and flag what the schema cannot see.

Schema validation proves the file parses. It says nothing about whether the day
still adds up, and the failure mode here is silent: a `pad_until` whose target
has already passed schedules NOTHING — a hole, not an error — so pulling a pad
back too far quietly empties a block and only shows up as dead air later.

Intervals make this a live risk, because every one of them adds wall-clock time
and 59 of them pull a pad target backwards to pay for it.

    check-schedule-clock.py playout/channel-z0.yml [playout/_sequences.yml]
"""

import sys

import yaml

CONTENT_SECONDS = {
    "signon": 61, "signoff": 35, "idents": 7, "weather": 120,
    "commercials": 30, "colorbars": 3600, "pad_short": 105, "rail": 900,
    "prelinger": 954, "slowtv": 1434, "newsreels": 300, "schoolroom": 600,
    "overnight": 1200, "animation_blocks": 396, "music": 180,
}
DEFAULT = 600
SEQUENCE_SECONDS = {
    "weather_break": 120, "sign_on": 68, "sign_off": 35, "station_break": 7,
    "station_break_long": 45, "feature_break": 67, "advert_break": 30,
    "short_subjects": 210, "overnight_variety": 900,
    "strip_down": 0, "strip_up": 0, "graphics_up": 0,
}


def main(path):
    doc = yaml.safe_load(open(path))
    P = doc["playout"]

    clock = 6 * 60
    problems = []
    pads = 0
    interval_seconds = 0
    prev_pad = None

    for i, ins in enumerate(P):
        if "duration" in ins:
            h, m, s = (int(x) for x in ins["duration"].split(":"))
            interval_seconds += h * 3600 + m * 60 + s
            clock += (h * 3600 + m * 60 + s) / 60.0
        elif "pad_until" in ins:
            # Model it the way the handler does: a pad names a TIME OF DAY, and
            # `tomorrow` decides whether a target already past rolls forward.
            # Tracking an explicit day counter here was wrong — the overnight
            # strand and the bars both carry `tomorrow`, so the rollover cannot
            # be pinned to one instruction.
            h, m = ins["pad_until"].split(":")
            tod = int(h) * 60 + int(m)
            target = (int(clock) // 1440) * 1440 + tod
            if target < clock:
                if ins.get("tomorrow"):
                    target += 1440
                else:
                    problems.append(
                        "instruction %d: pad_until %s (%s) is %.1f min past "
                        "when the clock reaches it, and tomorrow is false — "
                        "this block schedules nothing"
                        % (i, ins["pad_until"], ins.get("custom_title", "?"),
                           clock - target))
            pads += 1
            prev_pad = target
            clock = max(clock, target)
        elif "count" in ins and "content" in ins:
            clock += ins["count"] * CONTENT_SECONDS.get(
                ins["content"], DEFAULT) / 60.0
        elif "sequence" in ins and "shuffle_sequence" not in ins:
            clock += SEQUENCE_SECONDS.get(ins["sequence"], 0) / 60.0

    span = (prev_pad - 6 * 60) / 60.0
    print("pad_until instructions : %d" % pads)
    print("intervals              : %.1f min per cycle (%.1f min/day)"
          % (interval_seconds / 60.0, interval_seconds / 60.0 / 7))
    print("clock span             : %.1f h (a seven-day week is 168 h)" % span)

    if problems:
        print("\nPROBLEMS (%d):" % len(problems))
        for p in problems[:20]:
            print("  " + p)
        return 1
    print("\nOK — every pad target is still in the future when the clock "
          "reaches it")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
