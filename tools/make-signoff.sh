#!/usr/bin/env bash
# Channel Z0 — generate the nightly sign-off (the end-of-broadcast-day close the
# 00:00 SIGN-OFF schedule item cuts to before the colour bars take over). It's
# the ritual card — station wordmark, "THIS CONCLUDES OUR BROADCAST DAY,"
# "GOODNIGHT, LOCALS," the sign-on time — that then dissolves into a short tail
# of SMPTE bars, so it hands off cleanly to the `Colour Bars` filler that runs
# until the 06:00 sign-on.
#
# `make-slate.sh` makes a static sign-off *card*; this is the whole close, card
# into bars, in one file — the seed of the "sign-off anthem" on the roadmap.
#
# Usage:
#   tools/make-signoff.sh              # 25s card + 10s bars tail -> interstitials/
#   tools/make-signoff.sh 40 15        # 40s card, 15s bars tail
#   Z0_SILENT=1 tools/make-signoff.sh  # no closing hum (silence)
#
# Args: [card_seconds] [bars_tail_seconds]
# Output: $Z0_MEDIA_ROOT/interstitials/signoff.mp4 (1080p/30, channel profile).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"

CARD_SECS="${1:-25}"
BARS_SECS="${2:-10}"
TOTAL=$(( CARD_SECS + BARS_SECS ))
MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_DIR="${MEDIA_ROOT}/interstitials"
OUT="${OUT_DIR}/signoff.mp4"
FONT="$(z0_find_font)"

# A quiet closing hum that fades to nothing as the bars come up — the sound of a
# station going dark for the night. Z0_SILENT drops it entirely.
if [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_SRC="anullsrc=r=48000:cl=stereo"
else
  AUDIO_SRC="sine=frequency=220:sample_rate=48000,volume=0.05"
fi

# Fade-out on the card and fade-in on the bars land at wall-clock times.
CARD_FADEOUT="$(awk "BEGIN{print ${CARD_SECS}-0.6}")"
AUDIO_FADEOUT="$(awk "BEGIN{print ${TOTAL}-2}")"

mkdir -p "$OUT_DIR"

# Segment 1: the sign-off card on an ink field — red rules top and bottom, the
# small CHANNEL Z0 kicker, the two-line farewell, "GOODNIGHT, LOCALS" in red,
# the sign-on time, and the DESIG in the corner. Fades in from black, then out.
# Segment 2: a short SMPTE bars tail, fading in, that bridges to the filler.
# concat splices the two into a single clip.
ffmpeg -hide_banner -y \
  -f lavfi -i "color=c=${Z0_INK}:s=1920x1080:r=30:d=${CARD_SECS}" \
  -f lavfi -i "smptehdbars=size=1920x1080:rate=30" \
  -f lavfi -t "${TOTAL}" -i "${AUDIO_SRC}" \
  -filter_complex "\
[0:v]\
drawbox=x=0:y=120:w=iw:h=10:color=${Z0_RED}:t=fill,\
drawbox=x=0:y=950:w=iw:h=10:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${FONT}':text='CHANNEL Z0':fontcolor=0x8A8A8A:fontsize=30:x=(w-tw)/2:y=210,\
drawtext=fontfile='${FONT}':text='THIS CONCLUDES OUR':fontcolor=${Z0_PAPER}:fontsize=76:x=(w-tw)/2:y=330,\
drawtext=fontfile='${FONT}':text='BROADCAST DAY':fontcolor=${Z0_PAPER}:fontsize=76:x=(w-tw)/2:y=430,\
drawbox=x=(iw-360)/2:y=575:w=360:h=6:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${FONT}':text='GOODNIGHT, LOCALS':fontcolor=${Z0_RED}:fontsize=56:x=(w-tw)/2:y=625,\
drawtext=fontfile='${FONT}':text='SIGN-ON AT 06:00':fontcolor=${Z0_PAPER}:fontsize=40:x=(w-tw)/2:y=720,\
drawtext=fontfile='${FONT}':text='COLOUR BARS UNTIL SUNRISE':fontcolor=0x8A8A8A:fontsize=28:x=(w-tw)/2:y=810,\
drawtext=fontfile='${FONT}':text='DESIG RL-Z0':fontcolor=0x8A8A8A:fontsize=24:x=60:y=h-th-40,\
fade=t=in:st=0:d=1,fade=t=out:st=${CARD_FADEOUT}:d=0.6,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[card];\
[1:v]trim=duration=${BARS_SECS},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.6,format=yuv420p,setsar=1[bars];\
[card][bars]concat=n=2:v=1:a=0[v];\
[2:a]afade=t=in:st=0:d=1,afade=t=out:st=${AUDIO_FADEOUT}:d=2[a]" \
  -map "[v]" -map "[a]" -shortest \
  -c:v libx264 -preset veryfast -b:v 3000k -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 96k -ar 48000 -movflags +faststart \
  "$OUT"

echo ""
echo "sign-off ready: $OUT (${TOTAL}s — ${CARD_SECS}s card + ${BARS_SECS}s bars)"
echo "wire it as the 00:00 SIGN-OFF item; let the Colour Bars filler carry the rest of the night."
