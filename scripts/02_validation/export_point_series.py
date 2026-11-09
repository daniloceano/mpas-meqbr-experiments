#!/usr/bin/env python
"""Export compact hourly wind series per validation point for the HTML report.

The report's observation map lets the reader click a LiDAR or INMET station
and see the observed, ERA5 and MPAS series for that point. Browsers block
``fetch`` of local JSON when ``index.html`` is opened from disk, so each point
is written as a small JavaScript file that registers its data on
``window.MEQ_SERIES`` and is loaded on demand with a ``<script>`` tag.

Sources (all already produced by the validation stage; no raw MPAS history is
opened):
    results/site_timeseries/<EXP>_<period>_<SITE>.nc   (via mpas_meqbr.pairing)
    results/site_timeseries/ERA5_<period>_<SITE>.csv
    results/site_timeseries/inmet_paired.csv.gz

The LiDAR pairing reuses ``pairing.load_paired`` with the common evaluation
window, so the series shown are exactly those scored in
``validation_point_metrics.csv``. ERA5 is attached at 100 m only (see
``pairing.add_era5``).

Run on the host that holds the caches (Swell):
    python scripts/02_validation/export_point_series.py

Output: results/interactive/series/<NETWORK>_<POINT>_<PERIOD>.js
        results/interactive/series/index.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import pairing                            # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402

SOURCES = ["CTL", "EXP01", "EXP02", "EXP03", "EXP04", "EXP05", "EXP06"]


def _values(series: pd.Series, index: pd.DatetimeIndex) -> list:
    s = series[~series.index.duplicated()].reindex(index)
    return [None if not np.isfinite(v) else round(float(v), 2) for v in s.to_numpy()]


def _write(out_dir: Path, key: str, payload: dict) -> Path:
    path = out_dir / f"{key}.js"
    body = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    path.write_text(
        "window.MEQ_SERIES=window.MEQ_SERIES||{};"
        f"window.MEQ_SERIES[{json.dumps(key)}]={body};\n", encoding="utf-8")
    return path


def lidar_points(cfg, out_dir: Path) -> list[dict]:
    rows = []
    for period in sorted(cfg.periods):
        site = cfg.site(cfg.periods[period]["validation_site"])
        frames = pairing.load_paired(cfg, SOURCES, period, common=True)
        if not frames:
            continue
        era5 = pairing.add_era5(frames, cfg, period)
        times = sorted(set().union(*(set(f["time"]) for f in frames.values())))
        index = pd.date_range(min(times), max(times), freq="1h")
        heights = {}
        for height in sorted({int(h) for f in frames.values() for h in f["model_height"]}):
            entry = {}
            ref = None
            for exp, df in frames.items():
                sub = df[df["model_height"] == height].set_index("time")
                if sub.empty:
                    continue
                entry[exp] = _values(sub["mod_speed"], index)
                ref = sub if ref is None else ref
            if ref is None:
                continue
            entry["OBS"] = _values(ref["obs_speed"], index)
            if era5 is not None and height == 100:
                entry["ERA5"] = _values(era5.set_index("time")["era5_speed"], index)
            heights[str(height)] = entry
        key = f"LiDAR_{site.key}_{period}"
        payload = {"network": "LiDAR", "point": site.key, "period": period,
                   "t0": index[0].strftime("%Y-%m-%dT%H:%M"), "dt_h": 1,
                   "n": len(index), "units": "m s-1", "heights": heights}
        path = _write(out_dir, key, payload)
        rows.append({"key": key, "network": "LiDAR", "point": site.key,
                     "period": period, "file": path.name,
                     "heights": list(heights)})
        print(f"  {key}: {len(index)} h, heights {list(heights)}")
    return rows


def inmet_points(out_dir: Path) -> list[dict]:
    path = REPO_ROOT / "results" / "site_timeseries" / "inmet_paired.csv.gz"
    if not path.exists():
        print("  (no inmet_paired.csv.gz — INMET series skipped)")
        return []
    df = pd.read_csv(path, parse_dates=["time"], dtype={"station": str})
    rows = []
    for (period, station), grp in df.groupby(["period", "station"]):
        index = pd.date_range(grp["time"].min(), grp["time"].max(), freq="1h")
        entry = {}
        obs = grp.drop_duplicates("time").set_index("time")["obs_speed"]
        entry["OBS"] = _values(obs, index)
        for source, sub in grp.groupby("source"):
            entry[str(source)] = _values(sub.set_index("time")["model_speed"], index)
        key = f"INMET_{station}_{period}"
        payload = {"network": "INMET", "point": station, "period": str(period),
                   "t0": index[0].strftime("%Y-%m-%dT%H:%M"), "dt_h": 1,
                   "n": len(index), "units": "m s-1", "heights": {"10": entry}}
        out = _write(out_dir, key, payload)
        rows.append({"key": key, "network": "INMET", "point": station,
                     "period": str(period), "file": out.name, "heights": ["10"]})
        print(f"  {key}: {len(index)} h, sources {sorted(entry)}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results/interactive/series")
    args = ap.parse_args()
    cfg = load_config()
    out_dir = REPO_ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    print("LiDAR:")
    rows = lidar_points(cfg, out_dir)
    print("INMET:")
    rows += inmet_points(out_dir)
    if not rows:
        print("nothing exported", file=sys.stderr)
        return 1
    (out_dir / "index.json").write_text(json.dumps(
        {"created_by": "scripts/02_validation/export_point_series.py",
         "created": pd.Timestamp.utcnow().isoformat(), "points": rows},
        indent=1), encoding="utf-8")
    total = sum((out_dir / r["file"]).stat().st_size for r in rows)
    print(f"-> {out_dir.relative_to(REPO_ROOT)}  ({len(rows)} files, {total/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
