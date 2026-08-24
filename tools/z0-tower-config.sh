#!/usr/bin/env bash
# Channel Z0 — configure the tower, and prove it took.
#
# bootstrap-node.sh used to finish the tower role by printing "now do these two
# things immediately" and trusting you to. These are those things, plus the one
# it never mentioned and which matters more than either.
#
#   1. rotate the admin password off the default
#   2. set the stream key the playout nodes will publish with
#   3. FORCE VIDEO PASSTHROUGH ON
#
# (3) is the whole reason a 1 GB free-tier box can carry a television channel.
# With passthrough off, Owncast software-encodes the incoming stream. On a micro
# shape that runs at about 0.93x realtime, so the public stream falls behind by
# roughly six seconds per minute, forever — it never catches up, because the
# uplink is capped at 1.0x and every second lost is lost. It does not look like
# an encoder problem. It looks like "the stream is a couple of minutes behind",
# then ten, and /api/status says online:true the entire time.
#
# Usage:
#   tools/z0-tower-config.sh --watch-domain watch.ch0.example --check
#   tools/z0-tower-config.sh --watch-domain watch.ch0.example \
#       --admin-pass "$NEW" --stream-key "$KEY"
#   tools/z0-tower-config.sh --watch-domain watch.ch0.example --dns-a 1.2.3.4
#
# Credentials come from the environment, never the command line where a shell
# history would keep them:
#   Z0_OWNCAST_ADMIN_USER / Z0_OWNCAST_ADMIN_PASS   current admin login
#   CF_API_TOKEN + CF_ZONE                          only for --dns-a
set -uo pipefail

DOMAIN=""; NEW_PASS=""; NEW_KEY=""; DNS_A=""; CHECK=0; DRY=0; LATENCY=""

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
[[ -t 1 ]] || { BOLD=""; RED=""; GRN=""; YEL=""; OFF=""; }
say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s   %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %swarn%s %s\n' "$YEL" "$OFF" "$*"; }
die()  { printf '  %sERR%s  %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }
step() { printf '\n%s── %s%s\n' "$BOLD" "$*" "$OFF"; }
usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch-domain) DOMAIN="$2"; shift 2 ;;
    --admin-pass)   NEW_PASS="$2"; shift 2 ;;
    --stream-key)   NEW_KEY="$2"; shift 2 ;;
    --latency)      LATENCY="$2"; shift 2 ;;
    --dns-a)        DNS_A="$2"; shift 2 ;;
    --check)        CHECK=1; shift ;;
    --dry-run)      DRY=1; shift ;;
    -h|--help)      usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done
[[ -n "$DOMAIN" ]] || usage 1
command -v curl   >/dev/null || die "curl not installed"
command -v python3 >/dev/null || die "python3 not installed (used to read Owncast's JSON)"

BASE="https://${DOMAIN}"
AU="${Z0_OWNCAST_ADMIN_USER:-admin}"
AP="${Z0_OWNCAST_ADMIN_PASS:-}"
[[ -n "$AP" ]] || die "set Z0_OWNCAST_ADMIN_PASS (the CURRENT admin password) in the environment"

api_get()  { curl -fsS -m 20 -u "${AU}:${AP}" "${BASE}$1"; }
api_post() { # $1 path, $2 json body
  if (( DRY )); then say "  would POST $1"; return 0; fi
  curl -fsS -m 25 -u "${AU}:${AP}" -H 'Content-Type: application/json' -X POST "${BASE}$1" -d "$2"
}

# ── read the current state ───────────────────────────────────────────────────
step "Reading ${DOMAIN}"
CONF="$(api_get /api/admin/serverconfig)" || die "cannot reach the admin API — wrong password, or the tower is down"
ok "admin API reachable"

read_state() {
  printf '%s' "$CONF" | python3 -c '
import json,sys
d=json.load(sys.stdin)
v=d.get("videoSettings",{})
vars_=v.get("videoQualityVariants",[]) or [{}]
first=vars_[0]
print("passthrough", bool(first.get("videoPassthrough")))
print("nvariants", len(vars_))
print("latency", v.get("latencyLevel"))
print("nkeys", len(d.get("streamKeys") or []))
print("defaultpass", str(d.get("adminPassword")=="abc123").lower())
'
}
eval "$(read_state | while read -r k v; do echo "ST_${k}=${v}"; done)"

say "  passthrough:  ${ST_passthrough}"
say "  variants:     ${ST_nvariants}"
say "  latencyLevel: ${ST_latency}"
say "  stream keys:  ${ST_nkeys}"

if (( CHECK )); then
  step "Audit"
  RC=0
  if [[ "$ST_passthrough" != "True" ]]; then
    warn "VIDEO PASSTHROUGH IS OFF — the tower is re-encoding, and on a small"
    warn "shape the public stream will fall behind about 6s per minute and never"
    warn "recover. /api/status will say online:true throughout."
    RC=1
  else
    ok "passthrough on — the tower is not transcoding"
  fi
  (( ST_nvariants > 1 )) && { warn "${ST_nvariants} quality variants — more than one means transcoding"; RC=1; }
  (( ST_nkeys == 0 ))    && { warn "no stream keys configured — nothing can publish"; RC=1; }
  exit $RC
fi

# ── apply ────────────────────────────────────────────────────────────────────
CHANGED=0

if [[ -n "$NEW_KEY" ]]; then
  step "Setting the stream key"
  BODY="$(python3 -c '
