#!/usr/bin/env bash
# MEQ-06.8 — cron wrapper (Swell). Syncs bin/monitor_production.py from origin/main
# (only that file, via the separate monitor clone; the monitor branch worktree is not
# touched), then runs it. If the sync fails, runs the current copy and passes the
# reason in MONITOR_SYNC_ERR, which the script turns into an alert.
set -u
B=$HOME/meq06_monitor
F=scripts/06_monitor/monitor_production.py
export MONITOR_SYNC_ERR=""
tmp=$(mktemp)
if err=$(git -C "$B/site" fetch -q --depth 1 origin main 2>&1) \
   && err=$(git -C "$B/site" show "FETCH_HEAD:$F" 2>&1 > "$tmp") \
   && [ -s "$tmp" ] && err=$(python3 -m py_compile "$tmp" 2>&1); then
  cmp -s "$tmp" "$B/bin/monitor_production.py" || cp "$tmp" "$B/bin/monitor_production.py"
else
  MONITOR_SYNC_ERR="$(date -u +%FT%TZ) ${err:-arquivo vazio em origin/main}"
fi
rm -f "$tmp"
cd "$B" && exec /opt/anaconda3/bin/python3 bin/monitor_production.py --out "$B/site" --publish
