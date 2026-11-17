#!/usr/bin/env bash
# MEQ-05.4 — Etapa 2: sequential driver for the complementary parallel benchmark of EXP03.
# Adapted from MEQ-05.2 run_benchmark.sh (same trial build, idle checks, log checks, pinning syntax).
# Launch:  setsid nohup bash MEQ054_scripts/run_meq054.sh > MEQ054_records/driver.log 2>&1 < /dev/null &
# Writes ONLY new MEQ054_* entries inside $BENCH. Stops on any stop condition and writes MEQ054_records/STOP.
set -uo pipefail

ROOT=/p1-swell/danilocs/MPAS-Research
SRC_RUN=$ROOT/runs/meqbr_05km_oval_meq02a
SRC=$SRC_RUN/20211101_20211201
BENCH=$ROOT/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2
MESH=meqbr_05km_oval_meq02a
EXE=$ROOT/atmosphere_model
EXE_SHA=095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494
BUDGET_S=$((8*3600 - ${BUDGET_USED_S:-0}))   # 8 h of machine time (driver elapsed incl. idle waits), minus time used by earlier launches
REP_TOL=0.03                    # 3 % between repetitions -> 3rd repetition
CTRL_REF_S_PER_STEP=1.2233      # MEQ-05.2 A_N056 cfg_mean_s_per_step (meq05_parallel_benchmark.csv)
CTRL_TOL=0.03
# 2x the wall of the comparable MEQ-05.2 trial (trials.tsv): A56 mean 444 s, E56 mean 453.5 s, D pair 1011.5 s
LIM_A56=888; LIM_E56=907; LIM_PAIR=2023

source "$HOME/mpas-build/mpas_build_env.sh"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

cd "$BENCH"
REC=$BENCH/MEQ054_records
LOADS=$REC/loads.tsv
TRIALS=$REC/trials.tsv
[ -f "$LOADS" ]  || printf "utc\ttrial\tloadavg\tother_user_busy_procs\n" > "$LOADS"
[ -f "$TRIALS" ] || printf "trial\tseries\tranks\tpinning\trep\tstart_utc\tend_utc\twall_s\trc\tstatus\ttime_integration_s\tmpiexec_cmd\n" > "$TRIALS"
CUM_S=0
[ -f "$REC/cum_wall_s" ] && CUM_S=$(cat "$REC/cum_wall_s")
T0=$(date +%s)

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*" >&2; }   # stderr: visible in driver.log also from $( ) subshells
stop() { log "STOP: $*"; echo "$(ts) $*" > "$REC/STOP"; exit 2; }
elapsed() { echo $(( $(date +%s) - T0 )); }

seq_list() { local a=$1 b=$2 out=""; for ((i=a;i<=b;i++)); do out+="${out:+,}$i"; done; echo "$out"; }

# ---------------- CPU lists (socket 0: physical 0-27, SMT 56-83; socket 1: physical 28-55, SMT 84-111)
# rank -> CPU is sequential in the list (as MEQ-05.2): socket-0 block first, then socket-1 block.
PIN_A56="$(seq_list 0 27),$(seq_list 28 55)"
PIN_P90C="$(seq_list 0 22),$(seq_list 56 78),$(seq_list 28 49),$(seq_list 84 105)"
PIN_P90E="$(seq_list 0 27),$(seq_list 56 72),$(seq_list 28 55),$(seq_list 84 100)"
PIN_Q45S_1="$(seq_list 0 27),$(seq_list 56 72)";  PIN_Q45S_2="$(seq_list 28 55),$(seq_list 84 100)"
PIN_Q45C_1="$(seq_list 0 22),$(seq_list 56 77)";  PIN_Q45C_2="$(seq_list 28 50),$(seq_list 84 105)"
PIN_Q56_1="$(seq_list 0 27),$(seq_list 56 83)";   PIN_Q56_2="$(seq_list 28 55),$(seq_list 84 111)"

