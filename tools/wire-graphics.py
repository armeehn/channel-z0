#!/usr/bin/env python3
"""Wire the on-air graphics and the weather segment into the broadcast week.

The seven day blocks in channel-z0.yml are structurally identical, so this
edits the file mechanically rather than by hand — 150-odd lines inserted the
same way seven times, which is exactly the kind of edit a human gets wrong
once and then cannot find.

It is idempotent: run it twice and the second run is a no-op, so it can be
re-run after the schedule itself is edited.
"""

import re
import sys

FEATURES = {"noir", "scifi", "docs", "serials", "classics", "cult"}

DAY_FURNITURE = """
  # ── On-air furniture ────────────────────────────────────────────────────
  # Turned on at the top of every day, not once at the top of the file. The
  # elements are attached to playout ITEMS as they are built, so an element
  # switched on only at instruction 1 would not reach the air again until the
  # seven-day cycle came back around — a week of a bare screen after any
  # partial rebuild.
  - graphics_on: 'image/z0-rail-left.yml'
  - graphics_on: 'image/z0-weather-card.yml'
  - graphics_on: 'image/z0-bug.yml'
  - graphics_on: 'text/z0-upnext.yml'
"""

WEATHER_SEGMENT = """  # The forecast. One file, rewritten in place every 15 minutes by
  # tools/z0-weather.sh and always exactly the same length, so the library row
  # stays valid and this never needs a rescan.
  #
  # The corner card stands down for these two minutes: it repeats what the
  # segment is already saying, and at a 5% top margin it lands on top of the
  # segment's own header and rule.
  - graphics_off: 'image/z0-weather-card.yml'
  - epg_group: true
  - count: 1
    content: weather
    custom_title: 'THE WEATHER DESK'
  - epg_group: false
  - graphics_on: 'image/z0-weather-card.yml'
"""

CONTENT_KEY = """
  # ── The weather desk. Generated, not acquired: tools/z0-weather.sh renders
  #    the segment from the live forecast. It lives in its own folder so the
  #    tag is unambiguous — matching on the title would be fragile, because
  #    ErsatzTV's title analyser does not split on hyphens and
  #    'z0-local-forecast' is one token to it.
  - key: weather
    search:                       # The Weather Desk
    query: 'type:other_video AND tag:weather'
    order: chronological
"""


def normalize_search_discriminators(lines):
    """`search:` is a discriminator, and its value must be null.

    This file has always written `search: Cartoons`, using the slot as a
    human-readable label. ErsatzTV 25.2 had no schema validation and simply
    ignored it. From 25.4 the sequential schedule is validated against a JSON
    schema where `search` is `{"type": "null"}` and every object is
    additionalProperties:false — so a named search fails validation, and
    SequentialPlayoutBuilder returns None on a failed validation, meaning the
    playout does not build AT ALL.

    That failure is invisible: the existing playout items keep airing until
    they run out, and only then does the channel drop to fallback filler. So
    the label moves to a comment, where it was always really a comment.
    """
    fixed = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)search: (?!\s*$)(.+?)\s*$", line)
        if m and not m.group(2).startswith("#"):
            indent, label = m.group(1), m.group(2)
            lines[i] = f"{indent}search:" + " " * 23 + f"# {label}"
            fixed += 1
    return fixed


def make_tomorrow_explicit(lines):
    """Give every `pad_until` an explicit `tomorrow:`.

    ErsatzTV 26.x changed YamlPlayoutPadUntilInstruction.Tomorrow from bool to
    string so it can hold an expression, and YamlPlayoutPadUntilHandler does:

        if (timeOnly > result)
        {
            var expression = new Expression(padUntil.Tomorrow);

    with no null check. NCalc's constructor throws "ExpressionString cannot be
    null or empty", the exception escapes, and the ENTIRE playout build fails
    with one warning line and no items.

    The branch only runs when the pad target is already in the past, so this
    lies dormant and detonates the first time the playout is rebuilt later in
    the day than its earliest morning block — which is to say, eventually, and
    for reasons that will look unrelated. On 25.2 a bool simply defaulted to
    false. Spelling it out costs nothing and is immune to the change.
    """
    out = []
    added = 0
    i = 0
    while i < len(lines):
        out.append(lines[i])
        m = re.match(r"^  - pad_until: ", lines[i])
        if m:
            j = i + 1
            has_tomorrow = False
            while j < len(lines) and lines[j].startswith("    "):
                if re.match(r"^    tomorrow:", lines[j]):
                    has_tomorrow = True
                j += 1
            if not has_tomorrow:
                out.append("    tomorrow: false")
                added += 1
        i += 1
    lines[:] = out
    return added


