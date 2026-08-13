#!/usr/bin/env bash
# Channel Z0 — the weather desk. Renders every weather asset the channel airs:
#
#   branding/z0-weather-card.png    the persistent corner card
#   branding/z0-crawl.ass           the bottom-of-screen crawl
#   weather/z0-local-forecast.mp4   the full-screen segment
#
# Usage:
#   tools/z0-weather.sh              # render everything
#   tools/z0-weather.sh --card-only  # skip the segment (the slow part)
#
# Normally driven by cron every 15 minutes; see docs/weather.md.
#
# ── Two rules this script exists to enforce ─────────────────────────────────
#
# 1. EVERY INSTALL IS ATOMIC. ErsatzTV opens these files while it is streaming.
#    A half-written PNG doesn't glitch for a frame — ImageElement catches the
#    decode error, logs "Failed to initialize image element; will disable for
#    this content", and the overlay is GONE for the rest of that programme.
#    So we render to a scratch dir and rename() into place, which is atomic
#    within a dataset.
#
# 2. THE SEGMENT'S DURATION NEVER CHANGES. ErsatzTV scheduled the forecast from
#    the duration it saw at scan time. If a re-render came out longer or
#    shorter, playout and reality would drift apart with nothing to report it.
#    The output is pinned to Z0_WX_SEGMENT_SECS and the file keeps one name, so
#    the library row stays valid and no rescan is ever needed.
set -euo pipefail

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/mnt/main-data/channelz0}"
IMAGE="${Z0_FFMPEG_IMAGE:-ghcr.io/ersatztv/legacy:v26.7.1}"
SECS="${Z0_WX_SEGMENT_SECS:-120}"       # 4 slides x 30s
SLIDE=$(( SECS / 4 ))
CARD_ONLY=0
[[ "${1:-}" == "--card-only" ]] && CARD_ONLY=1

STATE="${MEDIA_ROOT}/.z0-station"
WORK="$(mktemp -d "${MEDIA_ROOT}/.z0-station/.wx-work.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "${MEDIA_ROOT}/branding" "${MEDIA_ROOT}/weather" "$STATE"

# The renderer runs inside the ErsatzTV image on purpose: it is the same ffmpeg
# and the same font set that the graphics engine will composite with, so what
# we measure here is what goes to air. (ErsatzTV's own 25.2 image shipped
# without drawtext at all, which is what made the old make-*.sh tools
# unrunnable against it.)
# The scratch dir lives under MEDIA_ROOT, so one bind mount at the identical
# path covers both it and any dropped-in music bed — and every path written
# into a filter script means the same thing inside the container as out.
ff() {
  docker run --rm --entrypoint /usr/local/bin/ffmpeg \
    -v "${MEDIA_ROOT}:${MEDIA_ROOT}" -u 0:0 "$IMAGE" "$@"
}
ffprobe_() {
  docker run --rm --entrypoint /usr/local/bin/ffprobe \
    -v "${MEDIA_ROOT}:${MEDIA_ROOT}" -u 0:0 "$IMAGE" "$@"
}

# ── 1. Fetch and lay out ─────────────────────────────────────────────────────
python3 "$(dirname "${BASH_SOURCE[0]}")/z0-weather.py" "$WORK" "$STATE"

install_atomic() { # src dst
  local dst="$2" tmp
  tmp="$(dirname "$dst")/.$(basename "$dst").tmp.$$"
  cp "$1" "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dst"      # rename(2): readers see old or new, never partial
}

# ── 2. The corner card ───────────────────────────────────────────────────────
ff -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=black@0.0:s=920x300,format=rgba" \
  -filter_script:v "${WORK}/card.vf" \
  -frames:v 1 "${WORK}/card.png"
install_atomic "${WORK}/card.png" "${MEDIA_ROOT}/branding/z0-weather-card.png"

# ── 3. The crawl ─────────────────────────────────────────────────────────────
install_atomic "${WORK}/z0-crawl.ass" "${MEDIA_ROOT}/branding/z0-crawl.ass"

if (( CARD_ONLY )); then
  echo "weather desk: card + crawl updated (segment skipped)"
  exit 0
