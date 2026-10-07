# Data sources and provenance

Every input, where it comes from, how to get it again, and what it can and
cannot support. Machine paths are in `config/paths.local.yaml`; nothing below is
hardcoded in a script.

---

## 1. MPAS simulation output — read in place, never copied

**Location** `runs_root` = `/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km`
**Structure** `<EXP>/<period>/history.YYYY-MM-DD_HH.MM.SS.nc`, one timestep per
file, hourly, 143 MB (`meqbr_05km`) or 178 MB (`meqbr_05km_buf`) each.
**Volume** ~700-1000 files per leg; ~500 GB in total across the set.

The authoritative description of the runs is in the simulation repository, not
here: `runs/meqbr_05km/README.md` (what they share),
`runs/meqbr_05km/EXPERIMENTS.md` (what each one is), and each experiment's own
`README.md` (its delta). `config/experiments.yaml` mirrors only what scripts
need; **if the two ever disagree, the run-side documents win.**

Auxiliary files used from the same directories:

| File | Used for |
|---|---|
| `<mesh>.init.nc` | `zgrid` + terrain together (only place both are guaranteed) |
| `<mesh>.sfc_update.nc` | the SST field `init_atmosphere` case 8 produced — audited by `scripts/03_selection/check_sst_forcing.py` |
| `namelist.atmosphere`, `streams.atmosphere` | archived configuration, per leg |

---

## 2. In-situ LiDAR — primary validation

Neither record has a download script: both were received from their operators.
`scripts/00_setup/link_observations.py` symlinks them from the sibling repository
`mpas-earthsyms2026-analysis`, whose `data/README.md` is the authoritative
description of how each was prepared, and verifies both read back with the
expected shape and period.

### P0 — floating LiDAR

- 2.694107 °S, 42.554807 °W; ~5 km from the modelled coastline.
- `data/obs/P0_LIDAR_matrix.mat`, MATLAB v5 struct `L`, 4831 records at 10 min.
- 2021-11-09 → 2021-12-13, fully inside the `2021` analysis window.
- 20 heights, 40-260 m. Heights used: 50, 100, 150, 200, and (240+260)/2 for the
  model's 250 m level.
- **QC**: per-height `avail` (completeness of the 10-min bin) must be ≥ 80 %.
  96 314 QC-passed height-records.
- The met sensor (`temp`/`press`/`humid`) fails after ~140 records and reports
  exact zeros; only the wind channels are read.

### LPI — fixed LiDAR, Porto-Ilha terminal

- 4.8789425 °S, 37.1478801 °W; offshore terminal, ~9 km from the modelled coast.
- `data/obs/LPI_processed.csv.gz`, already UTC, 10 min.
- 2022-06-23 → 2025-06-06; only the `2022` window overlaps.
- Heights 10, 26, 50, 100, 150, 200 m. Heights used: 50, 100, 150, 200.
- **QC**: physical range only — there is no availability flag. This asymmetry
  with P0 is real and is carried into the caveats rather than papered over.
- 875 991 QC-passed height-records.

---

## 3. INMET automatic stations — primary surface validation

**Why NOAA ISD and not INMET directly.** INMET's own endpoints
(`apitempo.inmet.gov.br`, `portal.inmet.gov.br`) resolve in DNS but the TCP
connection is reset from this host, while other outbound HTTPS works normally
(`www.google.com`, `raw.githubusercontent.com`, `www.ncei.noaa.gov` all return
200). The Brazilian INMET automatic network and the airport reports are
archived internationally in NOAA's Integrated Surface Database, which is
reachable, so that is the access route used. Station ids beginning `817`/`818`
are the INMET automatic stations (on the GTS since 2016-07-04); `822`-`825` are
the older synoptic/airport series.

**Fetch** `scripts/01_extract/fetch_isd_stations.py`
**Inventory** `https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv`
**Data** `https://www.ncei.noaa.gov/data/global-hourly/access/{year}/{station}.csv`
**Provenance** `data/metadata/isd_download.json`
**Coverage table** `results/tables/isd_station_coverage.csv`

