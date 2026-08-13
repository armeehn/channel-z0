#!/usr/bin/env bash
# Channel Z0 — generate the channel bug (the little logo that lives bottom-right
# forever). Outputs a transparent PNG you point ErsatzTV's watermark at; ErsatzTV
# handles the placement and ~15% opacity, so this is drawn solid and white.
#
# Usage:
#   tools/make-bug.sh                 # -> $Z0_MEDIA_ROOT/branding/z0-bug.png
#   tools/make-bug.sh /tmp/bug.png    # explicit output path
#
# Old-TV physics: semi-transparent, bottom-right, never explained.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"
z0_help_check "$@"

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT="${1:-${MEDIA_ROOT}/branding/z0-bug.png}"
FONT="$(z0_find_font)"

mkdir -p "$(dirname "$OUT")"

# 260x150 canvas: "Z0" wordmark, a red accent rule, and a small "CH·0" tag.
ffmpeg -hide_banner -y \
  -f lavfi -i "color=c=black@0.0:s=260x150,format=rgba" \
  -vf "\
drawtext=fontfile='${FONT}':text='Z0':fontcolor=white:fontsize=104:x=(w-tw)/2:y=6,\
drawbox=x=(iw-140)/2:y=118:w=140:h=6:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${FONT}':text='CH\\·0':fontcolor=white@0.85:fontsize=22:x=(w-tw)/2:y=124" \
  -frames:v 1 -update 1 "$OUT"

echo ""
echo "channel bug ready: $OUT"
echo "point ErsatzTV's channel watermark at it (bottom-right, ~15% opacity, always on)."
