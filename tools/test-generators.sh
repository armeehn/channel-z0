#!/usr/bin/env bash
# Channel Z0 — prove the card generators still make cards.
#
# The generators hand operator-supplied words to ffmpeg's drawtext, and ffmpeg's
# filtergraph parser reads ':' as an option separator, '%' as an expansion and a
# bare apostrophe as a quote. So "SIGN-OFF: 00:00" used to kill the render
# outright, and "WE'LL BE BACK" used to render as *nothing at all* while the
# script still cheerfully printed "slate ready". These are the assertions that
# keep that fixed:
#
#   ARGUMENTS    --help prints the usage and writes nothing; a bad duration
#                fails immediately instead of 200 lines into a filtergraph
#   TEXT         punctuation in a headline reaches the screen, not the parser
#   CONFORMANCE  every card comes out 1080p/30 with audio, at the asked length
#
# Everything renders into a scratch media root at 1–2 seconds a card, so this
# touches nothing real and finishes in well under a minute.
#
# Usage:
#   tools/test-generators.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for bin in ffmpeg ffprobe; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "test-generators: no ${bin} on PATH — nothing to test, skipping."; exit 0; }
done

# shellcheck source=tools/z0-lib.sh
source "${DIR}/z0-lib.sh"
z0_help_check "$@"
z0_find_font >/dev/null || {
  echo "test-generators: no usable font — skipping."; exit 0; }

Z0_MEDIA_ROOT="$(mktemp -d)"; export Z0_MEDIA_ROOT
export Z0_SILENT=1          # a silent source is still an audio stream, and quicker
export Z0_SERIAL=T35T       # pin the test card's serial so runs are comparable
SCRATCH="$(mktemp -d)"
INTER="${Z0_MEDIA_ROOT}/interstitials"

# z0-lib installs its own EXIT trap for the drawtext scratch dir; replacing it
# means taking that dir with us.
cleanup() { rm -rf "$Z0_MEDIA_ROOT" "$SCRATCH" "${Z0_TEXT_DIR:-}"; }
trap cleanup EXIT

pass=0; fail=0
ok()  { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$(( pass + 1 )); }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$(( fail + 1 )); }

LOG="${SCRATCH}/gen.log"
gen() { # script.sh args... — run a generator quietly, keep its output for a failure
  local s="$1"; shift
  bash "${DIR}/${s}" "$@" >"$LOG" 2>&1
}

