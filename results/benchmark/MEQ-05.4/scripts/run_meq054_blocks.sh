#!/usr/bin/env bash
# MEQ-05.5 (Swell dirs keep the MEQ054_ prefix) — revised design: two blocks with same-session references.
# Block order: REF_A56 -> P90C -> P90E -> Q45S -> REF_B112 -> Q45C -> Q56 -> E90C -> REF_A56
# Block 1 = repetition 1, block 2 = repetition 2. Block valid if its two REF_A56 differ <= 3 %
# (time integration); otherwise the block is redone once; a second failure stops the driver.
# Free-node criterion: load(1 min) < 2, no atmosphere_model/init_atmosphere running, no process of
# another user with INSTANTANEOUS CPU > 10 % (5 s /proc sample, cpu_others.py). 3 clean checks 2 min
# apart before each block, 1 before each trial. During trials, every 30 s: other users' CPU and mean
# CPU MHz; a foreign process > 25 % in 2 consecutive samples marks the trial 'interferido'; it runs to
# the end and is repeated once at the end of the block. Max total wait for a free node: 48 h.
# Launch: setsid nohup bash MEQ054_scripts/run_meq054_blocks.sh > MEQ054_records/blocks_driver.log 2>&1 < /dev/null &
# Writes ONLY new MEQ054_* entries inside $BENCH.
set -uo pipefail

ROOT=/p1-swell/danilocs/MPAS-Research
SRC=$ROOT/runs/meqbr_05km_oval_meq02a/20211101_20211201
BENCH=$ROOT/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2
MESH=meqbr_05km_oval_meq02a
EXE=$ROOT/atmosphere_model
EXE_SHA=095ee3b1debac20cf58de77717cc9a7934f61621bef7c393dac765541cd1e494
PY="/usr/bin/python3 -I $BENCH/MEQ054_scripts/cpu_others.py"
USED_BEFORE_S=${USED_BEFORE_S:-1144}  # launch 1+2: trials 897 s; driver 677 s + 467 s = 1144 s
BUDGET_S=$(( 8*3600 - USED_BEFORE_S ))  # machine time left = cumulative trial wall of this driver (pairs once)
WAIT_MAX_S=$(( 48*3600 ))
REF_TOL=0.03
FREE_PCT=10; INTERF_PCT=25
# 2x the wall of the comparable MEQ-05.2 trial: A56 444 s, B112 403.5 s, E56 453.5 s, D pair 1011.5 s
LIM_A56=888; LIM_B112=807; LIM_E=907; LIM_PAIR=2023

source "$HOME/mpas-build/mpas_build_env.sh"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

cd "$BENCH"
REC=$BENCH/MEQ054_records
TRIALS=$REC/blocks_trials.tsv
FREE=$REC/blocks_freecheck.tsv
VALID=$REC/blocks_validity.tsv
[ -f "$TRIALS" ] || printf "trial\tseries\tranks\tpinning\tblock\tattempt\tstart_utc\tend_utc\twall_s\trc\tstatus\ttime_integration_s\tinterferido\tmpiexec_cmd\n" > "$TRIALS"
[ -f "$FREE" ]   || printf "context\tload1\tmodel_procs\tcpu_others_line\tclean\n" > "$FREE"
[ -f "$VALID" ]  || printf "block\tattempt\tref_first_trial\tref_first_t_int\tref_last_trial\tref_last_t_int\trel_diff\tvalid\n" > "$VALID"
CUM_S=0; WAIT_S=0

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "[$(ts)] $*" >&2; }
stop() { log "STOP: $*"; echo "$(ts) $*" > "$REC/STOP"; exit 2; }
seq_list() { local a=$1 b=$2 out=""; for ((i=a;i<=b;i++)); do out+="${out:+,}$i"; done; echo "$out"; }

PIN_A56="$(seq_list 0 27),$(seq_list 28 55)"
PIN_B112="$(seq_list 0 27),$(seq_list 56 83),$(seq_list 28 55),$(seq_list 84 111)"
PIN_P90C="$(seq_list 0 22),$(seq_list 56 78),$(seq_list 28 49),$(seq_list 84 105)"
PIN_P90E="$(seq_list 0 27),$(seq_list 56 72),$(seq_list 28 55),$(seq_list 84 100)"
PIN_Q45S_1="$(seq_list 0 27),$(seq_list 56 72)";  PIN_Q45S_2="$(seq_list 28 55),$(seq_list 84 100)"
PIN_Q45C_1="$(seq_list 0 22),$(seq_list 56 77)";  PIN_Q45C_2="$(seq_list 28 50),$(seq_list 84 105)"
PIN_Q56_1="$(seq_list 0 27),$(seq_list 56 83)";   PIN_Q56_2="$(seq_list 28 55),$(seq_list 84 111)"

