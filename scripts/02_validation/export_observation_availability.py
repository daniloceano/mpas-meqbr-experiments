#!/usr/bin/env python
"""Daily availability of the validation observations (report timelines, GOV.4).

For every observational unit used in the report — LiDAR P0 (nov/2021) and LPI
(out/2022) at 100 m, and the INMET stations at 10 m — counts, per day of the
analysis window, the hours with a valid hourly observation.

* LiDAR: ``pairing.observed_hourly`` (QC + ``obs.to_hourly`` as used by the
  pairing, DEC-MEQ-004 limitation unchanged), before any pairing with the model.
* INMET: hours with a non-missing ``obs_speed`` in
  ``results/site_timeseries/inmet_paired.csv.gz``; the INMET hourly product is
  already restricted to the analysis window.

Run on Swell (raw observations live there):

    python scripts/02_validation/export_observation_availability.py

Output: results/tables/observation_availability.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import pairing                             # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

LIDAR_HEIGHT = 100


def daily_counts(times, start, end) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="1D", inclusive="left")
    t = pd.DatetimeIndex(pd.to_datetime(times)).unique()
    t = t[(t >= start) & (t < end)]
    counts = pd.Series(1, index=t).groupby(t.floor("D")).sum()
    return pd.DataFrame({"date": days.strftime("%Y-%m-%d"),
                         "hours_valid": counts.reindex(days, fill_value=0).astype(int).values,
                         "hours_total": 24})


def main() -> int:
    cfg = load_config()
    rows = []
    for period, per in sorted(cfg.periods.items()):
        start, end = pd.Timestamp(per["analysis_start"]), pd.Timestamp(per["analysis_end"])
        site_key = per["validation_site"]
        site = cfg.sites[site_key]
        hourly = pairing.observed_hourly(site, REPO_ROOT, cfg.pairing)
        h = hourly[hourly["model_height"] == LIDAR_HEIGHT]
        d = daily_counts(h["time"], start, end)
        d.insert(0, "network", "LiDAR"); d.insert(1, "point", site_key)
        d.insert(2, "label", f"LiDAR {site_key} · {LIDAR_HEIGHT} m")
        d.insert(3, "period", str(period))
        rows.append(d)
        print(f"{period} LiDAR {site_key}: {int(d.hours_valid.sum())} valid hours")

    inmet = REPO_ROOT / "results" / "site_timeseries" / "inmet_paired.csv.gz"
    if inmet.exists():
        df = pd.read_csv(inmet, parse_dates=["time"], dtype={"station": str})
        names = df.groupby("station")["name"].first().to_dict() if "name" in df else {}
        for (period, station), grp in df.groupby(["period", "station"]):
            per = cfg.periods[str(period)]
            start, end = pd.Timestamp(per["analysis_start"]), pd.Timestamp(per["analysis_end"])
            ok = grp.dropna(subset=["obs_speed"])["time"]
            d = daily_counts(ok, start, end)
            d.insert(0, "network", "INMET"); d.insert(1, "point", station)
            d.insert(2, "label", f"INMET {names.get(station, station)} · 10 m")
            d.insert(3, "period", str(period))
            rows.append(d)
            print(f"{period} INMET {station}: {int(d.hours_valid.sum())} valid hours")
    else:
        print("  (no inmet_paired.csv.gz — INMET skipped)")

    out = cfg.path("results", "tables", "observation_availability.csv")
    out_df = pd.concat(rows, ignore_index=True)
    out_df["source_script"] = "scripts/02_validation/export_observation_availability.py"
    out_df.to_csv(out, index=False)
    print(f"-> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
