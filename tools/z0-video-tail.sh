#!/usr/bin/env bash
# Channel Z0 — find, and fill, clips whose picture ends before their sound.
#
# A file whose video stream is shorter than its audio airs as N seconds of
# sound over no frames. ErsatzTV then logs
#   Media item [N] transcoded at 0.68x (throttled) which may not be fast enough
# because ffmpeg's speed= is the last VIDEO timestamp over wall time, not a
# measure of the encoder, and the tower drifts by exactly those N seconds.
# Found 2026-09-15: 14 of the 32 z0-anime clips had 35–51 s of picture under a
# 55 s anullsrc track (their glitch carrier came out short and the final mux
# had no -shortest). Encoder, GPU and graphics engine were all innocent.
#
# Usage:
#   z0-video-tail.sh scan <dir|file>...    list offenders; exit 1 if any
#   z0-video-tail.sh fix  <dir|file>...    loop the picture to the audio length
#
# fix re-encodes the video only (the clip loops from its start to fill the
# tail, which abstract material tolerates), copies the audio, and replaces the
# file by write-temp + rename so an item ErsatzTV is streaming is never torn.
# The duration does not change, so no rescan or playout rebuild is needed.
set -euo pipefail

# Audio and video legitimately differ by an AAC frame or two (21 ms each).
TAIL_TOLERANCE=0.5

# Same gate as the interval generators: nothing in the pool above 3000 kbps.
MAXRATE=2800k
BUFSIZE=5600k

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

MODE="${1:-}"; shift || true
[[ "$MODE" == scan || "$MODE" == fix ]] || usage
[[ $# -ge 1 ]] || usage

for bin in ffmpeg ffprobe; do
  command -v "$bin" >/dev/null 2>&1 || { echo "$bin not on PATH" >&2; exit 1; }
done

probe() { # file key -> value
  ffprobe -v error "${@:3}" -show_entries "$2" -of default=nw=1:nk=1 "$1" | head -1
}

# Prints "video audio" durations in seconds; empty when a stream is missing
# or the container does not carry per-stream durations (raw MPEG-TS).
tail_of() { # file
  local v a
  v=$(probe "$1" stream=duration -select_streams v:0 || true)
  a=$(probe "$1" stream=duration -select_streams a:0 || true)
  [[ -n "$v" && -n "$a" && "$v" != N/A && "$a" != N/A ]] || return 1
  awk -v v="$v" -v a="$a" -v tol="$TAIL_TOLERANCE" \
    'BEGIN { if (a - v > tol) printf "%.3f %.3f\n", v, a; else exit 1 }'
}

fill() { # file video-dur audio-dur
  local f="$1" tmp
  tmp="$(dirname "$f")/.$(basename "$f").part"
  # -stream_loop repeats the picture; -t cuts the loop at the audio length.
  # The audio is untouched so the loudness and the track layout stay as filed.
  ffmpeg -nostdin -v error -y -stream_loop -1 -i "$f" -i "$f" -f mp4 \
    -map 0:v:0 -map 1:a:0 -t "$3" \
    -c:v libx264 -preset medium -crf 20 -maxrate "$MAXRATE" -bufsize "$BUFSIZE" \
    -pix_fmt yuv420p -color_range tv -c:a copy -movflags +faststart "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$f"
}

found=0
while IFS= read -r -d '' f; do
  dur=$(tail_of "$f") || continue
  read -r v a <<<"$dur"
  found=$((found + 1))
  printf '%-60s video %7.3fs  audio %7.3fs  short by %6.3fs\n' "$f" "$v" "$a" "$(awk -v v="$v" -v a="$a" 'BEGIN{print a-v}')"
  if [[ "$MODE" == fix ]]; then
    fill "$f" "$v" "$a"
    read -r v2 a2 <<<"$(probe "$f" stream=duration -select_streams v:0) $(probe "$f" stream=duration -select_streams a:0)"
    printf '%-60s filled: video %7.3fs  audio %7.3fs\n' "" "$v2" "$a2"
  fi
done < <(find "$@" -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.mov' -o -iname '*.webm' -o -iname '*.m4v' \) -print0 | sort -z)

echo "$found file(s) with a short picture"
[[ "$MODE" == fix || $found -eq 0 ]]
