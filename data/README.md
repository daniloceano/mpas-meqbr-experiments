# data/

Inputs to the analysis. The MPAS output itself is **not** here — it is read in
place from `runs_root` (see `config/paths.local.yaml`). This folder holds only
the observational and reanalysis data that the model is compared against.

Full provenance, including how each was obtained and what it can support:
[`../docs/data_sources.md`](../docs/data_sources.md).

```
obs/       P0_LIDAR_matrix.mat, LPI_processed.csv.gz
           Symlinks into the sibling repo mpas-earthsyms2026-analysis, created by
           scripts/00_setup/link_observations.py. Gitignored. Neither record has a
           download script: both were received from their operators.

era5/      era5_wind_2021.nc, era5_wind_2022.nc
           Hourly 10 m / 100 m wind over both simulation windows, downloaded by
           scripts/01_extract/download_era5_periods.py. ~113 MB each, gitignored.

stations/  isd_<station>_<year>.csv   raw NOAA NCEI ISD, as downloaded
           isd_hourly.csv.gz          decoded, QC'd, all stations and periods
           Fetched by scripts/01_extract/fetch_isd_stations.py. Gitignored.

metadata/  *.json — provenance for every download: the exact request, the file
           checksum, the date, and what the data is for. Version controlled.
```

## Rules

- Raw data is never committed. Provenance always is.
- Nothing in `obs/` is regenerable — if a link breaks, re-run
  `scripts/00_setup/link_observations.py`, or `--copy` it if the sibling repo is
  not available on this machine.
- Both download scripts are re-runnable and skip work already done; pass
  `--force` to refetch.
