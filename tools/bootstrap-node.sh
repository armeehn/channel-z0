#!/usr/bin/env bash
# Channel Z0 — stand up a station node from a bare machine.
#
# One script, three kinds of machine. Run it on a fresh box, answer nothing if
# you passed flags, and the node comes up ready:
#
#   playout   ErsatzTV + the uplink supervisor. The machine that makes the
#             channel. Run it on more than one box for failover.
#   tower     Owncast + Caddy on the VPS. The thing the audience talks to.
#   worker    No channel, no uplink — just the tools, for farming out the
#             batch jobs (fetch-archive, make-proxies, normalize-ad).
#
# Usage:
#   tools/bootstrap-node.sh --check                     # inspect, change nothing
#   tools/bootstrap-node.sh --role playout --node-id playout-a \
#       --watch-domain watch.ch0.example --stream-key "$KEY" \
#       --media /mnt/z0 --yes
#   tools/bootstrap-node.sh --role tower --site-domain ch0.example --yes
#
# Adding a second playout node is the same command with a different --node-id,
# pointed at the same shared --media. See docs/clustering.md.
#
# It is idempotent: run it again after changing a flag and it reconciles.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${DIR}/.." && pwd)"

ROLE=""; NODE_ID=""; MEDIA=""; CLUSTER=""; WATCH_DOMAIN=""; SITE_DOMAIN=""
STREAM_KEY=""; TAG=""; NFS=""; ASSUME_YES=0; DRY=0; CHECK_ONLY=0; INSTALL_DOCKER=0

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role)           ROLE="$2"; shift 2 ;;
    --node-id)        NODE_ID="$2"; shift 2 ;;
    --media)          MEDIA="$2"; shift 2 ;;
    --cluster)        CLUSTER="$2"; shift 2 ;;
    --watch-domain)   WATCH_DOMAIN="$2"; shift 2 ;;
    --site-domain)    SITE_DOMAIN="$2"; shift 2 ;;
    --stream-key)     STREAM_KEY="$2"; shift 2 ;;
    --tag)            TAG="$2"; shift 2 ;;
    --nfs)            NFS="$2"; shift 2 ;;
    --install-docker) INSTALL_DOCKER=1; shift ;;
    --yes|-y)         ASSUME_YES=1; INSTALL_DOCKER=1; shift ;;
    --dry-run)        DRY=1; shift ;;
    --check)          CHECK_ONLY=1; shift ;;
    -h|--help)        usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'
[[ -t 1 ]] || { BOLD=""; RED=""; GRN=""; YEL=""; OFF=""; }
say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s   %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %swarn%s %s\n' "$YEL" "$OFF" "$*"; }
err()  { printf '  %sERR%s  %s\n' "$RED" "$OFF" "$*"; PROBLEMS=$(( PROBLEMS + 1 )); }
step() { printf '\n%s── %s%s\n' "$BOLD" "$*" "$OFF"; }
run()  {
  if (( DRY )); then printf '  would run: %s\n' "$*"; return 0; fi
  "$@"
}
# A dry run must never print "ok, it's up" — that's the one thing that would
# make the preview untrustworthy.
ok_real() { (( DRY )) || ok "$*"; }
PROBLEMS=0

host_name() { hostname -s 2>/dev/null || hostname 2>/dev/null || cat /etc/hostname 2>/dev/null || echo node; }

# ── Detect ────────────────────────────────────────────────────────────────────
step "Inspecting this machine"

OS_ID="unknown"; OS_NAME="unknown"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release; OS_ID="${ID:-unknown}"; OS_NAME="${PRETTY_NAME:-$OS_ID}"
fi
ok "os: ${OS_NAME}"

PKG=""
for p in apt-get dnf pacman zypper apk; do command -v "$p" >/dev/null && { PKG="$p"; break; }; done
[[ -n "$PKG" ]] && ok "package manager: ${PKG}" || warn "no known package manager — install deps yourself"

