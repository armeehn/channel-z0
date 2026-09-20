#!/usr/bin/env bash
# Channel Z0 — the uplink supervisor. Decides which playout node is on air.
#
# The station's core rule is that exactly ONE stream reaches the tower. Two
# nodes publishing the same stream key doesn't give you redundancy, it gives
# you a corrupted channel — Owncast sees interleaved keyframes from two
# unrelated encodes. So a standby node cannot simply "also run the uplink".
#
# This is the thing that makes standby nodes safe: a lease over shared storage.
# One node holds it and publishes; the others watch, and take over only when
# the holder has demonstrably stopped.
#
# Usage (normally run by playout/compose.yml, not by hand):
#   Z0_NODE_ID=playout-a playout/z0-leader.sh
#   playout/z0-leader.sh --status        # who's on air right now
#   playout/z0-leader.sh --release       # hand off from this node, then exit
#
# See docs/clustering.md for the topology and the failover runbook.
set -uo pipefail

CLUSTER_DIR="${Z0_CLUSTER_DIR:-${Z0_MEDIA_ROOT:-/media/channelz0}/.z0-cluster}"

# Minimal containers often ship without `hostname`, and this runs inside one.
host_name() {
  hostname -s 2>/dev/null || hostname 2>/dev/null \
    || cat /etc/hostname 2>/dev/null || echo "${HOSTNAME:-unknown}"
}
NODE_ID="${Z0_NODE_ID:-$(host_name)}"
CHANNEL_URL="${Z0_CHANNEL_URL:-http://127.0.0.1:8409/iptv/channel/1.ts}"
# Health probes read the segmenter playlist, not the .ts. A .ts request makes
# ErsatzTV spawn a wrapper ffmpeg for that one client and takes ~5 s to answer;
# at a 5 s tick that was 2,841 "Starting ts stream" a day (2026-09-18), each
# ending in Broken pipe. The playlist's newest segment decodes in ~0.1 s and
# proves the same thing: ErsatzTV is emitting a decodable stream.
HEALTH_URL="${Z0_HEALTH_URL:-${CHANNEL_URL%.ts}.m3u8?mode=segmenter}"

NODE_ROLE="${Z0_NODE_ROLE:-playout}"

LOCK="${CLUSTER_DIR}/uplink.lock"
BEAT="${LOCK}/beat"
HOLDER="${LOCK}/holder"
PUBDIR="${CLUSTER_DIR}/publishing"
NODEDIR="${CLUSTER_DIR}/nodes"

# Each node stamps a file every tick. It's how `--status` can show the whole
# cluster from any machine, and how you notice a standby quietly died months
# ago and you've been running without redundancy since.
#
# Fields are pipe-separated, not tab-separated: tab counts as IFS *whitespace*,
# so `read` collapses runs of them and one empty field silently shifts every
# column after it.
register() { # state
  mkdir -p "$NODEDIR" 2>/dev/null
  printf '%s|%s|%s|%s\n' "$NODE_ROLE" "$1" "$(host_name)" "$(date -u +%FT%TZ)" \
    > "${NODEDIR}/${NODE_ID}" 2>/dev/null
}

# ── Timing ────────────────────────────────────────────────────────────────────
# The safety argument, which is the only part of this file that really matters:
#
#   RENEW  the leader touches the heartbeat this often
#   FENCE  if the leader cannot renew for this long, it kills its own uplink
#   TTL    a standby steals the lease after the heartbeat is this stale
#   HEALTH_EVERY  the leader ffprobes its own channel this often
#
# TTL > FENCE by a wide margin, so the old leader has stopped publishing before
# the new one starts. With the defaults the leader is off air by T+12s and the
# standby comes up at T+20s — an 8s gap where the channel is down, which is the
# correct trade. Dead air for eight seconds beats two stations at once.
#
# HEALTH_EVERY is not part of that argument. Every probe opens a channel
# session that ErsatzTV logs as "Starting ts stream" and closes as "Broken
# pipe"; probing on every RENEW tick wrote 5,000+ such lines a day and buried
# the real ones. A probe that fails is repeated every tick, so the time from
# first failure to standing down is still FENCE. Standbys probe every tick.
RENEW="${Z0_LEASE_RENEW:-5}"
FENCE="${Z0_LEASE_FENCE:-12}"
TTL="${Z0_LEASE_TTL:-20}"
HEALTH_EVERY="${Z0_HEALTH_EVERY:-30}"

# Test seam: the failover harness swaps in a fake publisher so the invariant can
# be checked without a tower. Defaults to the real relay.
UPLINK_CMD="${Z0_UPLINK_CMD:-}"