import json,sys
print(json.dumps({"value":[{"key":sys.argv[1],"comment":"channel-z0 uplink"}]}))' "$NEW_KEY")"
  api_post /api/admin/config/streamkeys "$BODY" >/dev/null && { ok "stream key set"; CHANGED=1; } \
    || die "could not set the stream key"
fi

step "Forcing single-variant passthrough"
PT='{"value":[{"name":"Source","videoPassthrough":true,"audioPassthrough":true,"videoBitrate":0,"audioBitrate":0,"cpuUsageLevel":3,"framerate":30}]}'
api_post /api/admin/config/video/streamoutputvariants "$PT" >/dev/null \
  && { ok "one Source variant, passthrough on"; CHANGED=1; } || die "could not set video variants"

if [[ -n "$LATENCY" ]]; then
  step "Latency level ${LATENCY}"
  api_post /api/admin/config/video/latencylevel "{\"value\":${LATENCY}}" >/dev/null \
    && ok "latency level set" || warn "could not set latency level"
fi

# The password goes LAST. Change it first and every call after it is
# unauthenticated with the credentials we are holding.
if [[ -n "$NEW_PASS" ]]; then
  step "Rotating the admin password"
  BODY="$(python3 -c 'import json,sys; print(json.dumps({"value":sys.argv[1]}))' "$NEW_PASS")"
  api_post /api/admin/config/adminpass "$BODY" >/dev/null && { ok "admin password rotated"; AP="$NEW_PASS"; CHANGED=1; } \
    || die "could not rotate the admin password"
fi

# ── read it back ─────────────────────────────────────────────────────────────
# The API answers success:true and the config reads back correctly whether or
# not anything actually changed, so confirm from a fresh fetch.
if (( ! DRY )); then
  step "Reading it back"
  CONF="$(api_get /api/admin/serverconfig)" || die "cannot re-read the config"
  eval "$(read_state | while read -r k v; do echo "ST_${k}=${v}"; done)"
  [[ "$ST_passthrough" == "True" ]] && ok "passthrough confirmed on" || die "passthrough did NOT take"
  (( ST_nvariants == 1 )) && ok "single variant confirmed" || warn "still ${ST_nvariants} variants"
fi

# ── DNS ──────────────────────────────────────────────────────────────────────
if [[ -n "$DNS_A" ]]; then
  step "Cloudflare A record → ${DNS_A}"
  if [[ -z "${CF_API_TOKEN:-}" || -z "${CF_ZONE:-}" ]]; then
    warn "CF_API_TOKEN and CF_ZONE are not set — skipping the DNS step."
    say  "    Create a token with Zone:DNS:Edit on the zone, then re-run with:"
    say  "      CF_API_TOKEN=… CF_ZONE=ripostelabs.xyz $0 --watch-domain ${DOMAIN} --dns-a ${DNS_A}"
  else
    ZID="$(curl -fsS -m 20 -H "Authorization: Bearer ${CF_API_TOKEN}" \
      "https://api.cloudflare.com/client/v4/zones?name=${CF_ZONE}" \
      | python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; print(r[0]["id"] if r else "")')"
    [[ -n "$ZID" ]] || die "no such Cloudflare zone: ${CF_ZONE}"
    # proxied MUST be false. The orange cloud cannot carry RTMP, and it must not
    # sit in front of a 24/7 HLS stream either.
    REC="$(python3 -c '
import json,sys
print(json.dumps({"type":"A","name":sys.argv[1],"content":sys.argv[2],"ttl":60,"proxied":False}))' "$DOMAIN" "$DNS_A")"
    EXIST="$(curl -fsS -m 20 -H "Authorization: Bearer ${CF_API_TOKEN}" \
      "https://api.cloudflare.com/client/v4/zones/${ZID}/dns_records?type=A&name=${DOMAIN}" \
      | python3 -c 'import json,sys; r=json.load(sys.stdin)["result"]; print(r[0]["id"] if r else "")')"
    if (( DRY )); then
      say "  would $([[ -n "$EXIST" ]] && echo update || echo create) ${DOMAIN} A ${DNS_A} (grey cloud)"
    elif [[ -n "$EXIST" ]]; then
      curl -fsS -m 20 -X PUT -H "Authorization: Bearer ${CF_API_TOKEN}" -H 'Content-Type: application/json' \
        "https://api.cloudflare.com/client/v4/zones/${ZID}/dns_records/${EXIST}" -d "$REC" >/dev/null \
        && ok "A record updated (DNS-only)" || die "could not update the A record"
    else
      curl -fsS -m 20 -X POST -H "Authorization: Bearer ${CF_API_TOKEN}" -H 'Content-Type: application/json' \
        "https://api.cloudflare.com/client/v4/zones/${ZID}/dns_records" -d "$REC" >/dev/null \
        && ok "A record created (DNS-only)" || die "could not create the A record"
    fi
    warn "Pi-hole negative-caches NXDOMAIN. If the name resolves publicly but not"
    warn "at home, restart pihole-FTL rather than re-creating the record."
  fi
fi

step "Done"
if (( CHANGED )); then
  say "  ${BOLD}The running transcode did not change.${OFF} Owncast only builds a new"
  say "  pipeline when a NEW RTMP session starts — the config reads back correct"
  say "  while the old ffmpeg keeps running untouched. Restart the uplink on the"
  say "  playout node to make this take effect:"
  say "    docker restart z0-uplink"
fi