HAS_DOCKER=0; HAS_COMPOSE=0
if command -v docker >/dev/null 2>&1; then
  HAS_DOCKER=1
  if docker info >/dev/null 2>&1; then ok "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
  else warn "docker installed but the daemon isn't reachable (not running, or you're not in the docker group)"; fi
  docker compose version >/dev/null 2>&1 && { HAS_COMPOSE=1; ok "docker compose: $(docker compose version --short 2>/dev/null)"; } \
    || warn "docker compose v2 plugin missing"
else
  warn "docker: not installed"
fi

# GPU decides the ErsatzTV image tag, which is the single most consequential
# setting on a playout node — software encoding a 1080p channel will eat a CPU.
GPU="software"; DETECTED_TAG="latest"
if [[ -e /dev/dri/renderD128 ]]; then
  GPU="vaapi"; DETECTED_TAG="latest-vaapi"; ok "gpu: /dev/dri present — VAAPI / Quick Sync"
elif command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  GPU="nvidia"; DETECTED_TAG="latest-nvidia"; ok "gpu: $(nvidia-smi -L 2>/dev/null | head -1)"
else
  warn "gpu: none detected — falling back to software encoding (expect high CPU)"
fi
[[ -z "$TAG" ]] && TAG="$DETECTED_TAG"

for t in ffmpeg ffprobe curl jq; do
  command -v "$t" >/dev/null && ok "tool: ${t}" || warn "tool: ${t} missing (needed by tools/, not by the containers)"
done

# ── Defaults ──────────────────────────────────────────────────────────────────
[[ -z "$ROLE"     ]] && ROLE="playout"
[[ -z "$NODE_ID"  ]] && NODE_ID="$(host_name)"
[[ -z "$MEDIA"    ]] && MEDIA="/media/channelz0"
[[ -z "$CLUSTER"  ]] && CLUSTER="${MEDIA}/.z0-cluster"

case "$ROLE" in
  playout|tower|worker) ;;
  *) echo "unknown --role '${ROLE}' (playout | tower | worker)" >&2; exit 1 ;;
esac

# ── Role preflight ────────────────────────────────────────────────────────────
step "Preflight for role: ${ROLE}"

if [[ "$ROLE" == "playout" ]]; then
  if [[ -d "$MEDIA" ]]; then ok "media root: ${MEDIA}"
  else warn "media root ${MEDIA} does not exist yet — will be created"; fi

  # The lease has to live where every playout node can see it. This is the one
  # mistake that turns a "cluster" into two stations fighting over a stream key.
  # The directory may not exist yet, so ask about the nearest ancestor that does
  # — otherwise every fresh node reports "unknown" and the shared-storage
  # warning below becomes noise you learn to ignore.
  probe="$MEDIA"
  while [[ -n "$probe" && ! -d "$probe" ]]; do probe="$(dirname "$probe")"; [[ "$probe" == "/" ]] && break; done
  FSTYPE=$(stat -f -c %T "$probe" 2>/dev/null || echo unknown)
  if [[ -n "$NFS" ]]; then
    ok "shared media: will mount ${NFS} at ${MEDIA}"
  elif [[ "$FSTYPE" =~ nfs|cifs|smb|fuse ]]; then
    ok "shared media: ${MEDIA} is ${FSTYPE}"
  else
    warn "media root looks local (${FSTYPE}) — fine for ONE playout node."
    warn "  A second node needs shared storage, or each will think it's alone"
    warn "  and both will publish. Pass --nfs host:/export, or see docs/clustering.md."
  fi

  [[ -z "$WATCH_DOMAIN" ]] && err "--watch-domain is required for a playout node"
  [[ -z "$STREAM_KEY"   ]] && err "--stream-key is required for a playout node"
  [[ "$STREAM_KEY" == "CHANGE-ME" ]] && err "--stream-key is still the placeholder"

  if [[ -n "$WATCH_DOMAIN" ]] && command -v getent >/dev/null; then
    getent hosts "$WATCH_DOMAIN" >/dev/null 2>&1 \
      && ok "tower resolves: ${WATCH_DOMAIN}" \
      || warn "tower ${WATCH_DOMAIN} does not resolve from here yet"
  fi
fi

if [[ "$ROLE" == "tower" ]]; then
  [[ -z "$SITE_DOMAIN"  ]] && warn "--site-domain not set; Caddy will need editing by hand"
  [[ -z "$WATCH_DOMAIN" ]] && err "--watch-domain is required for a tower node"