# ── Tower watchdog ────────────────────────────────────────────────────────────
# ffmpeg only exits when a write fails. When the tower half-closes the RTMP
# session (Owncast logs "Inbound stream disconnected" but leaves the socket
# open), every write still succeeds into a black hole: the socket sits in
# CLOSE-WAIT, the process lives, and the channel is dark until somebody
# restarts the container. 2026-09-14: two such outages of 12 and 17 minutes.
# So ask the tower itself whether it is receiving, and restart the uplink
# when it has said "no" for longer than a normal reconnect takes (~15s).
TOWER_STATUS_URL="${Z0_TOWER_STATUS_URL:-https://${Z0_WATCH_DOMAIN:-}/api/status}"
# RTMP cannot cross a CDN proxy, so once the watch host sits behind one the
# push goes to a DNS-only name for the same box (docs/scaling.tex, tier 2).
INGEST_DOMAIN="${Z0_INGEST_DOMAIN:-${Z0_WATCH_DOMAIN:-}}"
OFFLINE_GRACE="${Z0_OFFLINE_GRACE:-45}"

# ── Live hold ─────────────────────────────────────────────────────────────────
# A live show reaches the tower through Smear (the FFglitch studio), which
# pushes to the same stream key. Owncast takes one publisher, so while Smear
# has a session aimed at our ingest this node must be off the air, and it must
# come back the moment that session ends. Smear's own status is the signal:
# starting a session IS the hand-off, and there is nothing to clear afterwards.
#
# Unreachable Smear counts as no hold — the schedule keeps airing. Being wrong
# that way costs one refused RTMP connect on Smear's side; being wrong the
# other way is dead air until somebody notices.
LIVE_HOLD_URL="${Z0_LIVE_HOLD_URL:-}"
LIVE_HOLD_MATCH="${Z0_LIVE_HOLD_MATCH:-${INGEST_DOMAIN}}"

log() { printf '%s z0-leader[%s] %s\n' "$(date -u +%H:%M:%S)" "$NODE_ID" "$*" >&2; }

# ── Health ────────────────────────────────────────────────────────────────────
# A node that can't actually produce a channel must never hold the lease, or
# it will win the election and air silence. ffprobe rather than an HTTP check:
# it proves ErsatzTV is emitting a decodable stream, not merely answering.
health_ok() {
  [[ -n "$UPLINK_CMD" ]] && return 0        # test mode: no ErsatzTV to probe
  timeout 12 ffprobe -v error -rw_timeout 8000000 \
    -select_streams v:0 -show_entries stream=codec_type \
    -of csv=p=0 "$HEALTH_URL" 2>/dev/null | grep -q video
}

# Unreachable tower counts as online: a dead API is not evidence the stream
# is dark, and churning the uplink on it would only add reconnects.
tower_online() {
  [[ -n "$UPLINK_CMD" ]] && return 0        # test mode: no tower to ask
  local body
  body=$(curl -fsS -m 8 "$TOWER_STATUS_URL" 2>/dev/null) || return 0
  grep -q '"online": *true' <<<"$body"
}

# A session that is up (waiting for OBS, or running) and whose push_url names
# our ingest. Any other session on the studio -- an HLS-only experiment, a push
# somewhere else -- is not our business.
live_hold() {
  [[ -z "$LIVE_HOLD_URL" ]] && return 1
  local body
  body=$(curl -fsS -m 5 "$LIVE_HOLD_URL" 2>/dev/null) || return 1
  grep -qE '"state": *"(waiting|running)"' <<<"$body" || return 1
  [[ -z "$LIVE_HOLD_MATCH" ]] && return 0
  grep -q "\"push_url\": *\"[^\"]*${LIVE_HOLD_MATCH}" <<<"$body"
}

# ── The lease ─────────────────────────────────────────────────────────────────
# mkdir is atomic and fails if the target exists — that's the acquisition. mv is
# atomic and only one racer can rename a given directory — that's the steal.
# Between them there is no window where two nodes believe they hold the lease.

lock_holder() { cat "$HOLDER" 2>/dev/null || echo ""; }

# Liveness without trusting clocks. Comparing a heartbeat mtime against the
# local clock breaks the moment two nodes disagree about the time, which on a
# homelab is whenever NTP hiccups. Instead each observer watches for the beat to
# *change*, and times that with its own monotonic-enough elapsed seconds. Skew
# between nodes becomes irrelevant.
last_beat=""; last_change=0
beat_is_stale() {
  local now beat
  now=$(date +%s)
  beat=$(cat "$BEAT" 2>/dev/null || echo "missing")
  if [[ "$beat" != "$last_beat" ]]; then
    last_beat="$beat"; last_change="$now"; return 1
  fi
  (( now - last_change >= TTL ))
}

