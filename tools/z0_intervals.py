"""Station intervals — generative art at every junction in the broadcast day.

Imported by tools/z0-build-schedule.py and applied to each day's instruction
list, so intervals are part of the generated week rather than something bolted
on afterwards. The art itself is made by tools/z0-generative.py; see
docs/intervals.md.

The ask was that the first and last four minutes of every segment become
generative art. Two properties of this schedule shape how that is delivered.

**Adjacent segments touch.** Taken literally, the tail of one segment and the
head of the next are eight unbroken minutes at every junction — around two
hours a day. So each junction gets ONE interval, shared between the segments it
separates: still the last four minutes of the one before and the first four of
the one after, counted once rather than twice.

**Segments are wildly different lengths.** CARTOON BLOCK runs two hours; THE
WEATHER DESK is exactly two minutes and SIGN-OFF is thirty-five seconds. A flat
four minutes would erase the short ones. So an interval is 12.5% of the SHORTER
of the two segments it separates, capped at four minutes — the full 4:00
between the big blocks, about fifteen seconds either side of the weather desk,
four seconds around sign-off.

One pool of ~55 second clips serves all of them, because `duration:` +
`trim: true` fills an exact wall-clock span and cuts the last item at the
boundary.
"""

MAX_INTERVAL = 240      # the four minutes that were asked for
MIN_INTERVAL = 4        # below this it is a glitch, not a transition
FRACTION = 0.125        # of the shorter neighbouring segment

# Nominal seconds, used ONLY to size intervals — these numbers never reach the
# schedule. Measured off the live PlayoutItem table; being a minute out on a
# feature moves nothing, because those junctions are already at the 4:00 cap.
CONTENT_SECONDS = {
    "signon": 61, "signoff": 35, "idents": 7, "weather": 120,
    "commercials": 30, "colorbars": 3600, "pad_short": 105, "rail": 900,
    "prelinger": 954, "slowtv": 1434, "newsreels": 300, "schoolroom": 600,
    "overnight": 1200, "animation_blocks": 396, "music": 180,
}
DEFAULT_CONTENT_SECONDS = 600

# Sequences that wrap their own epg_group, i.e. that ARE a segment.
SEQUENCE_SECONDS = {
    "weather_break": 120, "sign_on": 68, "sign_off": 35,
    "short_subjects": 210, "overnight_variety": 900,
}

# Instructions that precede a segment and belong to it — the strip coming down
# for a feature, its pre/post rolls, a late-night watermark. An interval must go
# in FRONT of these, or it plays with the strip already down and the rolls armed.
def _attaches_to_next(ins):
    if "sequence" in ins and ins["sequence"] in ("strip_down", "graphics_up"):
        return True
    for k in ("pre_roll", "post_roll", "watermark", "graphics_off",
              "shuffle_sequence"):
        if k in ins:
            return True
    return False


def _hhmm(total_minutes):
    total_minutes = int(round(total_minutes)) % 1440
    return "%02d:%02d" % (total_minutes // 60, total_minutes % 60)


def interval_block(seconds):
    """The instructions for one interval.

    Graphics go down for it and come back after. The bug and the weather card
    over abstract art look like a mistake, and the bottom strip is a subtitle
    element — the one re-rendered every frame that took the channel off air 27
    times in a morning. An hour or two a day with the compositor idle is a
    saving, not a cost.
    """
    hh, mm, ss = seconds // 3600, (seconds // 60) % 60, seconds % 60
    return [
        # `graphics_off: null` is all of them, so the strip_down sequence would
        # be redundant here; `graphics_up` puts all four back.
        {"graphics_off": None},
        {"epg_group": True},
        # `filler_kind` is what keeps these out of the programme guide, the
        # same mechanism the station idents use in _sequences.yml: ErsatzTV
        # drops any playout item whose FillerKind is not None from the XMLTV
        # output. Without it every junction became its own <programme> and
        # STATION INTERVAL was 48 of 114 guide entries — 43% of the guide.
        #
        # It does NOT change how the item is selected or cut: in
        # YamlPlayoutDurationHandler the trim, filler-kind and custom-title
        # values are passed as independent arguments and the `else if (trim)`
        # branch never consults the filler kind. `custom_title` is still set
        # on the item, it is simply no longer surfaced in the guide.
        {"duration": "%02d:%02d:%02d" % (hh, mm, ss),
         "content": "generative",
         "trim": True,
         "filler_kind": "preroll",
         "custom_title": "STATION INTERVAL"},
        {"epg_group": False},
        {"sequence": "graphics_up"},
    ]


def _segments(P):
    """Walk a day's instructions, tracking a wall clock, and return its
    segments as (open_index, close_index, minutes).

    `open_index` is where an interval introducing this segment goes: in front
    of the instructions that belong to it, not on top of them.
    """
    clock = 6 * 60          # the day opens at sign-on, 06:00
    segs = []
    open_at = None
    open_clock = None

    for i, ins in enumerate(P):
        if "sequence" in ins and ins["sequence"] in SEQUENCE_SECONDS:
            back = i
            while back > 0 and _attaches_to_next(P[back - 1]):
                back -= 1
            dur = SEQUENCE_SECONDS[ins["sequence"]] / 60.0
            segs.append((back, i, dur))
            clock += dur
            continue

        if "epg_group" in ins:
            if ins["epg_group"]:
                back = i
                while back > 0 and _attaches_to_next(P[back - 1]):
                    back -= 1
                open_at, open_clock = back, clock
            elif open_at is not None:
                segs.append((open_at, i, clock - open_clock))
                open_at = None
            continue

        if "pad_until" in ins:
            h, m = ins["pad_until"].split(":")
            target = int(h) * 60 + int(m)
            if ins.get("tomorrow"):
                target += 1440
            while target < clock:
                target += 1440
            clock = target
        elif "count" in ins and "content" in ins:
            clock += ins["count"] * CONTENT_SECONDS.get(
                ins["content"], DEFAULT_CONTENT_SECONDS) / 60.0

    return segs


def splice(P):
    """Return a day's instruction list with an interval at every junction.

    Where the instruction governing the next segment's start is a `pad_until`,
    its target is pulled BACK by the interval, so that segment still begins at
    the time the guide and the storefront advertise: CARTOON BLOCK pads to
    08:56, the interval runs 08:56–09:00, and PRELINGER THEATRE still opens at
    09:00. Intervals under a minute are never pulled back — `pad_until` targets
    are only HH:MM, and the few seconds self-correct at the next pad.
    """
    segs = _segments(P)
    if len(segs) < 2:
        return P

    out = list(P)
    # Back to front, so earlier indices stay valid.
    for k in range(len(segs) - 1, -1, -1):
        open_at, _, minutes = segs[k]
        prev_minutes = segs[k - 1][2]        # k=0 wraps to the day's last
        shorter = min(minutes, prev_minutes) * 60.0
        secs = max(MIN_INTERVAL, min(MAX_INTERVAL,
                                     int(round(shorter * FRACTION))))

        if secs >= 60:
            for j in range(open_at - 1, -1, -1):
                if "pad_until" in out[j]:
                    h, m = out[j]["pad_until"].split(":")
                    back = int(round(secs / 60.0))
                    out[j] = dict(out[j],
                                  pad_until=_hhmm(int(h) * 60 + int(m) - back))
                    break

        out[open_at:open_at] = interval_block(secs)

    return out