fi

# Clock skew is worth knowing about even though the lease was deliberately
# designed not to depend on it (nodes time the heartbeat's *change* locally).
if command -v timedatectl >/dev/null 2>&1; then
  timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes \
    && ok "clock: NTP synchronised" \
    || warn "clock: NTP not synchronised (not fatal — the lease doesn't trust clocks — but fix it for sane logs)"
fi

if (( CHECK_ONLY )); then
  step "Check only — nothing changed"
  (( PROBLEMS > 0 )) && { say "${RED}${PROBLEMS} problem(s) would block bootstrap.${OFF}"; exit 1; }
  say "This machine is ready to bootstrap as a ${ROLE} node."
  exit 0
fi
(( PROBLEMS > 0 )) && { say ""; say "${RED}Refusing to continue with ${PROBLEMS} problem(s) above.${OFF}"; exit 1; }

# ── Plan ──────────────────────────────────────────────────────────────────────
step "Plan"
cat <<PLAN
  role            ${ROLE}
  node id         ${NODE_ID}
  media root      ${MEDIA}
  cluster dir     ${CLUSTER}
  ersatztv tag    ${TAG}   (gpu: ${GPU})
  tower           ${WATCH_DOMAIN:-—}
  site            ${SITE_DOMAIN:-—}
PLAN
if (( ! ASSUME_YES && ! DRY )); then
  read -r -p "  proceed? [y/N] " a
  [[ "$a" =~ ^[Yy] ]] || { say "aborted."; exit 0; }
fi

# ── Docker ────────────────────────────────────────────────────────────────────
if (( ! HAS_DOCKER )); then
  step "Installing Docker"
  if (( ! INSTALL_DOCKER )); then
    say "  Docker is missing. Re-run with --install-docker (or --yes) to install it,"
    say "  or install it yourself and run this again. The command used is:"
    say "    curl -fsSL https://get.docker.com | sh"
    exit 1
  fi
  # Deliberately explicit rather than silent: this pipes a remote script into a
  # shell, which you should know about before it happens.
  if (( DRY )); then
    say "  would run: curl -fsSL https://get.docker.com | sh"
    say "  would run: systemctl enable --now docker"
  else
    say "  running: curl -fsSL https://get.docker.com | sh"
    curl -fsSL https://get.docker.com | sh || { err "docker install failed"; exit 1; }
    systemctl enable --now docker 2>/dev/null || true
    command -v docker >/dev/null && ok "docker installed" || { err "docker still missing"; exit 1; }
  fi
fi

# ── Shared media ──────────────────────────────────────────────────────────────
if [[ -n "$NFS" ]]; then
  step "Mounting shared media"
  run mkdir -p "$MEDIA"
  if mountpoint -q "$MEDIA" 2>/dev/null; then
    ok "${MEDIA} already mounted"
  else
    run mount -t nfs "$NFS" "$MEDIA" || err "mount failed — check exports and firewall"
    grep -q "[[:space:]]${MEDIA}[[:space:]]" /etc/fstab 2>/dev/null \
      || say "  note: add to /etc/fstab so it survives reboot:  ${NFS}  ${MEDIA}  nfs  defaults,_netdev  0 0"
  fi
fi

# ── Lay out the node ──────────────────────────────────────────────────────────
step "Laying out ${ROLE} node"

case "$ROLE" in
  playout|worker)
    run mkdir -p "$MEDIA" "$CLUSTER"
    if [[ -x "${DIR}/make-media-tree.sh" ]]; then
      if (( DRY )); then
        say "  would run: tools/make-media-tree.sh (Z0_MEDIA_ROOT=${MEDIA})"
      else
        Z0_MEDIA_ROOT="$MEDIA" bash "${DIR}/make-media-tree.sh" >/dev/null && ok "media tree ready"
      fi
    fi
    ;;
esac

