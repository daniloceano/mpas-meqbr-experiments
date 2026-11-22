#!/usr/bin/env bash
# MEQ-06.5 A2 — incremental LBC, one month at a time, with manifest.
# Month N (label YYYY-MM) covers [max(2021-10-21, 1st of N) 00, 1st of N+1 00], 6-hourly.
# Runs case 9 only when every ERA5 intermediate of that window exists, and never
# while atmosphere_model is running (keeps the restart-test timing clean).
# Loops every 20 min until all 21 manifests are PRONTO or one is FALHA.
#   nohup ./lbc_monthly.sh > logs/lbc_monthly.log 2>&1 &
set -uo pipefail
P=/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production
M=meqbr_05km_oval_meq02a
INIT=$P/preproc/init_20211021/$M.init.nc
MAN=$P/manifests; mkdir -p "$MAN"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
months=(); y=2021; m=10
while [ "$y$m" -le 202306 ]; do months+=("$(printf %04d-%02d $y $((10#$m)))"); m=$((10#$m+1)); [ $m -gt 12 ] && { m=1; y=$((y+1)); }; m=$(printf %02d $m); done
window() {  # window YYYY-MM -> prints "start stop" (YYYY-MM-DD_HH)
  local s="$1-01"; [ "$1" = 2021-10 ] && s=2021-10-21
  echo "$s $(date -u -d "$1-01 +1 month" +%Y-%m-%d)"
}
while true; do
  left=0
  for mo in "${months[@]}"; do
    f=$MAN/lbc_manifest_$mo.txt
    grep -q "^status: PRONTO" "$f" 2>/dev/null && continue
    grep -q "^status: FALHA" "$f" 2>/dev/null && { echo "[$(ts)] STOP: $mo is FALHA"; exit 1; }
    left=$((left+1))
    read s e < <(window "$mo")
    times=(); t=$(date -u -d "$s 00:00 UTC" +%s); te=$(date -u -d "$e 00:00 UTC" +%s)
    while [ $t -le $te ]; do times+=("$(date -u -d @$t +%Y-%m-%d_%H)"); t=$((t+21600)); done
    miss=0; for x in "${times[@]}"; do [ -s "$P/met_data/era5/${x//[-_]/}/ERA5:$x" ] || miss=$((miss+1)); done
    [ $miss -gt 0 ] && break           # months complete in order; wait for ERA5
    pgrep -x atmosphere_model >/dev/null && { echo "[$(ts)] $mo ready, waiting: atmosphere_model running"; break; }
    echo "[$(ts)] GEN $mo (${#times[@]} times)"; t0=$(date +%s)
    "$P/preproc_prod.sh" --name "lbc_$mo" --cases 9 --start "${s}_00:00:00" --stop "${e}_00:00:00" --init "$INIT" \
        > "$P/logs/preproc_lbc_$mo.log" 2>&1; rc=$?
    dt=$(( $(date +%s) - t0 ))
    W=$P/preproc/lbc_$mo; found=0; bad=0
    { echo "month: $mo"; echo "window: ${s}_00 -> ${e}_00 (6-hourly, inclusive)"
      echo "generated_utc: $(ts)"; echo "init_atmosphere_rc: $rc"; echo "elapsed_s: $dt"
      echo "init_file: $INIT ($(md5sum < "$INIT" | cut -c1-32))"
      echo "expected: ${#times[@]}"
      for x in "${times[@]}"; do
        lf="$W/lbc.${x}.00.00.nc"
        if [ -s "$lf" ]; then found=$((found+1)); echo "$x $(stat -c %s "$lf") $(md5sum < "$lf" | cut -c1-32)"
        else bad=$((bad+1)); echo "$x MISSING"; fi
      done
      echo "found: $found"; echo "total_bytes: $(du -cb "$W"/lbc.*.nc 2>/dev/null | tail -1 | cut -f1)"
      if [ $rc -eq 0 ] && [ $found -eq ${#times[@]} ]; then echo "status: PRONTO"; else echo "status: FALHA"; fi
    } > "$f"
    echo "[$(ts)] $mo $(tail -1 "$f") found=$found/${#times[@]} ${dt}s"
  done
  [ $left -eq 0 ] && { echo "[$(ts)] ALL 21 MANIFESTS PRONTO"; exit 0; }
  sleep 1200
done
