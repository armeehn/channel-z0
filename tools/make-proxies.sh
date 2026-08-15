#!/usr/bin/env bash
# Channel Z0 — build a test library: tiny stand-ins for the real media.
#
# A stocked library is tens of gigabytes and a single feature is a few hundred
# megabytes, which makes "does my schedule actually work" an expensive question.
# This mirrors the library into low-resolution proxies — same tree, same
# filenames, same *durations*, a fraction of a percent of the bytes. Point
# ErsatzTV at the proxy root and the whole broadcast day behaves identically;
# it just looks like a webcam from 1998.
#
# Duration is the thing that matters. Schedules, pad-to-the-half-hour, and the
# 19:00 anchor are all arithmetic on runtimes, so proxies keep runtimes exact
# unless you explicitly ask for --seconds.
#
# Usage:
#   tools/make-proxies.sh                          # mirror the whole library
#   tools/make-proxies.sh --placeholder            # cards instead of video — seconds, not hours
#   tools/make-proxies.sh psas/ movies/noir/       # only these
#   tools/make-proxies.sh --seconds 20 --out /tmp/z0-quick
#   tools/make-proxies.sh --dry-run
#
# Options:
#   --out DIR        proxy root (default: $Z0_MEDIA_ROOT-test)
#   --placeholder    don't decode the source; generate a labelled Z0 card of the
#                    same duration. Fastest, smallest, and honest about being fake.
#   --width N        proxy width, height follows aspect (default 320)
#   --crf N          x264 quality, higher is smaller (default 40)
#   --seconds N      trim to N seconds — breaks schedule arithmetic, good for smoke tests
#   --jobs N         parallel encodes (default 4)
#   --force          re-encode even if the proxy exists
#   --dry-run        list what would be built
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/z0-lib.sh"

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
OUT_ROOT="${Z0_PROXY_ROOT:-${MEDIA_ROOT}-test}"
WIDTH=320
CRF=40
SECONDS_LIMIT=""
PLACEHOLDER=0
JOBS="${Z0_PROXY_JOBS:-4}"
FORCE=0
DRY=0
INPUTS=()

usage() { sed -n '2,34p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

command -v ffmpeg  >/dev/null || { echo "ffmpeg not found" >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe not found" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)         OUT_ROOT="$2"; shift 2 ;;
    --width)       WIDTH="$2"; shift 2 ;;
    --crf)         CRF="$2"; shift 2 ;;
    --seconds)     SECONDS_LIMIT="$2"; shift 2 ;;
    --placeholder) PLACEHOLDER=1; shift ;;
    --jobs)        JOBS="$2"; shift 2 ;;
    --force)       FORCE=1; shift ;;
    --dry-run)     DRY=1; shift ;;
    -h|--help)     usage 0 ;;
    -*)            echo "unknown option: $1" >&2; usage 1 ;;
    *)             INPUTS+=("$1"); shift ;;
  esac
