#!/usr/bin/env bash
# Channel Z0 — the node's tool copy must follow a source the node can read.
#
# The forge went private with the Forgejo move on 2026-10-28. The node holds
# no credential, so every nightly z0-tools-sync since has died on
# "could not read Username" and the copy the station crons run from froze.
# Nothing diverged for two weeks only because nothing merged.
#
# Two assertions:
#   SOURCE   the default source answers an anonymous reader (the public mirror)
#   REPOINT  a clone made from an old source follows Z0_REPO_URL, not its
#            remembered origin
#
# Works on scratch directories only.
#
# Usage:
#   tools/test-tools-sync.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$DIR/../playout/z0-tools-sync.sh"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
fails=0

fail() { echo "  FAIL: $*"; fails=$((fails + 1)); }

# ── SOURCE ───────────────────────────────────────────────────────────────────
default_url="$(sed -n 's/^REPO_URL="\${Z0_REPO_URL:-\(.*\)}"$/\1/p' "$SYNC")"
case "$default_url" in
  *gitea.hq.*) fail "default source is the private forge ($default_url)" ;;
  "")          fail "no default REPO_URL found in z0-tools-sync.sh" ;;
esac

# ── REPOINT ──────────────────────────────────────────────────────────────────
# A source repository with one tool in it, and a clone whose origin is dead.
git init -q -b main "$SCRATCH/source"
mkdir -p "$SCRATCH/source/tools" "$SCRATCH/source/lists" "$SCRATCH/source/playout"
echo "v1" > "$SCRATCH/source/tools/probe.txt"
touch "$SCRATCH/source/lists/z0-lists.yml" "$SCRATCH/source/playout/_content.yml" \
      "$SCRATCH/source/playout/_sequences.yml"
cp "$SYNC" "$SCRATCH/source/playout/z0-tools-sync.sh"
git -C "$SCRATCH/source" add -A
git -C "$SCRATCH/source" -c user.name=t -c user.email=t@example.org commit -q -m seed

git clone -q --branch main "$SCRATCH/source" "$SCRATCH/clone"
git -C "$SCRATCH/clone" remote set-url origin "$SCRATCH/gone-private"

echo "v2" > "$SCRATCH/source/tools/probe.txt"
git -C "$SCRATCH/source" -c user.name=t -c user.email=t@example.org commit -q -am second

Z0_REPO_URL="$SCRATCH/source" Z0_REPO_CLONE="$SCRATCH/clone" \
Z0_TOOLS_DIR="$SCRATCH/out/tools" Z0_LISTS_DIR="$SCRATCH/out/lists" \
Z0_PLAYOUT_DIR="$SCRATCH/out/playout" Z0_SYNC_SELF="$SCRATCH/out/z0-tools-sync" \
  bash "$SYNC" > "$SCRATCH/log" 2>&1 || fail "sync exited non-zero: $(tail -1 "$SCRATCH/log")"

[ "$(cat "$SCRATCH/out/tools/probe.txt" 2>/dev/null)" = "v2" ] \
  || fail "an existing clone did not follow Z0_REPO_URL to the new source"
[ -x "$SCRATCH/out/z0-tools-sync" ] || fail "the script did not refresh its own installed copy"

if [ "$fails" -gt 0 ]; then
  echo "test-tools-sync: $fails failure(s)"
  exit 1
fi
echo "ok: tools sync reads a public source and re-points an old clone"
