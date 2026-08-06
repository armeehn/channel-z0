#!/usr/bin/env bash
# Channel Z0 — stock the media library from the Internet Archive.
#
# Fills the acquired half of the schedule in docs/programming.md — Prelinger
# Theatre, the Cartoon Block, the themed feature nights — with public-domain
# material, straight into the folders ErsatzTV already watches.
#
# Every recipe filters on a public-domain licence mark. That is the whole point:
# archive.org hosts plenty that is *not* yours to air (its classic-commercials
# collection includes 2007 FedEx spots), so this tool only ever takes items the
# uploader has marked public domain. See docs/ad-standards.md.
#
# Usage:
#   tools/fetch-archive.sh --list                  # show the recipes, fetch nothing
#   tools/fetch-archive.sh --status                # what's on disk, per slot
#   tools/fetch-archive.sh --dry-run --all         # plan the whole library
#   tools/fetch-archive.sh prelinger --count 20    # fetch one slot
#   tools/fetch-archive.sh --all                   # fetch every slot
#
# It is resumable and idempotent: every success is appended to the manifest at
# $Z0_MEDIA_ROOT/.z0-archive/manifest.jsonl, and anything already listed there
# is skipped on the next run. Kill it whenever; run it again to continue.
#
# See docs/archive-fetch.md for the full operating manual.
set -euo pipefail

MEDIA_ROOT="${Z0_MEDIA_ROOT:-/media/channelz0}"
STATE_DIR="${MEDIA_ROOT}/.z0-archive"
MANIFEST="${STATE_DIR}/manifest.jsonl"
CACHE_DIR="${STATE_DIR}/candidates"

# Politeness + protecting the house uplink. The playout PC usually shares a
# residential line with the thing that is actually on air, so default to a
# gentle pause between items and let the operator cap the rate.
SLEEP_BETWEEN="${Z0_FETCH_SLEEP:-2}"
RATE_LIMIT="${Z0_RATE_LIMIT:-}"          # e.g. 2M — passed to curl --limit-rate
MAX_MB="${Z0_MAX_MB:-3000}"              # skip any single file larger than this
UA="channel-z0-fetch/1.0 (+https://github.com/armeehn/channel-z0)"

# ── The recipes ───────────────────────────────────────────────────────────────
# slot | destination (under MEDIA_ROOT) | min secs | max secs | default count | query
# Durations are what separate a filler PSA from a feature, so they are part of
# the recipe rather than an afterthought.
PD='licenseurl:(*publicdomain*)'
RECIPES=(
  "psas|psas|20|300|40|collection:(prelinger) AND mediatype:(movies) AND ${PD}"
  "prelinger|prelinger|300|2400|30|collection:(prelinger) AND mediatype:(movies) AND ${PD}"
  "cartoons|cartoons|60|1200|30|collection:(animationandcartoons) AND mediatype:(movies) AND ${PD}"
  "noir|movies/noir|2400|10800|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND (subject:(film noir) OR subject:(noir))"
  "scifi|movies/scifi|2400|10800|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND (subject:(science fiction) OR subject:(sci-fi) OR subject:(horror))"
  "docs|movies/docs|2400|10800|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND subject:(documentary)"
  "serials|movies/serials|600|3600|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND subject:(serial)"
  "classics|movies/classics|2400|10800|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND (subject:(comedy) OR subject:(drama) OR subject:(western))"
  "cult|movies/cult|2400|10800|10|collection:(feature_films) AND mediatype:(movies) AND ${PD} AND (subject:(exploitation) OR subject:(cult))"
)

# Which derivative to take, best first. The h.264 derivative is the web-sized
# one and is what you want; the "MPEG4" original is frequently the 700 MB
# preservation master of a twelve-minute short.
FORMAT_PREF=("h.264" "512Kb MPEG4" "MPEG4" "HiRes MPEG4" "Ogg Video")

