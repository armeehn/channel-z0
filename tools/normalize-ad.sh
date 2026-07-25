#!/usr/bin/env bash
# Channel Z0 — normalize a submitted ad for air.
# Same resolution, same framerate, same loudness as everything else on the
# channel, so no spot is ever louder than the movie it interrupts.
#
# Usage:
#   tools/normalize-ad.sh submission.mp4 "Business Name - Spot Title (30s)"
#
# Output lands in $Z0_MEDIA_ROOT/commercials/local/ (default /media/channelz0),
# ready for the next ErsatzTV library scan.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <input-file> <output-name (no extension)>" >&2
  exit 1
fi

IN="$1"
NAME="$2"
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/commercials/local"
OUT="${OUT_DIR}/${NAME}.mp4"

[[ -f "$IN" ]] || { echo "no such file: $IN" >&2; exit 1; }
mkdir -p "$OUT_DIR"

ffmpeg -hide_banner -i "$IN" \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p" \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -c:v libx264 -preset slow -b:v 5000k -maxrate 6000k -bufsize 10000k \
  -c:a aac -b:a 128k -ar 48000 -movflags +faststart \
  "$OUT"

DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT" | cut -d. -f1)
echo ""
echo "cleared for air: $OUT (${DUR}s)"
if [[ "$DUR" != "15" && "$DUR" != "30" && "$DUR" != "60" ]]; then
  echo "note: duration is ${DUR}s — station standard is exactly 15/30/60s." >&2
fi
