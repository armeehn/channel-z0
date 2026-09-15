#!/bin/bash
# Channel Z0 — make the node's tool copy derive from main, mechanically.
#
#   Gitea main ──git fetch──▶ /opt/channel-z0/src ──rsync──▶ .z0tools/tools/
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
set -euo pipefail

REPO_URL="${Z0_REPO_URL:-https://gitea.hq.ripostelabs.xyz/sasha/channel-z0.git}"
CLONE="${Z0_REPO_CLONE:-/opt/channel-z0/src}"
TOOLS_DIR="${Z0_TOOLS_DIR:-/mnt/main-data/channelz0/.z0tools/tools}"
LISTS_DIR="${Z0_LISTS_DIR:-/mnt/main-data/channelz0/.z0tools/lists}"
SELF=/usr/local/sbin/z0-tools-sync

# Generated on the node, never in git: survive the --delete.
KEEP=(__pycache__ inventory.json)

if [ ! -d "$CLONE/.git" ]; then
    git clone --quiet --branch main "$REPO_URL" "$CLONE"
fi
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

# Keep this script current too. install(1) writes a new inode, so the
# copy bash is still reading is untouched.
install -m 755 "$CLONE/playout/z0-tools-sync.sh" "$SELF"

echo "$(date -u +%FT%TZ) tools lists <- main $(git -C "$CLONE" rev-parse --short HEAD)"
