#!/usr/bin/env bash
# Channel Z0 — generate a station ident (the "You're watching CHANNEL Z0" bumper
# the Station ID filler rotates between programs). This is 80% of what makes a
# stream feel like a station instead of a playlist.
#
# Usage:
#   tools/make-ident.sh                       # 6s, default line, -> bumpers/
#   tools/make-ident.sh 8 "ALWAYS ON"         # 8s with a custom tagline
#   Z0_SILENT=1 tools/make-ident.sh           # no tone
#
# Output: $Z0_MEDIA_ROOT/bumpers/z0-ident-<tag>.mp4, matched to the channel's
# 1080p/30 profile so it splices in without a re-encode hiccup.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"

SECS="${1:-6}"
TAG="${2:-A LOCAL CHANNEL, FOR LOCALS}"
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/bumpers"
SLUG="$(echo "$TAG" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-24)"
OUT="${OUT_DIR}/z0-ident-${SLUG}.mp4"
FONT="$(z0_find_font)"

if [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_SRC="anullsrc=r=48000:cl=stereo"
else
  AUDIO_SRC="sine=frequency=330:sample_rate=48000,volume=0.04"
fi

mkdir -p "$OUT_DIR"

# Ink field; a bone checker rule top and bottom; "YOU'RE WATCHING" small, the
# big red-and-bone wordmark, the tagline, and the RL-Z0 designation. Gentle
# fade in and out so it feels like a cut-in, not a jump.
ffmpeg -hide_banner -y \
  -f lavfi -i "color=c=${Z0_INK}:s=1920x1080:r=30:d=${SECS}" \
  -f lavfi -t "${SECS}" -i "${AUDIO_SRC}" \
  -filter_complex "\
[0:v]\
drawbox=x=0:y=150:w=iw:h=8:color=${Z0_PAPER}:t=fill,\
drawbox=x=0:y=922:w=iw:h=8:color=${Z0_PAPER}:t=fill,\
drawtext=fontfile='${FONT}':text='NOW WATCHING':fontcolor=${Z0_PAPER}:fontsize=42:x=(w-tw)/2:y=360,\
drawtext=fontfile='${FONT}':text='CHANNEL':fontcolor=${Z0_PAPER}:fontsize=200:x=(w-tw)/2:y=430,\
drawtext=fontfile='${FONT}':text='Z0':fontcolor=${Z0_RED}:fontsize=200:x=(w-tw)/2:y=650,\
drawtext=fontfile='${FONT}':text='${TAG}':fontcolor=${Z0_PAPER}:fontsize=34:x=(w-tw)/2:y=880,\
drawtext=fontfile='${FONT}':text='DESIG RL-Z0':fontcolor=0x8A8A8A:fontsize=24:x=w-tw-40:y=h-th-30,\
fade=t=in:st=0:d=0.4,fade=t=out:st=$(awk "BEGIN{print ${SECS}-0.4}"):d=0.4[v];\
[1:a]afade=t=in:st=0:d=0.4,afade=t=out:st=$(awk "BEGIN{print ${SECS}-0.4}"):d=0.4[a]" \
  -map "[v]" -map "[a]" -shortest \
  -c:v libx264 -preset veryfast -b:v 4500k -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 128k -ar 48000 -movflags +faststart \
  "$OUT"

echo ""
echo "station ident ready: $OUT (${SECS}s)"
echo "drop it in bumpers/; the Station ID filler rotates whatever's in there."
