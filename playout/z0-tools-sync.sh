#!/bin/bash
# Channel Z0 — make the node's tool copy derive from main, mechanically.
#
#   Gitea main ──git fetch──▶ /opt/channel-z0/src ──rsync──▶ .z0tools/tools/
#                                                    ├─rsync──▶ .z0tools/lists/
#                                                    │          ▲
#                                                    │  root's cron runs from ┘
#                                                    └─install─▶ playout/z0-leader.sh
#                                                               (the uplink supervisor;
#                                                                recreated when it changes)
#
# The station crons (weather, gap-log, drift-reset, day-align, lead-guard)
# run from .z0tools/tools/, not from a checkout, and the day aligner
# REGENERATES the schedule from that copy. Until 2026-09-15 the copy was
# hand-scp'd, so a merged generator change was undone by the next automatic
# repair (2026-08-19). This is now the only thing that writes the copy: cron
# runs it daily at 04:30, and it is run by hand right after a merge.
# lists/ rides along: z0-lists.py --check WRITES the ErsatzTV DB, so a stale
# manifest run from the copy deletes collections main still has (2026-09-15).
# The uplink supervisor (playout/z0-leader.sh) derives the same way since
# 2026-09-20: it used to be hand-copied into the live playout dir after a
# merge, with a .bak beside it, which is how a merged change sat undeployed.
# Idempotent. Watched by the sentinel check `z0-tools-in-sync`.
set -euo pipefail

REPO_URL="${Z0_REPO_URL:-https://gitea.hq.ripostelabs.xyz/sasha/channel-z0.git}"
CLONE="${Z0_REPO_CLONE:-/opt/channel-z0/src}"
TOOLS_DIR="${Z0_TOOLS_DIR:-/mnt/main-data/channelz0/.z0tools/tools}"
LISTS_DIR="${Z0_LISTS_DIR:-/mnt/main-data/channelz0/.z0tools/lists}"
PLAYOUT_DIR="${Z0_PLAYOUT_DIR:-/mnt/main-data/channelz0/.z0tools/playout}"
# The live compose project: where `docker compose up -d` was run from.
LIVE_DIR="${Z0_LIVE_PLAYOUT_DIR:-/opt/channel-z0/playout}"
# Seeded into the live .env once, if absent: the studio the uplink yields to
# for live shows (z0-leader.sh, "Live hold"). Station-specific, like REPO_URL.
LIVE_HOLD_URL="${Z0_LIVE_HOLD_URL:-https://smear.hq.ripostelabs.xyz/api/live/status}"
SELF="${Z0_TOOLS_SYNC_SELF:-/usr/local/sbin/z0-tools-sync}"

# Generated on the node, never in git: survive the --delete.
KEEP=(__pycache__ inventory.json)

if [ ! -d "$CLONE/.git" ]; then
    git clone --quiet --branch main "$REPO_URL" "$CLONE"
fi
git -C "$CLONE" fetch --quiet origin main
git -C "$CLONE" checkout --quiet --detach origin/main

# Keep this script current FIRST, and carry on as the new one: a merge that
# changes what sync does is then honoured on the run that fetches it, not the
# run after. install(1) writes a new inode, so the copy bash is still reading
# is untouched; the guard stops a bad install from re-exec'ing forever.
if ! cmp -s "$CLONE/playout/z0-tools-sync.sh" "$SELF"; then
    install -m 755 "$CLONE/playout/z0-tools-sync.sh" "$SELF"
    if [ -z "${Z0_TOOLS_SYNC_REEXEC:-}" ]; then
        echo "$(date -u +%FT%TZ) z0-tools-sync updated from main; re-running as the new one"
        Z0_TOOLS_SYNC_REEXEC=1 exec "$SELF" "$@"
    fi
fi

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

# The uplink supervisor. compose.yml bind-mounts ./z0-leader.sh into the
# uplink container read-only, by path, so a new inode here is invisible to
# the running one until it is recreated -- which is the point: the swap is
# one deliberate recreate, not a script changing under a running bash.
# 0600 like the hand-copied original: it sits next to .env.
deployed=""
if [ -f "$LIVE_DIR/compose.yml" ]; then
    if ! cmp -s "$CLONE/playout/z0-leader.sh" "$LIVE_DIR/z0-leader.sh"; then
        install -m 600 "$CLONE/playout/z0-leader.sh" "$LIVE_DIR/z0-leader.sh"
        deployed="z0-leader.sh"
    fi
    # One-time seed of the live-hold knob. .env is not in git, so a merged
    # feature that needs a new key would otherwise wait for a hand edit.
    if [ -f "$LIVE_DIR/.env" ] && ! grep -q '^Z0_LIVE_HOLD_URL=' "$LIVE_DIR/.env"; then
        printf '\n# Live shows come in through Smear; the uplink yields while it pushes\n# to our ingest (playout/z0-leader.sh, "Live hold"). Seeded by z0-tools-sync.\nZ0_LIVE_HOLD_URL=%s\n' \
            "$LIVE_HOLD_URL" >> "$LIVE_DIR/.env"
        deployed="${deployed:+$deployed }.env:Z0_LIVE_HOLD_URL"
    fi
    # Only a running uplink is recreated. A stopped one (a live show being run
    # by hand, or the bare-metal unit in use instead) is left alone; the next
    # `docker compose up -d uplink` picks the new script and env up anyway.
    if [ -n "$deployed" ] && command -v docker >/dev/null \
       && docker compose -f "$LIVE_DIR/compose.yml" ps --services --status running 2>/dev/null | grep -qx uplink; then
        docker compose -f "$LIVE_DIR/compose.yml" up -d --force-recreate --quiet-pull uplink
        deployed="$deployed (uplink recreated)"
    fi
fi

echo "$(date -u +%FT%TZ) tools lists playout <- main $(git -C "$CLONE" rev-parse --short HEAD)${deployed:+; deployed: $deployed}"