def split_items(lines, start, end):
    """Group the playout body into list items. An item begins with '  - ' and
    owns every following line until the next one."""
    items = []
    cur = None
    for i in range(start, end):
        line = lines[i]
        if line.startswith("  - "):
            if cur is not None:
                items.append(cur)
            cur = [i, i + 1]
        elif cur is not None:
            cur[1] = i + 1
    if cur is not None:
        items.append(cur)
    return items


def main(path, out):
    with open(path) as f:
        text = f.read()

    lines = text.split("\n")

    n = normalize_search_discriminators(lines)
    print(f"normalized {n} search discriminators")

    t = make_tomorrow_explicit(lines)
    print(f"made tomorrow explicit on {t} pad_until instructions")

    if "graphics_on" in text:
        print("graphics already wired — leaving the schedule alone")
        with open(out, "w") as f:
            f.write("\n".join(lines))
        return 0

    # ── 1. The content key, appended to the content: section ────────────────
    playout_idx = next(i for i, l in enumerate(lines) if l == "playout:")
    lines.insert(playout_idx, CONTENT_KEY.strip("\n"))
    lines.insert(playout_idx + 1, "")
    playout_idx += 2

    # Recompute against the mutated list from here on.
    body_start = playout_idx + 1
    body_end = len(lines)

    # ── 2. Collect insertion points, then apply them back-to-front so earlier
    #       indices stay valid. ───────────────────────────────────────────────
    inserts = []  # (line_index, text)

    def item_start_with_group(items, idx):
        """The natural place to splice in ahead of an item: before the
        `epg_group: true` that opens its guide entry, if it has one."""
        s = items[idx][0]
        if idx > 0 and lines[items[idx - 1][0]].strip() == "- epg_group: true":
            return items[idx - 1][0]
        return s

    items = split_items(lines, body_start, body_end)

    # Day markers -> furniture
    for i, l in enumerate(lines):
        if i >= body_start and re.match(r"\s*# ══ [A-Z]", l):
            inserts.append((i + 1, DAY_FURNITURE.strip("\n")))

    for idx, (s, e) in enumerate(items):
        block = "\n".join(lines[s:e])
        title_m = re.search(r"custom_title: '([^']*)'", block)
        title = title_m.group(1) if title_m else ""
        content_m = re.search(r"^\s+content: (\S+)\s*$", block, re.M)
        content = content_m.group(1) if content_m else ""

        # Morning forecast: after the sign-on ident, before the first pad.
        if title == "SIGN-ON · MORNING PATTERN":
            # walk forward to the next pad_until item and sit in front of it
            for j in range(idx + 1, len(items)):
                if lines[items[j][0]].startswith("  - pad_until:"):
                    inserts.append((item_start_with_group(items, j),
                                    WEATHER_SEGMENT.rstrip("\n")))
                    break

        # Midday, early evening, and the last one before sign-off.
        if title in ("LUNCH LOOPS", "NEIGHBOURHOOD DESK (STANDBY)", "SIGN-OFF"):
            inserts.append((item_start_with_group(items, idx),
                            WEATHER_SEGMENT.rstrip("\n")))

        # A crawl over a feature film is what makes people leave. Off for the
        # feature, back on after it.
        if content in FEATURES:
            inserts.append((item_start_with_group(items, idx),
                            "  - graphics_off: 'subtitle/z0-crawl.yml'"))
            inserts.append((e, "  - graphics_on: 'subtitle/z0-crawl.yml'"))

        # Overnight the screen is colour bars; the crawl adds nothing.
        if title == "COLOUR BARS":
            inserts.append((item_start_with_group(items, idx),
                            "  - graphics_off: 'subtitle/z0-crawl.yml'"))

    for at, chunk in sorted(inserts, key=lambda x: -x[0]):
        lines.insert(at, chunk)

    with open(out, "w") as f:
        f.write("\n".join(lines))

    print(f"inserted {len(inserts)} blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
