#!/usr/bin/env bash
# Channel Z0 — prove the cluster fails over, and that it never double-publishes.
#
# Redundancy you haven't tested isn't redundancy. This spins up N simulated
# playout nodes against a scratch cluster directory, kills the one that's on
# air, and asserts the two properties the design actually rests on:
#
#   SAFETY    never more than one node publishing, at any instant
#   LIVENESS  after the leader dies, a standby is on air within the lease TTL
#
# No tower, no ErsatzTV, no media — the nodes run a fake publisher through the
# Z0_UPLINK_CMD seam, so this is safe to run on a laptop.
#
# Usage:
#   tools/test-failover.sh              # 3 nodes, hard-kill + graceful handover
#   Z0_TEST_NODES=5 tools/test-failover.sh
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEADER="${DIR}/../playout/z0-leader.sh"
NODES="${Z0_TEST_NODES:-3}"

# Compressed timings so the whole run takes seconds, not minutes. The ratios
# are what matter and they match the defaults: TTL well above FENCE.
export Z0_LEASE_RENEW=1 Z0_LEASE_FENCE=3 Z0_LEASE_TTL=5
GRACE=$(( Z0_LEASE_TTL + 4 ))     # how long we allow for a takeover

CLUSTER="$(mktemp -d)"
export Z0_CLUSTER_DIR="$CLUSTER"
PUBDIR="${CLUSTER}/publishing"
LOG="${CLUSTER}/test.log"

PIDS_DIR="${CLUSTER}/pids"; mkdir -p "$PIDS_DIR"

# A stand-in for Smear's /api/live/status: one static JSON file the test
# rewrites, served over plain HTTP, so the live hold is exercised through the
# same curl the leader uses in production.
STUDIO_DIR="${CLUSTER}/studio"; mkdir -p "$STUDIO_DIR"
studio_says() { printf '%s\n' "$1" > "${STUDIO_DIR}/status"; }
studio_says '{"state": "idle"}'
STUDIO_PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
( python3 -m http.server "$STUDIO_PORT" --bind 127.0.0.1 --directory "$STUDIO_DIR" \
    >/dev/null 2>&1 & echo $! > "${CLUSTER}/studio.pid" )
STUDIO_PID=$(cat "${CLUSTER}/studio.pid")
export Z0_LIVE_HOLD_URL="http://127.0.0.1:${STUDIO_PORT}/status"
export Z0_LIVE_HOLD_MATCH="ingest.test"

