#!/usr/bin/env bash
# Channel Z0 — prove the spawn tools before you trust them with a new machine.
#
# Like tools/test-failover.sh, this needs no tower, no ErsatzTV, no media and no
# GPU. It builds a synthetic station out of a scratch SQLite database, runs the
# real z0-station-image.sh against it, and asserts the properties that actually
# decide whether a spawned node airs the right thing:
#
#   ENCODER    the ffmpeg profile is re-pointed at the new box's hardware, and
#              its NAME stops advertising the old one
#   ISOLATION  the source machine's Plex/Jellyfin/Emby libraries do not travel
#   ANCHOR     playout state is cleared, so the week re-enters at the top
#              instead of resuming at an instruction index that means nothing
#              here (the failure #38 exists to prevent)
#   INDEX      the search index is dropped, because a stale one silently makes
#              every tag query resolve to nothing
#   CHANNEL    the channel number is read from the station, never assumed to be 1
#   LEASE      the cluster lease is never copied between nodes
#
#   ./tools/test-spawn.sh
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GRN=$'\033[32m'; RED=$'\033[31m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
[[ -t 1 ]] || { GRN=""; RED=""; BOLD=""; OFF=""; }
PASS=0; FAIL=0
ok()   { printf '  %sPASS%s  %s\n' "$GRN" "$OFF" "$*"; PASS=$((PASS+1)); }
bad()  { printf '  %sFAIL%s  %s\n' "$RED" "$OFF" "$*"; FAIL=$((FAIL+1)); }
is()   { # is <label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then ok "$1 — ${2}"; else bad "$1 — got '${2}', expected '${3}'"; fi
}
step() { printf '\n%s── %s%s\n' "$BOLD" "$*" "$OFF"; }

command -v sqlite3 >/dev/null || { echo "sqlite3 required"; exit 1; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
SRC="${WORK}/config"; mkdir -p "${SRC}/search-index" "${SRC}/templates"

# ── a synthetic station ──────────────────────────────────────────────────────
# Two media sources: one local, one "Jellyfin" holding somebody else's 2000
# items. One channel, deliberately numbered 0 — the number this station really
# uses, and the one a hardcoded /iptv/channel/1.ts would miss.
sqlite3 "${SRC}/ersatztv.sqlite3" <<'SQL'
CREATE TABLE MediaSource (Id INTEGER PRIMARY KEY);
CREATE TABLE LocalMediaSource (Id INTEGER PRIMARY KEY);
CREATE TABLE JellyfinMediaSource (Id INTEGER PRIMARY KEY);
CREATE TABLE Library (Id INTEGER PRIMARY KEY, Name TEXT, MediaSourceId INTEGER);
CREATE TABLE LibraryPath (Id INTEGER PRIMARY KEY, LibraryId INTEGER, Path TEXT);
CREATE TABLE MediaItem (Id INTEGER PRIMARY KEY, LibraryPathId INTEGER);
CREATE TABLE SmartCollection (Id INTEGER PRIMARY KEY, Name TEXT, Query TEXT);
CREATE TABLE Channel (Id INTEGER PRIMARY KEY, Number INTEGER, Name TEXT, FFmpegProfileId INTEGER);
CREATE TABLE FFmpegProfile (Id INTEGER PRIMARY KEY, Name TEXT, HardwareAcceleration INTEGER,
                            VaapiDevice TEXT, VaapiDriver INTEGER, VideoBitrate INTEGER);
CREATE TABLE Playout (Id INTEGER PRIMARY KEY, ChannelId INTEGER);
CREATE TABLE PlayoutItem (Id INTEGER PRIMARY KEY, PlayoutId INTEGER);
CREATE TABLE PlayoutAnchor (Id INTEGER PRIMARY KEY, PlayoutId INTEGER, InstructionIndex INTEGER);
CREATE TABLE PlayoutHistory (Id INTEGER PRIMARY KEY);
CREATE TABLE PlayoutGap (Id INTEGER PRIMARY KEY);

INSERT INTO MediaSource VALUES (1),(2);
INSERT INTO LocalMediaSource VALUES (1);
INSERT INTO JellyfinMediaSource VALUES (2);
INSERT INTO Library VALUES (1,'Other Videos',1),(2,'Jellyfin Shows',2);
INSERT INTO LibraryPath VALUES (1,1,'/media'),(2,2,'jellyfin://abc');
INSERT INTO MediaItem SELECT NULL, 1 FROM (WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<789) SELECT x FROM c);
INSERT INTO MediaItem SELECT NULL, 2 FROM (WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<2000) SELECT x FROM c);
INSERT INTO SmartCollection VALUES (1,'Z0 Cartoons','type:other_video AND tag:cartoons');
INSERT INTO FFmpegProfile VALUES (1,'854x480 h264_nvenc aac',2,NULL,0,1600);
INSERT INTO Channel VALUES (1,0,'Channel Z0',1);
INSERT INTO Playout VALUES (1,1);
INSERT INTO PlayoutItem SELECT NULL,1 FROM (WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x<500) SELECT x FROM c);
INSERT INTO PlayoutAnchor VALUES (1,1,447);
INSERT INTO PlayoutHistory VALUES (1);
INSERT INTO PlayoutGap VALUES (1);
SQL
echo "stale" > "${SRC}/search-index/segments.gen"
echo "elements" > "${SRC}/templates/z0-rail-left.yml"