done
[[ ${#INPUTS[@]} -eq 0 ]] && INPUTS=("$MEDIA_ROOT")

# The label is operator data — a filename out of the library — so it carries
# apostrophes ("Kelowna's Own"), colons ("LAB HOUR: GROUND ZERO"), percents and
# commas: every character drawtext's nested parsers fight over. This used to be
# handled by flattening the title to a charset that couldn't bite, which is why
# a proxy for "Kelowna's Own: LAB HOUR" silently read KELOWNAS OWN LAB HOUR —
# no error, no clue, and the label is the one thing a proxy is *for*.
#
# So don't escape and don't flatten: hand the words to drawtext out-of-band with
# z0_text, exactly as the full-size generators in make-slate.sh do. Then there
# is no escaping layer left to get wrong the next time a title grows a bracket.
#
# Drop the trailing [archive-identifier] that fetch-archive.sh files with — it
# doubles the title and there's only 320px of card. 30 chars fits with margin.
# Newlines and tabs still go, because a filename holding one would wreck the
# card's layout rather than its escaping.
placeholder_label() {
  local s
  s="$(sed -e 's/ *\[[^]]*\] *$//' <<<"$1" | tr '\n\r\t' '   ' \
       | tr '[:lower:]' '[:upper:]')"
  printf '%s' "${s:0:30}"
}

hms() { awk -v s="${1:-0}" 'BEGIN{printf "%d:%02d:%02d", s/3600, (s%3600)/60, s%60}'; }

# ── One file ──────────────────────────────────────────────────────────────────
make_proxy() { # src, dst, duration
  local src="$1" dst="$2" dur="$3"
  mkdir -p "$(dirname "$dst")"
  local d="${SECONDS_LIMIT:-$dur}"

  if [[ "$PLACEHOLDER" == "1" ]]; then
    local label; label=$(placeholder_label "$(basename "${src%.*}")")
    local runtime; runtime=$(hms "$d")
    local font; font="$(z0_find_font)"
    # No input decode at all: a colour field, the title, and the runtime it is
    # standing in for.
    #
    # The surprise here is that the cost is the *audio*. A static frame is
    # nearly free to x264, but AAC-encoding 90 minutes of silence at 48k stereo
    # measured 38s against 6s for the video. Dropping the silence to 22050 mono
    # takes a feature-length card from ~43s to ~24s (2.8 MB). It is silence, and
    # ErsatzTV re-encodes to the channel profile anyway.
    ffmpeg -hide_banner -loglevel error -y \
      -f lavfi -i "color=c=${Z0_INK}:s=${WIDTH}x$(( WIDTH * 3 / 4 )):r=10:d=${d}" \
      -f lavfi -t "$d" -i "anullsrc=r=22050:cl=mono" \
      -vf "drawbox=x=0:y=8:w=iw:h=3:color=${Z0_RED}:t=fill,\
drawtext=fontfile='${font}':$(z0_text "${label}"):fontcolor=${Z0_PAPER}:fontsize=14:x=(w-tw)/2:y=(h/2)-20,\
drawtext=fontfile='${font}':$(z0_text "PROXY ${runtime}"):fontcolor=0x8A8A8A:fontsize=11:x=(w-tw)/2:y=(h/2)+10,\
drawtext=fontfile='${font}':text='RL-Z0 TEST':fontcolor=${Z0_RED}:fontsize=9:x=6:y=h-th-6" \
      -map 0:v -map 1:a \
      -c:v libx264 -preset ultrafast -tune stillimage -crf 34 -pix_fmt yuv420p \
      -c:a aac -b:a 16k -ac 1 -ar 22050 -shortest -movflags +faststart \
      "$dst" || return 1
  else
    # Real content, made small: scale to width, quality-targeted so a talky
    # short doesn't cost what an action reel does, mono audio because nobody is
    # judging the mix on a proxy.
    ffmpeg -hide_banner -loglevel error -y \
      ${SECONDS_LIMIT:+-t "$SECONDS_LIMIT"} -i "$src" \
      -vf "scale=${WIDTH}:-2:flags=fast_bilinear" \
      -c:v libx264 -preset veryfast -crf "$CRF" -pix_fmt yuv420p \
      -c:a aac -b:a 32k -ac 1 -ar 44100 \
      -movflags +faststart -sn -dn -map_chapters -1 \
      "$dst" || return 1
  fi

  # A proxy that won't probe is worse than no proxy — it turns a schedule test
  # into a debugging session about the test rig.
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$dst" >/dev/null 2>&1 \
    || { echo "  FAILED probe: $dst" >&2; rm -f "$dst"; return 1; }
}

# Encodes run in the background, so a failed one can't just decrement a counter
# in this shell. Each failure appends a line instead, and the tally at the end
# reads the file — otherwise a run where every encode died still reports success.
note_failure() { printf '%s\n' "$1" >> "$FAILLOG"; }

run_one() { # src, dst, duration, label
  make_proxy "$1" "$2" "$3" || note_failure "$4"
}

# ── Walk the inputs ───────────────────────────────────────────────────────────
echo "CHANNEL Z0 — test library"
echo "source: ${MEDIA_ROOT}"
echo "proxy:  ${OUT_ROOT}"
if [[ "$PLACEHOLDER" == "1" ]]; then
  echo "mode:   placeholder cards (${WIDTH}px)"
else
  echo "mode:   transcode ${WIDTH}px crf${CRF}"
fi
[[ -n "$SECONDS_LIMIT" ]] && echo "        trimmed to ${SECONDS_LIMIT}s — runtimes will NOT match the real library"
[[ "$DRY" == "1" ]] && echo "DRY RUN"
echo ""

attempted=0; skipped=0; src_bytes=0; dst_bytes=0
srclist="$(mktemp)"; FAILLOG="$(mktemp)"; dstlist="$(mktemp)"
# z0-lib installs an EXIT trap for the z0_text scratch dir; a second `trap ...
# EXIT` replaces it rather than adding to it, so carry that dir along or every
# run leaves a z0-text.XXXXXX behind in /tmp.
trap 'rm -f "$srclist" "$FAILLOG" "$dstlist"; rm -rf "${Z0_TEXT_DIR:-}"' EXIT

for input in "${INPUTS[@]}"; do
  # Accept an absolute path, or one relative to the media root, or a bare file.
  path="$input"
  [[ -e "$path" ]] || path="${MEDIA_ROOT}/${input#/}"
  [[ -e "$path" ]] || { echo "no such path: $input" >&2; continue; }
  if [[ -d "$path" ]]; then
    find "$path" -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.avi' \
      -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.ogv' -o -iname '*.mpg' \
      -o -iname '*.mpeg' -o -iname '*.webm' -o -iname '*.ts' \) -print0 >> "$srclist"
  else
    printf '%s\0' "$path" >> "$srclist"
  fi
done

while IFS= read -r -d '' src; do
  # Mirror the path relative to the media root so the proxy tree is the real
  # tree — the whole point, since ErsatzTV libraries are folder-shaped.
  case "$src" in
    "$MEDIA_ROOT"/*) rel="${src#"$MEDIA_ROOT"/}" ;;
    *)               rel="$(basename "$src")" ;;
  esac
  dst="${OUT_ROOT}/${rel%.*}.mp4"

  if [[ -f "$dst" && "$FORCE" != "1" ]]; then
    skipped=$(( skipped + 1 )); continue
  fi

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src" 2>/dev/null | cut -d. -f1)
  if [[ -z "$dur" || "$dur" == "N/A" ]]; then
    echo "  skip (unreadable source): $rel" >&2
    attempted=$(( attempted + 1 )); note_failure "$rel"; continue
  fi

  if [[ "$DRY" == "1" ]]; then
    printf '  would build %-8s %s\n' "$(hms "${SECONDS_LIMIT:-$dur}")" "$rel"
    attempted=$(( attempted + 1 )); continue
  fi

  echo "  ${rel} ($(hms "$dur"))"
  printf '%s\0' "$dst" >> "$dstlist"
  # Simple pool: keep at most $JOBS encodes in flight.
  while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n 2>/dev/null || true; done
  run_one "$src" "$dst" "$dur" "$rel" &
  attempted=$(( attempted + 1 ))
done < "$srclist"
wait

failed=$(wc -l < "$FAILLOG" | tr -d ' ')
built=$(( attempted - failed ))

# ── Report ────────────────────────────────────────────────────────────────────
# Compare only what this run touched. Summing everything under the proxy root
# would flatter the numbers on a second run against a subset of the library.
human() { awk -v b="${1:-0}" 'BEGIN{
  split("B KB MB GB TB", u, " "); i=1
  while (b >= 1024 && i < 5) { b /= 1024; i++ }
  printf (i>2 ? "%.1f %s" : "%.0f %s"), b, u[i] }'; }

if [[ "$DRY" != "1" ]]; then
  while IFS= read -r -d '' f; do
    [[ -f "$f" ]] && src_bytes=$(( src_bytes + $(stat -c%s "$f" 2>/dev/null || echo 0) ))
  done < "$srclist"
  if [[ -s "$dstlist" ]]; then
    while IFS= read -r -d '' f; do
      [[ -f "$f" ]] && dst_bytes=$(( dst_bytes + $(stat -c%s "$f" 2>/dev/null || echo 0) ))
    done < "$dstlist"
  fi
fi

echo ""
echo "built ${built}, skipped ${skipped} (already present), failed ${failed}"
if [[ "$DRY" != "1" && "$built" -gt 0 && "$src_bytes" -gt 0 ]]; then
  echo "source $(human "$src_bytes")  →  proxies $(human "$dst_bytes")  ($(awk -v s="$src_bytes" -v d="$dst_bytes" 'BEGIN{printf "%.2f%%", (d*100)/s}') of the bytes)"
fi
if [[ "$failed" -gt 0 ]]; then
  echo ""
  echo "failed:" >&2
  sed 's/^/  /' "$FAILLOG" >&2
fi
cat <<NOTE

Point a throwaway ErsatzTV at ${OUT_ROOT} — same folder names, same runtimes,
so schedules and filler behave exactly as they will on air. Keep it on a
separate channel number; you do not want proxies reaching the uplink.
NOTE
