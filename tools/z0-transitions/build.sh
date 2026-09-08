#!/usr/bin/env bash
# Build the segment transition cards: frames + sting -> mp4 + nfo, gated.
#
#   ./build.sh                 every card in segments.json into $TR_WORK
#   ./build.sh SHOW SLUG       one card, e.g. ./build.sh groundzero interview
#
# Output: $TR_WORK/z0-tr-<show>-<slug>.mp4 + .nfo (default /var/tmp/z0-transitions).
# Nothing is installed; staging on vile needs x, see docs/transitions.md.
# Deterministic: the same checkout renders the same frames and the same sting.
set -euo pipefail
cd "$(dirname "$0")"

WORK="${TR_WORK:-/var/tmp/z0-transitions}"
mkdir -p "$WORK"

echo "── tests"
python3 test_transitions.py

if [ $# -ge 2 ]; then
  names="z0-tr-$1-$2"
else
  names=$(python3 transitions.py list)
fi

for name in $names; do
  rest="${name#z0-tr-}"
  show="${rest%%-*}"
  slug="${rest#"$show"-}"
  frames="$WORK/frames-$name"
  echo "── $name"
  rm -rf "$frames"
  python3 transitions.py render "$show" "$slug" "$frames" >/dev/null
  python3 transitions.py audio "$show" "$slug" "$WORK/$name.wav" >/dev/null

  # CRF, not a bitrate cap: a source asset ErsatzTV re-encodes on playout.
  # No scaler — the 16-bit cards are doubled with NEAREST before they get
  # here, the others are authored at 640x480.
  ffmpeg -hide_banner -loglevel error -y \
    -framerate 30 -i "$frames/f%05d.png" -i "$WORK/$name.wav" \
    -filter_complex "[0:v]setsar=1,format=yuv420p[v]" -map '[v]' -map 1:a \
    -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 18 -preset slow -r 30 -g 60 \
    -c:a aac -b:a 160k -ar 48000 -ac 2 \
    -movflags +faststart -shortest \
    "$WORK/$name.mp4"
  python3 transitions.py nfo "$show" "$slug" > "$WORK/$name.nfo"
  rm -rf "$frames" "$WORK/$name.wav"

  # The gate: the house shape, exactly.  A card that is 3.97 s or 854 wide
  # would still play, and would be the one item in the pool that is wrong.
  ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,sample_rate,channels \
          -show_entries format=duration -of json "$WORK/$name.mp4" \
  | python3 -c '
import json, sys
p = json.load(sys.stdin)
v, a = p["streams"][0], p["streams"][1]
d = float(p["format"]["duration"])
bad = []
if (v["codec_name"], v["width"], v["height"], v["r_frame_rate"]) != ("h264", 640, 480, "30/1"):
    bad.append("video %r" % ((v["codec_name"], v["width"], v["height"], v["r_frame_rate"]),))
if (a["codec_name"], a["sample_rate"], a["channels"]) != ("aac", "48000", 2):
    bad.append("audio %r" % ((a["codec_name"], a["sample_rate"], a["channels"]),))
if abs(d - 4.0) > 0.05:
    bad.append("duration %.3f" % d)
if bad:
    sys.exit("GATE: " + "; ".join(bad))
print("   ok  %.3f s" % d)
'
done

echo
ls -la "$WORK"/*.mp4 | wc -l
echo "cards in $WORK"
