#!/usr/bin/env bash
# preproc_prod.sh — MEQ-06.5 preprocessing for the EXP03 production (block 1).
# Stage functions (emit_namelist / emit_streams) copied VERBATIM from
# runs/meqbr_05km_oval_meq02a/preproc_2022/run_preproc_2022.sh (EXP03 2022 leg):
# same init_atmosphere settings, 60 ranks, graph.info.part.60.
#
#   ./preproc_prod.sh --name NAME --cases "7|9|8" --start T --stop T [--init FILE]
#   T = YYYY-MM-DD_HH:MM:SS. Output in $P/preproc/NAME/. Never overwrites: aborts
#   if NAME already holds outputs of the requested cases.
set -uo pipefail
source "$HOME/mpas-build/mpas_build_env.sh"
NAME="" CASES="" START="" STOP="" INIT=""
while [ $# -gt 0 ]; do case "$1" in
  --name) NAME="$2"; shift 2;; --cases) CASES="$2"; shift 2;;
  --start) START="$2"; shift 2;; --stop) STOP="$2"; shift 2;;
  --init) INIT="$2"; shift 2;; *) echo "bad arg $1" >&2; exit 2;; esac; done
NP=60
MESH=meqbr_05km_oval_meq02a
REPO=/p1-swell/danilocs/MPAS-Research
REGION="$REPO/runs/meqbr_05km_oval_meq02a"
PRE="$REGION/preproc_2022"            # static assets (TBL, exe, zeta) as in EXP03
P="$REGION/meq06_production"
W="$P/preproc/$NAME"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# emit_namelist <case> <start> <stop> -- stage flags per init_atmosphere case
emit_namelist() {
    local c="$1" start="$2" stop="$3"
    local static=false vgrid=true metinterp=true insst=false fgint=21600
    case "$c" in
        7|9) ;;                                        # defaults above
        # case 8 reads the daily SST: series, so fg_interval is the SST cadence,
        # not the 6-hourly LBC cadence -- with 21600 it looks for an SST file
        # every 6 h, finds none, and aborts
        8)   vgrid=false; metinterp=false; insst=true; fgint=86400 ;;
    esac
    cat <<EOF
&nhyd_model
    config_init_case = $c
    config_start_time = '$start'
    config_stop_time = '$stop'
    config_theta_adv_order = 3
    config_coef_3rd_order = 0.25
    config_interface_projection = 'linear_interpolation'
/
&dimensions
    config_nvertlevels = 55
    config_nsoillevels = 4
    config_nfglevels = 38
    config_nfgsoillevels = 4
    config_gocartlevels = 30
/
&data_sources
    config_geog_data_path = '$REPO/met_data/WPS_GEOG/'
    config_met_prefix = 'ERA5'
    config_sfc_prefix = 'SST'
    config_fg_interval = $fgint
    config_landuse_data = 'MODIFIED_IGBP_MODIS_NOAH'
    config_soilcat_data = 'STATSGO'
    config_topo_data = 'GMTED2010'
    config_vegfrac_data = 'MODIS'
    config_albedo_data = 'MODIS'
    config_maxsnowalbedo_data = 'MODIS'
    config_supersample_factor = 3
    config_lu_supersample_factor = 1
    config_30s_supersample_factor = 1
    config_use_spechumd = false
/
&vertical_grid
    config_ztop = 30000.0
    config_hybrid_coordinate = true
    config_hybrid_top_z = 30000.0
    config_specified_zeta_levels = 'zeta_wind.txt'
    config_nsmterrain = 1
    config_smooth_surfaces = true
    config_dzmin = 0.3
    config_nsm = 30
    config_tc_vertical_grid = true
    config_blend_bdy_terrain = false
/
&interpolation_control
    config_extrap_airtemp = 'lapse-rate'
/
&preproc_stages
    config_static_interp = $static
    config_native_gwd_static = false
    config_vertical_grid = $vgrid
    config_met_interp = $metinterp
    config_input_sst = $insst
    config_frac_seaice = true
/
&io
    config_pio_num_iotasks = 0
    config_pio_stride = 1
/
&decomposition
    config_block_decomp_file_prefix = '${MESH}.graph.info.part.'
/
EOF
}

# emit_streams <case> -- input source and which output stream is active
emit_streams() {
    local c="$1" input
    # cases 7 and 8 read the static file; only case 9 reads the init file
    case "$c" in
        7|8) input="${MESH}.static.nc" ;;
        *)   input="${MESH}.init.nc" ;;
    esac
    # case 7 writes init.nc through the 'output' stream; 9 and 8 write via their
    # own streams, so 'output' is pointed at a throwaway name
    local outfile="${MESH}.foo.nc"
    [ "$c" = "7" ] && outfile="${MESH}.init.nc"
    cat <<EOF
