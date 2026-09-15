#!/usr/bin/env bash
# Channel Z0 — create the media library layout the station expects.
# Run once on the playout PC (see docs/build-guide.tex, Phase 2.1).
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
  "${MEDIA_ROOT}/movies/noir" \
  "${MEDIA_ROOT}/movies/scifi" \
  "${MEDIA_ROOT}/movies/docs" \
  "${MEDIA_ROOT}/movies/serials" \
  "${MEDIA_ROOT}/movies/classics" \
  "${MEDIA_ROOT}/movies/cult" \
  "${MEDIA_ROOT}/commercials/local" \
  "${MEDIA_ROOT}/commercials/lab" \
  "${MEDIA_ROOT}/bumpers" \
  "${MEDIA_ROOT}/psas" \
  "${MEDIA_ROOT}/prelinger" \
  "${MEDIA_ROOT}/cartoons" \
  "${MEDIA_ROOT}/slowtv" \
  "${MEDIA_ROOT}/interstitials"

cat <<TREE
media library ready at ${MEDIA_ROOT}:

  shows/            Plex-style naming: "Show - s01e01 - Title.ext"
    Ground Zero/    the flagship — file episodes under Season 01/
    Lab Hour/
  movies/           public-domain features, split by themed night
    noir/ scifi/ docs/ serials/ classics/ cult/
  commercials/
    local/          submitted spots (screened + normalized via tools/normalize-ad.sh)
    lab/            Riposte Labs promos
  bumpers/          "You're watching CHANNEL Z0" (5-15s each, tools/make-ident.sh)
  psas/             short vintage spots — the 'Vintage PSAs' ad-break filler
  prelinger/        longer educational shorts — PRELINGER THEATRE
  cartoons/         public-domain animation — the CARTOON BLOCK
  slowtv/           long-take ambient blocks (yours; nothing auto-fetches here)
  interstitials/    sign-off bars (tools/make-colorbars.sh), slates, test card

Next:
  1. tools/fetch-archive.sh --all   fill psas/, prelinger/, cartoons/, movies/*
     from the Internet Archive (public-domain only). See docs/archive-fetch.tex.
  2. Add these folders as libraries in ErsatzTV (Phase 2.3) and build the
     collections listed in docs/programming.tex.
TREE
