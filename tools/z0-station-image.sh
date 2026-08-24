#!/usr/bin/env bash
# Channel Z0 — capture the station's brain, and pour it into a new machine.
#
# Everything that makes ErsatzTV *this* station — the FFmpeg profile, the
# libraries, the 19 smart collections, the filler presets, the channel and its
# watermark, the graphics elements, the playout — is configured through the web
# UI and stored in a single SQLite file. There is no config API: /api/… serves
# the SPA, not JSON, so "just POST the channel" is not a thing you can do.
#
# So the only faithful way to stand up an identical node is to carry the
# database across. That is what this does.
#
#   --capture   read a live node, write a portable image (never writes to source)
#   --restore   pour an image into a fresh /config, re-pointed at the new box
#   --inspect   say what is inside an image without unpacking it anywhere
#
# Usage:
#   tools/z0-station-image.sh --capture --from root@vile:/mnt/solid-state/ersatztv \
#                             --out /tmp/z0-station.tgz
#   tools/z0-station-image.sh --inspect /tmp/z0-station.tgz
#   tools/z0-station-image.sh --restore /tmp/z0-station.tgz \
#                             --config ./ersatztv-config --hwaccel vaapi
#
# See docs/clustering.md, "Standing up a node".
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[[ -r "${DIR}/z0-lib.sh" ]] && . "${DIR}/z0-lib.sh" 2>/dev/null || true

MODE=""; FROM=""; OUT=""; IMAGE=""; CONFIG=""; HWACCEL=""; VAAPI_DEVICE="/dev/dri/renderD128"
KEEP_REMOTE=0; FORCE=0; DRY=0

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
[[ -t 1 ]] || { BOLD=""; RED=""; GRN=""; YEL=""; OFF=""; }
say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s   %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %swarn%s %s\n' "$YEL" "$OFF" "$*"; }
die()  { printf '  %sERR%s  %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }
step() { printf '\n%s── %s%s\n' "$BOLD" "$*" "$OFF"; }

usage() { sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --capture)      MODE="capture"; shift ;;
    --restore)      MODE="restore"; IMAGE="${2:-}"; shift 2 ;;
    --inspect)      MODE="inspect"; IMAGE="${2:-}"; shift 2 ;;
    --from)         FROM="$2"; shift 2 ;;
    --out)          OUT="$2"; shift 2 ;;
    --config)       CONFIG="$2"; shift 2 ;;
    --hwaccel)      HWACCEL="$2"; shift 2 ;;
    --vaapi-device) VAAPI_DEVICE="$2"; shift 2 ;;
    --keep-remote)  KEEP_REMOTE=1; shift ;;
    --force)        FORCE=1; shift ;;
    --dry-run)      DRY=1; shift ;;
    -h|--help)      usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done
[[ -n "$MODE" ]] || usage 1

need() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"; }
need tar

# ErsatzTV's HardwareAccelerationKind. Verified against the enum in
# ErsatzTV.Core/Domain/HardwareAccelerationKind.cs — these are not guesses, and
# getting one wrong yields a profile that silently falls back to software and
# eats the CPU alive.
hwaccel_id() {
  case "${1,,}" in
    none|software) echo 0 ;;
    qsv)           echo 1 ;;
    nvenc|nvidia)  echo 2 ;;
    vaapi)         echo 3 ;;
    videotoolbox)  echo 4 ;;
    amf)           echo 5 ;;
    v4l2m2m)       echo 6 ;;
    rkmpp)         echo 7 ;;
    *) die "unknown --hwaccel '$1' (none|qsv|nvenc|vaapi|videotoolbox|amf|v4l2m2m|rkmpp)" ;;
  esac
}

# Things that must never travel between machines.
#   cache/logs/temp-pool/transcode  regenerated, and large
#   *-secrets.json + data-protection  credentials for THIS box's Plex/Jellyfin,
#                                     encrypted with a key ring that is also here
#   *.bak-* / .z0-backup-*          someone else's safety copies, not state
#   *-wal / *-shm                   folded into the DB by the backup below
EXCLUDES=(
  --exclude=cache --exclude=logs --exclude=temp-pool --exclude=transcode
  --exclude=data-protection --exclude='*-secrets.json'
  --exclude='*.sqlite3-wal' --exclude='*.sqlite3-shm'
  --exclude='*.bak-*' --exclude='.z0-backup-*'
)