if [[ "$ROLE" == "playout" ]]; then
  ENV_FILE="${REPO}/playout/.env"
  step "Writing ${ENV_FILE}"
  if (( DRY )); then
    say "  would write .env with node id ${NODE_ID}, tag ${TAG}"
  else
    # Never clobber an existing filled-in env silently — it holds the one secret.
    [[ -f "$ENV_FILE" ]] && cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%s)" && ok "backed up existing .env"
    cat > "$ENV_FILE" <<ENV
# Channel Z0 — generated by tools/bootstrap-node.sh on $(date -u +%FT%TZ)
# Node: ${NODE_ID} (${ROLE})
Z0_SITE_DOMAIN=${SITE_DOMAIN:-}
Z0_WATCH_DOMAIN=${WATCH_DOMAIN}
Z0_STREAM_KEY=${STREAM_KEY}

Z0_CHANNEL_URL=http://127.0.0.1:8409/iptv/channel/1.ts
Z0_CHANNEL_XMLTV=http://127.0.0.1:8409/iptv/xmltv.xml
Z0_MEDIA_ROOT=${MEDIA}

# --- Cluster ---------------------------------------------------------------
# Node identity must be unique across the station. The cluster dir must be on
# storage every playout node can write; that's where the uplink lease lives.
Z0_NODE_ID=${NODE_ID}
Z0_CLUSTER_DIR_HOST=${CLUSTER}

ERSATZTV_TAG=${TAG}
ENV
    chmod 600 "$ENV_FILE"
    ok "wrote .env (mode 600 — it holds the stream key)"
  fi

  step "Starting the stack"
  run docker compose -f "${REPO}/playout/compose.yml" --project-directory "${REPO}/playout" up -d \
    && ok_real "ersatztv + uplink up" || err "compose up failed"
fi

if [[ "$ROLE" == "tower" ]]; then
  step "Starting the tower"
  say "  the tower stack lives in vps/ — Owncast + Caddy"
  run docker compose -f "${REPO}/vps/docker-compose.yml" --project-directory "${REPO}/vps" up -d \
    && ok_real "owncast up" || err "compose up failed"
  say ""
  say "  ${BOLD}Now do these two things immediately:${OFF}"
  say "    1. open https://${WATCH_DOMAIN}/admin and change the default admin password"
  say "    2. set the stream key to the same value your playout nodes use"
fi

# ── Verify ────────────────────────────────────────────────────────────────────
if [[ "$ROLE" == "playout" ]] && (( ! DRY )); then
  step "Verifying"
  for i in $(seq 1 30); do
    curl -fsS -m 3 -o /dev/null "http://127.0.0.1:8409" 2>/dev/null && break
    sleep 2
  done
  curl -fsS -m 3 -o /dev/null "http://127.0.0.1:8409" 2>/dev/null \
    && ok "ErsatzTV answering on :8409" \
    || warn "ErsatzTV not answering yet — 'docker logs z0-ersatztv' will say why"

  say ""
  bash "${REPO}/playout/z0-leader.sh" --status 2>/dev/null || true
fi

# ── What now ──────────────────────────────────────────────────────────────────
step "Done — ${ROLE} node '${NODE_ID}'"
case "$ROLE" in
  playout) cat <<NEXT
  1. Open http://$(host_name):8409 and build the channel (build-guide Phase 2.3):
     FFmpeg profile, libraries, collections, filler presets, schedule.
  2. Stock the library:   tools/fetch-archive.sh --all
  3. Add another node:    run this script on a second box with a different
     --node-id and the SAME shared --media. It comes up as a standby.
  4. Prove failover:      tools/test-failover.sh
  5. Watch the cluster:   playout/z0-leader.sh --status
NEXT
  ;;
  tower) cat <<NEXT
  1. Point DNS at this box: ${WATCH_DOMAIN} (A/AAAA), and open :1935 for RTMP.
  2. Change the Owncast admin password and stream key.
  3. Bring up a playout node with --watch-domain ${WATCH_DOMAIN}.
NEXT
  ;;
  worker) cat <<NEXT
  This node runs no channel. Use it for the batch jobs:
     Z0_MEDIA_ROOT=${MEDIA} tools/fetch-archive.sh --all
     Z0_MEDIA_ROOT=${MEDIA} tools/make-proxies.sh --placeholder
NEXT
  ;;
esac
