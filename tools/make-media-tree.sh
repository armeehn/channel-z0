#!/usr/bin/env bash
# Channel Z0 — create the media library layout the station expects.
# Run once on the playout PC (see docs/build-guide.md, Phase 2.1).
#
# Usage:
#   tools/make-media-tree.sh                   # builds under /media/channelz0
#   Z0_MEDIA_ROOT=/srv/z0 tools/make-media-tree.sh
set -euo pipefail

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"

mkdir -p \
  "${MEDIA_ROOT}/shows/Ground Zero/Season 01" \
  "${MEDIA_ROOT}/shows/Lab Hour/Season 01" \
  "${MEDIA_ROOT}/movies" \
  "${MEDIA_ROOT}/commercials/local" \
  "${MEDIA_ROOT}/commercials/lab" \
  "${MEDIA_ROOT}/bumpers" \
  "${MEDIA_ROOT}/psas" \
  "${MEDIA_ROOT}/interstitials"

cat <<TREE
media library ready at ${MEDIA_ROOT}:

  shows/            Plex-style naming: "Show - s01e01 - Title.ext"
    Ground Zero/    the flagship — file episodes under Season 01/
    Lab Hour/
  movies/           public-domain features
  commercials/
    local/          submitted spots (screened + normalized via tools/normalize-ad.sh)
    lab/            Riposte Labs promos
  bumpers/          "You're watching CHANNEL Z0" (5-15s each)
  psas/             vintage Prelinger material (archive.org/details/prelinger)
  interstitials/    sign-off bars (tools/make-colorbars.sh), slates

Next: add these folders as libraries in ErsatzTV (Phase 2.3).
TREE
