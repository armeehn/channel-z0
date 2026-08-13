#!/usr/bin/env python3
"""
z0-validate-schedule.py — check a Channel Z0 schedule before it reaches air.

Two layers:

  1. ErsatzTV's OWN JSON schema (/app/Resources/sequential-schedule.schema.json,
     copied into this repo as schedule/sequential-schedule.schema.json). This is
     the same validation the app runs, and it matters enormously, because when
     it fails SequentialPlayoutBuilder returns None and the playout does not
     build AT ALL — the channel keeps airing whatever it had and then runs off
     the end of the old playout.

  2. The Z0 trap list. Every one of these has taken this channel off air or put
     a hole in it, and NONE of them are schema violations:

       * `search:` used as a human label. From 25.4 the schema declares
         `search` as {"type": "null"} with additionalProperties false, so
         `search: Cartoons` fails validation and the playout silently does not
         build. The label belongs in a comment.

       * `pad_until` without an explicit `tomorrow`. 26.x changed Tomorrow from
         bool to string so it can hold an expression, and the handler does
         `new Expression(padUntil.Tomorrow)` with no null check — NCalc throws
         "ExpressionString cannot be null or empty" and the whole build dies.
         The branch only runs when the pad target is already past, so a bare
         `pad_until` is dormant until the first rebuild later in the day than
         its earliest morning block.

       * Unbalanced epg_group. LockGuideGroup calls AdvanceGuideGroup, which is
         a no-op while already locked, so two `epg_group: true` in a row merge
         two programmes into one guide row.

       * A content key that is referenced but never defined, or defined but
         never used. The first is a hole; the second is usually a rename that
         only got done in one place.

       * Padding from a pool of very short items. Filling half an hour from
         six-second idents schedules ~300 items and loops the same four stings.

       * A graphics element that does not exist on disk.

Usage:
    z0-validate-schedule.py schedule/channel-z0.yml [--graphics-root DIR]
                            [--strict]
"""

import argparse
import os
import sys

import yaml

try:
    import jsonschema
except ImportError:
    jsonschema = None

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# The schemas are copied out of the running container
# (/app/Resources/*.schema.json) and kept next to the schedules. Look beside the
# file being validated first so this works from a deploy directory too.
SCHEMA_DIRS = [os.path.join(REPO, "playout"), os.path.join(REPO, "schedule"), REPO]

# Pools whose members are seconds long. Padding a gap from one of these is the
# ~300-idents-on-a-loop failure.
TINY_POOLS = {"idents", "signon", "signoff", "testcard", "standby", "pad_tiny"}

