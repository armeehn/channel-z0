#!/bin/bash
# z0-r2-offload.sh — move Channel Z0's HLS delivery off the tower's disk and
# onto an S3-compatible bucket behind a CDN (Cloudflare R2 in the reference
# build). See docs/pdf/docs-scaling.pdf, tier 1.
#
# Through Owncast's admin API it:
#   1. sets the S3 storage block (endpoint, key pair, bucket, region, path-style)
#   2. sets the video serving endpoint (the CDN hostname players pull from)
#   3. raises the latency level to 3 if it is lower (object storage adds seconds)
#
# Owncast only builds the new pipeline on a NEW RTMP session, so nothing
# changes on air until the uplink reconnects. The script says so at the end.
#
#   z0-r2-offload.sh          apply
#   z0-r2-offload.sh --off    revert to serving HLS from the tower
#   z0-r2-offload.sh --show   print the current storage + latency config
#
# Env:
#   Z0_OWNCAST_ADMIN_USER / Z0_OWNCAST_ADMIN_PASS   Owncast admin credentials
#   Z0_WATCH_HOST     tower hostname        (default watch.ch0.ripostelabs.xyz)
#   Z0_R2_ENDPOINT    https://<account-id>.r2.cloudflarestorage.com
#   Z0_R2_ACCESS_KEY / Z0_R2_SECRET
#   Z0_R2_BUCKET      bucket name           (e.g. ch0-hls)
#   Z0_HLS_HOST       CDN custom domain     (e.g. hls.ch0.ripostelabs.xyz)
set -euo pipefail

WATCH_HOST="${Z0_WATCH_HOST:-watch.ch0.ripostelabs.xyz}"
API="https://${WATCH_HOST}/api/admin"
# Owncast latency levels run 0 (lowest latency) to 4 (most buffering). Object
# storage adds a few seconds, so settle one notch above the default of 2.
TARGET_LATENCY_LEVEL=3
# R2 has no regions; its S3 endpoint wants the literal "auto".
R2_REGION=auto

MODE=apply
case "${1:-}" in
  --off)  MODE=off ;;
  --show) MODE=show ;;
  "")     ;;
  *) echo "usage: $0 [--off|--show]" >&2; exit 2 ;;
esac

: "${Z0_OWNCAST_ADMIN_USER:?}" "${Z0_OWNCAST_ADMIN_PASS:?}"

admin() {
  # admin <method> <path> [json-body]
  local method=$1 path=$2 body=${3:-}
  if [ -n "$body" ]; then
    curl -sf -u "${Z0_OWNCAST_ADMIN_USER}:${Z0_OWNCAST_ADMIN_PASS}" \
      -H 'Content-Type: application/json' -X "$method" "${API}${path}" -d "$body"
  else
    curl -sf -u "${Z0_OWNCAST_ADMIN_USER}:${Z0_OWNCAST_ADMIN_PASS}" -X "$method" "${API}${path}"
  fi
}

current_level() {
  admin GET /serverconfig | python3 -c 'import json,sys; print(json.load(sys.stdin)["videoSettings"]["latencyLevel"])'
}

show() {
  admin GET /serverconfig | python3 -c '
import json, sys
c = json.load(sys.stdin)
s3 = c.get("s3", {})
print("s3.enabled        ", s3.get("enabled"))
print("s3.endpoint       ", s3.get("endpoint"))
print("s3.bucket         ", s3.get("bucket"))
print("s3.region         ", s3.get("region"))
print("s3.forcePathStyle ", s3.get("forcePathStyle"))
print("servingEndpoint   ", c.get("videoServingEndpoint"))
print("latencyLevel      ", c["videoSettings"]["latencyLevel"])
'
}

if [ "$MODE" = show ]; then
  show
  exit 0
fi

if [ "$MODE" = off ]; then
  admin POST /config/s3 '{"value":{"enabled":false}}' >/dev/null
  admin POST /config/videoservingendpoint '{"value":""}' >/dev/null
  echo "S3 offload disabled and serving endpoint cleared."
  echo "Latency level left as is; lower it by hand if you raised it."
  echo "Restart the uplink so Owncast starts a new pipeline."
  exit 0
fi

: "${Z0_R2_ENDPOINT:?}" "${Z0_R2_ACCESS_KEY:?}" "${Z0_R2_SECRET:?}" "${Z0_R2_BUCKET:?}" "${Z0_HLS_HOST:?}"

# 1. Storage block. ACL stays empty: R2 has no object ACLs and public access
#    comes from the custom domain, not from the object.
S3_JSON=$(R2_REGION="$R2_REGION" python3 -c '
import json, os
print(json.dumps({"value": {
  "enabled": True,
  "endpoint": os.environ["Z0_R2_ENDPOINT"],
  "accessKey": os.environ["Z0_R2_ACCESS_KEY"],
  "secret": os.environ["Z0_R2_SECRET"],
  "bucket": os.environ["Z0_R2_BUCKET"],
  "region": os.environ["R2_REGION"],
  "acl": "",
  "forcePathStyle": True,
}}))')
admin POST /config/s3 "$S3_JSON" >/dev/null
echo "S3 storage set: ${Z0_R2_BUCKET} at ${Z0_R2_ENDPOINT}"

# 2. Serving endpoint: the playlist URLs Owncast hands to players.
admin POST /config/videoservingendpoint "{\"value\":\"https://${Z0_HLS_HOST}\"}" >/dev/null
echo "Serving endpoint set: https://${Z0_HLS_HOST}"

# 3. More buffering for the object-storage hop; never lower an operator's choice.
LEVEL=$(current_level)
if [ "$LEVEL" -lt "$TARGET_LATENCY_LEVEL" ]; then
  admin POST /config/video/streamlatencylevel "{\"value\":${TARGET_LATENCY_LEVEL}}" >/dev/null
  echo "Latency level ${LEVEL} -> ${TARGET_LATENCY_LEVEL}"
else
  echo "Latency level already ${LEVEL}; not raised"
fi

echo
show
cat <<EOF

Next:
  1. Restart the uplink on the playout host so a new RTMP session starts
     (a config change alone leaves the old pipeline running).
  2. curl -sI https://${Z0_HLS_HOST}/hls/stream.m3u8 | grep -i "cf-cache-status\|access-control"
     Expect HIT (after the first fetch) and Access-Control-Allow-Origin: *.
  3. Nothing to change in the storefront: the master playlist stays on
     ${WATCH_HOST} and now points variants and segments at ${Z0_HLS_HOST}.
EOF