check_list() {  # $1 label, $2 list, $3 expected count, $4 expected socket(s)
    local lab=$1 l=$2 n=$3 sk=$4 c cnt dup pk bad=""
    cnt=$(tr ',' '\n' <<< "$l" | wc -l); dup=$(tr ',' '\n' <<< "$l" | sort | uniq -d | wc -l)
    for c in ${l//,/ }; do
        pk=$(cat /sys/devices/system/cpu/cpu$c/topology/physical_package_id 2>/dev/null || echo X)
        [[ "$sk" == *"$pk"* ]] || bad+="cpu$c pkg=$pk;"
    done
    printf "%s\tcount=%s\texpected=%s\tduplicates=%s\tsocket_check=%s\n" "$lab" "$cnt" "$n" "$dup" "${bad:-ok}" >> "$REC/blocks_cpu_list_check.tsv"
    [ "$cnt" -eq "$n" ] && [ "$dup" -eq 0 ] && [ -z "$bad" ] || stop "CPU list $lab: count=$cnt expected=$n dup=$dup bad=[$bad]"
}
preflight_lists() {
    { echo "# lscpu at $(ts)"; lscpu | grep -E '^(CPU\(s\)|On-line|Thread|Core|Socket|NUMA node)'; } > "$REC/blocks_cpu_list_check.tsv"
    check_list REF_A56 "$PIN_A56" 56 01;  check_list REF_B112 "$PIN_B112" 112 01
    check_list P90C "$PIN_P90C" 90 01;    check_list P90E "$PIN_P90E" 90 01
    check_list Q45S_s0 "$PIN_Q45S_1" 45 0; check_list Q45S_s1 "$PIN_Q45S_2" 45 1
    check_list Q45C_s0 "$PIN_Q45C_1" 45 0; check_list Q45C_s1 "$PIN_Q45C_2" 45 1
    check_list Q56_s0 "$PIN_Q56_1" 56 0;   check_list Q56_s1 "$PIN_Q56_2" 56 1
    log "CPU lists checked against lscpu/sysfs: OK"
}

free_check() {  # $1 context ; returns 0 if clean
    local ctx=$1 l1 procs line mx clean=no
    l1=$(cut -d' ' -f1 /proc/loadavg)
    procs=$(pgrep '^(atmosphere_mod|init_atmospher)' | tr '\n' ',' || true)
    line=$($PY 5 - $FREE_PCT 2>&1)
    mx=$(sed -n 's/.*max_other_pct=\([0-9.]*\).*/\1/p' <<< "$line")
    if [ -z "$procs" ] && awk -v l="$l1" -v m="${mx:-999}" -v t=$FREE_PCT 'BEGIN{exit !(l<2 && m<=t)}'; then clean=yes; fi
    printf "%s\t%s\t%s\t%s\t%s\n" "$ctx" "$l1" "${procs:-none}" "$line" "$clean" >> "$FREE"
    [ $clean = yes ]
}

wait_free() {  # $1 context, $2 consecutive clean checks required, $3 spacing s
    local ctx=$1 need=$2 sp=$3 ok=0 t0; t0=$(date +%s)
    while :; do
        if free_check "$ctx"; then ok=$((ok+1)); else ok=0; fi
        [ $ok -ge $need ] && break
        if [ $(( WAIT_S + $(date +%s) - t0 )) -ge $WAIT_MAX_S ]; then
            WAIT_S=$(( WAIT_S + $(date +%s) - t0 )); echo $WAIT_S > "$REC/blocks_wait_s"
            stop "48 h maximum wait for a free node reached before $ctx"
        fi
        sleep $(( ok>0 ? sp : 60 ))
    done
    WAIT_S=$(( WAIT_S + $(date +%s) - t0 )); echo $WAIT_S > "$REC/blocks_wait_s"
}

part_file() {
    local n=$1
    if [ -e "$BENCH/MEQ054_partitions/$MESH.graph.info.part.$n" ]; then echo "$BENCH/MEQ054_partitions/$MESH.graph.info.part.$n"
    else readlink -f "$BENCH/partitions/$MESH.graph.info.part.$n"; fi
}

make_trial() {  # identical to MEQ-05.2 (except partition lookup)
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

sample_pinning() {  # $1 dir, $2 outfile ; affinity / CPU / memory of the ranks (90 s, then every 120 s)
    local d=$1 out=$2 k=0 pid cwd
    while :; do
        k=$((k+1)); sleep $(( k==1 ? 90 : 120 ))
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
            echo "loadavg=$(cat /proc/loadavg)"
        } >> "$out"
    done
}

monitor() {  # $1 cpu list of the trial (all cases), then dirs ; every 30 s: foreign CPU + MHz; flags INTERFERED
    local cpus=$1; shift
    local prev="" cur line p
    while :; do
        line=$($PY 5 "$cpus" $FREE_PCT 2>&1)
        for d in "$@"; do echo "$line" >> "$d/monitor.txt"; done
        cur=$(sed -n 's/.*other=\([^ ]*\) .*/\1/p' <<< "$line" | tr ';' '\n' | awk -F: -v t=$INTERF_PCT '$4>t {print $2}' | sort -u)
        if [ -n "$prev" ] && [ -n "$cur" ]; then
            for p in $cur; do
                grep -qx "$p" <<< "$prev" && for d in "$@"; do echo "$(ts) pid $p > ${INTERF_PCT}% in 2 consecutive samples" >> "$d/INTERFERED"; done
            done
        fi
        prev=$cur
        sleep 25
    done
}

check_log() {   # identical to MEQ-05.2
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
outputs_stat() {
    local d=$1
    printf "file\tbirth_epoch\tmtime_epoch\tsize_bytes\n" > "$d/outputs_stat.tsv"
    for f in "$d"/history.*.nc "$d"/restart.*.nc; do
        [ -L "$f" ] && continue; [ -f "$f" ] || continue
        stat -c $'%n\t%.9W\t%.9Y\t%s' "$f" | sed "s|^$d/||" >> "$d/outputs_stat.tsv"
    done
}
status_of() {  # $1 rc, $2 problems
    local rc=$1 prob=$2 st=ok
    [ $rc -eq 124 ] || [ $rc -eq 137 ] && st="timeout_gt_2x_comparable_MEQ-05.2"
    [ $rc -ne 0 ] && [ "$st" = ok ] && st="rc_$rc"
    [ -n "$prob" ] && st="${st};${prob}"
    echo "$st"
}
budget_tmo() {
    local lim=$1 rem=$(( BUDGET_S - CUM_S ))
    [ $rem -le 60 ] && stop "8 h machine-time budget reached (used before=${USED_BEFORE_S}s, this driver=${CUM_S}s)"
    [ $rem -lt $lim ] && lim=$rem
    echo $lim
}
pre_trial() {  # $1 label
    [ "$(sha256sum "$EXE" | cut -d' ' -f1)" = "$EXE_SHA" ] || stop "executable sha256 mismatch"
    wait_free "trial:$1" 1 60
}

# run_single name series ranks plab cpus streams limit block attempt
run_single() {
    local name=$1 ser=$2 n=$3 plab=$4 cpus=$5 sv=$6 lim=$7 blk=$8 att=$9 d tmo
    d=$BENCH/$name
    pre_trial "$name"
    tmo=$(budget_tmo "$lim") || exit 2
    make_trial "$d" "$n" "$sv"
    local cmd="mpiexec -n $n -bind-to user:$cpus ./atmosphere_model"
    echo "$cmd" > "$d/mpiexec_cmd.txt"
    log "START $name | n=$n | $plab | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d" && /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $cmd > mpas.out 2>&1 ) &
    local mp=$!
    sample_pinning "$d" "$d/pinning_samples.txt" & local sp=$!
    monitor "$cpus" "$d" & local mo=$!
    wait $mp; local rc=$?
    kill $sp $mo 2>/dev/null; wait $sp $mo 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/blocks_cum_wall_s"
    echo "$w" > "$d/wrapper_wall_s.txt"; echo "$st" > "$d/wrapper_start_utc.txt"; ts > "$d/wrapper_end_utc.txt"
    [ "$sv" = production ] && outputs_stat "$d"
    local prob ti status itf=nao
    prob=$(check_log "$d"); ti=$(t_int "$d"); status=$(status_of "$rc" "$prob")
    [ -f "$d/INTERFERED" ] && itf=sim
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$name" "$ser" "$n" "$plab" "$blk" "$att" "$st" "$(ts)" "$w" "$rc" "$status" "${ti:-NA}" "$itf" "$cmd" >> "$TRIALS"
    log "END   $name | rc=$rc | wall=${w}s | t_int=${ti:-NA} | interferido=$itf | status=$status | cum=${CUM_S}s"
    [ "$status" = ok ] || stop "$name failed: $status"
    LAST_TI=$ti; LAST_ITF=$itf
}

# run_pair prefix series ranks list0 list1 plab0 plab1 block attempt
run_pair() {
    local pre=$1 ser=$2 n=$3 l1=$4 l2=$5 pl1=$6 pl2=$7 blk=$8 att=$9 tmo
    pre_trial "$pre"
    tmo=$(budget_tmo "$LIM_PAIR") || exit 2
    local d1=$BENCH/${pre}_s0 d2=$BENCH/${pre}_s1
    make_trial "$d1" "$n" nooutput; make_trial "$d2" "$n" nooutput
    local c1="mpiexec -n $n -bind-to user:$l1 ./atmosphere_model"
    local c2="mpiexec -n $n -bind-to user:$l2 ./atmosphere_model"
    echo "$c1" > "$d1/mpiexec_cmd.txt"; echo "$c2" > "$d2/mpiexec_cmd.txt"
    log "START $pre (pair) | n=$n x2 | timeout ${tmo}s"
    local s0 st; s0=$(date +%s); st=$(ts)
    ( cd "$d1" && s=$(date +%s); /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $c1 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m1=$!
    ( cd "$d2" && s=$(date +%s); /usr/bin/time -v -o time_v.txt timeout --signal=TERM --kill-after=60 "$tmo" $c2 > mpas.out 2>&1; rc=$?; echo $(( $(date +%s)-s )) > wrapper_wall_s.txt; ts > wrapper_end_utc.txt; exit $rc ) &
    local m2=$!
    sample_pinning "$d1" "$d1/pinning_samples.txt" & local p1=$!
    sample_pinning "$d2" "$d2/pinning_samples.txt" & local p2=$!
    monitor "$l1,$l2" "$d1" "$d2" & local mo=$!
    wait $m1; local rc1=$?; wait $m2; local rc2=$?
    kill $p1 $p2 $mo 2>/dev/null; wait $p1 $p2 $mo 2>/dev/null
    local w=$(( $(date +%s) - s0 )); CUM_S=$(( CUM_S + w )); echo $CUM_S > "$REC/blocks_cum_wall_s"
    echo "$st" > "$d1/wrapper_start_utc.txt"; echo "$st" > "$d2/wrapper_start_utc.txt"
    echo "$w" > "$d1/pair_wall_s.txt"; echo "$w" > "$d2/pair_wall_s.txt"
    local fail="" i d rc cmd plab prob ti status itf=nao
    [ -f "$d1/INTERFERED" ] && itf=sim
    for i in 1 2; do
        if [ $i -eq 1 ]; then d=$d1; rc=$rc1; cmd=$c1; plab=$pl1; else d=$d2; rc=$rc2; cmd=$c2; plab=$pl2; fi
        prob=$(check_log "$d"); ti=$(t_int "$d"); status=$(status_of "$rc" "$prob")
        printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(basename "$d")" "$ser" "$n" "$plab" "$blk" "$att" "$st" "$(ts)" "$(cat "$d/wrapper_wall_s.txt")" "$rc" "$status" "${ti:-NA}" "$itf" "$cmd" >> "$TRIALS"
        [ "$status" = ok ] || fail+="$(basename "$d"):$status "
    done
    log "END   $pre | rc=$rc1/$rc2 | pair wall=${w}s | t_int=$(t_int "$d1")/$(t_int "$d2") | interferido=$itf | cum=${CUM_S}s"
    [ -z "$fail" ] || stop "$pre failed: $fail"
    LAST_ITF=$itf
}

run_step() {  # $1 step, $2 prefix, $3 suffix, $4 block, $5 attempt
    local s=$1 P=$2 x=$3 b=$4 a=$5
    case $s in
        REF_A56_first) run_single "${P}_REF_A56_first$x" REF_A56 56 "physical_28+28_block(as_A56)" "$PIN_A56" nooutput $LIM_A56 $b $a ;;
        REF_A56_last)  run_single "${P}_REF_A56_last$x"  REF_A56 56 "physical_28+28_block(as_A56)" "$PIN_A56" nooutput $LIM_A56 $b $a ;;
        REF_B112) run_single "${P}_REF_B112$x" REF_B112 112 "logical_1per_thread_socket_block(as_B112)" "$PIN_B112" nooutput $LIM_B112 $b $a ;;
        P90C) run_single "${P}_P90C_N090$x" P90C 90 "compact_cores0-22+28-49_with_SMT_pairs" "$PIN_P90C" nooutput $LIM_A56 $b $a ;;
        P90E) run_single "${P}_P90E_N090$x" P90E 90 "spread_56phys+SMT56-72,84-100" "$PIN_P90E" nooutput $LIM_A56 $b $a ;;
        E90C) run_single "${P}_E90C_N090$x" E90C 90 "compact_cores0-22+28-49_with_SMT_pairs" "$PIN_P90C" production $LIM_E $b $a ;;
        Q45S) run_pair "${P}_Q45S_N045x2$x" Q45S 45 "$PIN_Q45S_1" "$PIN_Q45S_2" "socket0_0-27+56-72" "socket1_28-55+84-100" $b $a ;;
        Q45C) run_pair "${P}_Q45C_N045x2$x" Q45C 45 "$PIN_Q45C_1" "$PIN_Q45C_2" "socket0_0-22+56-77" "socket1_28-50+84-105" $b $a ;;
        Q56)  run_pair "${P}_Q56_N056x2$x"  Q56  56 "$PIN_Q56_1"  "$PIN_Q56_2"  "socket0_0-27+56-83" "socket1_28-55+84-111" $b $a ;;
        *) stop "unknown step $s" ;;
    esac
}

