#!/usr/bin/env bash
# MEQ-06.6 — restart test (authorized 2026-11-21). EXP03 config verbatim, 90 ranks,
# part.90 copy, P90C pinning, hourly output (stream_list.atmosphere.wind_energy).
#   C : 2021-10-21 00 -> +2 d continuous
#   R1: 2021-10-21 00 -> +1 d ; R2: restart from restart.2021-10-22 -> +1 d
set -uo pipefail
source "$HOME/mpas-build/mpas_build_env.sh"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
REG=/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a
REF=$REG/20211101_20211201                    # validated EXP03 2021 leg (config source)
P=$REG/meq06_production
T=$REG/meq06_restart_test
M=meqbr_05km_oval_meq02a
PIN="0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
[ -e "$T/C" ] && { echo "REFUSE: $T/C exists"; exit 3; }
mkdir -p "$T/common" "$T/C" "$T/R1" "$T/R2" "$T/records"
cp -n "$P/$M.graph.info.part.90" "$T/common/"
md5sum "$P/$M.graph.info.part.90" "$T/common/$M.graph.info.part.90" > "$T/records/partition_md5.txt"
setup() {  # setup <dir> <start> <duration> <do_restart>
  local d=$1; cd "$T/$d"
  for f in "$REF"/*; do b=$(basename "$f")
    case "$b" in history.*|restart.*|lbc.*|diag.*|log.*|mpas.out|*.init.nc|*.sfc_update.nc|*.part.60|namelist.atmosphere) ;;
      *) if [ -L "$f" ]; then ln -sfn "$(readlink -f "$f")" .; else cp -n "$f" .; fi ;; esac
  done
  ln -sfn "$T/common/$M.graph.info.part.90" .
  ln -sfn "$P/preproc/init_20211021/$M.init.nc" .
  ln -sfn "$P/preproc/sfc_block1/$M.sfc_update.nc" .
  for f in "$P"/preproc/lbc_test_20211021_20211023/lbc.*.nc; do ln -sfn "$f" .; done
  sed -e "s/config_start_time = .*/config_start_time = '$2'/" \
      -e "s/config_run_duration = .*/config_run_duration = '$3'/" \
      -e "s/config_do_restart = .*/config_do_restart = $4/" "$REF/namelist.atmosphere" > namelist.atmosphere
  diff "$REF/namelist.atmosphere" namelist.atmosphere > namelist.diff
  diff "$REF/streams.atmosphere" streams.atmosphere > streams.diff
  md5sum stream_list.atmosphere.* streams.atmosphere namelist.atmosphere > config_md5.txt
}
run() {  # run <dir>
  cd "$T/$1"; echo "mpiexec -n 90 -bind-to user:$PIN ./atmosphere_model" > mpiexec_cmd.txt
  echo "[$(ts)] START $1 load=$(cut -d' ' -f1-3 /proc/loadavg)"; t0=$(date +%s)
  mpiexec -n 90 -bind-to user:$PIN ./atmosphere_model > mpas.out 2>&1; rc=$?
  dt=$(( $(date +%s) - t0 )); echo "$dt" > wall_s.txt
  nerr=$(grep -E "^ *(Error|Critical error) messages =" log.atmosphere.0000.out 2>/dev/null | awk '{s+=$NF} END{print s+0}')
  echo "[$(ts)] END $1 rc=$rc errors=$nerr wall=${dt}s history=$(ls history.*.nc 2>/dev/null | wc -l) restart=$(ls restart.*.nc 2>/dev/null | wc -l)"
  [ "$rc" -eq 0 ] && [ "$nerr" -eq 0 ]
}
setup C  2021-10-21_00:00:00 2_00:00:00 false
setup R1 2021-10-21_00:00:00 1_00:00:00 false
setup R2 2021-10-22_00:00:00 1_00:00:00 true
run C || exit 1
run R1 || exit 1
ln -sfn "$T/R1/restart.2021-10-22_00.00.00.nc" "$T/R2/"
run R2 || exit 1
echo "[$(ts)] ALL DONE"
