#!/usr/bin/env bash
# MEQ-05.2 — Etapa 2: sequential driver for the EXP03 parallel benchmark.
# Launch:  setsid nohup bash scripts/run_benchmark.sh > records/driver.log 2>&1 < /dev/null &
# Writes ONLY inside $BENCH. Stops on any stop condition and writes records/STOP.
set -uo pipefail

ROOT=/p1-swell/danilocs/MPAS-Research
SRC_RUN=$ROOT/runs/meqbr_05km_oval_meq02a
SRC=$SRC_RUN/20211101_20211201
BENCH=$ROOT/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2
MESH=meqbr_05km_oval_meq02a
EXE=$ROOT/atmosphere_model
EXE_SHA=095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494
BUDGET_S=$((24*3600))           # node wall budget
REP_TOL=0.03                    # 3 % between repetitions -> 3rd repetition

source "$HOME/mpas-build/mpas_build_env.sh"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

cd "$BENCH"
REC=$BENCH/records
LOADS=$REC/loads.tsv
TRIALS=$REC/trials.tsv
[ -f "$LOADS" ]  || printf "utc\ttrial\tloadavg\tother_user_busy_procs\n" > "$LOADS"
[ -f "$TRIALS" ] || printf "trial\tseries\tranks\tpinning\trep\tstart_utc\tend_utc\twall_s\trc\tstatus\ttime_integration_s\tmpiexec_cmd\n" > "$TRIALS"
CUM_S=0
[ -f "$REC/cum_wall_s" ] && CUM_S=$(cat "$REC/cum_wall_s")

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*"; }
stop() { log "STOP: $*"; echo "$(ts) $*" > "$REC/STOP"; exit 2; }

seq_list() { local a=$1 b=$2 out=""; for ((i=a;i<=b;i++)); do out+="${out:+,}$i"; done; echo "$out"; }

# CPU lists (socket 0 physical: 0-27, SMT 56-83; socket 1 physical: 28-55, SMT 84-111)
pin_list_A() {   # N ranks, N/2 per socket, ranks 0..N/2-1 on socket 0, N/2..N-1 on socket 1
    local n=$1 h=$(( $1/2 ))
    echo "$(seq_list 0 $((h-1))),$(seq_list 28 $((28+h-1)))"
}
PIN_B="$(seq_list 0 27),$(seq_list 56 83),$(seq_list 28 55),$(seq_list 84 111)"
PIN_D1="$(seq_list 0 27)"
PIN_D2="$(seq_list 28 55)"

other_busy() {  # CPU-heavy processes of other users (pcpu > 50)
    ps -eo user:20,pcpu,pid,comm --no-headers | awk -v me="$USER" '$1!=me && $2>50 {printf "%s:%s:%s:%s;", $1,$2,$3,$4}'
}

wait_idle() {   # $1 = trial label; wait up to 15 min for loadavg(1 min) < 2
    local lab=$1 t=0 l1 busy procs
    while :; do
        procs=$(pgrep -a '^(atmosphere_mod|init_atmospher)' || true)
        l1=$(cut -d' ' -f1 /proc/loadavg)
        busy=$(other_busy)
        if [ -z "$procs" ] && awk -v l="$l1" 'BEGIN{exit !(l<2)}'; then
            printf "%s\t%s\t%s\t%s\n" "$(ts)" "$lab" "$(cat /proc/loadavg)" "${busy:-none}" >> "$LOADS"
            return 0
        fi
        if [ $t -ge 900 ]; then
            printf "%s\t%s\t%s\t%s\n" "$(ts)" "$lab" "$(cat /proc/loadavg)" "${busy:-none}" >> "$LOADS"
            stop "node not idle before $lab after 15 min (load=$l1; procs=[$procs]; other=[$busy])"
        fi
        sleep 30; t=$((t+30))
    done
}

