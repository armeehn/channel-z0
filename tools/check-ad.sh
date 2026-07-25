#!/usr/bin/env bash
# Channel Z0 — screen a submitted spot before it airs.
# The pre-flight check that goes with tools/normalize-ad.sh: is it the right
# length (15/30/60), and how loud is it really? Read-only — it touches nothing,
# just tells you what you're looking at so you can accept, reject, or normalize.
#
# Usage:
#   tools/check-ad.sh submission.mp4
set -euo pipefail

IN="${1:-}"
[[ -n "$IN" && -f "$IN" ]] || { echo "usage: $0 <submission-file>" >&2; exit 1; }

echo "── screening: $IN"

# Container / codecs / resolution.
read -r VCODEC WIDTH HEIGHT < <(ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height -of default=nw=1:nk=1 "$IN" | paste -sd' ' -)
ACODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$IN" || true)
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$IN")
DUR_R=$(printf '%.0f' "$DUR")

echo "   video   : ${VCODEC:-?} ${WIDTH:-?}x${HEIGHT:-?}"
echo "   audio   : ${ACODEC:-none}"
echo "   duration: ${DUR}s  (rounds to ${DUR_R}s)"

# Length: station standard is exactly 15/30/60.
case "$DUR_R" in
  15|30|60) echo "   length  : OK — standard slot" ;;
  *)        echo "   length  : ⚠ non-standard (${DUR_R}s); normalize-ad.sh will trim/pad at your discretion" ;;
esac

# Codecs: we want H.264 + AAC in the end; flag anything else (normalize fixes it).
[[ "$VCODEC" == "h264" ]] || echo "   video   : ⚠ not H.264 — normalize before air"
[[ "$ACODEC" == "aac"  ]] || echo "   audio   : ⚠ not AAC — normalize before air"

# Loudness: measure integrated LUFS (loudnorm first pass). The station target is
# -16 LUFS; anything much hotter is the classic 'ad louder than the movie' sin.
echo "   loudness: measuring…"
LUFS=$(ffmpeg -hide_banner -nostats -i "$IN" -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 \
  | awk -F'"' '/input_i/ {print $4}' | head -1)
if [[ -n "${LUFS:-}" ]]; then
  echo "   loudness: ${LUFS} LUFS integrated (station target -16; normalize-ad.sh corrects it)"
else
  echo "   loudness: (could not measure — silent track?)"
fi

echo "── verdict: watch it, then either clear it or run"
echo "   tools/normalize-ad.sh \"$IN\" \"Business - Spot Title (${DUR_R}s)\""
