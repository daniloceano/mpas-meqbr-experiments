# scripts/

The pipeline, in execution order. `./run_all.sh` runs all of it; `./run_all.sh 03`
starts from a stage. Every script takes `--help`, and most take `--experiments`,
`--period` and `--common-period` / `--no-common-period`.

The expensive steps are incremental or skip existing output, so re-running after
a simulation finishes reads only the new hours.

## 00_setup — is the ground truth what config says it is

| Script | Does |
|---|---|
| `link_observations.py` | symlink the two LiDAR files from the sibling poster repo, and verify they read back with the expected shape and period. **Run once after cloning.** |
| `inventory_experiments.py` | per leg: files on disk, time coverage, gaps, spin-up still present, cell count, vertical grid. Writes `results/tables/experiment_inventory.csv` and regenerates `docs/run_status.md`. Exits non-zero if a leg declared complete is not. |

## 01_extract — the heavy pass, run once, cached

| Script | Does | Cost |
|---|---|---|
| `extract_site_timeseries.py` | model profiles + surface diagnostics at the 5 nearest ocean cells to each site. Incremental. | ~7 min/leg cold, seconds warm |
| `compute_field_statistics.py` | domain-wide time-mean fields (speed, cube, vector mean, diurnal composite, surface diagnostics). Use `--window common` when the output will be differenced. | ~1.5 min/leg |
| `download_era5_periods.py` | ERA5 hourly 10 m / 100 m over both windows, with provenance | CDS queue |
| `extract_era5_sites.py` | ERA5 series at the LiDAR sites and the stations | seconds |
| `fetch_isd_stations.py` | public surface stations from NOAA ISD, decoded and QC'd | ~2 min |

## 02_validation — how good is each run at the LiDAR sites

| Script | Produces |
|---|---|
| `compute_site_metrics.py` | `results/tables/site_metrics*.csv` — every score, every experiment, site and height. The quantitative backbone. |
| `plot_timeseries_scatter.py` | time series + density scatter |
| `plot_diurnal_cycle.py` | mean diurnal cycle in local time, with amplitude and phase errors |
| `plot_vertical_profile.py` | mean profile, bias by height, shear exponent |
| `plot_taylor_diagram.py` | correlation / variance / centred RMSE on one plot |
| `plot_wind_distributions.py` | histogram + fitted Weibull, and wind roses |
| `check_cell_sensitivity.py` | the same scores on all five nearest cells — the representativeness floor |
| `validate_surface_stations.py` | 10 m land stations: coastal diurnal cycle and along-coast structure |

## 03_selection — the decision

| Script | Produces |
|---|---|
| `check_sst_forcing.py` | **data-integrity gate.** Audits the SST field each run actually saw; exits non-zero on OISST land-fill contamination. Run this before believing any ranking. |
| `rank_experiments.py` | paired block-bootstrap tests between every experiment pair, plus cost; `results/tables/selection_summary*.md` |
| `attribution_diagnostics.py` | the mechanism: SST → surface fluxes → PBL depth → wind, at the site |
| `boundary_influence.py` | is the `EXP02` − `EXP01` difference organised by distance from the relaxation zone, as the boundary-treatment hypothesis predicts? |

## 04_era5 — is this better than the reanalysis it came from

| Script | Produces |
|---|---|
| `added_value.py` | Murphy skill score vs ERA5 at 100 m, with bootstrap intervals |
| `climatological_context.py` | how typical the simulated months were, against 1990-2020; and the ERA5 baseline resource map |
| `resource_comparison.py` | MPAS vs ERA5 mean wind and WPD, on ERA5's own grid |

## 05_exploration — what the model is actually doing

| Script | Produces |
|---|---|
| `map_mean_fields.py` | mean speed, WPD, directional constancy, diurnal amplitude, on the native mesh |
| `map_experiment_differences.py` | experiment differences on a common lattice; refuses to difference unequal windows |
| `plot_cross_section.py` | coast-normal vertical section — the sea-breeze cell |
| `animate_wind.py` | mp4 (or GIF) of the 100 m wind field |
