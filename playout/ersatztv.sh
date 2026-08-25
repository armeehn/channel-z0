#!/usr/bin/env bash
# Channel Z0 — start ErsatzTV on the playout PC (docker), without compose.
#
# Prefer compose.yml + tools/bootstrap-node.sh; this is the bare-metal escape
# hatch. Two things here used to be wrong and are worth stating plainly:
#
#   * the image is ghcr.io/ersatztv/LEGACY, not .../ersatztv, which does not
#     exist as tagged here;
#   * the tag is pinned. latest-vaapi and latest-nvidia are abandoned upstream
#     — there is no -nvidia build after v25.2.0 — so "latest" is frozen years
#     back and has no graphics engine. One image covers every accelerator; the
#     hardware is chosen by what you pass through, below.
#
# See docs/build-guide.md, Phase 2.
set -euo pipefail

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
TAG="${ERSATZTV_TAG:-v26.7.1}"
HWACCEL="${Z0_HWACCEL:-vaapi}"

ACCEL=()
case "$HWACCEL" in
  nvenc|nvidia)
    ACCEL=( --runtime nvidia
            -e "NVIDIA_VISIBLE_DEVICES=${Z0_NVIDIA_UUID:-all}"
            -e "NVIDIA_DRIVER_CAPABILITIES=compute,utility,video"
            -e "ETV_DISABLE_VULKAN=1" ) ;;
  vaapi|qsv)  ACCEL=( --device /dev/dri:/dev/dri ) ;;
  software)   ACCEL=() ; echo "warning: software encoding — this will occupy a CPU" >&2 ;;
  *) echo "unknown Z0_HWACCEL='${HWACCEL}' (nvenc|vaapi|qsv|software)" >&2; exit 1 ;;
esac

docker run -d --name ersatztv \
  -p 8409:8409 \
  -v /opt/ersatztv/config:/config \
  -v "${MEDIA_ROOT}:/media:ro" \
  "${ACCEL[@]}" \
  --restart unless-stopped \
  "ghcr.io/ersatztv/legacy:${TAG}"

echo "ErsatzTV starting → http://localhost:8409"
# The channel NUMBER, not an index — this station is channel 0, and
# /iptv/channel/1.ts on it is a 404.
echo "Sanity check the channel with:  vlc http://localhost:8409/iptv/channel/${Z0_CHANNEL_NUMBER:-0}.ts"
