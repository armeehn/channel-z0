#!/usr/bin/env bash
# Channel Z0 — generate a slate card (a full-screen title the station cuts to).
# Fills the interstitials the build guide asks for but never generated:
# technical difficulties, the sign-off card, "please stand by," and friends.
#
# Usage:
#   tools/make-slate.sh                                  # TECHNICAL DIFFICULTIES, 30s
#   tools/make-slate.sh "SIGN-OFF" "GOODNIGHT, LOCALS" 15
#   tools/make-slate.sh "PLEASE STAND BY" "WE'LL RETURN SHORTLY" 20 standby
#
# Args: <headline> [subline] [seconds] [output-slug]
# Output: $Z0_MEDIA_ROOT/interstitials/<slug>.mp4 (1080p/30, matches the channel).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"
z0_help_check "$@"

HEAD="${1:-TECHNICAL DIFFICULTIES}"
SUB="${2:-DO NOT ADJUST YOUR SET}"
SECS="${3:-30}"
z0_require_int "seconds" "$SECS"
SLUG="${4:-$(echo "$HEAD" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-' | cut -c1-28)}"
SLUG="${SLUG:-slate}"   # a headline of pure punctuation must not become ".mp4"
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/interstitials"
OUT="${OUT_DIR}/${SLUG}.mp4"
FONT="$(z0_find_font)"

if [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_SRC="anullsrc=r=48000:cl=stereo"
else
  AUDIO_SRC="sine=frequency=440:sample_rate=48000,volume=0.05"
fi

mkdir -p "$OUT_DIR"

# Ink field, red rules top and bottom, big bone headline, subline, and the
# station designation in the corner.
ffmpeg -hide_banner -y \
  -f lavfi -i "color=c=${Z0_INK}:s=1920x1080:r=30:d=${SECS}" \
  -f lavfi -t "${SECS}" -i "${AUDIO_SRC}" \
  -vf "\
drawbox=x=0:y=120:w=iw:h=10:color=${Z0_RED}:t=fill,\
drawbox=x=0:y=950:w=iw:h=10:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${FONT}':text='CHANNEL Z0':fontcolor=0x8A8A8A:fontsize=30:x=(w-tw)/2:y=200,\
drawtext=fontfile='${FONT}':$(z0_text "${HEAD}"):fontcolor=${Z0_PAPER}:fontsize=108:x=(w-tw)/2:y=(h-th)/2-40,\
drawtext=fontfile='${FONT}':$(z0_text "${SUB}"):fontcolor=${Z0_PAPER}@0.85:fontsize=40:x=(w-tw)/2:y=(h/2)+90,\
drawtext=fontfile='${FONT}':text='DESIG RL-Z0':fontcolor=0x8A8A8A:fontsize=24:x=60:y=h-th-40" \
  -map 0:v -map 1:a \
  -c:v libx264 -preset veryfast -b:v 3000k -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 96k -ar 48000 -shortest -movflags +faststart \
  "$OUT"

echo ""
echo "slate ready: $OUT (${SECS}s) — \"${HEAD}\""
echo "wire it into ErsatzTV: emergencies as an OBS scene, or the Dead Air filler."