make_trial() {  # $1 dir, $2 ranks, $3 streams variant (nooutput|production)
    local d=$1 n=$2 sv=$3
    [ -e "$d" ] && stop "trial dir already exists: $d"
    mkdir -p "$d"
    ln -s "$EXE" "$d/atmosphere_model"
    for f in CAM_ABS_DATA.DBL CAM_AEROPT_DATA.DBL CCN_ACTIVATE_DATA GENPARM.TBL LANDUSE.TBL NoahmpTable.TBL \
             OZONE_DAT.TBL OZONE_LAT.TBL OZONE_PLEV.TBL RRTMG_LW_DATA RRTMG_LW_DATA.DBL RRTMG_SW_DATA \
             RRTMG_SW_DATA.DBL SOILPARM.TBL VEGPARM.TBL stream_list.atmosphere.diagnostics \
             stream_list.atmosphere.diag_ugwp stream_list.atmosphere.output stream_list.atmosphere.surface \
             stream_list.atmosphere.wind_energy zeta_wind.txt; do
        ln -s "$(readlink -f "$SRC/$f")" "$d/$f"
    done
    ln -s "$(readlink "$SRC/$MESH.init.nc")"          "$d/$MESH.init.nc"        # same first-level target as production
    ln -s "$(readlink "$SRC/$MESH.sfc_update.nc")"    "$d/$MESH.sfc_update.nc"  # same first-level target as production
    ln -s "$SRC/restart.2021-11-15_00.00.00.nc"       "$d/restart.2021-11-15_00.00.00.nc"
    for f in "$SRC"/lbc.2021-11-15_*.nc "$SRC"/lbc.2021-11-16_00.00.00.nc; do ln -s "$f" "$d/$(basename "$f")"; done
    ln -s "$BENCH/partitions/$MESH.graph.info" "$d/$MESH.graph.info"
    ln -s "$(readlink -f "$BENCH/partitions/$MESH.graph.info.part.$n")" "$d/$MESH.graph.info.part.$n"
    cp "$BENCH/common/namelist.atmosphere" "$d/namelist.atmosphere"
    cp "$BENCH/common/streams.atmosphere.$sv" "$d/streams.atmosphere"
    diff "$BENCH/common/namelist.atmosphere.orig" "$d/namelist.atmosphere" > "$d/namelist.diff"
    diff "$BENCH/common/streams.atmosphere.orig" "$d/streams.atmosphere"  > "$d/streams.diff"
}

sample_pinning() {  # $1 dir, $2 outfile ; sample affinity and current CPU of the ranks running in $1
    local d=$1 out=$2 k pid cwd
    for k in 1 2 3; do
        sleep $(( k==1 ? 90 : 120 ))
        {
            echo "### sample $k at $(ts)"
            for pid in $(pgrep '^atmosphere_mod' || true); do
                cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
                [ "$cwd" = "$d" ] || continue
                printf "pid=%s psr=%s %s\n" "$pid" "$(ps -o psr= -p "$pid" | tr -d ' ')" "$(taskset -cp "$pid" 2>/dev/null | sed 's/.*: /affinity=/')"
            done
            echo "other_user_busy=$(other_busy)"
        } >> "$out"
    done
}

check_log() {   # $1 dir ; returns non-empty problem string if any
    local d=$1 p=""
    local L=$d/log.atmosphere.0000.out
    [ -f "$L" ] || { echo "no log"; return; }
    grep -q "CRITICAL ERROR" "$d"/log.atmosphere.*.{out,err} 2>/dev/null && p+="CRITICAL_ERROR;"
    grep -qiw "nan" "$L" && p+="NaN_in_log;"
    ls "$d"/log.atmosphere.*.err >/dev/null 2>&1 && p+="err_files_present;"
    grep -q "Critical error messages = *0" "$L" || p+="critical_count_not_zero_or_missing;"
    grep -q " time integration " "$L" || p+="no_timer_table;"
    echo "$p"
}

t_int() { awk '$2=="time" && $3=="integration" {print $4; exit}' "$1/log.atmosphere.0000.out" 2>/dev/null; }

