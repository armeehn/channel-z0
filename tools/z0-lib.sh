#!/usr/bin/env bash
# Channel Z0 — shared helpers for the station tools.
# Not run directly; sourced by the make-*.sh generators.

# The station's look is monospace on ink. ffmpeg's drawtext needs a real font
# file, so find one. Override with Z0_FONT=/path/to/font.ttf to force a choice.
z0_find_font() {
  if [[ -n "${Z0_FONT:-}" ]]; then
    [[ -f "$Z0_FONT" ]] && { echo "$Z0_FONT"; return 0; }
    echo "Z0_FONT set but not found: $Z0_FONT" >&2; return 1
  fi
  # Prefer a monospace face via fontconfig, if present.
  if command -v fc-match >/dev/null 2>&1; then
    local f
    f=$(fc-match -f '%{file}' 'monospace' 2>/dev/null || true)
    [[ -n "$f" && -f "$f" ]] && { echo "$f"; return 0; }
  fi
  # Otherwise walk the usual suspects.
  local candidates=(
    /usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf
    /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
    /usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf
    /usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf
    /usr/share/fonts/TTF/DejaVuSansMono.ttf
    /Library/Fonts/Menlo.ttc
    /System/Library/Fonts/Menlo.ttc
    /System/Library/Fonts/SFNSMono.ttf
    /usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf
  )
  local c
  for c in "${candidates[@]}"; do
    [[ -f "$c" ]] && { echo "$c"; return 0; }
  done
  echo "no monospace font found — install fonts-dejavu (Debian/Ubuntu) or set Z0_FONT=/path/to.ttf" >&2
  return 1
}

# The station palette, so every generated card matches the storefront.
Z0_INK="0x141414"      # near-black
Z0_PAPER="0xF2F0E9"    # bone
Z0_RED="0xE02A1B"      # riposte red

# ── Caller-supplied text ──────────────────────────────────────────────────────
# ffmpeg's filtergraph parser splits filter options on ':', so a headline like
# "SIGN-OFF: 00:00" tears the graph in half and the render dies. drawtext then
# expands '%' on what survives, and a stray apostrophe or backslash is eaten by
# the quoting layers — silently, so you get a card with the wrong words on it.
# Escaping cleanly through all three layers is famously unreliable, so don't:
# hand the text to drawtext out-of-band, in a file it reads verbatim.
#
#   drawtext=fontfile='${FONT}':$(z0_text "$HEAD"):fontcolor=...
#
# z0_text prints `textfile='...':expansion=none` — a drop-in replacement for
# `text='...'` — and its scratch files go away when the script exits.
#
# The scratch dir is made here, at source time, on purpose: z0_text is called
# from inside a command substitution, and a subshell cannot hand back either a
# variable or a trap. Note that sourcing this library installs an EXIT trap.
Z0_TEXT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/z0-text.XXXXXX")"
trap 'rm -rf "${Z0_TEXT_DIR}"' EXIT

z0_text() {
  local f
  f="$(mktemp "${Z0_TEXT_DIR}/line.XXXXXX")"
  printf '%s' "$1" >"$f"
  printf "textfile='%s':expansion=none" "$f"
}

# ── Argument handling ─────────────────────────────────────────────────────────
# The generators used to hand their positional arguments straight to ffmpeg,
# which made `--help` an unbound variable inside an arithmetic expansion and
# turned a typo'd duration into a filter-description error 200 lines deep.

# Print the calling script's header comment — its usage notes — and exit 0.
z0_usage() {
  sed -n '2,/^set /{ /^set /d; s/^# \{0,1\}//; p; }' "${BASH_SOURCE[-1]}"
}

# Wire up -h/--help. Call as `z0_help_check "$@"` before touching the arguments.
z0_help_check() {
  local a
  for a in "$@"; do
    case "$a" in
      -h|--help) z0_usage; exit 0 ;;
    esac
  done
}

# A duration or count has to be a positive whole number — it ends up in `d=` and
# in $(( )), and neither says anything useful about "30s" or "--help".
z0_require_int() { # label value
  local me="${BASH_SOURCE[-1]##*/}"
  if [[ ! "$2" =~ ^[0-9]+$ ]] || (( 10#$2 == 0 )); then
    echo "${me}: ${1} must be a positive whole number, got '${2}'" >&2
    echo "try: ${me} --help" >&2
    exit 2
  fi
}
