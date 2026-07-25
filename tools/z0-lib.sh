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
