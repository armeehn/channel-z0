#!/usr/bin/env bash
# Channel Z0 — mirror the library onto a new node, faithfully.
#
# Why this exists, when fetch-archive.sh already stocks a library:
#
#   fetch-archive.sh runs SEARCH QUERIES against archive.org. Run it on a fresh
#   box and you get *a* library — 30 cartoons, 10 noir features — but not THIS
#   one. Different titles, different durations, different tags. The schedule
#   still builds, and then Tuesday's cartoon block is films nobody chose. Its
#   manifest only ever SKIPS what is already down; it cannot replay a library.
#
#   And roughly a fifth of the library has no recipe at all: schoolroom, the
#   Canadian and BC public-domain sets, the 73 music cards, everything under
#   generative/, the idents and cards. Those were curated or generated. A query
#   will never return them.
#
# So: to stand up a node that airs the same station, copy the library.
#
# Usage:
#   tools/z0-media-sync.sh --from-peer root@vile:/mnt/main-data/channelz0
#   tools/z0-media-sync.sh --from-peer /mnt/nas/channelz0 --to /media/channelz0
#   tools/z0-media-sync.sh --from-peer root@vile:/mnt/main-data/channelz0 --verify
#
# Resumable: it is rsync underneath. Kill it and run it again.
set -uo pipefail

FROM=""; TO="${Z0_MEDIA_ROOT:-/media/channelz0}"; BWLIMIT=""; DRY=0; VERIFY_ONLY=0; DELETE=0

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
[[ -t 1 ]] || { BOLD=""; RED=""; GRN=""; YEL=""; OFF=""; }
say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s   %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %swarn%s %s\n' "$YEL" "$OFF" "$*"; }
die()  { printf '  %sERR%s  %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }
step() { printf '\n%s── %s%s\n' "$BOLD" "$*" "$OFF"; }
usage() { sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-peer) FROM="$2"; shift 2 ;;
    --to)        TO="$2"; shift 2 ;;
    --bwlimit)   BWLIMIT="$2"; shift 2 ;;
    --delete)    DELETE=1; shift ;;
    --verify)    VERIFY_ONLY=1; shift ;;
    --dry-run)   DRY=1; shift ;;
    -h|--help)   usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done
[[ -n "$FROM" ]] || usage 1
command -v rsync >/dev/null || die "rsync not installed"

# Never copy these.
#
#   .z0-cluster   THE LEASE. It is a directory whose existence means "a node is
#                 on air". Copy it onto a new box and that box starts up already
#                 believing it holds the lease — which is the exact double-
#                 publish this station's whole locking design exists to prevent,
#                 and the symptom is a channel that will not play.
#   .z0-archive/candidates   a search-result cache, regenerated on demand
#   transcode/, .tmp        scratch
EXCLUDES=(
  --exclude='.z0-cluster/'
  --exclude='.z0-archive/candidates/'
  --exclude='transcode/'
  --exclude='*.partial' --exclude='*.tmp' --exclude='.DS_Store'
)

SRC="${FROM%/}/"
DST="${TO%/}/"

