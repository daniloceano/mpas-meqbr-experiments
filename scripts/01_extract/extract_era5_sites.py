#!/usr/bin/env python
"""ERA5 time series at the LiDAR sites and at the surface stations.

Produces the reference series that the MPAS runs are scored against in
`scripts/04_era5/added_value.py`. ERA5's 100 m wind is used at the LiDAR sites —
it is ERA5's own hub-height diagnostic, so neither side of the comparison has a
shear extrapolation imposed on it. The 10 m wind is used at the surface stations,
matching their anemometer height.

    python scripts/01_extract/extract_era5_sites.py

Requires scripts/01_extract/download_era5_periods.py to have run.
Output: results/site_timeseries/ERA5_<period>_<SITE>.csv
        results/site_timeseries/ERA5_stations.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import era5                               # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load_config()
    periods = args.period or sorted(cfg.periods)
    station_frames = []
    rc = 0

    for period in periods:
        try:
            ds = era5.open_periods(cfg.era5_periods_dir, period)
        except FileNotFoundError as exc:
            print(f"[{period}] {exc}", file=sys.stderr)
            rc = 1
            continue

        meta = cfg.periods[period]
        # The CDS request expands year x month x day, so trim to the window.
        ds = ds.sel(time=slice(meta["integration_start"], meta["analysis_end"]))

        site_key = meta["validation_site"]
        site = cfg.site(site_key)
        df = era5.at_point(ds, site.lat, site.lon)
        out = cfg.path("results", "site_timeseries", f"ERA5_{period}_{site_key}.csv")
        df.to_csv(out, index=False)
        print(f"[{period}] {site_key}: {len(df)} hours "
              f"({df['time'].min()} -> {df['time'].max()}), "
              f"mean 100 m speed {df['speed_100'].mean():.2f} m/s "
              f"-> {out.relative_to(REPO_ROOT)}")

        for st in cfg.secondary["stations"]:
            sdf = era5.at_point(ds, st["lat"], st["lon"])
            sdf = sdf.assign(station=st["id"], name=st["name"], period=period)
            station_frames.append(sdf)
        ds.close()

    if station_frames:
        allst = pd.concat(station_frames, ignore_index=True)
        out = cfg.path("results", "site_timeseries", "ERA5_stations.csv")
        allst.to_csv(out, index=False)
        print(f"stations: {len(allst)} rows -> {out.relative_to(REPO_ROOT)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
