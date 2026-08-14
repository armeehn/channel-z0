#!/usr/bin/env bash
# Rebuild the 73 LUNCH LOOPS music videos with their track card on screen.
#
# The audio is STREAM-COPIED (`-c:a copy`). These are the only surviving digital
# transfers of the 78s and they have already been through one encode; re-running
# them through AAC to change a picture that was never there would be a pointless
# generation loss.
#
# The card PNGs are rendered at deviceScaleFactor 2, i.e. 1280x960. They MUST
# be scaled back to 640x480 here — without the -vf the muxed output is
# 1280x960, which is off-spec and puts a per-item scale back on the live
# transcode, the exact cost the whole library was normalised to remove.
#
# Every frame of the output is IDENTICAL, so motion estimation is pure waste:
# `-preset medium` spent ~2 minutes per 3-minute track (2.5h for 73).
# `-preset veryfast -tune stillimage` with a long GOP produces a visually
# identical still at a fraction of the cost. The channel spec that matters
# (h264 high / 640x480 / yuv420p / 30fps / aac 48k stereo) is unchanged.
#
# Output goes to a dot-DIRECTORY temp and is renamed onto the original path.
# Both halves matter: ErsatzTV's scanner skips dot-DIRECTORIES but happily
# indexes dot-FILES, so an in-place ".name.tmp.mp4" becomes a real media item
# and then a State=1 ghost the moment it is renamed away. Renaming onto the SAME
# path is an update, not a rename, so no ghost row is created either.
set -uo pipefail

ROOT=/media
CARDS=/cards
TMP="$ROOT/.z0-convtmp"
mkdir -p "$TMP"

ok=0; fail=0
while IFS= read -r stem; do
  [ -n "$stem" ] || continue
  src="$ROOT/music/$stem.mp4"
  card="$CARDS/$stem.png"
  tmp="$TMP/music_$(printf '%s' "$stem" | tr ' /' '__').mp4"

  [ -f "$src" ]  || { echo "MISS-SRC  $stem";  fail=$((fail+1)); continue; }
  [ -f "$card" ] || { echo "MISS-CARD $stem"; fail=$((fail+1)); continue; }

  # -nostdin is LOAD-BEARING: without it ffmpeg reads the loop's stdin and
  # eats the rest of /tracks.txt. First run processed 12 of 73 and reported
  # MISS-SRC for names like "oodlands" and "wn Pals - ..." — those are not
  # missing files, they are the tail ends of lines ffmpeg had half-consumed.
  if ffmpeg -nostdin -hide_banner -loglevel error -y \
       -loop 1 -framerate 30 -i "$card" \
       -i "$src" \
       -map 0:v:0 -map 1:a:0 \
       -c:a copy \
       -vf "scale=640:480:flags=lanczos,setsar=1,format=yuv420p" \
       -c:v libx264 -profile:v high -pix_fmt yuv420p \
       -b:v 1200k -maxrate 1500k -bufsize 2400k -preset veryfast -tune stillimage \
       -r 30 -g 300 \
       -shortest -movflags +faststart "$tmp"; then
    # duration guard, same principle as normalize-z0-media.sh: never replace a
    # good file with a shorter one
    ds=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src" | cut -d. -f1)
    dt=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$tmp" | cut -d. -f1)
    if [ -n "$ds" ] && [ -n "$dt" ] && [ "$((ds > dt ? ds - dt : dt - ds))" -le 2 ]; then
      mv -f "$tmp" "$src" && { echo "OK   $stem (${dt}s)"; ok=$((ok+1)); }
    else
      echo "FAIL $stem duration ${ds}s -> ${dt}s, refusing to replace"
      rm -f "$tmp"; fail=$((fail+1))
    fi
  else
    echo "FAIL $stem (encode)"; rm -f "$tmp"; fail=$((fail+1))
  fi
done < /tracks.txt

echo "=== music remux done: $ok ok, $fail failed ==="