vprobe() { ffprobe -v error -select_streams v:0 -show_entries "stream=$2" -of csv=p=0 "$1"; }
dur()    { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }
has_audio() {
  [[ -n "$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$1")" ]]
}
framehash() { # the middle-ish frame, as a hash we can compare
  ffmpeg -hide_banner -loglevel error -ss 0.5 -i "$1" -frames:v 1 \
    -f framehash -hash md5 - 2>/dev/null | awk '/^0,/{print $NF}'
}

GENERATORS=(make-colorbars make-testcard make-signoff make-ident make-slate make-bug)

echo "CHANNEL Z0 — generator test"
echo "media root: ${Z0_MEDIA_ROOT}"
echo ""

# ── 1 · Arguments ─────────────────────────────────────────────────────────────
echo "  arguments"
for s in "${GENERATORS[@]}"; do
  out="$(bash "${DIR}/${s}.sh" --help 2>&1)"; rc=$?
  if (( rc == 0 )) && [[ "$out" == *"Usage:"* ]]; then
    ok "${s}.sh --help prints its usage"
  else
    bad "${s}.sh --help exited ${rc} without printing usage"
  fi
done

n=$(find "$Z0_MEDIA_ROOT" -type f 2>/dev/null | wc -l | tr -d ' ')
[[ "$n" == "0" ]] && ok "--help wrote nothing to the media root" \
                  || bad "--help wrote ${n} file(s) — it should render nothing"

gen make-slate.sh "HEADLINE" "SUBLINE" 30s; rc=$?
(( rc == 2 )) && ok "a non-numeric duration is refused up front (exit 2)" \
              || bad "expected exit 2 for a duration of '30s', got ${rc}"

gen make-colorbars.sh --minutes 5; rc=$?
(( rc != 0 )) && ok "an unknown flag is refused, not handed to ffmpeg (exit ${rc})" \
              || bad "an unknown flag was accepted"

# ── 2 · Text that used to break the filtergraph ───────────────────────────────
echo ""
echo "  text in a headline"
HOSTILE=(
  "SIGN-OFF: 00:00"
  "WE'LL BE BACK"
  "50% OFF, TODAY"
  'A BACK \ SLASH'
  "[STAND BY]; SOON"
)
# Two references for "the words never made it to the screen": a card with no
# headline, and a card with no headline and no subline. An apostrophe used to
# land on the second one — ffmpeg closed the quote early and dropped every
# drawtext after it — while the script still said "slate ready".
gen make-slate.sh " " "SUBLINE" 1 "no-head"
gen make-slate.sh " " " "       1 "no-text"
blank="$(framehash "${INTER}/no-head.mp4")"
empty="$(framehash "${INTER}/no-text.mp4")"

i=0
for text in "${HOSTILE[@]}"; do
  i=$(( i + 1 ))
  # The same line with every special character removed. If the punctuation is
  # being eaten somewhere between here and the screen, the two cards render
  # identically — which is exactly the bug this guards.
  plain="${text//[^A-Za-z0-9 -]/}"

  if ! gen make-slate.sh "$text" "SUBLINE" 1 "hostile-${i}"; then
    bad "slate refused \"${text}\" (exit $?)"; sed 's/^/        /' "$LOG" | tail -3; continue
  fi
  gen make-slate.sh "$plain" "SUBLINE" 1 "plain-${i}"

  a="$(framehash "${INTER}/hostile-${i}.mp4")"
  b="$(framehash "${INTER}/plain-${i}.mp4")"
  if [[ -z "$a" ]]; then
    bad "\"${text}\" produced an unreadable card"
  elif [[ "$a" == "$blank" || "$a" == "$empty" ]]; then
    bad "\"${text}\" never reached the screen — drawtext was dropped"
  elif [[ "$a" == "$b" ]]; then
    bad "\"${text}\" rendered identically to \"${plain}\" — the punctuation was eaten"
  else
    ok "\"${text}\" reaches the screen intact"
  fi
done

if gen make-ident.sh 1 "ALWAYS ON: 24/7"; then
  ok "ident accepts a tagline with a colon"
else
  bad "ident refused a tagline with a colon (exit $?)"
fi

# ── 3 · The cards themselves ──────────────────────────────────────────────────
echo ""
echo "  card conformance (1080p / 30, with audio)"
check_card() { # label file want_seconds
  local label="$1" f="$2" want="$3" w h r d
  if [[ ! -s "$f" ]]; then bad "${label}: nothing at ${f}"; return; fi
  w="$(vprobe "$f" width)"; h="$(vprobe "$f" height)"; r="$(vprobe "$f" r_frame_rate)"
  d="$(dur "$f")"
  [[ "$w" == "1920" && "$h" == "1080" && "$r" == "30/1" ]] \
    && ok "${label}: ${w}x${h} @ ${r}" \
    || bad "${label}: expected 1920x1080 @ 30/1, got ${w}x${h} @ ${r}"
  if awk -v d="$d" -v w="$want" 'BEGIN{ exit !(d > w-0.5 && d < w+0.5) }'; then
    ok "${label}: ${d}s, as asked (${want}s)"
  else
    bad "${label}: asked for ${want}s, got ${d}s"
  fi
  has_audio "$f" && ok "${label}: carries an audio track" \
                 || bad "${label}: no audio stream — ErsatzTV will splice badly"
}

gen make-slate.sh "PLEASE STAND BY" "WE'LL RETURN SHORTLY" 2 standby
check_card "slate"       "${INTER}/standby.mp4"  2
gen make-testcard.sh 2
check_card "test card"   "${INTER}/testcard.mp4" 2
gen make-signoff.sh 2 1
check_card "sign-off"    "${INTER}/signoff.mp4"  3
gen make-ident.sh 2 "IDENT TEST"
check_card "ident"       "${Z0_MEDIA_ROOT}/bumpers/z0-ident-ident-test.mp4" 2
gen make-colorbars.sh 1
check_card "colour bars" "${INTER}/colorbars-1m.mp4" 60

echo ""
echo "  the channel bug"
if gen make-bug.sh "${SCRATCH}/bug.png" && [[ -s "${SCRATCH}/bug.png" ]]; then
  pf="$(vprobe "${SCRATCH}/bug.png" pix_fmt)"
  [[ "$pf" == *a* ]] && ok "channel bug is a transparent PNG (${pf})" \
                     || bad "channel bug has no alpha channel (${pf}) — the watermark will be a box"
else
  bad "make-bug.sh produced no PNG"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────"
printf 'passed %d, failed %d\n' "$pass" "$fail"
if (( fail > 0 )); then
  echo ""
  echo "last generator output:"; sed 's/^/  /' "$LOG" | tail -20
fi
exit $(( fail > 0 ))