# ── capture ──────────────────────────────────────────────────────────────────
if [[ "$MODE" == "capture" ]]; then
  [[ -n "$FROM" ]] || die "--capture needs --from <path> or <user@host:path>"
  [[ -n "$OUT"  ]] || die "--capture needs --out <file.tgz>"
  step "Capturing station image"

  REMOTE=""; SRC="$FROM"
  if [[ "$FROM" == *:* && "$FROM" != /* ]]; then
    REMOTE="${FROM%%:*}"; SRC="${FROM#*:}"
    say "  source: ${SRC} on ${REMOTE}"
  else
    say "  source: ${SRC} (local)"
  fi

  # Run a command on whichever side the config lives.
  at_src() { if [[ -n "$REMOTE" ]]; then ssh -o BatchMode=yes "$REMOTE" "$@"; else bash -c "$*"; fi; }

  at_src "test -f '${SRC}/ersatztv.sqlite3'" \
    || die "no ersatztv.sqlite3 under ${SRC} — is that the /config folder?"
  at_src "command -v sqlite3 >/dev/null" \
    || die "sqlite3 not available on the source — needed for a consistent copy"

  # The one thing that must not be a plain file copy. ErsatzTV runs with WAL on,
  # so cp'ing the .sqlite3 alone can capture a torn database that opens fine and
  # is missing the last few minutes of config. .backup is the online-backup API:
  # it takes a consistent snapshot of a database being written to, and it does
  # not modify the source.
  STAGE="/tmp/z0-station-image.$$"
  at_src "rm -rf '${STAGE}' && mkdir -p '${STAGE}'" || die "could not stage on source"
  if (( DRY )); then
    say "  would run: sqlite3 .backup + tar of ${SRC}"
  else
    at_src "sqlite3 'file:${SRC}/ersatztv.sqlite3?mode=ro' \".backup '${STAGE}/ersatztv.sqlite3'\"" \
      || die "sqlite3 .backup failed"
    at_src "sqlite3 '${STAGE}/ersatztv.sqlite3' 'PRAGMA integrity_check;'" | grep -qx ok \
      || die "captured database fails integrity_check — refusing to ship it"
    ok "database captured, integrity_check ok"
  fi
fi

if [[ "$MODE" == "capture" ]] && (( DRY )); then
  say ""; ok "dry run — nothing was read from the source and nothing written"; exit 0
fi

# Provenance is written into the image so a restore can say where it came from.
if [[ "$MODE" == "capture" ]]; then
  CHNUM="$(at_src "sqlite3 '${STAGE}/ersatztv.sqlite3' 'SELECT Number FROM Channel ORDER BY Id LIMIT 1;'" 2>/dev/null | tr -d '\r')"
  NITEMS="$(at_src "sqlite3 '${STAGE}/ersatztv.sqlite3' 'SELECT COUNT(*) FROM MediaItem;'" 2>/dev/null | tr -d '\r')"
  NCOLL="$(at_src "sqlite3 '${STAGE}/ersatztv.sqlite3' 'SELECT COUNT(*) FROM SmartCollection;'" 2>/dev/null | tr -d '\r')"
  HWID="$(at_src "sqlite3 '${STAGE}/ersatztv.sqlite3' 'SELECT HardwareAcceleration FROM FFmpegProfile ORDER BY Id LIMIT 1;'" 2>/dev/null | tr -d '\r')"
  at_src "cat > '${STAGE}/.z0-image.json'" <<META
{
  "captured_from": "${FROM}",
  "captured_at": "$(date -u +%FT%TZ)",
  "channel_number": "${CHNUM}",
  "media_items": "${NITEMS}",
  "smart_collections": "${NCOLL}",
  "source_hwaccel": "${HWID}"
}
META
  ok "channel ${CHNUM} · ${NITEMS} media items · ${NCOLL} smart collections"

  # Everything else in /config that is station identity rather than scratch:
  # the playout YAMLs, the graphics elements, the watermark and rail frames,
  # the search index, the templates and scripts.
  EXC=""
  for e in "${EXCLUDES[@]}"; do EXC+=" --exclude='${e#--exclude=}'"; done
  TARCMD="tar czf - -C '${SRC}'${EXC} --exclude='ersatztv.sqlite3' . 2>/dev/null"
  if [[ -n "$REMOTE" ]]; then
    ssh -o BatchMode=yes "$REMOTE" "$TARCMD" > "${OUT}.rest" || die "tar of source failed"
    ssh -o BatchMode=yes "$REMOTE" "tar czf - -C '${STAGE}' ersatztv.sqlite3 .z0-image.json" > "${OUT}.db" || die "tar of db failed"
    ssh -o BatchMode=yes "$REMOTE" "rm -rf '${STAGE}'" || true
  else
    bash -c "$TARCMD" > "${OUT}.rest" || die "tar of source failed"
    tar czf - -C "${STAGE}" ersatztv.sqlite3 .z0-image.json > "${OUT}.db" || die "tar of db failed"
    rm -rf "${STAGE}"
  fi

  # Fold the two halves into one image.
  WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
  tar xzf "${OUT}.rest" -C "$WORK" && tar xzf "${OUT}.db" -C "$WORK" || die "could not assemble image"
  rm -f "${OUT}.rest" "${OUT}.db"
  tar czf "$OUT" -C "$WORK" . || die "could not write ${OUT}"
  ok "wrote $(du -h "$OUT" | cut -f1) → ${OUT}"
  say ""
  say "  Restore it on the new box with:"
  say "    tools/z0-station-image.sh --restore ${OUT} --config ./ersatztv-config --hwaccel <kind>"
  exit 0
fi

# ── inspect ──────────────────────────────────────────────────────────────────
if [[ "$MODE" == "inspect" ]]; then
  [[ -f "$IMAGE" ]] || die "no such image: ${IMAGE}"
  step "Station image: ${IMAGE}"
  tar xzf "$IMAGE" -O ./.z0-image.json 2>/dev/null || tar xzf "$IMAGE" -O .z0-image.json 2>/dev/null \
    || warn "no .z0-image.json — image predates provenance, or is not a station image"
  say ""
  say "  contents:"
  tar tzf "$IMAGE" | sed 's|^\./||' | awk -F/ '{print $1}' | sort | uniq -c | sort -rn | head -15 | sed 's/^/    /'
  exit 0
fi

# ── restore ──────────────────────────────────────────────────────────────────
if [[ "$MODE" == "restore" ]]; then
  [[ -f "$IMAGE"  ]] || die "no such image: ${IMAGE}"
  [[ -n "$CONFIG" ]] || die "--restore needs --config <ersatztv /config dir>"
  need sqlite3
  step "Restoring station image into ${CONFIG}"

  if [[ -e "${CONFIG}/ersatztv.sqlite3" ]] && (( ! FORCE )); then
    die "${CONFIG} already holds a station — pass --force to replace it (it will be backed up)"
  fi
  if [[ -e "${CONFIG}/ersatztv.sqlite3" ]]; then
    B="${CONFIG}.bak.$(date +%s)"
    (( DRY )) && say "  would back up existing config to ${B}" \
              || { cp -a "$CONFIG" "$B" && ok "backed up existing config → ${B}"; }
  fi

  if (( DRY )); then
    say "  would unpack $(basename "$IMAGE") into ${CONFIG}"
  else
    mkdir -p "$CONFIG" || die "cannot create ${CONFIG}"
    tar xzf "$IMAGE" -C "$CONFIG" || die "unpack failed"
    ok "unpacked"
  fi

  DB="${CONFIG}/ersatztv.sqlite3"
  (( DRY )) || [[ -f "$DB" ]] || die "image contained no ersatztv.sqlite3"

  sq() { (( DRY )) && { say "  would sql: $1"; return 0; }; sqlite3 "$DB" "$1"; }

  # 1. Point the encoder at THIS machine's hardware.
  if [[ -n "$HWACCEL" ]]; then
    HID="$(hwaccel_id "$HWACCEL")"
    step "Encoder → ${HWACCEL} (HardwareAcceleration=${HID})"
    if [[ "$HID" == "3" ]]; then
      sq "UPDATE FFmpegProfile SET HardwareAcceleration=${HID}, VaapiDevice='${VAAPI_DEVICE}';"
    else
      sq "UPDATE FFmpegProfile SET HardwareAcceleration=${HID}, VaapiDevice=NULL;"
    fi
    # The profile name carries the encoder in it ("854x480 h264_nvenc aac"). Leave
    # it alone and the UI cheerfully shows nvenc on a VAAPI box forever, which is
    # a lie that costs somebody an hour.
    case "$HID" in
      0) ENC="libx264" ;; 1) ENC="h264_qsv" ;;   2) ENC="h264_nvenc" ;;
      3) ENC="h264_vaapi" ;; 4) ENC="h264_videotoolbox" ;; 5) ENC="h264_amf" ;;
      6) ENC="h264_v4l2m2m" ;; 7) ENC="h264_rkmpp" ;; *) ENC="" ;;
    esac
    if [[ -n "$ENC" ]]; then
      for old in libx264 h264_qsv h264_nvenc h264_vaapi h264_videotoolbox h264_amf h264_v4l2m2m h264_rkmpp; do
        [[ "$old" == "$ENC" ]] && continue
        sq "UPDATE FFmpegProfile SET Name=REPLACE(Name,'${old}','${ENC}');"
      done
    fi
    ok "ffmpeg profile re-pointed"
  else
    warn "no --hwaccel given — keeping the source machine's encoder setting, which is"
    warn "probably wrong for this box (software fallback eats a CPU alive)"
  fi

  # 2. Drop the source machine's Plex/Jellyfin/Emby links.
  #
  # On the station these hold thousands of items belonging to somebody else's
  # media server, and none of Z0's 19 smart collections touch them — every one
  # is type:other_video against the local library. Carrying them across gives
  # the new node dead libraries pointing at a host it cannot reach, and an item
  # count that makes the scan look wrong for hours.
  if (( ! KEEP_REMOTE )); then
    step "Stripping remote media sources"
    sq "DELETE FROM MediaItem WHERE LibraryPathId IN (SELECT lp.Id FROM LibraryPath lp JOIN Library l ON lp.LibraryId=l.Id WHERE l.MediaSourceId IN (SELECT Id FROM MediaSource WHERE Id NOT IN (SELECT Id FROM LocalMediaSource)));"
    sq "DELETE FROM LibraryPath WHERE LibraryId IN (SELECT Id FROM Library WHERE MediaSourceId NOT IN (SELECT Id FROM LocalMediaSource));"
    sq "DELETE FROM Library WHERE MediaSourceId NOT IN (SELECT Id FROM LocalMediaSource);"
    sq "DELETE FROM MediaSource WHERE Id NOT IN (SELECT Id FROM LocalMediaSource);"
    ok "remote libraries removed — this node owns only its local /media"
  fi

  # 3. Reset the playout anchor. THIS IS THE ONE THAT BITES.
  #
  # A playout anchor stores an instruction INDEX into the flattened schedule.
  # Restored onto a new box the index is still there, still valid-looking, and
  # still pointing at whatever instruction happened to sit at that offset. The
  # channel would not fail — it would come up mid-block, airing the wrong thing,
  # and the only symptom is a day that looks subtly wrong. Same failure #38 was
  # written to prevent. A fresh node must re-enter the week from the top.
  step "Resetting playout state"
  for t in PlayoutItem PlayoutAnchor PlayoutProgramScheduleAnchor PlayoutHistory \
           PlayoutGap PlayoutBuildStatus PlayoutItemWatermark PlayoutItemGraphicsElement \
           PlayoutScheduleItemFillGroupIndex; do
    if (( DRY )) || sqlite3 "$DB" "SELECT 1 FROM sqlite_master WHERE type='table' AND name='${t}';" | grep -q 1; then
      sq "DELETE FROM ${t};"
    fi
  done
  ok "playout will rebuild from the current wall clock, not a stale index"

  # 4. The search index is a separate store, and a stale one is invisible.
  #
  # Deleting items above leaves the index still listing them. ErsatzTV queries
  # the index, not the table, so a smart collection can resolve to items that no
  # longer exist — and an empty pool schedules nothing and leaves a silent hole
  # in the guide. Force a rebuild rather than trusting a scan to do it.
  step "Forcing a search-index rebuild"
  if (( DRY )); then
    say "  would remove ${CONFIG}/search-index"
  else
    rm -rf "${CONFIG}/search-index" && ok "index dropped — ErsatzTV rebuilds it on first start"
  fi

  (( DRY )) || sqlite3 "$DB" "PRAGMA integrity_check;" | grep -qx ok \
    || die "restored database fails integrity_check"
  (( DRY )) || ok "integrity_check ok"

  CH="$( (( DRY )) && echo "?" || sqlite3 "$DB" 'SELECT Number FROM Channel ORDER BY Id LIMIT 1;')"
  step "Restored"
  say "  channel number: ${CH}"
  say ""
  say "  The uplink must point at THIS number — the channel URL is /iptv/channel/<number>.ts,"
  say "  and the number is whatever the station was built with, not necessarily 1."
  say "    Z0_CHANNEL_URL=http://127.0.0.1:8409/iptv/channel/${CH}.ts"
  exit 0
fi
