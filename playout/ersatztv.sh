#!/usr/bin/env bash
# Channel Z0 — start ErsatzTV on the playout PC (docker).
# Tag guide:  latest-vaapi = Intel Quick Sync · latest-nvidia = NVENC · latest = software
# See docs/build-guide.md, Phase 2.
set -euo pipefail

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
TAG="${ERSATZTV_TAG:-latest-vaapi}"

docker run -d --name ersatztv \
  -p 8409:8409 \
  -v /opt/ersatztv/config:/config \
  -v "${MEDIA_ROOT}:/media:ro" \
  --device /dev/dri:/dev/dri \
  --restart unless-stopped \
  "docker.io/ersatztv/ersatztv:${TAG}"

echo "ErsatzTV starting → http://localhost:8409"
echo "Sanity check the channel with:  vlc http://localhost:8409/iptv/channel/1.ts"