usage() { sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1" >&2; exit 1; }; }
need curl; need jq; need ffprobe

recipe_field() { # slot, field index (1-based)
  local r; for r in "${RECIPES[@]}"; do
    [[ "${r%%|*}" == "$1" ]] && { echo "$r" | cut -d'|' -f"$2"; return 0; }
  done
  return 1
}

# archive.org reports file duration either as seconds ("768.54") or as a clock
# ("12:48", "1:02:33"). Normalise to whole seconds; empty for anything unparsable.
to_seconds() {
  local v="${1:-}"
  [[ -z "$v" || "$v" == "null" ]] && { echo ""; return; }
  if [[ "$v" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then printf '%.0f\n' "$v"; return; fi
  awk -F: '{ s=0; for(i=1;i<=NF;i++) s = s*60 + $i; printf "%d\n", s }' <<<"$v"
}

# Filesystem-safe, and close enough to Plex naming that ErsatzTV files features
# correctly. Trailing [identifier] is ignored by the scanner and keeps every
# file traceable back to its archive.org item.
safe_name() {
  sed -e 's#[/\\:*?"<>|]# #g' -e 's/[[:cntrl:]]//g' -e 's/  */ /g' -e 's/^ *//' -e 's/ *$//' <<<"$1" | cut -c1-150
}

# ── Candidate discovery ───────────────────────────────────────────────────────
# `sort[]=random` is the important part. The obvious paging — walk results in
# identifier order — hands you a library where every title starts with "A",
# because these collections are large and we only ever want the first few dozen.
# Random sort samples the whole corpus instead. It is stable between calls, so
# resuming a run sees the same order, but it is NOT a stable total order across
# pages: pages overlap by roughly a sixth, hence the dedupe below.
#
# advancedsearch has a hard 10,000-result window (page × rows), which is far
# past anything a station needs.
fetch_candidates() { # slot, query, wanted
  local slot="$1" query="$2" wanted="$3"
  local cache="${CACHE_DIR}/${slot}.jsonl"
  # Over-fetch: most candidates get rejected on duration, size, or a missing
  # derivative before one is worth downloading.
  local target=$(( wanted * 8 + 60 ))
  (( target > 3000 )) && target=3000

  if [[ -s "$cache" ]] && [[ $(wc -l < "$cache") -ge $target ]]; then
    echo "  candidates: $(wc -l < "$cache") cached" >&2
    cat "$cache"; return 0
  fi

  local page=1 rows=300 got=0 tmp
  tmp="$(mktemp)"
  while (( page <= 33 )); do
    local resp n
    resp=$(curl -sS --max-time 90 -A "$UA" -G 'https://archive.org/advancedsearch.php' \
      --data-urlencode "q=${query}" \
      --data-urlencode 'fl[]=identifier' --data-urlencode 'fl[]=title' \
      --data-urlencode 'fl[]=year' --data-urlencode 'fl[]=licenseurl' \
      --data-urlencode 'sort[]=random' \
      --data-urlencode "rows=${rows}" --data-urlencode "page=${page}" \
      --data-urlencode 'output=json' 2>/dev/null) || break
    jq -e '.response.docs' >/dev/null 2>&1 <<<"$resp" \
      || { echo "  search failed on page ${page}" >&2; break; }
    n=$(jq -r '.response.docs|length' <<<"$resp")
    (( n == 0 )) && break
    jq -c '.response.docs[]' <<<"$resp" >> "$tmp"
    got=$(jq -s '[.[].identifier]|unique|length' "$tmp")
    (( got >= target )) && break
    (( n < rows )) && break
    page=$(( page + 1 ))
    sleep 1
  done

  # Dedupe preserving first-seen order — the source order is already random, so
  # keeping it gives a varied library and a fixed, resumable sequence on disk.
  mkdir -p "$CACHE_DIR"
  jq -sc 'reduce .[] as $x ({seen:{}, out:[]};
            if .seen[$x.identifier] then . else .seen[$x.identifier]=true | .out += [$x] end)
          | .out[]' "$tmp" > "$cache"
  rm -f "$tmp"
  echo "  candidates: $(wc -l < "$cache") found" >&2
  cat "$cache"
}

# ── Per-item fetch ────────────────────────────────────────────────────────────
already_have() { grep -Fq "\"identifier\":\"$1\"" "$MANIFEST" 2>/dev/null; }

log_manifest() { # json line
  mkdir -p "$STATE_DIR"; printf '%s\n' "$1" >> "$MANIFEST"
}

fetch_item() { # slot, dest_abs, min, max, identifier, title, year, licenseurl
  local slot="$1" dest="$2" min="$3" max="$4" id="$5" title="$6" year="$7" lic="$8"

  local meta
  meta=$(curl -sS --max-time 60 -A "$UA" "https://archive.org/metadata/${id}" 2>/dev/null) || return 1
  jq -e '.files' >/dev/null 2>&1 <<<"$meta" || return 1

  # Pick the best available derivative.
  local fmt name size len=""
  for fmt in "${FORMAT_PREF[@]}"; do
    name=$(jq -r --arg f "$fmt" 'first(.files[] | select(.format==$f) | .name) // empty' <<<"$meta")
    [[ -n "$name" ]] || continue
    size=$(jq -r --arg n "$name" 'first(.files[] | select(.name==$n) | .size) // "0"' <<<"$meta")
    len=$(jq -r --arg n "$name" 'first(.files[] | select(.name==$n) | .length) // empty' <<<"$meta")
    break
  done
  [[ -n "${name:-}" ]] || { echo "    skip ${id}: no usable video derivative"; return 1; }

  local secs; secs=$(to_seconds "$len")
  if [[ -n "$secs" ]]; then
    (( secs < min )) && { echo "    skip ${id}: ${secs}s shorter than ${min}s"; return 1; }
    (( secs > max )) && { echo "    skip ${id}: ${secs}s longer than ${max}s"; return 1; }
  fi

  local mb=$(( size / 1048576 ))
  (( mb > MAX_MB )) && { echo "    skip ${id}: ${mb}MB over ${MAX_MB}MB cap"; return 1; }

  local ext="${name##*.}"
  local base; base=$(safe_name "${title}${year:+ ($year)} [${id}]")
  local out="${dest}/${base}.${ext}"

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '    would fetch %-9s %6sMB %5ss  %s\n' "$fmt" "$mb" "${secs:-?}" "$base"
    return 0
  fi

  mkdir -p "$dest"
  local enc; enc=$(jq -rn --arg s "$name" '$s|@uri')
  local url="https://archive.org/download/${id}/${enc}"
  local part="${out}.part"

  echo "    fetch ${base} (${mb}MB)"
  # -C - resumes a half-finished .part from a previous run or a killed session.
  if ! curl -fsSL --max-time 7200 -A "$UA" ${RATE_LIMIT:+--limit-rate "$RATE_LIMIT"} \
       -C - -o "$part" "$url"; then
    echo "    FAILED download ${id}" >&2
    log_manifest "$(jq -nc --arg s "$slot" --arg i "$id" --arg st "failed-download" '{slot:$s,identifier:$i,status:$st}')"
    return 1
  fi

  # Prove it plays before it is allowed near the schedule. A file that ffprobe
  # can't read is a black hole in the broadcast day.
  local probed
  probed=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$part" 2>/dev/null || true)
  if [[ -z "$probed" || "$probed" == "N/A" ]]; then
    echo "    FAILED probe ${id} — discarding" >&2
    rm -f "$part"
    log_manifest "$(jq -nc --arg s "$slot" --arg i "$id" --arg st "failed-probe" '{slot:$s,identifier:$i,status:$st}')"
    return 1
  fi

  mv -f "$part" "$out"
  log_manifest "$(jq -nc \
    --arg s "$slot" --arg i "$id" --arg t "$title" --arg y "$year" \
    --arg f "$out" --arg fmt "$fmt" --arg l "$lic" \
    --argjson b "$size" --argjson d "$(printf '%.0f' "$probed")" \
    '{slot:$s,identifier:$i,title:$t,year:$y,file:$f,format:$fmt,bytes:$b,duration:$d,licenseurl:$l,status:"ok"}')"
  return 0
}

run_slot() { # slot
  local slot="$1"
  local dest_rel min max defcount query
  dest_rel=$(recipe_field "$slot" 2) || { echo "unknown slot: $slot (try --list)" >&2; return 1; }
  min=$(recipe_field "$slot" 3); max=$(recipe_field "$slot" 4)
  defcount=$(recipe_field "$slot" 5)
  query=$(for r in "${RECIPES[@]}"; do [[ "${r%%|*}" == "$slot" ]] && cut -d'|' -f6- <<<"$r"; done)
  local want="${COUNT:-$defcount}"
  local dest="${MEDIA_ROOT}/${dest_rel}"

  echo ""
  echo "── ${slot} → ${dest_rel}/  (want ${want}, ${min}-${max}s)"

  local got=0 tried=0 line id title year lic
  while IFS= read -r line; do
    (( got >= want )) && break
    (( tried++ ))
    id=$(jq -r '.identifier' <<<"$line")
    title=$(jq -r '.title // .identifier' <<<"$line")
    year=$(jq -r '.year // ""' <<<"$line")
    lic=$(jq -r '.licenseurl // ""' <<<"$line")
    already_have "$id" && continue
    if fetch_item "$slot" "$dest" "$min" "$max" "$id" "$title" "$year" "$lic"; then
      (( got++ ))
      [[ "${DRY_RUN:-0}" == "1" ]] || sleep "$SLEEP_BETWEEN"
    fi
  done < <(fetch_candidates "$slot" "$query" "$want")

  echo "  ${slot}: ${got}/${want} acquired (${tried} candidates considered)"
  (( got < want )) && echo "  note: pool exhausted for '${slot}' — widen the query or lower --count" >&2
  return 0
}

cmd_list() {
  printf '%-10s %-16s %-14s %-6s %s\n' SLOT DESTINATION DURATION COUNT QUERY
  local r
  for r in "${RECIPES[@]}"; do
    printf '%-10s %-16s %-14s %-6s %s\n' \
      "$(cut -d'|' -f1 <<<"$r")" "$(cut -d'|' -f2 <<<"$r")" \
      "$(cut -d'|' -f3 <<<"$r")-$(cut -d'|' -f4 <<<"$r")s" \
      "$(cut -d'|' -f5 <<<"$r")" "$(cut -d'|' -f6- <<<"$r" | cut -c1-60)…"
  done
}

cmd_status() {
  echo "media root: ${MEDIA_ROOT}"
  if [[ -s "$MANIFEST" ]]; then
    echo "manifest:   ${MANIFEST} ($(wc -l < "$MANIFEST") entries)"
  else
    echo "manifest:   none yet — nothing fetched"
  fi
  echo ""
  printf '%-10s %-16s %6s %6s %10s\n' SLOT DESTINATION OK FAILED HOURS
  local r slot dest ok failed secs
  for r in "${RECIPES[@]}"; do
    slot=$(cut -d'|' -f1 <<<"$r"); dest=$(cut -d'|' -f2 <<<"$r")
    ok=0; failed=0; secs=0
    if [[ -s "$MANIFEST" ]]; then
      ok=$(jq -r --arg s "$slot" 'select(.slot==$s and .status=="ok")|.identifier' "$MANIFEST" 2>/dev/null | wc -l)
      failed=$(jq -r --arg s "$slot" 'select(.slot==$s and (.status|startswith("failed")))|.identifier' "$MANIFEST" 2>/dev/null | wc -l)
      secs=$(jq -r --arg s "$slot" 'select(.slot==$s and .status=="ok")|.duration' "$MANIFEST" 2>/dev/null | awk '{n+=$1} END{print n+0}')
    fi
    printf '%-10s %-16s %6s %6s %10s\n' "$slot" "$dest" "$ok" "$failed" "$(awk -v s="$secs" 'BEGIN{printf "%.1f", s/3600}')"
  done
  echo ""
  echo "resume with: $0 --all"
}

# ── Arguments ─────────────────────────────────────────────────────────────────
SLOTS=(); DRY_RUN=0; COUNT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)    cmd_list; exit 0 ;;
    --status)  cmd_status; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --all)     for r in "${RECIPES[@]}"; do SLOTS+=("${r%%|*}"); done; shift ;;
    --count)   COUNT="$2"; shift 2 ;;
    -h|--help) usage 0 ;;
    -*)        echo "unknown option: $1" >&2; usage 1 ;;
    *)         SLOTS+=("$1"); shift ;;
  esac
done
export DRY_RUN COUNT

[[ ${#SLOTS[@]} -eq 0 ]] && usage 1

mkdir -p "$STATE_DIR" "$CACHE_DIR"

echo "CHANNEL Z0 — archive intake"
echo "media root: ${MEDIA_ROOT}${RATE_LIMIT:+  (rate-limited to ${RATE_LIMIT})}"
[[ "$DRY_RUN" == "1" ]] && echo "DRY RUN — nothing will be downloaded"

for s in "${SLOTS[@]}"; do run_slot "$s" || true; done

echo ""
echo "── done. inspect with: $0 --status"
cat <<'NOTE'

Two of these destinations are new folders the build guide doesn't create:
  cartoons/    → add as an ErsatzTV "Other Videos" library, collection `Cartoons`
  prelinger/   → add as an ErsatzTV "Other Videos" library, collection `Prelinger`
The movies/* subfolders sit inside the existing movies library; make each one a
collection (`Features · Noir`, `· SciFi`, …) as described in docs/programming.md.
NOTE
