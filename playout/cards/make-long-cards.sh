#!/usr/bin/env bash
# Render the COMING SOON cards long enough to HOLD their slot.
#
# The slot is padded from the card pool, so the card must be long enough that
# padding an hour does not schedule dozens of items — a 60-second card would be
# booked ~60 times. Five minutes tiles the hour in ~12 plays, which is the same
# order as an ordinary SHORT SUBJECTS block, and `trim: true` on the pad cuts
# the last one so the slot lands exactly on the clock.
#
# The sliding accent marker exists so an hour of card does not read as a frozen
# channel. It is a hard-edged brand-colour block on a track, no blur, no fade —
# consistent with the rest of the station's furniture.
set -euo pipefail
cd /root/z0cards

render() {
  local name="$1" y="$2" colour="$3"
  ffmpeg -hide_banner -loglevel error -y \
    -loop 1 -framerate 30 -t 300 -i "${name}.png" \
    -f lavfi -t 300 -i anullsrc=r=48000:cl=stereo \
    -filter_complex "[0:v]scale=640:480:flags=lanczos,setsar=1,format=yuv420p,drawbox=x='-72+mod(t*36,712)':y=${y}:w=72:h=4:color=${colour}@1.0:t=fill[v]" \
    -map '[v]' -map 1:a \
    -c:v libx264 -profile:v high -pix_fmt yuv420p \
    -b:v 1200k -maxrate 1500k -bufsize 2400k -preset medium -r 30 -g 60 \
    -c:a aac -b:a 192k -ar 48000 -ac 2 \
    -movflags +faststart -shortest "${name}-5min.mp4"
  echo "encoded ${name}-5min.mp4"
}

# The marker track sits just under the tri-band, at the TOP. Its first home
# (y 430-440) was inside the band the up-next strip and channel bug occupy,
# so the one element whose whole job was to prove the channel is alive was
# the element most likely to be covered up.
render lab-hour    13 0xf0477d   # Riposte pink on the bone field
render ground-zero 11 0xfe9a0d   # marigold on the ink field
ls -la ./*-5min.mp4