run_one() {   # $1 trial name, $2 series, $3 ranks, $4 pinning label, $5 cpu list (or "none"), $6 streams, $7 predicted min
    local name=$1 ser=$2 n=$3 plab=$4 cpus=$5 sv=$6 pred=$7
    local d=$BENCH/$name rep=${name##*_r}
    local tmo=$(( 2*pred*60 ))
    [ $CUM_S -ge $BUDGET_S ] && stop "24 h node-wall budget reached before $name (cum=${CUM_S}s)"
    [ $(( BUDGET_S - CUM_S )) -lt $tmo ] && tmo=$(( BUDGET_S - CUM_S ))
    [ "$(sha256sum "$EXE" | cut -d' ' -f1)" = "$EXE_SHA" ] || stop "executable sha256 mismatch"
    wait_idle "$name"
    make_trial "$d" "$n" "$sv"
    local cmd
    if [ "$cpus" = none ]; then cmd="mpiexec -n $n ./atmosphere_model"
    else cmd="mpiexec -n $n -bind-to user:$cpus ./atmosphere_model"; fi
    echo "$cmd" > "$d/mpiexec_cmd.txt"
    log "START $name | $cmd | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d" && timeout --signal=TERM --kill-after=60 "$tmo" $cmd > mpas.out 2>&1 ) &
    local mp=$!
    sample_pinning "$d" "$d/pinning_samples.txt" &
    local sp=$!
    wait $mp; local rc=$?
    kill $sp 2>/dev/null; wait $sp 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/cum_wall_s"
    echo "$w" > "$d/wrapper_wall_s.txt"; echo "$st" > "$d/wrapper_start_utc.txt"; ts > "$d/wrapper_end_utc.txt"
    local prob; prob=$(check_log "$d"); local ti; ti=$(t_int "$d")
    local status=ok
    [ $rc -eq 124 ] || [ $rc -eq 137 ] && status="timeout_gt_2x_predicted"
    [ $rc -ne 0 ] && [ "$status" = ok ] && status="rc_$rc"
    [ -n "$prob" ] && status="${status};${prob}"
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$name" "$ser" "$n" "$plab" "$rep" "$st" "$(ts)" "$w" "$rc" "$status" "${ti:-NA}" "$cmd" >> "$TRIALS"
    log "END   $name | rc=$rc | wall=${w}s | t_int=${ti:-NA} | status=$status | cum=${CUM_S}s"
    [ "$status" = ok ] || stop "$name failed: $status"
    LAST_TI=$ti
}

need_third() { awk -v a="$1" -v b="$2" -v t="$REP_TOL" 'BEGIN{d=a-b; if(d<0)d=-d; exit !(d/((a+b)/2) > t)}'; }

run_series_point() {  # same args as run_one minus name/rep: $1 prefix, $2 series, $3 ranks, $4 plab, $5 cpus, $6 streams, $7 pred
    local p=$1; shift
    run_one "${p}_r1" "$@"; local a=$LAST_TI
    run_one "${p}_r2" "$@"; local b=$LAST_TI
    if need_third "$a" "$b"; then log "repetitions differ > 3 % ($a vs $b): 3rd repetition"; run_one "${p}_r3" "$@"; fi
}

