#!/usr/bin/env python3
"""Prove tools/rebrand.py on a scratch copy of the tree. No third-party deps.

1. With no identity file the tree is already in step (--check passes).
2. A sample identity leaves no upstream identity in the brand-facing files
   and renames every SLUG path.
3. A second run is a no-op.
4. Restoring the upstream identity gives back the byte-exact upstream tree.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import rebrand  # noqa: E402

SAMPLE = {
    'STATION_NAME': 'Public Access Nine',
    'STATION_SHORT': 'PA9',
    'CHANNEL_LABEL': 'CH 9',
    'CHANNEL_TAG': 'CH9',
    'DESIGNATION': 'PA-9',
    'TAGLINE': 'television for one town',
    'SIGNOFF_LINE': 'GOODNIGHT, TOWN',
    'FLAGSHIP_SHOW': 'Main Street',
    'LAB_SHOW': 'Shop Hour',
    'SLUG': 'public-access-nine',
    'REPO': 'someone/public-access-nine',
    'SITE_DOMAIN': 'pa9.example',
    'WATCH_DOMAIN': 'watch.pa9.example',
    'CONTACT_EMAIL': 'desk@pa9.example',
    'SPONSOR_LEGAL': 'Nine Street Co-op Ltd.',
    'SPONSOR_NAME': 'Nine Street Co-op',
    'SPONSOR_SHORT': 'Nine Street',
    'SPONSOR_MANTRA': 'MAKE · SHARE · REPAIR',
    'SHOP_URL': 'https://shop.pa9.example',
    'SPONSOR_DOMAIN': 'ninestreet.example',
    'CITY': 'Nelson',
    'REGION': 'BC',
    'TIMEZONE': 'America/Edmonton',
    'WX_LAT': '49.49',
    'WX_LON': '-117.29',
}

# Files a fork reads first; none may still carry the upstream identity.
BRAND_FILES = [
    'README.md',
    'site/index.html',
    'site/retro/index.html',
    'site/_redirects',
    'wrangler.jsonc',
    'package.json',
    'worker/moderate.js',
    'worker/index.js',
    'vps/Caddyfile',
    '.env.example',
    'tools/make-signoff.sh',
    'tools/make-testcard.sh',
    'tools/z0-weather.py',
    'playout/z0-uplink.service',
    'playout/channel-z0.yml',
    '.github/workflows/verify.yml',
    '.gitea/workflows/mirror-to-github.yml',
]

# Upstream fragments that must be gone from BRAND_FILES after a rebrand.
UPSTREAM_FRAGMENTS = [
    'Channel Z0',
    'CHANNEL Z0',
    'ripostelabs',
    'Riposte',
    'RIPOSTE',
    'armeehn',
    'Kelowna',
    'KELOWNA',
    'GROUND ZERO',
    'Ground Zero',
    'RL-Z0',
    'channel-z0',
    'GOODNIGHT, LOCALS',
]


def kept_regions_removed(text):
    """Drop rebrand:off … rebrand:on spans; they name the upstream on purpose."""
    return re.sub(re.escape(rebrand.SKIP_ON) + ".*?" + re.escape(rebrand.SKIP_OFF), "", text, flags=re.S)


def run(cwd, *args):
    return subprocess.run([sys.executable, os.path.join(cwd, "tools", "rebrand.py"), *args],
                          cwd=cwd, capture_output=True, text=True)


def snapshot(root):
    files = {}
    for path in rebrand.tracked_files():
        full = os.path.join(root, path)
        if os.path.isfile(full):
            with open(full, "rb") as fh:
                files[path] = fh.read()

    return files


def copy_tree(dst):
    for path in rebrand.tracked_files():
        src = os.path.join(ROOT, path)
        if not os.path.isfile(src):
            continue

        target = os.path.join(dst, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)


def write_identity(root, values):
    with open(os.path.join(root, rebrand.IDENTITY_FILE), "w", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write("%s=%s\n" % (key, value))


def main():
    failures = []

    def check(cond, label):
        print(("ok   " if cond else "FAIL ") + label)
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        copy_tree(tmp)
        rebrand.ROOT = tmp
        before = snapshot(tmp)
        before.pop(rebrand.IDENTITY_FILE, None)

        res = run(tmp, "--check")
        check(res.returncode == 0, "upstream tree passes --check: " + res.stdout.strip().splitlines()[-1])

        write_identity(tmp, SAMPLE)
        res = run(tmp)
        check(res.returncode == 0, "rebrand applies: " + res.stdout.strip().splitlines()[-1])

        for path in BRAND_FILES:
            full = os.path.join(tmp, path.replace(rebrand.upstream_values()["SLUG"], SAMPLE["SLUG"]))
            with open(full, encoding="utf-8", errors="replace") as fh:
                text = kept_regions_removed(fh.read())
            left = [f for f in UPSTREAM_FRAGMENTS if f in text]
            check(not left, "%s carries none of the upstream identity%s"
                  % (path, "" if not left else ": " + ", ".join(left)))

        old_slug, new_slug = rebrand.upstream_values()["SLUG"], SAMPLE["SLUG"]
        renamed = [p for p in before if old_slug in p]
        for path in renamed:
            check(os.path.exists(os.path.join(tmp, path.replace(old_slug, new_slug))),
                  "renamed " + path)

        res = run(tmp, "--check")
        check(res.returncode == 0, "second run is a no-op")

        write_identity(tmp, rebrand.upstream_values())
        res = run(tmp)
        check(res.returncode == 0, "restore applies")
        after = snapshot(tmp)
        after.pop(rebrand.IDENTITY_FILE, None)
        after.pop(rebrand.APPLIED_FILE, None)
        diff = sorted(set(before) ^ set(after)) + sorted(
            p for p in before if p in after and before[p] != after[p])
        check(not diff, "round trip is byte-exact" + ("" if not diff else ": " + ", ".join(diff[:10])))

    print("%d failure(s)" % len(failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