IMG="${WORK}/station.tgz"
tar czf "$IMG" -C "$SRC" . || { echo "could not build fixture"; exit 1; }

step "Fixture"
echo "  789 local items + 2000 remote · channel 0 · nvenc profile · anchor at instruction 447"

# ── restore onto a VAAPI box ─────────────────────────────────────────────────
step "Restore onto a VAAPI machine"
DST="${WORK}/dst"
bash "${DIR}/z0-station-image.sh" --restore "$IMG" --config "$DST" --hwaccel vaapi >/dev/null 2>&1
D="${DST}/ersatztv.sqlite3"
q() { sqlite3 "$D" "$1" 2>/dev/null; }

is "ENCODER   hwaccel is Vaapi(3)"       "$(q 'SELECT HardwareAcceleration FROM FFmpegProfile;')" "3"
is "ENCODER   vaapi device set"          "$(q 'SELECT VaapiDevice FROM FFmpegProfile;')" "/dev/dri/renderD128"
is "ENCODER   name no longer says nvenc" "$(q "SELECT Name FROM FFmpegProfile;")" "854x480 h264_vaapi aac"
is "ISOLATION only the local source"     "$(q 'SELECT COUNT(*) FROM MediaSource;')" "1"
is "ISOLATION remote library dropped"    "$(q 'SELECT COUNT(*) FROM Library;')" "1"
is "ISOLATION only local items remain"   "$(q 'SELECT COUNT(*) FROM MediaItem;')" "789"
is "ANCHOR    playout items cleared"     "$(q 'SELECT COUNT(*) FROM PlayoutItem;')" "0"
is "ANCHOR    instruction index cleared" "$(q 'SELECT COUNT(*) FROM PlayoutAnchor;')" "0"
is "CHANNEL   number preserved as 0"     "$(q 'SELECT Number FROM Channel;')" "0"
is "STATION   collections survive"       "$(q 'SELECT COUNT(*) FROM SmartCollection;')" "1"
is "STATION   graphics templates travel" "$(ls "${DST}/templates" 2>/dev/null | wc -l)" "1"
[[ -d "${DST}/search-index" ]] && bad "INDEX     stale search index was carried across" \
                               || ok  "INDEX     stale search index dropped"
is "INTEGRITY database is sound"         "$(q 'PRAGMA integrity_check;')" "ok"

# ── and onto an NVENC box ────────────────────────────────────────────────────
step "Restore onto an NVENC machine"
DST2="${WORK}/dst2"
bash "${DIR}/z0-station-image.sh" --restore "$IMG" --config "$DST2" --hwaccel nvenc >/dev/null 2>&1
D="$DST2"; q() { sqlite3 "${DST2}/ersatztv.sqlite3" "$1" 2>/dev/null; }
is "ENCODER   hwaccel is Nvenc(2)"       "$(q 'SELECT HardwareAcceleration FROM FFmpegProfile;')" "2"
# Single quotes for the SQL string literal: sqlite >= 3.53 resolves a
# double-quoted token as an identifier, so "none" becomes an unknown column and
# the assertion quietly compares against an empty error result.
is "ENCODER   vaapi device cleared"      "$(q "SELECT COALESCE(VaapiDevice,'none') FROM FFmpegProfile;")" "none"

# ── --keep-remote is honoured ────────────────────────────────────────────────
step "Restore keeping the remote libraries"
DST3="${WORK}/dst3"
bash "${DIR}/z0-station-image.sh" --restore "$IMG" --config "$DST3" --hwaccel none --keep-remote >/dev/null 2>&1
is "ISOLATION --keep-remote keeps them"  "$(sqlite3 "${DST3}/ersatztv.sqlite3" 'SELECT COUNT(*) FROM MediaItem;' 2>/dev/null)" "2789"

# ── the lease must never travel ──────────────────────────────────────────────
# Two nodes that both think they hold the lease both publish, and the channel
# stops playing. The exclusion is one line in z0-media-sync.sh and this is the
# test that keeps it there.
step "Media sync never copies the lease"
PEER="${WORK}/peer"; mkdir -p "${PEER}/.z0-cluster/uplink.lock" "${PEER}/cartoons"
echo "heartbeat" > "${PEER}/.z0-cluster/uplink.lock/heartbeat"
echo "film" > "${PEER}/cartoons/a.mp4"; echo "<nfo/>" > "${PEER}/cartoons/a.nfo"
MDST="${WORK}/mdst"
bash "${DIR}/z0-media-sync.sh" --from-peer "$PEER" --to "$MDST" >/dev/null 2>&1
[[ -e "${MDST}/.z0-cluster" ]] && bad "LEASE     the lease was copied — this node would double-publish" \
                               || ok  "LEASE     lease not copied"
is "LEASE     media still copied"        "$(ls "${MDST}/cartoons" 2>/dev/null | wc -l)" "2"

# ── refuse to clobber ────────────────────────────────────────────────────────
step "Refuses to overwrite a station without --force"
bash "${DIR}/z0-station-image.sh" --restore "$IMG" --config "$DST" --hwaccel none >/dev/null 2>&1
is "SAFETY    non-empty config refused"  "$?" "1"

step "Result"
printf '  %d passed, %d failed\n' "$PASS" "$FAIL"
(( FAIL == 0 )) || exit 1