run_pair_D() {   # $1 rep ; two 28-rank cases simultaneously, socket 0 and socket 1
    local r=$1 pred=23
    local tmo=$(( 2*pred*60 ))
    [ $CUM_S -ge $BUDGET_S ] && stop "24 h node-wall budget reached before D r$r"
    [ $(( BUDGET_S - CUM_S )) -lt $tmo ] && tmo=$(( BUDGET_S - CUM_S ))
    wait_idle "D_N028x2_r$r"
    local d1=$BENCH/D_N028x2_s0_r$r d2=$BENCH/D_N028x2_s1_r$r
    make_trial "$d1" 28 nooutput; make_trial "$d2" 28 nooutput
    local c1="mpiexec -n 28 -bind-to user:$PIN_D1 ./atmosphere_model"
    local c2="mpiexec -n 28 -bind-to user:$PIN_D2 ./atmosphere_model"
    echo "$c1" > "$d1/mpiexec_cmd.txt"; echo "$c2" > "$d2/mpiexec_cmd.txt"
    log "START D r$r | $c1 || $c2 | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d1" && s=$(date +%s); timeout --signal=TERM --kill-after=60 "$tmo" $c1 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m1=$!
    ( cd "$d2" && s=$(date +%s); timeout --signal=TERM --kill-after=60 "$tmo" $c2 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m2=$!
    sample_pinning "$d1" "$d1/pinning_samples.txt" & local p1=$!
    sample_pinning "$d2" "$d2/pinning_samples.txt" & local p2=$!
    wait $m1; local rc1=$?; wait $m2; local rc2=$?
    kill $p1 $p2 2>/dev/null; wait $p1 $p2 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/cum_wall_s"
    echo "$st" > "$d1/wrapper_start_utc.txt"; echo "$st" > "$d2/wrapper_start_utc.txt"
    echo "$w" > "$d1/pair_wall_s.txt"; echo "$w" > "$d2/pair_wall_s.txt"
    local fail=""
    local i d rc cmd plab prob ti status
    for i in 1 2; do
        if [ $i -eq 1 ]; then d=$d1; rc=$rc1; cmd=$c1; plab="physical_socket0_0-27"
        else d=$d2; rc=$rc2; cmd=$c2; plab="physical_socket1_28-55"; fi
        prob=$(check_log "$d"); ti=$(t_int "$d"); status=ok
        [ $rc -eq 124 ] || [ $rc -eq 137 ] && status="timeout_gt_2x_predicted"
        [ $rc -ne 0 ] && [ "$status" = ok ] && status="rc_$rc"
        [ -n "$prob" ] && status="${status};${prob}"
        printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(basename "$d")" D 28 "$plab" "$r" "$st" "$(ts)" "$(cat "$d/wrapper_wall_s.txt")" "$rc" "$status" "${ti:-NA}" "$cmd" >> "$TRIALS"
        [ "$status" = ok ] || fail+="$(basename "$d"):$status "
    done
    log "END   D r$r | rc=$rc1/$rc2 | pair wall=${w}s | cum=${CUM_S}s"
    [ -z "$fail" ] || stop "D r$r failed: $fail"
    LAST_TI_D1=$(t_int "$d1"); LAST_TI_D2=$(t_int "$d2")
}

# ------------------------------------------------------------------ main
if [ -n "${MAKE_ONLY:-}" ]; then make_trial "$BENCH/$MAKE_ONLY" 56 "${MAKE_STREAMS:-nooutput}"; exit 0; fi
log "driver start | host=$(hostname) | mpiexec=$(command -v mpiexec) | cum=${CUM_S}s"
PLAN=${PLAN:-"C A56 A42 A28 A14 A8 B D E"}
for step in $PLAN; do
    [ -f "$REC/STOP" ] && exit 2
    case $step in
        C)   run_series_point C_N060   C 60  "none(production-like)"            none            nooutput 11 ;;
        A56) run_series_point A_N056   A 56  "physical_28+28_block"              "$(pin_list_A 56)" nooutput 11 ;;
        A42) run_series_point A_N042   A 42  "physical_21+21_block"              "$(pin_list_A 42)" nooutput 15 ;;
        A28) run_series_point A_N028   A 28  "physical_14+14_block"              "$(pin_list_A 28)" nooutput 23 ;;
        A14) run_series_point A_N014   A 14  "physical_7+7_block"                "$(pin_list_A 14)" nooutput 45 ;;
        A8)  run_series_point A_N008   A 8   "physical_4+4_block"                "$(pin_list_A 8)"  nooutput 80 ;;
        B)   run_series_point B_N112   B 112 "logical_1per_thread_socket_block"  "$PIN_B"         nooutput 11 ;;
        D)   run_pair_D 1; a1=$LAST_TI_D1; a2=$LAST_TI_D2
             run_pair_D 2; b1=$LAST_TI_D1; b2=$LAST_TI_D2
             if need_third "$a1" "$b1" || need_third "$a2" "$b2"; then log "D repetitions differ > 3 %: 3rd repetition"; run_pair_D 3; fi ;;
        E)   run_series_point E_N056   E 56  "physical_28+28_block"              "$(pin_list_A 56)" production 11 ;;
        *)   stop "unknown plan step $step" ;;
    esac
done
log "driver finished | cum=${CUM_S}s"
echo "$(ts) all planned trials finished" > "$REC/DONE"