# Instruction keys that name a sequence rather than take one as a value.
SEQ_REFS = ("sequence", "shuffle_sequence")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def dump(self, strict):
        for w in self.warnings:
            print(f"  WARN  {w}")
        for e in self.errors:
            print(f"  FAIL  {e}")
        bad = len(self.errors) + (len(self.warnings) if strict else 0)
        print(f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return 1 if bad else 0


def load(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def resolve_imports(path, doc, rep):
    """Merge imported fragments the way SequentialPlayoutBuilder does: the
    importing file wins on any key collision, and imports are resolved relative
    to the importing file's directory."""
    content = list(doc.get("content") or [])
    sequence = list(doc.get("sequence") or [])
    base = os.path.dirname(os.path.abspath(path))

    for imp in doc.get("import") or []:
        p = imp if os.path.exists(imp) else os.path.join(base, imp)
        if not os.path.exists(p):
            rep.error(f"import {imp!r} does not exist (looked at {p})")
            continue
        frag = load(p)
        have_c = {c.get("key") for c in content}
        have_s = {s.get("key") for s in sequence}
        for c in frag.get("content") or []:
            if c.get("key") not in have_c:
                content.append(c)
        for s in frag.get("sequence") or []:
            if s.get("key") not in have_s:
                sequence.append(s)
    return content, sequence


def schema_check(path, doc, is_import, rep):
    if jsonschema is None:
        rep.warn("jsonschema not installed; skipped ErsatzTV schema validation "
                 "(this is the check that catches a playout which will not "
                 "build at all)")
        return
    name = ("sequential-schedule-import.schema.json" if is_import
            else "sequential-schedule.schema.json")
    here = os.path.dirname(os.path.abspath(path))
    sp = next((os.path.join(d, name)
               for d in [here] + SCHEMA_DIRS
               if os.path.exists(os.path.join(d, name))), None)
    if sp is None:
        rep.warn(f"{name} not found next to the schedule or in "
                 f"{SCHEMA_DIRS}; skipped ErsatzTV schema validation")
        return
    import json
    schema = json.load(open(sp))
    v = jsonschema.Draft202012Validator(schema)
    for err in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        rep.error(f"{os.path.basename(path)}: schema: {loc}: {err.message}")


def walk_instructions(items):
    for i in items or []:
        yield i


def check_traps(doc, content, sequence, rep, graphics_root):
    keys = {c.get("key") for c in content}
    seq_keys = {s.get("key") for s in sequence}

    # ── content definitions ───────────────────────────────────────────────────
    for c in content:
        if "search" in c and c["search"] is not None:
            rep.error(
                f"content {c.get('key')!r}: `search:` must be null. It is a "
                f"typed slot, not a label — the schema declares it "
                f"{{'type': 'null'}} and a value there makes the whole playout "
                f"fail to build, silently. Got {c['search']!r}")
        if "order" in c and c["order"] not in ("chronological", "shuffle"):
            rep.error(f"content {c.get('key')!r}: order must be "
                      f"chronological or shuffle, got {c['order']!r}")
        if "playlist" in c and "playlist_group" not in c:
            rep.error(f"content {c.get('key')!r}: a playlist needs "
                      f"playlist_group; the pair is the lookup key")

    # ── every instruction stream ──────────────────────────────────────────────
    streams = [("playout", doc.get("playout") or [])]
    for s in sequence:
        streams.append((f"sequence {s.get('key')!r}", s.get("items") or []))

    used_content, used_seq = set(), set()

    for label, items in streams:
        depth = 0
        for n, ins in enumerate(walk_instructions(items), start=1):
            where = f"{label}[{n}]"

            if "epg_group" in ins:
                if ins["epg_group"]:
                    if depth:
                        rep.error(
                            f"{where}: `epg_group: true` while already open. "
                            f"LockGuideGroup is a no-op when already locked, so "
                            f"these two programmes merge into one guide row")
                    depth += 1
                else:
                    depth -= 1
                    if depth < 0:
                        rep.error(f"{where}: `epg_group: false` with none open")
                        depth = 0

            if "pad_until" in ins and "tomorrow" not in ins:
                rep.error(
                    f"{where}: `pad_until` without an explicit `tomorrow:`. "
                    f"The handler evaluates Tomorrow as an NCalc expression "
                    f"with no null check, so this throws and kills the whole "
                    f"build — but only once the pad target is in the past, "
                    f"which is why it looks fine until it isn't")

            for k in ("pad_until", "pad_to_next"):
                if k in ins and ins.get("content") in TINY_POOLS:
                    rep.error(
                        f"{where}: padding from {ins['content']!r}, whose items "
                        f"are seconds long. This schedules hundreds of items "
                        f"and loops the same few stings until the next block")

            if "content" in ins:
                used_content.add(ins["content"])
                if ins["content"] not in keys:
                    rep.error(f"{where}: content key {ins['content']!r} is not "
                              f"defined")
            if "fallback" in ins:
                used_content.add(ins["fallback"])
                if ins["fallback"] not in keys:
                    rep.error(f"{where}: fallback key {ins['fallback']!r} is "
                              f"not defined")

            for sk in SEQ_REFS:
                if sk in ins and isinstance(ins[sk], str):
                    used_seq.add(ins[sk])
                    if ins[sk] not in seq_keys:
                        rep.error(f"{where}: sequence {ins[sk]!r} is not "
                                  f"defined")

            if "graphics_on" in ins and graphics_root:
                g = os.path.join(graphics_root, ins["graphics_on"])
                if not os.path.exists(g):
                    rep.error(f"{where}: graphics element {ins['graphics_on']!r} "
                              f"not found at {g}")

        if depth != 0:
            rep.error(f"{label}: {depth} epg_group(s) left open at the end")

    # ── unused ────────────────────────────────────────────────────────────────
    # _content.yml is a shared vocabulary imported by every schedule variant, so
    # any single schedule is expected to leave most of it unused. These are
    # listed, not warned about, because the signal worth having is the reverse
    # direction — a key that is REFERENCED and missing, which is an error above.
    unused_c = sorted(keys - used_content)
    unused_s = sorted(seq_keys - used_seq)
    if unused_c:
        print(f"   {len(unused_c)} content key(s) defined but unused here "
              f"(expected: _content.yml is shared by every variant)")
    if unused_s:
        print(f"   unused sequences: {', '.join(unused_s)}")

    # ── the playout must loop ─────────────────────────────────────────────────
    playout = doc.get("playout") or []
    if not any("repeat" in i for i in playout):
        rep.warn("no `repeat: true` at the end of the playout — the channel "
                 "stops when it runs out of instructions")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("schedule")
    ap.add_argument("--graphics-root",
                    help="directory holding graphics-elements/, to check that "
                         "every graphics_on target exists")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as failures")
    args = ap.parse_args()

    rep = Report()
    doc = load(args.schedule)
    print(f"── {args.schedule} ──")

    schema_check(args.schedule, doc, is_import=False, rep=rep)

    base = os.path.dirname(os.path.abspath(args.schedule))
    for imp in doc.get("import") or []:
        p = imp if os.path.exists(imp) else os.path.join(base, imp)
        if os.path.exists(p):
            schema_check(p, load(p), is_import=True, rep=rep)

    content, sequence = resolve_imports(args.schedule, doc, rep)
    print(f"   {len(content)} content keys, {len(sequence)} sequences, "
          f"{len(doc.get('playout') or [])} playout instructions")
    check_traps(doc, content, sequence, rep, args.graphics_root)

    return rep.dump(args.strict)


if __name__ == "__main__":
    sys.exit(main())
