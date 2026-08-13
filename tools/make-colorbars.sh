#!/usr/bin/env bash
# Channel Z0 — generate the sign-off colour bars (SMPTE bars + a quiet hum).
# The station shows these from midnight sign-off to morning sign-on,
# and ErsatzTV's Dead Air fallback uses them if a schedule ever runs dry.
#
# Usage:
#   tools/make-colorbars.sh            # 1 hour, into $Z0_MEDIA_ROOT/interstitials/
#   tools/make-colorbars.sh 30         # 30 minutes instead
#   Z0_SILENT=1 tools/make-colorbars.sh  # bars with silence instead of the hum
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"
z0_help_check "$@"

MINUTES="${1:-60}"
z0_require_int "minutes" "$MINUTES"
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/interstitials"
OUT="${OUT_DIR}/colorbars-${MINUTES}m.mp4"
SECONDS_TOTAL=$(( MINUTES * 60 ))

if [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_SRC="anullsrc=r=48000:cl=stereo"
else
  AUDIO_SRC="sine=frequency=440:sample_rate=48000,volume=0.05"
fi

mkdir -p "$OUT_DIR"

ffmpeg -hide_banner \
  -f lavfi -i "smptehdbars=size=1920x1080:rate=30" \
  -f lavfi -i "$AUDIO_SRC" \
  -c:v libx264 -preset veryfast -b:v 2000k -pix_fmt yuv420p \
  -c:a aac -b:a 96k -t "$SECONDS_TOTAL" \
  "$OUT"

echo ""
echo "sign-off ready: $OUT (${MINUTES} minutes)"