<streams>
<immutable_stream name="input"
                  type="input"
                  filename_template="$input"
                  input_interval="initial_only" />

<immutable_stream name="output"
                  type="output"
                  filename_template="$outfile"
                  packages="initial_conds"
                  io_type="pnetcdf,cdf5"
                  clobber_mode="overwrite"
                  output_interval="initial_only" />

<immutable_stream name="surface"
                  type="output"
                  filename_template="${MESH}.sfc_update.nc"
                  filename_interval="none"
                  packages="sfc_update"
                  io_type="pnetcdf,cdf5"
                  clobber_mode="overwrite"
                  output_interval="86400" />

<immutable_stream name="lbc"
                  type="output"
                  filename_template="lbc.\$Y-\$M-\$D_\$h.\$m.\$s.nc"
                  filename_interval="output_interval"
                  packages="lbcs"
                  io_type="pnetcdf,cdf5"
                  clobber_mode="overwrite"
                  output_interval="6:00:00" />
</streams>
EOF
}


mkdir -p "$W"; cd "$W" || exit 1
for c in $CASES; do
  case $c in 7) o=${MESH}.init.nc;; 8) o=${MESH}.sfc_update.nc;; 9) o=$(ls lbc.*.nc 2>/dev/null | head -1);; esac
  [ -n "$o" ] && [ -e "$o" ] && { echo "[$(ts)] REFUSE: $W already has $o"; exit 3; }
done
for f in init_atmosphere_model zeta_wind.txt; do ln -sfn "$(readlink -f "$PRE/$f")" .; done
ln -sfn "$(readlink -f "$REGION/${MESH}.static.nc")" .
ln -sfn "$(readlink -f "$REGION/${MESH}.graph.info.part.${NP}")" .
for t in "$PRE"/*.TBL "$PRE"/RRTMG_* "$PRE"/CAM_* "$PRE"/CCN_*; do [ -e "$t" ] && ln -sfn "$(readlink -f "$t")" .; done
[ -n "$INIT" ] && ln -sfn "$INIT" "${MESH}.init.nc"
k_start="${START%%:*}"; k_stop="${STOP%%:*}"
n_era=0
for f in "$P"/met_data/era5/*/ERA5:*; do
  [ -e "$f" ] || continue; b=$(basename "$f"); t="${b#ERA5:}"
  if [[ ! "$t" < "$k_start" ]] && [[ ! "$t" > "$k_stop" ]]; then ln -sfn "$f" .; n_era=$((n_era+1)); fi
done
n_sst=0
for f in "$P"/oisst_corrected/SST:*; do
  b=$(basename "$f"); t="${b#SST:}"
  if [[ ! "$t" < "$k_start" ]] && [[ ! "$t" > "$k_stop" ]]; then ln -sfn "$f" .; n_sst=$((n_sst+1)); fi
done
echo "[$(ts)] $NAME | $START -> $STOP | cases $CASES | linked $n_era ERA5, $n_sst SST"
fail=0
for c in $CASES; do
  emit_namelist "$c" "$START" "$STOP" > namelist.init_atmosphere
  emit_streams "$c" > streams.init_atmosphere
  t0=$(date +%s)
  mpiexec -n "$NP" ./init_atmosphere_model > "init_case${c}.out" 2>&1; rc=$?
  dt=$(( $(date +%s) - t0 ))
  nerr=$(grep -E "^ *(Error|Critical error) messages =" log.init_atmosphere.0000.out 2>/dev/null | awk '{s+=$NF} END{print s+0}')
  cp -f log.init_atmosphere.0000.out "log.init_case${c}.out"; cp -f namelist.init_atmosphere "namelist.init_atmosphere.case${c}"; cp -f streams.init_atmosphere "streams.init_atmosphere.case${c}"
  if [ "$rc" -eq 0 ] && [ "$nerr" -eq 0 ]; then echo "[$(ts)] case $c OK ${dt}s"; else echo "[$(ts)] case $c FAILED rc=$rc errors=$nerr ${dt}s"; fail=1; break; fi
done
rm -f ${MESH}.foo.nc
echo "[$(ts)] $NAME done exit=$fail init=$(ls ${MESH}.init.nc 2>/dev/null|wc -l) lbc=$(ls lbc.*.nc 2>/dev/null|wc -l) sfc=$(ls ${MESH}.sfc_update.nc 2>/dev/null|wc -l)"
exit $fail
