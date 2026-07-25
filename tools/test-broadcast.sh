#!/usr/bin/env bash
# Channel Z0 — prove the pipe works (build guide, Phase 1.5).
# Sends live colour bars + a quiet tone from this machine straight at the tower.
# If https://$Z0_WATCH_DOMAIN shows bars within ~30 seconds, the tower is good.
#
# Usage:
#   set -a; source .env; set +a        # or export Z0_WATCH_DOMAIN / Z0_STREAM_KEY
#   tools/test-broadcast.sh
# Stop with Ctrl-C.
set -euo pipefail

: "${Z0_WATCH_DOMAIN:?set Z0_WATCH_DOMAIN (e.g. watch.channelz0.example) — see .env.example}"
: "${Z0_STREAM_KEY:?set Z0_STREAM_KEY — see .env.example}"

echo "test pattern → rtmp://${Z0_WATCH_DOMAIN}:1935/live/*** (Ctrl-C to stop)"

ffmpeg -hide_banner -re \
  -f lavfi -i "smptehdbars=size=1280x720:rate=30" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000,volume=0.1" \
  -c:v libx264 -preset veryfast -b:v 2500k -pix_fmt yuv420p -g 60 \
  -c:a aac -b:a 96k \
  -f flv "rtmp://${Z0_WATCH_DOMAIN}:1935/live/${Z0_STREAM_KEY}"
