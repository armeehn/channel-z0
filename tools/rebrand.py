#!/usr/bin/env python3
"""Make this repository yours: rewrite the identity baked into every text file.

    tools/rebrand.py            apply IDENTITY_FILE to the tree
    tools/rebrand.py --dry-run  list what would change, touch nothing
    tools/rebrand.py --check    exit 1 if the tree is out of step with IDENTITY_FILE

How it works
------------
IDENTITY_FILE holds the values you want (KEY=value, one per line).
APPLIED_FILE holds the values the tree currently carries; it is written after
every run, and on a fresh checkout it is the upstream identity (UPSTREAM below).
Each run rewrites every occurrence of an applied value into the wanted value,
longest value first, whole tokens only, so "Channel Z0" never bites into
"channel-z0" and "ch0.example" never bites into "watch.ch0.example". Keys
flagged CASED also carry an UPPER CASE twin, which is how "CHANNEL Z0" on the
test card follows "Channel Z0" in the footer.

Paths containing SLUG are renamed too, and because the tree is rewritten from
the *applied* values, the tool is re-runnable: change IDENTITY_FILE again and run
again. Setting every key back to its upstream value returns the tree to the
byte-exact upstream, which tools/test_rebrand.py proves on every CI run.

What it will not do: redraw glyph-built logos, re-render committed PDFs or
video, or rename internal ids (container names, ErsatzTV element ids, file
names other than SLUG). See FORKING.md.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDENTITY_FILE = "station.env"
APPLIED_FILE = ".station.applied"
SLUG_KEY = "SLUG"
CASED = "cased"       # value also has an UPPER CASE twin in the tree
PLAIN = "plain"       # value appears exactly as written

# Region markers: text between them is left alone (licence trailers, this doc).
SKIP_ON = "rebrand:off"
SKIP_OFF = "rebrand:on"

# Files never rewritten: the tool itself, its state, binaries, committed renders.
SKIP_PATHS = {IDENTITY_FILE, APPLIED_FILE, "LICENSE", "FORKING.md"}
SKIP_PREFIXES = ("tools/rebrand.py", "tools/test_rebrand.py", "docs/pdf/", "station.env", ".station.applied")

# The upstream identity: (KEY, upstream value, case handling, what it is).
UPSTREAM = [
    ('STATION_NAME', 'Channel Z0', CASED, 'the station, as spoken and printed'),
    ('STATION_SHORT', 'Z0', PLAIN, 'the short form: masthead, list prefix, prose'),
    ('CHANNEL_LABEL', 'CH 0', PLAIN, 'the dial position on cards and intervals'),
    ('CHANNEL_TAG', 'CH0', PLAIN, 'compact label in the now-playing prefix (letters and digits only)'),
    ('DESIGNATION', 'RL-Z0', PLAIN, 'document/desig code on every card'),
    ('TAGLINE', 'a local channel, for locals', PLAIN, 'one line under the name'),
    ('SIGNOFF_LINE', 'GOODNIGHT, LOCALS', PLAIN, 'the midnight sign-off card'),
    ('FLAGSHIP_SHOW', 'Ground Zero', CASED, 'the nightly flagship'),
    ('LAB_SHOW', 'Lab Hour', CASED, "the sponsor's own show"),
    ('SLUG', 'channel-z0', PLAIN, 'machine name: worker, swarm id, schedule file names'),
    ('REPO', 'armeehn/channel-z0', PLAIN, 'GitHub owner/name'),
    ('SITE_DOMAIN', 'ch0.ripostelabs.xyz', PLAIN, 'the storefront'),
    ('WATCH_DOMAIN', 'watch.ch0.ripostelabs.xyz', PLAIN, 'the tower (Owncast)'),
    ('CONTACT_EMAIL', 'ch0@ripostelabs.xyz', PLAIN, 'ad submissions and rights claims'),
    ('SPONSOR_LEGAL', 'Riposte Laboratories Inc.', CASED, 'copyright holder'),
    ('SPONSOR_NAME', 'Riposte Laboratories', CASED, 'the sponsor'),
    ('SPONSOR_SHORT', 'Riposte Labs', CASED, 'the sponsor, short'),
    ('SPONSOR_MANTRA', 'PARRY · RIPOSTE · RECYCLE · REPEAT', PLAIN, "the sponsor's footer line"),
    ('SHOP_URL', 'https://shop.ripostelabs.xyz', PLAIN, 'merch'),
    ('SPONSOR_DOMAIN', 'ripostelabs.xyz', PLAIN, "the sponsor's site"),
    ('CITY', 'Kelowna', CASED, 'weather desk and cards'),
    ('REGION', 'BC', PLAIN, 'province/state on the weather desk'),
    ('TIMEZONE', 'America/Vancouver', PLAIN, 'station clock (IANA)'),
    ('WX_LAT', '49.88307', PLAIN, 'weather desk latitude'),
    ('WX_LON', '-119.48568', PLAIN, 'weather desk longitude'),
]

# One applied value can carry aliases that mean the same thing upstream and
# must follow the key: e.g. two spellings of one timezone.
ALIASES = {

}

BOUNDARY_L = r"(?<![A-Za-z0-9_])"
BOUNDARY_R = r"(?![A-Za-z0-9_])"


def read_kv(path):
    values = {}
    if not os.path.exists(path):
        return values

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value

    return values


def write_kv(path, values):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Written by tools/rebrand.py: the identity the tree carries now.\n")
        fh.write("# Do not edit; edit %s and run the tool.\n" % IDENTITY_FILE)
        for key, _, _, _ in UPSTREAM:
            fh.write("%s=%s\n" % (key, values[key]))


def upstream_values():
    return {key: value for key, value, _, _ in UPSTREAM}


def tracked_files():
    """Tracked and untracked-but-not-ignored files; a plain walk outside git."""
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        found = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
            found.extend(os.path.relpath(os.path.join(base, f), ROOT) for f in files)
        return sorted(found)

    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], cwd=ROOT, check=True,
                         capture_output=True).stdout
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def is_text(data):
    return b"\0" not in data[:8192]


def skipped(path):
    if path in SKIP_PATHS:
        return True

    return path.startswith(SKIP_PREFIXES)


def build_rules(applied, wanted):
    """(compiled pattern, replacement) pairs, longest source first."""
    pairs = []
    for key, _, mode, _ in UPSTREAM:
        src, dst = applied[key], wanted[key]
        if src == dst:
            continue

        pairs.append((src, dst))
        for alias in ALIASES.get(key, ()):
            pairs.append((alias, dst))

        if mode == CASED and src.upper() != src:
            pairs.append((src.upper(), dst.upper()))

    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return [(re.compile(BOUNDARY_L + re.escape(s) + BOUNDARY_R), d) for s, d in pairs]


def rewrite(text, rules):
    """Apply rules outside rebrand:off … rebrand:on regions."""
    out, pos, live = [], 0, True
    marker = re.compile("(%s|%s)" % (re.escape(SKIP_ON), re.escape(SKIP_OFF)))

    for m in marker.finditer(text):
        chunk = text[pos:m.start()]
        out.append(apply_rules(chunk, rules) if live else chunk)
        out.append(m.group(0))
        live = m.group(0) == SKIP_OFF
        pos = m.end()

    tail = text[pos:]
    out.append(apply_rules(tail, rules) if live else tail)
    return "".join(out)


def apply_rules(text, rules):
    for pattern, replacement in rules:
        text = pattern.sub(replacement.replace("\\", "\\\\"), text)

    return text


def plan(applied, wanted):
    """Return ([(path, new_bytes)], [(old_path, new_path)])."""
    rules = build_rules(applied, wanted)
    edits, renames = [], []
    old_slug, new_slug = applied[SLUG_KEY], wanted[SLUG_KEY]

    for path in tracked_files():
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            continue

        if not skipped(path) and rules:
            with open(full, "rb") as fh:
                data = fh.read()

            if is_text(data):
                text = data.decode("utf-8", errors="surrogateescape")
                new = rewrite(text, rules)
                if new != text:
                    edits.append((path, new.encode("utf-8", errors="surrogateescape")))

        if old_slug != new_slug and old_slug in path:
            renames.append((path, path.replace(old_slug, new_slug)))

    return edits, renames


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when the tree does not match %s" % IDENTITY_FILE)
    args = ap.parse_args()

    wanted = dict(upstream_values())
    wanted.update(read_kv(os.path.join(ROOT, IDENTITY_FILE)))
    applied = dict(upstream_values())
    applied.update(read_kv(os.path.join(ROOT, APPLIED_FILE)))

    for key in wanted:
        if not wanted[key]:
            sys.exit("%s: %s is empty" % (IDENTITY_FILE, key))

    edits, renames = plan(applied, wanted)
    for path, _ in edits:
        print("rewrite  %s" % path)
    for old, new in renames:
        print("rename   %s -> %s" % (old, new))

    if args.check:
        if edits or renames:
            print("tree is out of step with %s: run tools/rebrand.py" % IDENTITY_FILE)
            sys.exit(1)
        print("tree matches %s" % IDENTITY_FILE)
        return

    if args.dry_run:
        print("%d file(s) to rewrite, %d to rename (dry run)" % (len(edits), len(renames)))
        return

    for path, data in edits:
        with open(os.path.join(ROOT, path), "wb") as fh:
            fh.write(data)

    for old, new in renames:
        os.makedirs(os.path.dirname(os.path.join(ROOT, new)) or ROOT, exist_ok=True)
        os.replace(os.path.join(ROOT, old), os.path.join(ROOT, new))

    write_kv(os.path.join(ROOT, APPLIED_FILE), wanted)
    print("%d file(s) rewritten, %d renamed" % (len(edits), len(renames)))


if __name__ == "__main__":
    main()
