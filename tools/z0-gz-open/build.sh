#!/usr/bin/env bash
# Build — and optionally install — the GROUND ZERO opening title sequence.
#
#   ./build.sh                 render + encode into $GZ_WORK
#   ./build.sh --install       ...and copy it onto the playout machine
#
# Everything is deterministic: no seeds, no clock, no network.  The same
# checkout produces the same 1800 frames and the same 60 s of audio, so the
# master can always be regenerated rather than archived.
#
# The output is 640x480, which is what the other station cards are authored at
# and what pillarboxes cleanly into the channel's 854x480 — a 4:3 item lands
# exactly inside the on-air rails rather than under them.  See
# docs/ground-zero-open.md.
set -euo pipefail
cd "$(dirname "$0")"

WORK="${GZ_WORK:-/var/tmp/z0-gz-open}"
NAME="GROUND ZERO - OPENING TITLES"
VILE="${VILE:-root@10.0.1.222}"
DEST="/mnt/main-data/channelz0/opens/groundzero"

mkdir -p "$WORK"

echo "── audio checks"
# Run before rendering, not after.  All three of these have been wrong at some
# point — the echo unit silent, the pan law clamped so the mix was mono, a
# voice off its note — and none of them is visible in a waveform.
python3 test_audio.py

echo "── score"
python3 gzaudio.py "$WORK/open.wav"

echo "── frames"
rm -rf "$WORK/frames"
python3 make_frames.py "$WORK/frames"

echo "── encode"
# CRF rather than a bitrate cap: this is a source asset that ErsatzTV will
# re-encode on playout, so what matters is that the hard pixel edges survive
# the first generation.  `neighbor` for the same reason — any other scaler
# turns a 320x240 pixel into a soft 2x2 blob.
ffmpeg -hide_banner -loglevel error -y \
  -framerate 30 -i "$WORK/frames/f%05d.png" -i "$WORK/open.wav" \
  -filter_complex "[0:v]scale=640:480:flags=neighbor,setsar=1,format=yuv420p[v]" \
  -map '[v]' -map 1:a \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 16 -preset slow -r 30 -g 60 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart -shortest \
  "$WORK/$NAME.mp4"

# The sidecar is what gives the file its tags.  Folder tags and NFO tags are
# the same field and the NFO wins — a sidecar that omits a tag DELETES it — so
# this lists the whole folder chain (media / opens / groundzero) verbatim.
cat > "$WORK/$NAME.nfo" <<XML
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>$NAME</title>
  <sorttitle>ground zero - opening titles</sorttitle>
  <mpaa>Z0-GENERAL</mpaa>
  <outline>Opening titles for GROUND ZERO.</outline>
  <plot>Opening titles for GROUND ZERO. The day, from the point it happened.</plot>
  <tag>media</tag>
  <tag>opens</tag>
  <tag>groundzero</tag>
</movie>
XML

ls -la "$WORK/$NAME.mp4"
ffprobe -hide_banner -v error -show_entries format=duration \
        -show_entries stream=codec_name,width,height,r_frame_rate \
        -of default=nw=1 "$WORK/$NAME.mp4"

if [ "${1:-}" = "--install" ]; then
  echo "── install to $VILE:$DEST"
  # `opens/` is deliberately NOT `cards/groundzero/`: that folder is the pool
  # `coming_soon_gnd` shuffles to pad the hour, and an opening shuffled into
  # the middle of its own slot is worse than no opening at all.
  ssh "$VILE" "mkdir -p '$DEST'"
  scp "$WORK/$NAME.mp4" "$WORK/$NAME.nfo" "$VILE:$DEST/"
  ssh "$VILE" "ls -la '$DEST'"
  echo
  echo "Installed.  It is in NO pool yet and airs nothing until:"
  echo "  1. ErsatzTV rescans /media (it does so on its own within 6 h, or"
  echo "     trigger it from the UI — do NOT null LastScan on the live DB)."
  echo "  2. the gz_open content key and the 19:00 slot change are deployed"
  echo "     (see docs/ground-zero-open.md · Putting it on air)."
fi
