#!/bin/bash
# Channel Z0 — make the node's tool copy derive from main, mechanically.
#
#   main (mirror) ─git fetch─▶ /opt/channel-z0/src ──rsync──▶ .z0tools/tools/
#                                                    └─rsync──▶ .z0tools/lists/
#                                                              ▲
#                                        root's cron runs from ┘
#
# The station crons (weather, gap-log, drift-reset, day-align, lead-guard)
# run from .z0tools/tools/, not from a checkout, and the day aligner
# REGENERATES the schedule from that copy. Until 2026-09-15 the copy was
# hand-scp'd, so a merged generator change was undone by the next automatic
# repair (2026-08-19). This is now the only thing that writes the copy: cron
# runs it daily at 04:30, and it is run by hand right after a merge.
# lists/ rides along: z0-lists.py --check WRITES the ErsatzTV DB, so a stale
# manifest run from the copy deletes collections main still has (2026-09-15).
# Idempotent. Watched by the sentinel check `z0-tools-in-sync`.
#
# The source is the public GitHub mirror, not the forge. The forge has needed
# a login since the Forgejo move (2026-10-28) and the node holds no
# credential, so every run from then until 2026-11-10 died on "could not read
# Username". The mirror is pushed from the forge on every merge to main; run
# this by hand only once that push has gone through.
set -euo pipefail

REPO_URL="${Z0_REPO_URL:-https://github.com/armeehn/channel-z0.git}"
CLONE="${Z0_REPO_CLONE:-/opt/channel-z0/src}"
TOOLS_DIR="${Z0_TOOLS_DIR:-/mnt/main-data/channelz0/.z0tools/tools}"
LISTS_DIR="${Z0_LISTS_DIR:-/mnt/main-data/channelz0/.z0tools/lists}"
PLAYOUT_DIR="${Z0_PLAYOUT_DIR:-/mnt/main-data/channelz0/.z0tools/playout}"
SELF="${Z0_SYNC_SELF:-/usr/local/sbin/z0-tools-sync}"

# Generated on the node, never in git: survive the --delete.
KEEP=(__pycache__ inventory.json)

if [ ! -d "$CLONE/.git" ]; then
    git clone --quiet --branch main "$REPO_URL" "$CLONE"
fi
# A clone remembers the source it was made from. Re-point it every run, or a
# node cloned from the forge keeps asking the forge.
git -C "$CLONE" remote set-url origin "$REPO_URL"
git -C "$CLONE" fetch --quiet origin main
git -C "$CLONE" checkout --quiet --detach origin/main

EXCL=()
for k in "${KEEP[@]}"; do
    EXCL+=(--exclude "$k")
done
mkdir -p "$TOOLS_DIR"
rsync -a --delete "${EXCL[@]}" "$CLONE/tools/" "$TOOLS_DIR/"
mkdir -p "$LISTS_DIR"
rsync -a --delete "$CLONE/lists/" "$LISTS_DIR/"
# The two import fragments ride along too, so `z0 fragments` on x can deploy
# what main actually has (2026-09-15: the bumps/promos keys). Deploying into
# /config stays a deliberate step; this only stages the copy.
mkdir -p "$PLAYOUT_DIR"
rsync -a "$CLONE/playout/_content.yml" "$CLONE/playout/_sequences.yml" "$PLAYOUT_DIR/"

# Keep this script current too. install(1) writes a new inode, so the
# copy bash is still reading is untouched.
install -m 755 "$CLONE/playout/z0-tools-sync.sh" "$SELF"

echo "$(date -u +%FT%TZ) tools lists playout <- main $(git -C "$CLONE" rev-parse --short HEAD)"