The candidate list in `config/sites.yaml` was built by filtering the ISD
inventory to the mesh region and near-coastal latitudes, then probing every
station for data in both 2021 and 2022 (verified 2026-09-02). Stations with
fewer than 200 hours inside a window are dropped at fetch time; 8 survive with
usable coverage, reporting between 7 and 24 hours per day.

The `WND` field is decoded as `direction, dir-quality, type, speed×10,
speed-quality`; ISD quality codes 2/3/6/7 (values the archive's own checks
rejected) are dropped, and multiple reports in one hour are averaged.

**Evidence boundary:** these 10 m land anemometers are primary for the coastal
surface circulation, not offshore hub-height resource. Airport/synoptic records
are supplementary and are never pooled with INMET.

---

## 4. ERA5 for the simulation periods — downloaded here

**Why it had to be downloaded:** the local ERA5 archive (section 5) stops at
2020 and covers neither simulated period.

**Script** `scripts/01_extract/download_era5_periods.py` (cdsapi,
`~/.cdsapirc`)
**Product** `reanalysis-era5-single-levels`
**Variables** `10m_u/v_component_of_wind`, `100m_u/v_component_of_wind`
**Area** 5 / −52 / −10 / −32 (N/W/S/E)
**Cadence** hourly
**Windows** 2021-10-21 → 2021-12-01, 2022-09-21 → 2022-11-01 (full integration
windows, spin-up included)
**Output** `data/era5/era5_wind_<period>.nc` (~113 MB each)
**Provenance** `data/metadata/era5_<period>_download.json` — request, MD5, date

The CDS expands year × month × day, so each file contains a few days outside the
requested window; downstream code trims on the analysis window rather than
assuming.

ERA5's 100 m wind is used at the LiDAR sites — it is ERA5's own hub-height
diagnostic, so no shear extrapolation is imposed on either side of the
comparison. Interpolation to a site is **bilinear**: at 0.25° the nearest grid
point can be 15 km away and, near a coastline, on the wrong side of the land-sea
contrast.

---

## 5. ERA5 1990-2020 archive — read in place

**Location** `/p1-sto-swell/danilocs/ERA5_surface_wind_data_Brazil`
**Contents** 365 monthly files, hourly, 0.25°, `u10`, `v10`, `u100`, `v100`,
box 10 °N-38 °S, 79-29 °W, ~89 GB total. Converted from GRIB by cfgrib in
March 2025 (see each file's `history` attribute).

**Seven months are absent** from the archive (372 expected, 365 present):
2003-08, 2003-09, 2013-10, 2014-07, 2017-03, 2019-01, 2020-05. The scripts skip
missing files silently rather than failing, and the number of years actually
used is recorded in every output — so the October distribution rests on 30 years
and the November one on 31, and
`results/tables/era5_month_representativeness.csv` states which. The gaps are
scattered and small enough not to bias a 30-year distribution, but they are why
the two site-months have different sample sizes.

Used for exactly two things, both in `scripts/04_era5/climatological_context.py`:

1. **Representativeness** — the 1990-2020 distribution of monthly-mean 100 m wind
   at each site for the simulated calendar month, against which the simulated
   month is ranked. ERA5 against ERA5, so unaffected by ERA5's own site bias
   (given that the bias is stationary — see `SCIENTIFIC_NOTES.md`, Assumptions).
2. **Baseline resource** — the climatological mean 100 m wind and WPD map that an
   MPAS-based product would be proposed as an improvement on
   (`results/fields/era5_climatology_map.nc`).

---

## 6. What is generated, and what is version controlled

| Path | Contents | In git? |
|---|---|---|
| `data/metadata/*.json` | download provenance | **yes** |
| `results/tables/*.csv`, `*.md` | every metric and decision table | **yes** — small, and the record of what was decided |
| `data/era5/`, `data/stations/`, `data/obs/` | downloaded or linked inputs | no |
| `results/site_timeseries/`, `results/fields/` | extraction caches | no — regenerate |
| `results/logs/` | pipeline logs | no |
| `figures/` | all figures and animations | no — regenerate |

Nothing large or regenerable is committed. Every figure carries a footer naming
the script, the window and the processing choices that produced it, so a figure
found loose in a slide deck can still be traced back.
