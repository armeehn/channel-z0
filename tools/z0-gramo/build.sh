#!/usr/bin/env bash
# Build the GRAMOPHONE lunch cards from the Virtual Gramophone sides.
#
#   ./build.sh                 every side both clocks clear (sides.json)
#   ./build.sh 14397 15964     just these
#
# Output lands in $GRAMO_WORK/out (default /var/tmp/z0-gramo) under the
# library path the side will have, gramophone/<chanson|reel|chant>/<stem>.mp4,
# each verified against the card spec, the bitrate gate and the tail check
# (picture at least as long as the sound). Nothing is installed: copying into
# /media and writing the sidecars with z0-nfo.py is the operator's step, see
# docs/gramophone.md. $JOBS sides render at once (default 4).
set -euo pipefail
cd "$(dirname "$0")"

WORK="${GRAMO_WORK:-/var/tmp/z0-gramo}"
JOBS="${JOBS:-4}"
MAX_KBPS=3000
mkdir -p "$WORK/src" "$WORK/out"

field() { # id key
  python3 -c "import json,sys;print([s for s in json.load(open('sides.json')) if s['id']==sys.argv[1]][0][sys.argv[2]])" "$1" "$2"
}

one() { # id -> one finished card, or a non-zero exit with the reason
  local id="$1" url want src env out rel
  url=$(field "$id" url); want=$(field "$id" bytes)
  src="$WORK/src/$id.mp3"; env="$WORK/src/$id.env.json"
  rel=$(python3 gramo.py stem "$id"); out="$WORK/out/$rel"

  if [ -s "$out" ]; then echo "$id  have  $rel"; return 0; fi

  python3 gramo.py check "$id" | grep -q "^$id *CLEAR" || { echo "$id  REJECT"; return 1; }

  # --fail, and the exact byte count: archive hosts answer 5xx with an HTML
  # body that ffprobe will happily call an mp3 with a short duration.
  if [ ! -s "$src" ] || [ "$(stat -c %s "$src")" != "$want" ]; then
    curl -sS --fail --retry 3 -o "$src" "$url"
  fi
  [ "$(stat -c %s "$src")" = "$want" ] || { echo "$id  size mismatch"; return 1; }

  [ -s "$env" ] || python3 gramo.py envelope "$src" "$env" >/dev/null
  mkdir -p "$(dirname "$out")"
  python3 gramo.py render "$id" "$src" "$env" "$out.part.mp4"

  local probe kbps
  probe=$(ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,sample_rate,channels,pix_fmt:format=bit_rate -of default=nw=1 "$out.part.mp4")
  for want in codec_name=h264 width=640 height=480 r_frame_rate=30/1 pix_fmt=yuv420p codec_name=aac sample_rate=48000 channels=2; do
    grep -q "^$want\$" <<<"$probe" || { echo "$id  spec: missing $want"; rm -f "$out.part.mp4"; return 1; }
  done
  kbps=$(( $(grep bit_rate= <<<"$probe" | tail -1 | cut -d= -f2) / 1000 ))
  [ "$kbps" -le "$MAX_KBPS" ] || { echo "$id  $kbps kbps over the $MAX_KBPS gate"; rm -f "$out.part.mp4"; return 1; }

  mv "$out.part.mp4" "$out"
  echo "$id  ok    $rel ($kbps kbps)"
}

if [ "${1:-}" = "--one" ]; then one "$2"; exit; fi

echo "── tests"
python3 test_gramo.py

echo "── sides"
if [ $# -gt 0 ]; then
  ids=("$@")
else
  mapfile -t ids < <(python3 gramo.py check | awk '$2=="CLEAR"{print $1}')
fi
echo "${#ids[@]} to build, $JOBS at a time"

# xargs keeps going past a failed side; the count at the end is the verdict.
printf '%s\n' "${ids[@]}" | xargs -P "$JOBS" -I{} bash "$0" --one {} || true

echo "── tail check (picture must run as long as the sound)"
../z0-video-tail.sh scan "$WORK/out"

have=$(find "$WORK/out" -name '*.mp4' ! -name '*.part.mp4' | wc -l)
[ "$have" -eq "${#ids[@]}" ] || { echo "FAIL: $have of ${#ids[@]} cards built"; exit 1; }
echo "ok: $have cards in $WORK/out"
