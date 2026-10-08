#!/usr/bin/env python
"""Download public surface-station wind for the simulation periods (NOAA NCEI ISD).

Why ISD rather than INMET directly: INMET's own API and portal
(`apitempo.inmet.gov.br`, `portal.inmet.gov.br`) are not reachable from this
host — the TCP connection is reset, while other outbound HTTPS works. The
Brazilian automatic stations (the INMET "A" network) and the airport reports are
archived internationally in NOAA's Integrated Surface Database, which is
reachable, so that is the access route used here. The station list in
`config/sites.yaml` distinguishes the hourly INMET automatic stations from the
older synoptic/airport series, which report fewer hours per day.

Automatic INMET stations are the primary surface-validation axis. They are
kept separate from the primary offshore LiDAR axis because 10 m land wind and
50-250 m offshore wind answer different questions. Airport/synoptic series are
downloaded only as a supplementary exposure check and are never pooled with
INMET. Read `docs/validation_protocol.md` before interpreting either axis.

    python scripts/01_extract/fetch_isd_stations.py [--force]

Output: data/stations/isd_<station>_<year>.csv (raw, as downloaded)
        data/stations/isd_hourly.csv.gz        (decoded, QC'd, all stations)
        data/metadata/isd_download.json        (provenance)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import obs                                # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402

TIMEOUT = 120


def fetch(url: str, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return False
            dest.write_bytes(resp.read())
        return dest.stat().st_size > 1000
    except Exception as exc:                              # noqa: BLE001
        print(f"    {url} -> {exc}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    sec = cfg.surface
    raw_dir = REPO_ROOT / "data" / "stations"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Each period's ISD year, and the window to keep (integration window, so the
    # station series covers spin-up too and can show when the run departs).
    windows = {p: (pd.Timestamp(m["integration_start"]), pd.Timestamp(m["analysis_end"]))
               for p, m in cfg.periods.items()}

    frames, records = [], []
    for st in sec["stations"]:
        for period, (w0, w1) in windows.items():
            year = w0.year
            dest = raw_dir / f"isd_{st['id']}_{year}.csv"
            if not dest.exists() or args.force:
                url = sec["url"].format(year=year, station=st["id"])
                print(f"  {st['name'][:34]:34s} {year} ...", end=" ", flush=True)
                ok = fetch(url, dest)
                print("ok" if ok else "MISSING")
                if not ok:
                    dest.unlink(missing_ok=True)
                    continue
            if not dest.exists():
                continue

            raw = pd.read_csv(dest, low_memory=False)
            decoded = obs.parse_isd_wind(
                raw,
                exclude_quality_codes=tuple(sec["qc"]["exclude_quality_codes"]),
                speed_range=tuple(sec["qc"]["speed_range_ms"]),
            )
            decoded = decoded[(decoded["time"] >= w0) & (decoded["time"] <= w1)]
            if len(decoded) < sec["qc"]["min_records_per_period"]:
                print(f"    {st['name']} {period}: only {len(decoded)} records "
                      f"in window — excluded")
                continue
            decoded = decoded.assign(station=st["id"], name=st["name"],
                                     lat=st["lat"], lon=st["lon"],
                                     kind=st["kind"], period=period)
            frames.append(decoded)
            # Hours-per-day tells a reader immediately whether a station can
            # support a diurnal-cycle statement or only a daytime one.
            days = decoded["time"].dt.normalize().nunique()
            records.append({
                "station": st["id"], "name": st["name"], "period": period,
                "lat": st["lat"], "lon": st["lon"], "kind": st["kind"],
                "n_hours": int(len(decoded)), "n_days": int(days),
                "hours_per_day": round(len(decoded) / max(days, 1), 1),
                "start": str(decoded["time"].min()), "end": str(decoded["time"].max()),
            })

    if not frames:
        print("no station data retrieved", file=sys.stderr)
        return 1

    all_obs = pd.concat(frames, ignore_index=True).sort_values(["station", "time"])
    out = cfg.path("data", "stations", "isd_hourly.csv.gz")
    all_obs.to_csv(out, index=False, compression="gzip")

    summary = pd.DataFrame(records)
    print("\n" + summary.to_string(index=False))
    summary_path = cfg.path("results", "tables", "isd_station_coverage.csv")
    summary.to_csv(summary_path, index=False)

    meta = cfg.path("data", "metadata", "isd_download.json")
    meta.write_text(json.dumps({
        "dataset": "NOAA NCEI Integrated Surface Database (ISD), global-hourly",
        "source_url": sec["url"],
        "inventory_url": sec["inventory_url"],
        "why_not_inmet": (
            "INMET's own API/portal is not reachable from this host (connection "
            "reset); ISD is where the same stations are internationally archived."
        ),
        "variables": ["WND (direction, speed) at 10 m"],
        "qc": sec["qc"],
        "periods": {p: [str(w[0]), str(w[1])] for p, w in windows.items()},
        "download_date": datetime.now(timezone.utc).isoformat(),
        "downloaded_by": "Danilo Couto de Souza",
        "tool": "urllib (plain HTTP)",
        "files": [str(out.relative_to(REPO_ROOT))],
        "stations": records,
        "caveat": (
            "Primary surface-validation data at 10 m over land; kept separate "
            "from the offshore hub-height LiDAR axis. Airport/synoptic records "
            "are supplementary and are never pooled with INMET."
        ),
    }, indent=2))

    print(f"\n-> {out.relative_to(REPO_ROOT)} ({len(all_obs):,} hourly records)")
    print(f"-> {summary_path.relative_to(REPO_ROOT)}")
    print(f"-> {meta.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