try_acquire() {
  if mkdir "$LOCK" 2>/dev/null; then
    printf '%s\n' "$NODE_ID" > "$HOLDER"
    date +%s%N > "$BEAT"
    log "acquired the lease — this node is on air"
    return 0
  fi
  [[ "$(lock_holder)" == "$NODE_ID" ]] && return 0

  if beat_is_stale; then
    # Steal. The rename is the arbiter: if two standbys try at once, exactly one
    # succeeds and the loser sees ENOENT and backs off to try again next tick.
    local dead="${LOCK}.dead.${NODE_ID}.$(date +%s)"
    if mv "$LOCK" "$dead" 2>/dev/null; then
      local dead_holder; dead_holder=$(cat "${dead}/holder" 2>/dev/null)
      log "lease was stale (holder '${dead_holder}') — taking over"
      # A node that died hard never cleaned up its publishing marker. It has
      # been fenced by now (TTL > FENCE), so clearing it here is safe — and
      # without this, --status would report two publishers forever.
      [[ -n "$dead_holder" ]] && rm -f "${PUBDIR}/${dead_holder}" 2>/dev/null
      rm -rf "$dead"
      last_beat=""; last_change=0
      mkdir "$LOCK" 2>/dev/null || return 1
      printf '%s\n' "$NODE_ID" > "$HOLDER"
      date +%s%N > "$BEAT"
      return 0
    fi
  fi
  return 1
}

renew() {
  [[ "$(lock_holder)" == "$NODE_ID" ]] || return 1
  date +%s%N > "$BEAT" 2>/dev/null || return 1
  return 0
}

release() {
  if [[ "$(lock_holder)" == "$NODE_ID" ]]; then
    rm -rf "$LOCK" 2>/dev/null && log "released the lease"
  fi
  rm -f "${PUBDIR}/${NODE_ID}" 2>/dev/null
}

# ── The uplink child ──────────────────────────────────────────────────────────
UPLINK_PID=""
uplink_since=0
offline_since=0

start_uplink() {
  [[ -n "$UPLINK_PID" ]] && kill -0 "$UPLINK_PID" 2>/dev/null && return 0
  mkdir -p "$PUBDIR"
  # The marker is how `--status` and tools/test-failover.sh observe who is
  # actually publishing, as opposed to who merely thinks they hold the lease.
  printf '%s\n' "$(date -u +%FT%TZ)" > "${PUBDIR}/${NODE_ID}"
  if [[ -n "$UPLINK_CMD" ]]; then
    bash -c "$UPLINK_CMD" &
  else
    ffmpeg -hide_banner -loglevel warning \
      -i "$CHANNEL_URL" -c copy \
      -f flv "rtmp://${INGEST_DOMAIN}:1935/live/${Z0_STREAM_KEY}" &
  fi
  UPLINK_PID=$!
  uplink_since=$(date +%s); offline_since=0
  log "uplink started (pid ${UPLINK_PID})"
}

stop_uplink() { # reason
  if [[ -n "$UPLINK_PID" ]] && kill -0 "$UPLINK_PID" 2>/dev/null; then
    log "stopping uplink: ${1:-requested}"
    kill -TERM "$UPLINK_PID" 2>/dev/null
    # Don't wait politely forever — the whole safety argument depends on this
    # process being off the air before the fencing deadline.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$UPLINK_PID" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL "$UPLINK_PID" 2>/dev/null
  fi
  wait "$UPLINK_PID" 2>/dev/null
  UPLINK_PID=""
  rm -f "${PUBDIR}/${NODE_ID}" 2>/dev/null
}

