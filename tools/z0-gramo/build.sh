#!/usr/bin/env bash
# Build one GRAMOPHONE listening interval from a Virtual Gramophone side.
#
#   ./build.sh SIDE_ID [NAME]        e.g. ./build.sh 14397 z0-gramo-00
#
# Output lands in $GRAMO_WORK (default /var/tmp/z0-gramo): NAME.mp4 + NAME.nfo,
# verified against the house spec and the interval bitrate gate. Nothing is
# installed: staging on vile needs x (the only host vile trusts), see
# docs/gramophone.md.
set -euo pipefail
cd "$(dirname "$0")"

SIDE="${1:?side id}"
NAME="${2:-z0-gramo-00}"
WORK="${GRAMO_WORK:-/var/tmp/z0-gramo}"
mkdir -p "$WORK"

url=$(python3 -c "import json;print([s for s in json.load(open('sides.json')) if s['id']=='$SIDE'][0]['url'])")
want=$(python3 -c "import json;print([s for s in json.load(open('sides.json')) if s['id']=='$SIDE'][0]['bytes'])")
src="$WORK/$SIDE.mp3"

echo "── tests"
python3 test_gramo.py

echo "── rights"
python3 gramo.py check "$SIDE"

echo "── fetch"
# --fail, and the exact byte count: archive hosts answer 5xx with an HTML
# body that ffprobe will happily call an mp3 with a short duration.
if [ ! -s "$src" ] || [ "$(stat -c %s "$src")" != "$want" ]; then
  curl -sS --fail --retry 3 -o "$src" "$url"
fi
have=$(stat -c %s "$src")
[ "$have" = "$want" ] || { echo "size $have != $want"; exit 1; }

echo "── envelope"
python3 gramo.py envelope "$src" "$WORK/$SIDE.env.json"

echo "── render"
python3 gramo.py render "$SIDE" "$src" "$WORK/$SIDE.env.json" "$WORK/$NAME.mp4"
python3 gramo.py nfo "$SIDE" "$WORK/$NAME.nfo"

echo "── verify"
probe=$(ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,pix_fmt:format=duration,bit_rate -of default=nw=1 "$WORK/$NAME.mp4")
echo "$probe"
grep -q 'codec_name=h264' <<<"$probe"
grep -q 'width=854' <<<"$probe"
grep -q 'height=480' <<<"$probe"
grep -q 'r_frame_rate=30/1' <<<"$probe"
grep -q 'pix_fmt=yuv420p' <<<"$probe"
grep -q 'codec_name=aac' <<<"$probe"
grep -q 'sample_rate=48000' <<<"$probe"
grep -q 'channels=2' <<<"$probe"
kbps=$(( $(grep bit_rate= <<<"$probe" | tail -1 | cut -d= -f2) / 1000 ))
[ "$kbps" -le 3000 ] || { echo "$kbps kbps over the 3000 gate"; exit 1; }
echo "ok: $WORK/$NAME.mp4 ($kbps kbps)"
