#!/usr/bin/env bash
# Drive the station-interval pipeline across the three hosts it needs.
#
# Run this from `x` (the Proxmox node). It is the only host that can see all
# three: it owns LXC 114 and LXC 111, and it is the only machine whose SSH key
# is in vile's authorized_keys.
#
#   z0-intervals.sh stage      copy rendered chunks 114 -> 111
#   z0-intervals.sh assemble   build the mp4s in 111
#   z0-intervals.sh install    push them to vile/media/generative (atomic)
#   z0-intervals.sh rescan     make ErsatzTV notice them
#   z0-intervals.sh all        stage + assemble + install + rescan
#
# Rendering itself is NOT here: it is a multi-hour batch and belongs in a
# nohup on 114. See docs/intervals.md.
set -euo pipefail

C114=114
C111=111
VILE=${VILE:-10.0.1.222}
MEDIA=/mnt/main-data/channelz0
DB=/mnt/solid-state/ersatztv/ersatztv.sqlite3

# Container rootfs as seen from x. Copying through these is far cheaper than
# pct pull/push for hundreds of files -- but note anything x writes lands owned
# by host root, which an unprivileged container sees as nobody and cannot write
# to, so the destination directories are created INSIDE the container and the
# copies are chowned to the container's mapped uid.
R114=/z1-pool/subvol-114-disk-0
R111=/z1-pool/subvol-111-disk-0
SUBUID=100000

CHUNKS_114=/var/lib/z0gen/chunks
WORK_111=/root/z0gen

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

stage() {
  say "staging chunks 114 -> 111"
  pct exec $C111 -- mkdir -p $WORK_111/chunks $WORK_111/intervals
  local src=$R114$CHUNKS_114 dst=$R111$WORK_111/chunks
  [[ -f $src/manifest.json ]] || { echo "no manifest in $src -- has the render run?"; exit 1; }
  cp -u "$src"/manifest.json "$src"/*.avi "$dst"/
  chown $SUBUID:$SUBUID "$dst"/*
  echo "staged $(ls "$dst"/*.avi | wc -l) chunks"
}

assemble() {
  say "assembling intervals in 111"
  pct exec $C111 -- python3 /tmp/z0-interval-assemble.py \
      --chunks-dir $WORK_111/chunks --out-dir $WORK_111/intervals
}

install_clips() {
  say "installing to vile:$MEDIA/generative"
  ssh -o BatchMode=yes root@"$VILE" "mkdir -p $MEDIA/generative"
  local n=0
  for f in $R111$WORK_111/intervals/*.mp4; do
    [[ -e $f ]] || continue
    local base; base=$(basename "$f")
    # write-temp + rename(2), the same guarantee tools/z0-weather.sh gives:
    # ErsatzTV opens these files while streaming, and a torn read makes it
    # disable the item for the rest of the programme.
    scp -q -o BatchMode=yes "$f" "root@$VILE:$MEDIA/generative/.$base.part"
    ssh -o BatchMode=yes root@"$VILE" \
        "chmod 0644 $MEDIA/generative/.$base.part && mv -f $MEDIA/generative/.$base.part $MEDIA/generative/$base"
    n=$((n+1))
  done
  echo "installed $n clips"
  ssh -o BatchMode=yes root@"$VILE" "ls -la $MEDIA/generative | tail -3; du -sh $MEDIA/generative"
}

rescan() {
  say "asking ErsatzTV to rescan /media"
  # Deliberately NOT running the scanner by hand. The app holds
  # /config/search-index/write.lock, so an external scan adds DB rows and
  # leaves the Lucene index untouched -- `search:` queries keep returning zero
  # and the schedule quietly builds holes.
  ssh -o BatchMode=yes root@"$VILE" \
      "sqlite3 $DB \"UPDATE LibraryPath SET LastScan = NULL WHERE Path = '/media';\""
  ssh -o BatchMode=yes root@"$VILE" "docker restart z0-ersatztv" >/dev/null
  echo "restarted z0-ersatztv; the scan runs on startup"
  echo "watch it with:  ssh root@$VILE 'docker logs --tail 40 -f z0-ersatztv'"
}

case "${1:-all}" in
  stage)     stage ;;
  assemble)  assemble ;;
  install)   install_clips ;;
  rescan)    rescan ;;
  all)       stage; assemble; install_clips; rescan ;;
  *) echo "usage: $0 {stage|assemble|install|rescan|all}"; exit 2 ;;
esac
