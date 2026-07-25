#!/usr/bin/env bash
# Channel Z0 — generate the station test card (the branded signal-check pattern
# the channel shows before sign-on and whenever the tower needs a picture to
# align to). This is the classic test-card furniture — geometry grid, colour
# bars, a greyscale step wedge, corner castellations, a centre identity panel —
# rendered in the station's monospace-on-ink look, carrying a 1 kHz line-up tone.
#
# Unlike raw `smptehdbars` (what `test-broadcast.sh` fires at the tower), this is
# the card with the station's name on it: point ErsatzTV at it for the pre-06:00
# sign-on fill, or as the "picture's up but we're not on yet" slate.
#
# Usage:
#   tools/make-testcard.sh              # 60s loopable card -> interstitials/
#   tools/make-testcard.sh 300          # 5 minutes instead
#   Z0_SILENT=1 tools/make-testcard.sh  # drop the 1 kHz tone (silence)
#
# Output: $Z0_MEDIA_ROOT/interstitials/testcard.mp4 (1080p/30, channel profile).
# ErsatzTV loops a short clip happily, so 60s is plenty to fill a long slot.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"

SECS="${1:-60}"
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/interstitials"
OUT="${OUT_DIR}/testcard.mp4"
FONT="$(z0_find_font)"

# A test card traditionally carries a 1 kHz line-up tone, kept polite so a night
# of it doesn't torment anyone within earshot of the TV.
if [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_SRC="anullsrc=r=48000:cl=stereo"
else
  AUDIO_SRC="sine=frequency=1000:sample_rate=48000,volume=0.06"
fi

mkdir -p "$OUT_DIR"

# Build the greyscale step wedge (black -> white in 11 steps) as a row of
# drawbox fills; the trailing comma splices it into the filter chain.
STEPS=11; SW=160; X0=80; WY=380; WH=110
WEDGE=""
for i in $(seq 0 $((STEPS - 1))); do
  v=$(( i * 255 / (STEPS - 1) ))
  hx=$(printf '%02X' "$v")
  x=$(( X0 + i * SW ))
  WEDGE+="drawbox=x=${x}:y=${WY}:w=${SW}:h=${WH}:color=0x${hx}${hx}${hx}:t=fill,"
done

# Corner castellations — framing/overscan check marks in the four corners.
CORNERS="\
drawbox=x=16:y=16:w=36:h=36:color=${Z0_PAPER}:t=fill,\
drawbox=x=iw-52:y=16:w=36:h=36:color=${Z0_PAPER}:t=fill,\
drawbox=x=16:y=ih-52:w=36:h=36:color=${Z0_PAPER}:t=fill,\
drawbox=x=iw-52:y=ih-52:w=36:h=36:color=${Z0_PAPER}:t=fill,"

# Ink field with a faint geometry grid and a framing border; the greyscale
# wedge; a bordered centre identity panel (ink-filled so the grid doesn't muddy
# the text); the station wordmark, a red accent rule, tagline; top and bottom
# technical strips. Then a real SMPTE colour-bars band overlaid across the top.
ffmpeg -hide_banner -y \
  -f lavfi -i "color=c=${Z0_INK}:s=1920x1080:r=30:d=${SECS}" \
  -f lavfi -i "smptehdbars=size=1900x200:rate=30" \
  -f lavfi -t "${SECS}" -i "${AUDIO_SRC}" \
  -filter_complex "\
[0:v]\
drawgrid=w=120:h=120:t=2:c=${Z0_PAPER}@0.14,\
drawbox=x=10:y=10:w=iw-20:h=ih-20:color=${Z0_PAPER}@0.45:t=2,\
${WEDGE}\
${CORNERS}\
drawbox=x=410:y=540:w=1100:h=300:color=${Z0_INK}:t=fill,\
drawbox=x=410:y=540:w=1100:h=300:color=${Z0_PAPER}:t=4,\
drawbox=x=(iw-320)/2:y=730:w=320:h=6:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${FONT}':text='CHANNEL Z0':fontcolor=${Z0_PAPER}:fontsize=40:x=60:y=44,\
drawtext=fontfile='${FONT}':text='TEST CARD':fontcolor=0x8A8A8A:fontsize=40:x=w-tw-60:y=44,\
drawtext=fontfile='${FONT}':text='GREYSCALE · 0 to 100 IRE':fontcolor=0x8A8A8A:fontsize=26:x=(w-tw)/2:y=500,\
drawtext=fontfile='${FONT}':text='TEST CARD':fontcolor=0x8A8A8A:fontsize=34:x=(w-tw)/2:y=568,\
drawtext=fontfile='${FONT}':text='CHANNEL Z0':fontcolor=${Z0_PAPER}:fontsize=96:x=(w-tw)/2:y=610,\
drawtext=fontfile='${FONT}':text='A LOCAL CHANNEL, FOR LOCALS':fontcolor=0x8A8A8A:fontsize=28:x=(w-tw)/2:y=760,\
drawtext=fontfile='${FONT}':text='1 kHz LINE-UP TONE · 1080p / 30 · CH 0 · DESIG RL-Z0 · SIGN-ON 06:00':fontcolor=0x8A8A8A:fontsize=26:x=(w-tw)/2:y=1002\
[base];\
[base][1:v]overlay=x=10:y=150[v]" \
  -map "[v]" -map 2:a \
  -c:v libx264 -preset veryfast -b:v 3000k -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 96k -ar 48000 -shortest -movflags +faststart \
  "$OUT"

echo ""
echo "test card ready: $OUT (${SECS}s)"
echo "point ErsatzTV at it for the pre-sign-on fill, or a 'please stand by' with a picture to align to."