# ── Subcommands ───────────────────────────────────────────────────────────────
case "${1:-}" in
  --status)
    echo "cluster dir: ${CLUSTER_DIR}"
    if [[ -d "$LOCK" ]]; then
      echo "lease holder: $(lock_holder)"
    else
      echo "lease holder: (none — no node is on air)"
    fi
    if [[ -d "$PUBDIR" ]] && compgen -G "${PUBDIR}/*" >/dev/null; then
      echo "publishing:"
      for f in "${PUBDIR}"/*; do echo "  $(basename "$f")  since $(cat "$f")"; done
      n=$(find "$PUBDIR" -type f | wc -l)
      (( n > 1 )) && echo "  ** ${n} PUBLISHERS — the tower is receiving two streams **" >&2
    else
      echo "publishing: nobody"
    fi
    echo ""
    if [[ -d "$NODEDIR" ]] && compgen -G "${NODEDIR}/*" >/dev/null; then
      printf '%-16s %-9s %-9s %-22s %s\n' NODE ROLE STATE LAST-SEEN HOST
      for f in "${NODEDIR}"/*; do
        IFS='|' read -r role state host seen < "$f"
        age=$(( $(date +%s) - $(stat -c %Y "$f" 2>/dev/null || echo 0) ))
        (( age > TTL * 3 )) && state="stale(${age}s)"
        printf '%-16s %-9s %-9s %-22s %s\n' "$(basename "$f")" "$role" "$state" "$seen" "$host"
      done
    else
      echo "nodes: none registered yet"
    fi
    exit 0 ;;
  --release) release; exit 0 ;;
  -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

if [[ -z "$UPLINK_CMD" ]]; then
  : "${Z0_WATCH_DOMAIN:?set Z0_WATCH_DOMAIN}"; : "${Z0_STREAM_KEY:?set Z0_STREAM_KEY}"
fi

mkdir -p "$CLUSTER_DIR" "$PUBDIR" || { echo "cannot write cluster dir: $CLUSTER_DIR" >&2; exit 1; }

# A clean shutdown is a clean handover: drop the uplink, drop the lease, and a
# standby picks it up on its next tick instead of waiting out the full TTL.
shutting_down=0
on_term() { shutting_down=1; log "shutting down"; stop_uplink "shutdown"; release; exit 0; }
trap on_term TERM INT

log "watching (cluster=${CLUSTER_DIR} renew=${RENEW}s fence=${FENCE}s ttl=${TTL}s health=${HEALTH_EVERY}s)"
[[ -n "$LIVE_HOLD_URL" ]] && log "live hold: yielding to ${LIVE_HOLD_URL} while it pushes to '${LIVE_HOLD_MATCH:-anywhere}'"

leader=0
last_renew=$(date +%s)
unhealthy_since=0
last_probe=0
held=0

while (( ! shutting_down )); do
  now=$(date +%s)

  if (( leader )); then
    if renew; then
      last_renew="$now"
    elif (( now - last_renew >= FENCE )); then
      # Either the shared storage went away or someone else holds the lease.
      # Either way this node must get off the air before TTL elapses.
      stop_uplink "cannot renew lease (fencing)"
      leader=0
      log "demoted — lost the lease"
    fi

    if (( leader )) && live_hold; then
      # Keep renewing the lease (done above) so no standby takes it and starts
      # publishing into a tower that is busy; just get, and stay, off the air.
      if (( ! held )); then
        held=1; log "live show incoming (${LIVE_HOLD_URL}) — standing by off air"
      fi
      [[ -n "$UPLINK_PID" ]] && stop_uplink "live show hold"
      register "hold"
      sleep "$RENEW"
      continue
    elif (( held )); then
      held=0; (( leader )) && log "live show over — resuming the schedule"
    fi

    if (( leader )); then
      # Probe on the HEALTH_EVERY cadence while healthy, every tick once a probe
      # has failed, so the FENCE clock below runs at RENEW resolution.
      if (( unhealthy_since > 0 || now - last_probe >= HEALTH_EVERY )); then
        last_probe="$now"
        if health_ok; then
          unhealthy_since=0
        else
          (( unhealthy_since == 0 )) && unhealthy_since="$now"
        fi
      fi

      if (( unhealthy_since == 0 )); then
        start_uplink
      elif (( now - unhealthy_since >= FENCE )); then
        log "channel unhealthy for $(( now - unhealthy_since ))s — standing down so a standby can take it"
        stop_uplink "unhealthy"
        release
        leader=0
        unhealthy_since=0
      fi
      # A running uplink the tower is not receiving is a hung uplink. Give a
      # fresh one OFFLINE_GRACE to connect before believing the tower.
      if [[ -n "$UPLINK_PID" ]] && (( now - uplink_since >= OFFLINE_GRACE )); then
        if tower_online; then
          offline_since=0
        else
          (( offline_since == 0 )) && offline_since="$now"
          if (( now - offline_since >= OFFLINE_GRACE )); then
            log "tower reports offline for $(( now - offline_since ))s with uplink pid ${UPLINK_PID} alive — restarting it"
            stop_uplink "tower offline"
          fi
        fi
      fi

      # The uplink can also just die (tower restart, network blip). Let the next
      # tick restart it; that's the same reconnect-forever behaviour as before.
      if [[ -n "$UPLINK_PID" ]] && ! kill -0 "$UPLINK_PID" 2>/dev/null; then
        log "uplink exited; will restart"
        UPLINK_PID=""; rm -f "${PUBDIR}/${NODE_ID}" 2>/dev/null
      fi
    fi
  else
    # Only healthy nodes stand for election, and nobody does during a live hold:
    # winning it would only mean publishing into a busy tower.
    if ! live_hold && health_ok && try_acquire; then
      leader=1; last_renew=$(date +%s); unhealthy_since=0; last_probe="$last_renew"
      start_uplink
    fi
  fi

  # Registered at the end of the tick, once this node's state for this round is
  # settled — registering first would advertise last tick's state.
  register "$( (( leader )) && echo leader || echo standby )"
  sleep "$RENEW"
done