# ── verify ───────────────────────────────────────────────────────────────────
# Counting both sides is the cheap proof. Sizes catch a truncated transfer that
# a file count alone would call a success.
side_stats() { # $1 = path spec (local path, or user@host:/path)
  # The counting script goes over stdin, never through a quoted -c string.
  # Building it with printf is how the \n in find's -printf ends up as a real
  # newline in the middle of an awk program, which fails in a way that reads
  # like the peer is empty.
  local spec="$1"
  if [[ "$spec" == *:* && "$spec" != /* ]]; then
    ssh -o BatchMode=yes "${spec%%:*}" bash -s -- "${spec#*:}" <<'STATS'
p="$1"
find "$p" -type f ! -path "*/.z0-cluster/*" ! -path "*/.z0-archive/candidates/*" -printf '%s\n' 2>/dev/null \
  | awk '{n++; b+=$1} END {print n+0, b+0}'
STATS
  else
    bash -s -- "$spec" <<'STATS'
p="$1"
find "$p" -type f ! -path "*/.z0-cluster/*" ! -path "*/.z0-archive/candidates/*" -printf '%s\n' 2>/dev/null \
  | awk '{n++; b+=$1} END {print n+0, b+0}'
STATS
  fi
}

human() { numfmt --to=iec --suffix=B "${1:-0}" 2>/dev/null || echo "${1:-0}B"; }

if (( VERIFY_ONLY )); then
  step "Verifying ${DST} against ${FROM}"
  read -r SN SB <<<"$(side_stats "${FROM%/}")"
  read -r DN DB <<<"$(side_stats "${TO%/}")"
  say "  source: ${SN:-?} files, $(human "${SB:-0}")"
  say "  here:   ${DN:-?} files, $(human "${DB:-0}")"
  if [[ "${SN:-x}" == "${DN:-y}" && "${SB:-x}" == "${DB:-y}" ]]; then
    ok "library matches the peer"
    exit 0
  fi
  warn "library does NOT match — re-run the sync (it resumes)"
  exit 1
fi

# ── sync ─────────────────────────────────────────────────────────────────────
step "Mirroring the library"
say "  from: ${FROM}"
say "  to:   ${TO}"
[[ -n "$BWLIMIT" ]] && say "  cap:  ${BWLIMIT} KB/s"

# The uplink shares the house line with the thing that is actually on air. An
# uncapped pull here saturates the WAN and the LIVE stream drops out — that has
# happened, and it looked like the tower had died. Cap it if the source is off-box.
if [[ -z "$BWLIMIT" && "$FROM" == *:* && "$FROM" != /* ]]; then
  warn "no --bwlimit on a remote pull — this can saturate the line the station"
  warn "is broadcasting over. Consider --bwlimit 20000 (≈20 MB/s) or run it off-hours."
fi

# A dry run must not create anything, and must not report a failure it did not
# have — a preview you cannot trust is worse than no preview.
if (( DRY )); then
  [[ -d "$TO" ]] || say "  (dry run: ${TO} does not exist yet; it would be created)"
else
  mkdir -p "$TO" 2>/dev/null || die "cannot create ${TO}"
fi

RSYNC=( rsync -a --partial --partial-dir=.rsync-partial --human-readable
        --info=progress2,stats1 "${EXCLUDES[@]}" )
(( DELETE )) && RSYNC+=( --delete )
[[ -n "$BWLIMIT" ]] && RSYNC+=( "--bwlimit=${BWLIMIT}" )
(( DRY )) && RSYNC+=( --dry-run )

say ""
"${RSYNC[@]}" "$SRC" "$DST"
RC=$?
# 24 is "a file vanished while we copied" — normal against a library that a
# running station is still writing to, and not a failure.
if [[ $RC -eq 255 ]]; then
  die "cannot reach ${FROM%%:*} over ssh. Set up a key first:
       ssh-copy-id ${FROM%%:*}
     (rsync exits 255 for any ssh-level failure, so this is auth or routing,
      not the transfer itself.)"
fi
[[ $RC -eq 0 || $RC -eq 24 ]] || die "rsync failed (exit ${RC})"
(( DRY )) && { ok "dry run — nothing copied"; exit 0; }
ok "transfer complete"

# The sidecars are the tags, and the tags are the schedule.
#
# Every smart collection on this station is a tag query. An NFO that did not
# make the trip means its film is untagged, which means it is in no collection,
# which means a block quietly resolves to fewer items — or to nothing, and an
# empty pool schedules nothing and leaves a hole in the guide with no error.
NFO=$(find "$TO" -name '*.nfo' 2>/dev/null | wc -l)
VID=$(find "$TO" -type f \( -name '*.mp4' -o -name '*.mkv' -o -name '*.avi' -o -name '*.webm' \) 2>/dev/null | wc -l)
step "Landed"
say "  ${VID} video files, ${NFO} NFO sidecars"
(( NFO == 0 )) && warn "no NFO sidecars — every tag query will resolve to nothing"

step "Checking against the peer"
read -r SN SB <<<"$(side_stats "${FROM%/}")"
read -r DN DB <<<"$(side_stats "${TO%/}")"
say "  source: ${SN:-?} files, $(human "${SB:-0}")"
say "  here:   ${DN:-?} files, $(human "${DB:-0}")"
if [[ "${SN:-x}" == "${DN:-y}" && "${SB:-x}" == "${DB:-y}" ]]; then
  ok "library matches the peer"
else
  warn "counts differ — run again to resume, then --verify"
  exit 1
fi

say ""
say "  Next: ErsatzTV must SCAN this library, and the search index must rebuild"
say "  after it. A scan alone leaves the index stale, and a stale index makes"
say "  tag queries return nothing while every folder looks correctly populated."
