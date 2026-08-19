#!/usr/bin/env bash
# One-shot Channel Z0 playout reset, run BEFORE sign-on.
#
# WHY: a playout reset taken mid-day costs the NEXT day's entire morning. The
# overnight block overruns its target by hours and every block with an earlier
# target — COLOUR BARS, SIGN-ON, SHORT SUBJECTS, CARTOON CARNIVAL, PRELINGER,
# LAB HOUR — collapses to zero. Reproduced across three resets on 2026-08-14
# (10:41, 11:25, 12:01); day 3 was clean every time. Entering day 1 before the
# 06:00 sign-on means no block has a target in the past, so nothing collapses.
#
# SAFETY: this stops a live broadcast container while nobody is watching. The
# EXIT trap starts it again unconditionally — on success, on failure, on a
# syntax error, on SIGTERM. The worst case is meant to be "reset didn't happen",
# never "channel is off air until someone notices".
set -uo pipefail

D=/mnt/solid-state/ersatztv
DB="$D/ersatztv.sqlite3"
LOG=/tmp/z0-presignon-reset.log

exec >>"$LOG" 2>&1
echo "=== $(date -Is) pre-sign-on reset starting ==="

restart_always() {
  local rc=$?
  if ! docker ps --format '{{.Names}}' | grep -qx z0-ersatztv; then
    echo "$(date -Is) EXIT trap: container not running, starting it"
    docker start z0-ersatztv || echo "$(date -Is) FATAL: docker start FAILED"
  fi
  echo "=== $(date -Is) finished, rc=$rc ==="
}
trap restart_always EXIT

# ── The rotation guard ───────────────────────────────────────────────────────
# This script is what put the channel a day behind on 2026-08-15. It was run at
# 05:15 on a SATURDAY against a channel-z0.yml rotated to start on FRIDAY, and a
# reset enters the file at block one: Saturday therefore aired Friday, Sunday
# aired Saturday, and so on for four days with nothing reporting it.
#
# A reset is only ever correct if the deployed file starts on the day you are
# resetting on. Refuse rather than regenerate — a reset needs a reason, and the
# ordinary way to put the week back on the calendar is now
#   tools/z0-day-align.py --apply
# which cuts at a block boundary instead of re-entering the whole week.
TODAY=$(date +%A | tr "[:upper:]" "[:lower:]")
ROTATION=$(grep -m1 -oE "Rotated to start on [A-Z]+" "$D/channel-z0.yml" \
           | awk "{print \$NF}" | tr "[:upper:]" "[:lower:]")
if [ "$ROTATION" != "$TODAY" ]; then
  echo "REFUSING: $D/channel-z0.yml is rotated to start on ${ROTATION:-<unknown>},"
  echo "and today is $TODAY. Resetting now would air ${ROTATION}'s programming today"
  echo "and every following day would be wrong too — silently."
  echo
  echo "Either regenerate for today first:"
  echo "  z0-build-schedule.py --start-day $TODAY --out $D/channel-z0.yml"
  echo "or, if the week has simply drifted off the calendar, use the aligner"
  echo "instead of a reset:  z0-day-align.py --apply"
  exit 1
fi
echo "rotation check: file starts on $ROTATION, today is $TODAY"

B="$D/.z0-backup-presignon-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$B" || exit 1
sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null
cp "$DB" "$B/" || { echo "backup failed, aborting before any destructive step"; exit 1; }
echo "backup -> $B"

docker stop -t 30 z0-ersatztv || { echo "stop failed"; exit 1; }
echo "stopped"

sqlite3 "$DB" "PRAGMA foreign_keys=ON; delete from PlayoutItem; delete from PlayoutAnchor; delete from PlayoutHistory;" \
  || { echo "delete failed — container will be restarted by the trap"; exit 1; }
echo "cleared: items=$(sqlite3 "$DB" 'select count(*) from PlayoutItem;')" \
     "orphanGfx=$(sqlite3 "$DB" 'select count(*) from PlayoutItemGraphicsElement;')"
sqlite3 "$DB" "PRAGMA quick_check;"

docker start z0-ersatztv
echo "started; waiting for rebuild"

for _ in $(seq 1 60); do
  sleep 10
  n=$(sqlite3 "$DB" "select count(*) from PlayoutItem;" 2>/dev/null || echo 0)
  [ "${n:-0}" -gt 50 ] && { echo "rebuilt: $n items"; break; }
done

# Did it actually recover the morning? This is the whole point of the exercise.
echo "--- next morning 06:00-12:00 (local), non-filler ---"
sqlite3 "$DB" "select substr(datetime(Start,'-7 hours'),1,16)||'  '||CustomTitle
               from PlayoutItem
               where datetime(Start,'-7 hours') >= date('now','-7 hours','+1 day')||' 06:00'
                 and datetime(Start,'-7 hours') <  date('now','-7 hours','+1 day')||' 12:00'
                 and CustomTitle <> 'STATION INTERVAL'
               group by CustomTitle order by Start;"
