#!/bin/sh
# Channel Z0 — passive playout-gap logger (cron, every 2 minutes).
#
# ErsatzTV occasionally stops feeding the channel for 2-3 minutes between two
# items, logs NOTHING while it happens, and the lost time ratchets into
# permanent stream drift (see the 2026-08-26 journal entry on x). This logs
# one line per run so the next investigation can line a gap up with the
# ErsatzTV log to the minute:
#
#   epoch, newest session PDT, item-ffmpeg count in z0-ersatztv, etv cpu%
#
# A healthy line advances PDT ~120 s per run with ffmpeg>=1. A gap shows as
# PDT standing still across consecutive lines with ffmpeg=0 and cpu ~0.
#
# Reading it: awk -F, 'p{d=$2-p} {p=$2} d<90{print}' gap-log.csv  (stalls)

LOG=/mnt/main-data/channelz0/.z0-station/gap-log.csv

NOW=$(date -u +%s)
PDT=$(curl -s --max-time 5 http://127.0.0.1:8409/iptv/session/0/hls.m3u8 \
      | grep '^#EXT-X-PROGRAM-DATE-TIME:' | tail -1 | cut -d: -f2-)
PDT_EPOCH=$(date -d "$PDT" +%s 2>/dev/null || echo 0)

# item transcodes only: the per-item ffmpeg reads from a file or pipe, while
# probe wrappers come and go in under a second — a point sample is fine.
FF=$(docker top z0-ersatztv 2>/dev/null | grep -c '[f]fmpeg')
CPU=$(docker stats --no-stream --format '{{.CPUPerc}}' z0-ersatztv 2>/dev/null | tr -d '%')

echo "$NOW,$PDT_EPOCH,$FF,${CPU:-?}" >> "$LOG"

# keep roughly two months
if [ "$(wc -l < "$LOG")" -gt 50000 ]; then
    tail -n 40000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