fi

# ── 4. The full-screen segment ───────────────────────────────────────────────
# Each slide is rendered as a still first. Building the whole segment as one
# filtergraph would work, but a 100-drawtext chain is undebuggable when one
# coordinate is wrong — this way a bad slide is a PNG you can look at.
for i in 1 2 3 4; do
  ff -hide_banner -loglevel error -y \
    -f lavfi -i "color=c=${Z0_INK_HEX:-0x141414}:s=1920x1080" \
    -filter_script:v "${WORK}/slide${i}.vf" \
    -frames:v 1 "${WORK}/slide${i}.png"
done

# A dropped-in bed wins; otherwise a low pad. make-slate.sh's 440Hz sine is
# right for a 20-second card and punishing for two minutes, so this is quieter
# and an octave lower.
BED=""
for cand in "${MEDIA_ROOT}"/weather/bed/*.{m4a,mp3,wav,flac,ogg}; do
  [[ -f "$cand" ]] && { BED="$cand"; break; }
done

AUDIO_IN=()
if [[ -n "$BED" ]]; then
  AUDIO_IN=(-stream_loop -1 -i "$BED")
  AFILTER="[4:a]volume=0.35,afade=t=in:d=2,afade=t=out:st=$((SECS-3)):d=3,aformat=channel_layouts=stereo[a]"
elif [[ "${Z0_SILENT:-0}" == "1" ]]; then
  AUDIO_IN=(-f lavfi -i "anullsrc=r=48000:cl=stereo")
  AFILTER="[4:a]anull[a]"
else
  AUDIO_IN=(-f lavfi -i "sine=frequency=110:sample_rate=48000:duration=${SECS}")
  AFILTER="[4:a]volume=0.035,tremolo=f=0.15:d=0.4,afade=t=in:d=3,afade=t=out:st=$((SECS-4)):d=4,aformat=channel_layouts=stereo[a]"
fi

# Slides are concatenated (not cross-faded) so the total is exactly SECS.
ff -hide_banner -loglevel error -y \
  -loop 1 -t "$SLIDE" -i "${WORK}/slide1.png" \
  -loop 1 -t "$SLIDE" -i "${WORK}/slide2.png" \
  -loop 1 -t "$SLIDE" -i "${WORK}/slide3.png" \
  -loop 1 -t "$SLIDE" -i "${WORK}/slide4.png" \
  "${AUDIO_IN[@]}" \
  -filter_complex "\
[0:v]fade=t=in:st=0:d=0.5,fade=t=out:st=$((SLIDE-1)):d=0.5[v0];\
[1:v]fade=t=in:st=0:d=0.5,fade=t=out:st=$((SLIDE-1)):d=0.5[v1];\
[2:v]fade=t=in:st=0:d=0.5,fade=t=out:st=$((SLIDE-1)):d=0.5[v2];\
[3:v]fade=t=in:st=0:d=0.5,fade=t=out:st=$((SLIDE-1)):d=0.5[v3];\
[v0][v1][v2][v3]concat=n=4:v=1:a=0,fps=30,format=yuv420p[v];\
${AFILTER}" \
  -map "[v]" -map "[a]" -t "$SECS" \
  -c:v libx264 -preset veryfast -b:v 3000k -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 96k -ar 48000 -movflags +faststart \
  "${WORK}/forecast.mp4"

# Refuse to install a segment of the wrong length rather than let playout and
# air drift apart silently.
DUR=$(ffprobe_ -v error -show_entries format=duration -of csv=p=0 \
        "${WORK}/forecast.mp4")
OK=$(python3 -c "print(1 if abs(float('$DUR') - $SECS) <= 0.5 else 0)")
if [[ "$OK" != "1" ]]; then
  echo "weather desk: REFUSING to install — segment is ${DUR}s, expected ${SECS}s" >&2
  exit 1
fi

install_atomic "${WORK}/forecast.mp4" "${MEDIA_ROOT}/weather/z0-local-forecast.mp4"
echo "weather desk: card, crawl and ${SECS}s segment updated"