ORDER="REF_A56_first P90C P90E Q45S REF_B112 Q45C Q56 E90C REF_A56_last"

run_block() {  # $1 block, $2 attempt ; returns 0 if valid
    local b=$1 a=$2 P="MEQ054_B${1}T${2}" s redo="" ref1 ref2 n1 n2
    log "BLOCK $b attempt $a: waiting for 3 clean checks 2 min apart"
    wait_free "block:$b:$a" 3 120
    for s in $ORDER; do
        run_step "$s" "$P" "" "$b" "$a"
        [ "$LAST_ITF" = sim ] && redo+="$s "
        case $s in REF_A56_first) ref1=$LAST_TI; n1="${P}_REF_A56_first" ;; REF_A56_last) ref2=$LAST_TI; n2="${P}_REF_A56_last" ;; esac
    done
    for s in $redo; do
        log "repeating interfered step $s (once) at the end of block $b attempt $a"
        run_step "$s" "$P" "_redo" "$b" "$a"
        case $s in REF_A56_first) ref1=$LAST_TI; n1="${P}_REF_A56_first_redo" ;; REF_A56_last) ref2=$LAST_TI; n2="${P}_REF_A56_last_redo" ;; esac
    done
    local d ok
    d=$(awk -v x="$ref1" -v y="$ref2" 'BEGIN{d=(y-x)/((x+y)/2); printf "%.5f", d}')
    ok=$(awk -v d="$d" -v t=$REF_TOL 'BEGIN{if(d<0)d=-d; print (d<=t)?"yes":"no"}')
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$b" "$a" "$n1" "$ref1" "$n2" "$ref2" "$d" "$ok" >> "$VALID"
    log "BLOCK $b attempt $a: REF_A56 $ref1 vs $ref2 (rel diff $d) valid=$ok"
    [ "$ok" = yes ]
}

# ------------------------------------------------------------------ main
log "blocks driver start | host=$(hostname) | budget=${BUDGET_S}s (8 h - ${USED_BEFORE_S}s) | wait max=${WAIT_MAX_S}s"
preflight_lists
[ -n "${PREFLIGHT_ONLY:-}" ] && { free_check preflight && log "free_check clean" || log "free_check NOT clean"; tail -1 "$FREE" >&2; exit 0; }
for b in ${BLOCKS:-1 2}; do
    [ -f "$REC/STOP" ] && exit 2
    if ! run_block "$b" 1; then
        log "block $b invalid: redoing once"
        run_block "$b" 2 || stop "block $b invalid twice (REF_A56 differ > 3 %)"
    fi
done
log "blocks driver finished | cum=${CUM_S}s | wait=${WAIT_S}s"
echo "$(ts) all blocks finished" > "$REC/DONE"
