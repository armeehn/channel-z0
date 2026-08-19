#!/usr/bin/env bash
# Channel Z0 — generate the channel bug: the little mark that sits in the same
# place forever, so a viewer landing mid-programme knows whose signal this is.
#
# Usage:
#   tools/make-bug.sh                 # -> $Z0_MEDIA_ROOT/branding/z0-rail-bug.png
#   tools/make-bug.sh /tmp/bug.png    # explicit output path
#
# ── Why this is a tall, narrow portrait now ─────────────────────────────────
#
# The bug used to be a 260x150 landscape drawn on transparent and dimmed to
# 72% by the compositor, because it sat ON the picture and had to apologise
# for being there. It doesn't any more: the channel pillarboxes 4:3 picture
# into an 854x480 frame and the bug lives in the 107px black bar down the
# right-hand side. Nothing behind it, so nothing to see through it.
#
# That changes the drawing in three ways, all of them improvements:
#   - it is drawn at final size and composited 1:1, so no resampling
#   - it is fully opaque, because opacity was only ever hiding the picture
#   - it carries the red spine down its INNER edge, continuing the one the
#     weather block above it starts. The two abut exactly (340 + 140 = 480),
#     which is what makes the spine read as a single unbroken rule.
#
# Old-TV physics: always there, never explained.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"
z0_help_check "$@"

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT="${1:-${MEDIA_ROOT}/branding/z0-rail-bug.png}"
# When rendering inside the ErsatzTV image the font is resolved in the
# CONTAINER, so z0_find_font's host-side existence check would reject a
# perfectly good path. Default to the same face tools/z0-weather.py sets the
# rails in — the two halves of the right rail must not disagree about the font.
if [[ -n "${Z0_FFMPEG_IMAGE:-}" ]]; then
  FONT="${Z0_FONT:-/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf}"
else
  FONT="$(z0_find_font)"
fi

# Geometry, derived exactly as tools/z0-weather.py derives it. Kept in step by
# the same three environment variables rather than by being written down twice.
FRAME_W="${Z0_FRAME_W:-854}"
FRAME_H="${Z0_FRAME_H:-480}"
CONTENT_W="${Z0_CONTENT_W:-640}"
RAIL_W=$(( (FRAME_W - CONTENT_W) / 2 ))    # 107
WX_H="${Z0_WX_RAIL_H:-340}"
BUG_H=$(( FRAME_H - WX_H ))                # 140
SPINE=3
PAD=8
COL_W=$(( RAIL_W - SPINE - PAD - PAD ))    # 88
X0=$(( SPINE + PAD ))                      # right rail: clear of the spine

mkdir -p "$(dirname "$OUT")"

# The bug has to be drawn with the same face the rails are drawn with, or the
# two halves of the right rail are set in different fonts. Point Z0_FFMPEG_IMAGE
# at the ErsatzTV image (as tools/z0-weather.sh does) and the render happens
# inside it, using the same ffmpeg and the same font set that the graphics
# engine will composite with. Without it this falls back to the host's ffmpeg,
# which is fine on a workstation and wrong on vile.
ff() {
  if [[ -n "${Z0_FFMPEG_IMAGE:-}" ]]; then
    docker run --rm --entrypoint /usr/local/bin/ffmpeg \
      -v "${MEDIA_ROOT}:${MEDIA_ROOT}" -u 0:0 "$Z0_FFMPEG_IMAGE" "$@"
  else
    ffmpeg "$@"
  fi
}

# Centre within the text column, not within the rail — centring on the rail
# would push everything half the spine's width off to the right.
CX="${X0}+((${COL_W}-tw)/2)"

ff -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=black@0.0:s=${RAIL_W}x${BUG_H},format=rgba" \
  -vf "\
drawbox=x=0:y=0:w=${SPINE}:h=${BUG_H}:color=${Z0_RED}:t=fill:replace=1,\
drawtext=fontfile='${FONT}':text='Z0':fontcolor=${Z0_PAPER}:fontsize=52:x=${CX}:y=26,\
drawbox=x=$(( X0 + (COL_W - 56) / 2 )):y=92:w=56:h=4:color=${Z0_RED}:t=fill:replace=1,\
drawtext=fontfile='${FONT}':text='CH\\·0':fontcolor=${Z0_PAPER}:fontsize=13:x=${CX}:y=106" \
  -frames:v 1 -update 1 "$OUT"

echo ""
echo "channel bug ready: $OUT  (${RAIL_W}x${BUG_H}, bottom of the right rail)"
echo "wired by playout/graphics-elements/image/z0-bug.yml — BottomRight, scale: false."