cleanup() {
  [[ -n "${STUDIO_PID:-}" ]] && kill -KILL "$STUDIO_PID" 2>/dev/null
  for f in "$PIDS_DIR"/*; do
    [[ -f "$f" ]] || continue
    kill -KILL -- "-$(cat "$f")" 2>/dev/null
  done
  [[ -n "${SAMPLER_PID:-}" ]] && kill -KILL "$SAMPLER_PID" 2>/dev/null
  rm -rf "$CLUSTER"
}
trap cleanup EXIT

pass=0; fail=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; pass=$(( pass + 1 )); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$(( fail + 1 )); }

publishers()   { find "$PUBDIR" -type f 2>/dev/null | wc -l | tr -d ' '; }
publisher_id() { find "$PUBDIR" -type f 2>/dev/null -printf '%f\n' 2>/dev/null | head -1; }

start_node() { # id
  # Each node gets its own session so a "machine death" can take the supervisor
  # and its publisher together, the way a real power cut would.
  #
  # The subtlety: `$!` is the *setsid* process, which is not necessarily the
  # leader. The inner shell records its own PID and then execs, so the recorded
  # PID is the leader itself — and because setsid made it a session leader, that
  # PID is also its process-group id. Killing -PGID then takes the whole node.
  local id="$1" pidfile="${PIDS_DIR}/$1"
  # Launched inside a subshell that exits at once, so this shell never adopts it
  # as a job — otherwise killing a node prints a "Killed" line that reads like a
  # test failure when it's just job-control chatter.
  ( setsid bash -c "echo \$\$ > '${pidfile}'; exec env Z0_NODE_ID='${id}' \
      Z0_UPLINK_CMD='sleep 3600' bash '${LEADER}'" >>"$LOG" 2>&1 & )
  for _ in $(seq 1 50); do [[ -s "$pidfile" ]] && break; sleep 0.1; done
}

node_pid() { cat "${PIDS_DIR}/$1" 2>/dev/null; }
kill_node_hard() { kill -KILL -- "-$(node_pid "$1")" 2>/dev/null; }
kill_node_term() { kill -TERM "$(node_pid "$1")" 2>/dev/null; }

# A sampler running through the whole test, so a momentary double-publish
# between assertions still gets caught.
MAXSEEN="${CLUSTER}/maxseen"; echo 0 > "$MAXSEEN"
sampler() {
  while true; do
    local n; n=$(publishers)
    local m; m=$(cat "$MAXSEEN" 2>/dev/null || echo 0)
    (( n > m )) && echo "$n" > "$MAXSEEN"
    sleep 0.1
  done
}
SAMPLER_PIDFILE="${CLUSTER}/sampler.pid"
( sampler & echo $! > "$SAMPLER_PIDFILE" )
SAMPLER_PID=$(cat "$SAMPLER_PIDFILE")

echo "CHANNEL Z0 — failover test"
echo "nodes: ${NODES}   renew ${Z0_LEASE_RENEW}s / fence ${Z0_LEASE_FENCE}s / ttl ${Z0_LEASE_TTL}s"
echo "cluster: ${CLUSTER}"
echo ""

# ── 1 · Election ──────────────────────────────────────────────────────────────
for i in $(seq 1 "$NODES"); do start_node "node-${i}"; done
sleep $(( Z0_LEASE_RENEW * 3 ))

n=$(publishers)
[[ "$n" == "1" ]] && ok "exactly one node took the air (${n})" \
                  || bad "expected 1 publisher after election, got ${n}"
first="$(publisher_id)"
echo "       on air: ${first}"

# ── 2 · Hard failure of the leader ────────────────────────────────────────────
echo ""
echo "  killing ${first} (SIGKILL to its process group — simulated power cut)"
kill_node_hard "$first"

took=0
for _ in $(seq 1 $(( GRACE * 10 ))); do
  cur="$(publisher_id)"
  if [[ -n "$cur" && "$cur" != "$first" ]]; then break; fi
  sleep 0.1; took=$(( took + 1 ))
done
second="$(publisher_id)"
if [[ -n "$second" && "$second" != "$first" ]]; then
  ok "a standby took over in ~$(awk -v t="$took" 'BEGIN{printf "%.1f", t/10}')s (${second})"
else
  bad "no standby took over within ${GRACE}s (publisher now: '${second:-none}')"
fi

sleep 2
n=$(publishers)
[[ "$n" == "1" ]] && ok "still exactly one publisher after failover (${n})" \
                  || bad "expected 1 publisher after failover, got ${n}"

# ── 3 · Graceful handover ─────────────────────────────────────────────────────
# A clean stop should release the lease immediately rather than making the
# cluster wait out the full TTL — that's the difference between a planned
# reboot costing seconds and costing the better part of a minute.
echo ""
echo "  stopping ${second} gracefully (SIGTERM — a planned reboot)"
kill_node_term "$second"

took=0
for _ in $(seq 1 $(( GRACE * 10 ))); do
  cur="$(publisher_id)"
  if [[ -n "$cur" && "$cur" != "$second" ]]; then break; fi
  sleep 0.1; took=$(( took + 1 ))
done
third="$(publisher_id)"
handover=$(awk -v t="$took" 'BEGIN{printf "%.1f", t/10}')
if [[ -n "$third" && "$third" != "$second" ]]; then
  ok "graceful handover in ~${handover}s (${third})"
  awk -v h="$handover" -v ttl="$Z0_LEASE_TTL" 'BEGIN{ exit !(h < ttl) }' \
    && ok "handover beat the TTL (${handover}s < ${Z0_LEASE_TTL}s) — released, not timed out" \
    || bad "handover took ${handover}s, no faster than waiting out the TTL"
else
  bad "no node took over after graceful stop"
fi

# ── 4 · Live hold ─────────────────────────────────────────────────────────────
# A live show comes in through the studio on the same stream key. The moment
# the studio has a session aimed at our ingest, whoever is on air must get off
# it -- and keep the lease, so nobody else gets on -- then resume when it ends.
echo ""
echo "  studio opens a session pushing to our ingest"
studio_says '{"state": "waiting", "config": {"output": {"push_url": "rtmp://ingest.test:1935/live/k"}}}'
took=0
for _ in $(seq 1 $(( GRACE * 10 ))); do
  [[ "$(publishers)" == "0" ]] && break
  sleep 0.1; took=$(( took + 1 ))
done
yielded=$(awk -v t="$took" 'BEGIN{printf "%.1f", t/10}')
[[ "$(publishers)" == "0" ]] && ok "uplink stood down for the live show in ~${yielded}s" \
                            || bad "uplink still publishing $(publishers) during the live hold"
sleep $(( Z0_LEASE_RENEW * 3 ))
[[ "$(publishers)" == "0" ]] && ok "stayed off air while the session ran (nobody stole the lease)" \
                            || bad "a node came on air during the live hold"
grep -q '|hold|' "${CLUSTER}/nodes/${third}" 2>/dev/null \
  && ok "${third} reports 'hold' to --status" \
  || bad "${third} did not register the hold state"

echo "  studio session ends"
studio_says '{"state": "idle"}'
took=0
for _ in $(seq 1 $(( GRACE * 10 ))); do
  [[ "$(publishers)" == "1" ]] && break
  sleep 0.1; took=$(( took + 1 ))
done
resumed=$(awk -v t="$took" 'BEGIN{printf "%.1f", t/10}')
fourth="$(publisher_id)"
[[ "$(publishers)" == "1" ]] && ok "schedule resumed in ~${resumed}s (${fourth})" \
                            || bad "nobody resumed after the live show"
[[ "$fourth" == "$third" ]] && ok "the same node resumed — the lease was kept through the hold" \
                            || bad "a different node (${fourth}) took over; the lease was lost during the hold"

echo "  studio session pushing somewhere else is ignored"
studio_says '{"state": "running", "config": {"output": {"push_url": "rtmp://elsewhere.test/live/k"}}}'
sleep $(( Z0_LEASE_RENEW * 3 ))
[[ "$(publishers)" == "1" ]] && ok "a push to another destination does not hold the channel" \
                            || bad "the channel yielded to a session that was not aimed at it"
studio_says '{"state": "idle"}'

# ── 5 · The invariant ─────────────────────────────────────────────────────────
echo ""
maxseen=$(cat "$MAXSEEN")
[[ "$maxseen" -le 1 ]] && ok "SAFETY: never more than one publisher (max observed: ${maxseen})" \
                       || bad "SAFETY VIOLATED: ${maxseen} simultaneous publishers observed"

kill -KILL "$SAMPLER_PID" 2>/dev/null

echo ""
echo "──────────────────────────────────────────"
printf 'passed %d, failed %d\n' "$pass" "$fail"
if (( fail > 0 )); then
  echo ""
  echo "supervisor log:"; sed 's/^/  /' "$LOG" | tail -40
fi
exit $(( fail > 0 ))