check_list() {  # $1 label, $2 list, $3 expected count, $4 expected socket(s) "0", "1" or "01"
    local lab=$1 l=$2 n=$3 sk=$4 c cnt dup pk bad=""
    cnt=$(tr ',' '\n' <<< "$l" | wc -l)
    dup=$(tr ',' '\n' <<< "$l" | sort | uniq -d | wc -l)
    for c in ${l//,/ }; do
        [ "$(cat /sys/devices/system/cpu/cpu$c/online 2>/dev/null || echo 1)" = 1 ] || bad+="cpu$c offline;"
        pk=$(cat /sys/devices/system/cpu/cpu$c/topology/physical_package_id 2>/dev/null || echo X)
        [[ "$sk" == *"$pk"* ]] || bad+="cpu$c pkg=$pk;"
    done
    printf "%s\tcount=%s\texpected=%s\tduplicates=%s\tsocket_check=%s\n" "$lab" "$cnt" "$n" "$dup" "${bad:-ok}" >> "$REC/cpu_list_check.tsv"
    [ "$cnt" -eq "$n" ] && [ "$dup" -eq 0 ] && [ -z "$bad" ] || stop "CPU list $lab: count=$cnt expected=$n dup=$dup bad=[$bad]"
}

preflight_lists() {
    : > "$REC/cpu_list_check.tsv"
    { echo "# lscpu at $(ts)"; lscpu | grep -E '^(CPU\(s\)|On-line|Thread|Core|Socket|NUMA node)'; } >> "$REC/cpu_list_check.tsv"
    check_list CTRL_A56 "$PIN_A56" 56 01
    check_list P90C     "$PIN_P90C" 90 01
    check_list P90E     "$PIN_P90E" 90 01
    check_list Q45S_s0  "$PIN_Q45S_1" 45 0;  check_list Q45S_s1 "$PIN_Q45S_2" 45 1
    check_list Q45C_s0  "$PIN_Q45C_1" 45 0;  check_list Q45C_s1 "$PIN_Q45C_2" 45 1
    check_list Q56_s0   "$PIN_Q56_1" 56 0;   check_list Q56_s1  "$PIN_Q56_2" 56 1
    log "CPU lists checked against lscpu/sysfs: OK"
}

other_busy() {  # CPU-heavy processes of other users (pcpu > 50)
    ps -eo user:20,pcpu,pid,comm --no-headers | awk -v me="$USER" '$1!=me && $2>50 {printf "%s:%s:%s:%s;", $1,$2,$3,$4}'
}

wait_idle() {   # $1 = trial label; wait up to 15 min for loadavg(1 min) < 2 and no model process
    local lab=$1 t=0 l1 busy procs
    while :; do
        procs=$(pgrep -a '^(atmosphere_mod|init_atmospher)' || true)
        l1=$(cut -d' ' -f1 /proc/loadavg)
        busy=$(other_busy)
        if [ -z "$procs" ] && awk -v l="$l1" 'BEGIN{exit !(l<2)}'; then
            printf "%s\t%s\t%s\t%s\n" "$(ts)" "$lab" "$(cat /proc/loadavg)" "${busy:-none}" >> "$LOADS"
            [ -n "$busy" ] && stop "node occupied by third parties before $lab: [$busy]"
            return 0
        fi
        if [ $t -ge 900 ]; then
            printf "%s\t%s\t%s\t%s\n" "$(ts)" "$lab" "$(cat /proc/loadavg)" "${busy:-none}" >> "$LOADS"
            stop "node not idle before $lab after 15 min (load=$l1; procs=[$procs]; other=[$busy])"
        fi
        sleep 30; t=$((t+30))
    done
}

part_file() {  # partition file for N ranks (new ones in MEQ054_partitions, existing ones in partitions/)
    local n=$1
    if [ -e "$BENCH/MEQ054_partitions/$MESH.graph.info.part.$n" ]; then echo "$BENCH/MEQ054_partitions/$MESH.graph.info.part.$n"
    else readlink -f "$BENCH/partitions/$MESH.graph.info.part.$n"; fi
}

make_trial() {  # $1 dir, $2 ranks, $3 streams variant (nooutput|production) -- identical to MEQ-05.2
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
    ln -s "$(readlink "$SRC/$MESH.init.nc")"          "$d/$MESH.init.nc"
    ln -s "$(readlink "$SRC/$MESH.sfc_update.nc")"    "$d/$MESH.sfc_update.nc"
    ln -s "$SRC/restart.2021-11-15_00.00.00.nc"       "$d/restart.2021-11-15_00.00.00.nc"
    for f in "$SRC"/lbc.2021-11-15_*.nc "$SRC"/lbc.2021-11-16_00.00.00.nc; do ln -s "$f" "$d/$(basename "$f")"; done
    ln -s "$BENCH/partitions/$MESH.graph.info" "$d/$MESH.graph.info"
    ln -s "$(part_file "$n")" "$d/$MESH.graph.info.part.$n"
    cp "$BENCH/common/namelist.atmosphere" "$d/namelist.atmosphere"
    cp "$BENCH/common/streams.atmosphere.$sv" "$d/streams.atmosphere"
    diff "$BENCH/common/namelist.atmosphere.orig" "$d/namelist.atmosphere" > "$d/namelist.diff"
    diff "$BENCH/common/streams.atmosphere.orig" "$d/streams.atmosphere"  > "$d/streams.diff"
}

sample_pinning() {  # $1 dir, $2 outfile ; affinity, current CPU and memory of the ranks running in $1
    # samples at 90, 210, 330 s (as MEQ-05.2), then every 120 s until killed
    local d=$1 out=$2 k=0 pid cwd
    while :; do
        k=$((k+1))
        sleep $(( k==1 ? 90 : 120 ))
        {
            echo "### sample $k at $(ts)"
            for pid in $(pgrep '^atmosphere_mod' || true); do
                cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
                [ "$cwd" = "$d" ] || continue
                printf "pid=%s psr=%s %s rss_kb=%s hwm_kb=%s\n" "$pid" "$(ps -o psr= -p "$pid" | tr -d ' ')" \
                    "$(taskset -cp "$pid" 2>/dev/null | sed 's/.*: /affinity=/')" \
                    "$(awk '/^VmRSS/{print $2}' /proc/$pid/status 2>/dev/null)" \
                    "$(awk '/^VmHWM/{print $2}' /proc/$pid/status 2>/dev/null)"
            done
            echo "other_user_busy=$(other_busy)"
            echo "loadavg=$(cat /proc/loadavg)"
        } >> "$out"
    done
}

check_log() {   # $1 dir ; returns non-empty problem string if any (identical to MEQ-05.2)
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

check_third_party() {  # $1 pinning file ; non-empty if any sample saw CPU-heavy processes of other users
    grep '^other_user_busy=.' "$1" 2>/dev/null | head -1
}

outputs_stat() {  # $1 dir ; birth / mtime of written history/restart files (series E90C)
    local d=$1
    printf "file\tbirth_epoch\tmtime_epoch\tsize_bytes\n" > "$d/outputs_stat.tsv"
    for f in "$d"/history.*.nc "$d"/restart.*.nc; do
        [ -L "$f" ] && continue; [ -f "$f" ] || continue
        stat -c $'%n\t%.9W\t%.9Y\t%s' "$f" | sed "s|^$d/||" >> "$d/outputs_stat.tsv"
    done
}

t_int() { awk '$2=="time" && $3=="integration" {print $4; exit}' "$1/log.atmosphere.0000.out" 2>/dev/null; }

budget_tmo() {  # $1 limit ; cap timeout to the remaining 8 h budget, stop if exhausted
    local lim=$1 rem=$(( BUDGET_S - $(elapsed) ))
    [ $rem -le 60 ] && stop "8 h machine-time budget reached (elapsed=$(elapsed)s)"
    [ $rem -lt $lim ] && lim=$rem
    echo $lim
}

status_of() {  # $1 rc, $2 problems, $3 pinning file
    local rc=$1 prob=$2 pf=$3 st=ok tp
    [ $rc -eq 124 ] || [ $rc -eq 137 ] && st="timeout_gt_2x_comparable_MEQ-05.2"
    [ $rc -ne 0 ] && [ "$st" = ok ] && st="rc_$rc"
    [ -n "$prob" ] && st="${st};${prob}"
    tp=$(check_third_party "$pf"); [ -n "$tp" ] && st="${st};third_party_during_run"
    echo "$st"
}

run_one() {   # $1 trial name, $2 series, $3 ranks, $4 pinning label, $5 cpu list, $6 streams, $7 limit s
    local name=$1 ser=$2 n=$3 plab=$4 cpus=$5 sv=$6 lim=$7
    local d=$BENCH/$name rep=${name##*_r} tmo
    [ "$(sha256sum "$EXE" | cut -d' ' -f1)" = "$EXE_SHA" ] || stop "executable sha256 mismatch"
    wait_idle "$name"
    tmo=$(budget_tmo "$lim") || exit 2
    make_trial "$d" "$n" "$sv"
    local cmd="mpiexec -n $n -bind-to user:$cpus ./atmosphere_model"
    echo "$cmd" > "$d/mpiexec_cmd.txt"
    echo "/usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 $tmo $cmd" > "$d/wrapper_cmd.txt"
    log "START $name | $cmd | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d" && /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $cmd > mpas.out 2>&1 ) &
    local mp=$!
    sample_pinning "$d" "$d/pinning_samples.txt" &
    local sp=$!
    wait $mp; local rc=$?
    kill $sp 2>/dev/null; wait $sp 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/cum_wall_s"
    echo "$w" > "$d/wrapper_wall_s.txt"; echo "$st" > "$d/wrapper_start_utc.txt"; ts > "$d/wrapper_end_utc.txt"
    [ "$sv" = production ] && outputs_stat "$d"
    local prob; prob=$(check_log "$d"); local ti; ti=$(t_int "$d")
    local status; status=$(status_of "$rc" "$prob" "$d/pinning_samples.txt")
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$name" "$ser" "$n" "$plab" "$rep" "$st" "$(ts)" "$w" "$rc" "$status" "${ti:-NA}" "$cmd" >> "$TRIALS"
    log "END   $name | rc=$rc | wall=${w}s | t_int=${ti:-NA} | status=$status | cum=${CUM_S}s | elapsed=$(elapsed)s"
    [ "$status" = ok ] || stop "$name failed: $status"
    LAST_TI=$ti
}

need_third() { awk -v a="$1" -v b="$2" -v t="$REP_TOL" 'BEGIN{d=a-b; if(d<0)d=-d; exit !(d/((a+b)/2) > t)}'; }

run_series_point() {  # $1 prefix, then run_one args from series on
    local p=$1; shift
    run_one "${p}_r1" "$@"; local a=$LAST_TI
    run_one "${p}_r2" "$@"; local b=$LAST_TI
    if need_third "$a" "$b"; then log "repetitions differ > 3 % ($a vs $b): 3rd repetition"; run_one "${p}_r3" "$@"; fi
}

run_pair() {   # $1 prefix (e.g. MEQ054_Q45S_N045x2), $2 series, $3 ranks, $4 rep, $5 list s0, $6 list s1, $7 plab s0, $8 plab s1
    local pre=$1 ser=$2 n=$3 r=$4 l1=$5 l2=$6 pl1=$7 pl2=$8 tmo
    [ "$(sha256sum "$EXE" | cut -d' ' -f1)" = "$EXE_SHA" ] || stop "executable sha256 mismatch"
    wait_idle "${pre}_r$r"
    tmo=$(budget_tmo "$LIM_PAIR") || exit 2
    local d1=$BENCH/${pre}_s0_r$r d2=$BENCH/${pre}_s1_r$r
    make_trial "$d1" "$n" nooutput; make_trial "$d2" "$n" nooutput
    local c1="mpiexec -n $n -bind-to user:$l1 ./atmosphere_model"
    local c2="mpiexec -n $n -bind-to user:$l2 ./atmosphere_model"
    echo "$c1" > "$d1/mpiexec_cmd.txt"; echo "$c2" > "$d2/mpiexec_cmd.txt"
    log "START ${pre} r$r | $c1 || $c2 | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d1" && s=$(date +%s); /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $c1 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m1=$!
    ( cd "$d2" && s=$(date +%s); /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $c2 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m2=$!
    sample_pinning "$d1" "$d1/pinning_samples.txt" & local p1=$!
    sample_pinning "$d2" "$d2/pinning_samples.txt" & local p2=$!
    wait $m1; local rc1=$?; wait $m2; local rc2=$?
    kill $p1 $p2 2>/dev/null; wait $p1 $p2 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/cum_wall_s"
    echo "$st" > "$d1/wrapper_start_utc.txt"; echo "$st" > "$d2/wrapper_start_utc.txt"
    echo "$w" > "$d1/pair_wall_s.txt"; echo "$w" > "$d2/pair_wall_s.txt"
    local fail="" i d rc cmd plab prob ti status
    for i in 1 2; do
        if [ $i -eq 1 ]; then d=$d1; rc=$rc1; cmd=$c1; plab=$pl1; else d=$d2; rc=$rc2; cmd=$c2; plab=$pl2; fi
        prob=$(check_log "$d"); ti=$(t_int "$d")
        status=$(status_of "$rc" "$prob" "$d/pinning_samples.txt")
        printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(basename "$d")" "$ser" "$n" "$plab" "$r" "$st" "$(ts)" "$(cat "$d/wrapper_wall_s.txt")" "$rc" "$status" "${ti:-NA}" "$cmd" >> "$TRIALS"
        [ "$status" = ok ] || fail+="$(basename "$d"):$status "
    done
    log "END   ${pre} r$r | rc=$rc1/$rc2 | pair wall=${w}s | t_int=$(t_int "$d1")/$(t_int "$d2") | cum=${CUM_S}s | elapsed=$(elapsed)s"
    [ -z "$fail" ] || stop "${pre} r$r failed: $fail"
    LAST_TI_1=$(t_int "$d1"); LAST_TI_2=$(t_int "$d2")
}

run_pair_point() {  # same args as run_pair minus rep
    local pre=$1 ser=$2 n=$3 l1=$4 l2=$5 pl1=$6 pl2=$7 a1 a2 b1 b2
    run_pair "$pre" "$ser" "$n" 1 "$l1" "$l2" "$pl1" "$pl2"; a1=$LAST_TI_1; a2=$LAST_TI_2
    run_pair "$pre" "$ser" "$n" 2 "$l1" "$l2" "$pl1" "$pl2"; b1=$LAST_TI_1; b2=$LAST_TI_2
    if need_third "$a1" "$b1" || need_third "$a2" "$b2"; then log "$pre repetitions differ > 3 %: 3rd repetition"; run_pair "$pre" "$ser" "$n" 3 "$l1" "$l2" "$pl1" "$pl2"; fi
}

control_check() {  # CTRL_A56 vs MEQ-05.2 A56 cfg_mean_s_per_step
    local ti=$1 sps dev
    sps=$(awk -v t="$ti" 'BEGIN{printf "%.5f", t/360}')
    dev=$(awk -v s="$sps" -v r="$CTRL_REF_S_PER_STEP" 'BEGIN{d=(s-r)/r; printf "%.5f", d}')
    printf "ctrl_s_per_step=%s\tref_A56_cfg_mean_s_per_step=%s\trel_dev=%s\ttolerance=%s\n" "$sps" "$CTRL_REF_S_PER_STEP" "$dev" "$CTRL_TOL" > "$REC/control_check.txt"
    log "CONTROL CTRL_A56 s/step=$sps vs A56 $CTRL_REF_S_PER_STEP (rel dev $dev)"
    awk -v d="$dev" -v t="$CTRL_TOL" 'BEGIN{if(d<0)d=-d; exit !(d>t)}' && stop "CTRL_A56 differs > 3 % from MEQ-05.2 A56 (rel dev $dev)"
    return 0
}

# ------------------------------------------------------------------ main
log "driver start | host=$(hostname) | mpiexec=$(command -v mpiexec) | budget=${BUDGET_S}s | used_before=${BUDGET_USED_S:-0}s | ctrl=${CTRL_NAME:-MEQ054_CTRL_A56_r1} | plan=${PLAN:-default}"
preflight_lists
if [ -n "${PREFLIGHT_ONLY:-}" ]; then for n in 45 56 90; do log "part_file $n -> $(part_file $n)"; done; exit 0; fi
PLAN=${PLAN:-"CTRL P90C P90E Q45S Q45C Q56 E90C"}
for step in $PLAN; do
    [ -f "$REC/STOP" ] && exit 2
    case $step in
        CTRL) run_one "${CTRL_NAME:-MEQ054_CTRL_A56_r1}" CTRL 56 "physical_28+28_block(as_A56)" "$PIN_A56" nooutput $LIM_A56; control_check "$LAST_TI" ;;
        P90C) run_series_point MEQ054_P90C_N090 P90C 90 "compact_cores0-22+28-49_with_SMT_pairs" "$PIN_P90C" nooutput $LIM_A56 ;;
        P90E) run_series_point MEQ054_P90E_N090 P90E 90 "spread_56phys+SMT56-72,84-100" "$PIN_P90E" nooutput $LIM_A56 ;;
        Q45S) run_pair_point MEQ054_Q45S_N045x2 Q45S 45 "$PIN_Q45S_1" "$PIN_Q45S_2" "socket0_0-27+56-72" "socket1_28-55+84-100" ;;
        Q45C) run_pair_point MEQ054_Q45C_N045x2 Q45C 45 "$PIN_Q45C_1" "$PIN_Q45C_2" "socket0_0-22+56-77" "socket1_28-50+84-105" ;;
        Q56)  run_pair_point MEQ054_Q56_N056x2  Q56  56 "$PIN_Q56_1"  "$PIN_Q56_2"  "socket0_0-27+56-83" "socket1_28-55+84-111" ;;
        E90C) run_series_point MEQ054_E90C_N090 E90C 90 "compact_cores0-22+28-49_with_SMT_pairs" "$PIN_P90C" production $LIM_E56 ;;
        *)    stop "unknown plan step $step" ;;
    esac
done
log "driver finished | cum=${CUM_S}s | elapsed=$(elapsed)s"
echo "$(ts) all planned trials finished" > "$REC/DONE"
