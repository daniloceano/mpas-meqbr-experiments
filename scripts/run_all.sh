#!/usr/bin/env bash
# Reproduce the whole analysis, in order, from the raw simulation output.
#
# Safe to re-run: the expensive steps (site extraction, field statistics) are
# incremental or skip existing output, so re-running after a simulation finishes
# only reads the new hours. Run it that way rather than picking scripts by hand —
# the numbered stages exist so that nothing is left stale.
#
#   ./scripts/run_all.sh              # everything
#   ./scripts/run_all.sh 02           # only stage 02 onward
#
# Stages
#   00  inventory: what exists on disk, and is it what config says
#   01  extraction: site time series, field statistics, ERA5, stations
#   02  validation: metrics and figures at the LiDAR sites
#   03  selection: ranking with uncertainty, mechanism and SST-forcing checks
#   04  ERA5: added value, climatological context, resource maps
#   05  exploration: maps, difference maps, cross-sections, animations
set -uo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python}
FROM=${1:-00}
LOG=results/logs
mkdir -p "$LOG"

run() {   # run <label> <command...>
    local label=$1; shift
    echo ""
    echo "=============================================================="
    echo ">> $label"
    echo "=============================================================="
    "$@" 2>&1 | tee "$LOG/${label}.log" | grep -vE "UserWarning|from pandas" || true
    local rc=${PIPESTATUS[0]}
    if [ "$rc" -ne 0 ]; then
        echo "!! $label exited $rc (see $LOG/${label}.log)"
    fi
    return 0
}

stage() { [ "$1" \> "$FROM" ] || [ "$1" = "$FROM" ]; }

# --- 00 inventory ---------------------------------------------------------
if stage 00; then
    run 00_inventory        $PY scripts/00_setup/inventory_experiments.py
fi

# --- 01 extraction --------------------------------------------------------
if stage 01; then
    run 01_sites            $PY scripts/01_extract/extract_site_timeseries.py
    run 01_fields           $PY scripts/01_extract/compute_field_statistics.py
    # A second set of field statistics over the window common to all
    # experiments, for the difference maps while EXP02 is still integrating.
    run 01_fields_common    $PY scripts/01_extract/compute_field_statistics.py \
                               --window common --tag common --force
    run 01_era5_download    $PY scripts/01_extract/download_era5_periods.py
    run 01_era5_sites       $PY scripts/01_extract/extract_era5_sites.py
    run 01_stations         $PY scripts/01_extract/fetch_isd_stations.py
fi

# --- 02 validation --------------------------------------------------------
if stage 02; then
    run 02_metrics          $PY scripts/02_validation/compute_site_metrics.py
    # ... and again over each experiment's own full window, which is the right
    # view for the two completed experiments.
    run 02_metrics_full     $PY scripts/02_validation/compute_site_metrics.py \
                               --no-common-period \
                               --out results/tables/site_metrics_full_window.csv
    run 02_timeseries       $PY scripts/02_validation/plot_timeseries_scatter.py
    run 02_diurnal          $PY scripts/02_validation/plot_diurnal_cycle.py
    run 02_profile          $PY scripts/02_validation/plot_vertical_profile.py
    run 02_taylor           $PY scripts/02_validation/plot_taylor_diagram.py
    run 02_distributions    $PY scripts/02_validation/plot_wind_distributions.py
    run 02_cellsensitivity  $PY scripts/02_validation/check_cell_sensitivity.py
    run 02_stations         $PY scripts/02_validation/validate_surface_stations.py
fi

# --- 03 selection ---------------------------------------------------------
if stage 03; then
    run 03_sst_check        $PY scripts/03_selection/check_sst_forcing.py
    run 03_ranking          $PY scripts/03_selection/rank_experiments.py
    # The completed pair over their full windows: more statistical power than
    # the window EXP02 currently restricts everyone to.
    run 03_ranking_full     $PY scripts/03_selection/rank_experiments.py \
                               --experiments CTL EXP01 --tag fullwindow
    run 03_attribution      $PY scripts/03_selection/attribution_diagnostics.py
fi

# --- 04 ERA5 --------------------------------------------------------------
if stage 04; then
    run 04_added_value      $PY scripts/04_era5/added_value.py
    run 04_added_value_full $PY scripts/04_era5/added_value.py \
                               --experiments CTL EXP01 --tag fullwindow
    run 04_climatology      $PY scripts/04_era5/climatological_context.py --months all
    run 04_resource         $PY scripts/04_era5/resource_comparison.py
fi

# --- 05 exploration -------------------------------------------------------
if stage 05; then
    run 05_mean_fields      $PY scripts/05_exploration/map_mean_fields.py
    run 05_differences      $PY scripts/05_exploration/map_experiment_differences.py \
                               --period 2021 --tag common
    run 05_differences_2022 $PY scripts/05_exploration/map_experiment_differences.py \
                               --period 2022
    for site in P0 LPI; do
        for hour in 3 9 15 21; do
            run "05_xsection_${site}_${hour}" $PY scripts/05_exploration/plot_cross_section.py \
                --site "$site" --experiment CTL --time-of-day "$hour"
        done
    done
    run 05_animation_2021   $PY scripts/05_exploration/animate_wind.py \
                               --experiment CTL --period 2021 --days 5
    run 05_animation_2022   $PY scripts/05_exploration/animate_wind.py \
                               --experiment CTL --period 2022 --days 5
fi

echo ""
echo "done. Tables in results/tables/, figures in figures/, logs in $LOG/."
