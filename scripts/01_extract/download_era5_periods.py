#!/usr/bin/env python
"""Download ERA5 hourly 10 m and 100 m wind over the two simulation windows.

Why this download exists: the local ERA5 archive on this machine
(``/p1-sto-swell/danilocs/ERA5_surface_wind_data_Brazil``) stops at 2020 and so
does not cover either simulated period. ERA5 for 2021-11 and 2022-10 is needed
because ERA5 *is* the model's forcing — the MPAS-vs-ERA5 comparison at the LiDAR
sites is what quantifies the added value of the downscaling, which is the whole
argument for using these runs as an ERA5 alternative for wind resource work.

Dataset : ERA5 reanalysis, single levels (reanalysis-era5-single-levels)
Variables: 10m_u/v_component_of_wind, 100m_u/v_component_of_wind
Period  : full integration windows, spin-up included
          2021-10-21 -> 2021-12-01 ; 2022-09-21 -> 2022-11-01
Area    : 5 / -52 / -10 / -32 (N/W/S/E) — covers the mesh interior and both sites
Cadence : hourly
Tool    : cdsapi (credentials in ~/.cdsapirc)
Output  : data/era5/era5_wind_<period>.nc  + data/metadata/era5_<period>_download.json

    python scripts/01_extract/download_era5_periods.py [--period 2021] [--force]

Re-runnable: an existing, non-empty output file is kept unless --force is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr.config import load_config, REPO_ROOT  # noqa: E402

AREA = [5, -52, -10, -32]          # N, W, S, E
VARIABLES = [
    "10m_u_component_of_wind", "10m_v_component_of_wind",
    "100m_u_component_of_wind", "100m_v_component_of_wind",
]
# Full integration windows (spin-up included) so the ERA5 series can also be
# used to look at how the run departs from its forcing during spin-up.
WINDOWS = {
    "2021": ("2021-10-21", "2021-12-01"),
    "2022": ("2022-09-21", "2022-11-01"),
}


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def request_for(period: str) -> dict:
    import pandas as pd

    start, end = WINDOWS[period]
    days = pd.date_range(start, end, freq="D")
    return {
        "product_type": ["reanalysis"],
        "variable": VARIABLES,
        "year": sorted({f"{d.year}" for d in days}),
        "month": sorted({f"{d.month:02d}" for d in days}),
        "day": sorted({f"{d.day:02d}" for d in days}),
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", choices=sorted(WINDOWS) + ["all"], default="all")
    ap.add_argument("--force", action="store_true",
                    help="re-download even if the output file already exists")
    args = ap.parse_args()

    import cdsapi

    cfg = load_config()
    out_dir = cfg.era5_periods_dir
    meta_dir = REPO_ROOT / "data" / "metadata"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    periods = sorted(WINDOWS) if args.period == "all" else [args.period]
    client = cdsapi.Client()
    rc = 0

    for period in periods:
        out = out_dir / f"era5_wind_{period}.nc"
        if out.exists() and out.stat().st_size > 0 and not args.force:
            print(f"[skip] {out} already present ({out.stat().st_size/1e6:.1f} MB)")
            continue

        req = request_for(period)
        start, end = WINDOWS[period]
        print(f"[{period}] requesting {start} -> {end}, area {AREA} ...", flush=True)
        try:
            client.retrieve("reanalysis-era5-single-levels", req, str(out))
        except Exception as exc:                       # noqa: BLE001
            print(f"[{period}] FAILED: {exc}", file=sys.stderr)
            rc = 1
            continue

        # The CDS request is by (year, month, day) cross-product, so it returns
        # a superset of the window when it straddles two months. Record the
        # intended window so downstream code trims rather than assuming.
        meta = {
            "dataset": "ERA5",
            "product": "reanalysis-era5-single-levels",
            "source": "Copernicus Climate Data Store (cdsapi)",
            "source_url": "https://cds.climate.copernicus.eu",
            "variables": VARIABLES,
            "area_N_W_S_E": AREA,
            "period": {"start": start, "end": end},
            "note_request_is_superset": (
                "CDS expands year x month x day, so the file may contain days "
                "outside [start, end]; trim on the analysis window when using it."
            ),
            "temporal_resolution": "hourly",
            "format": "netcdf",
            "request": req,
            "download_date": datetime.now(timezone.utc).isoformat(),
            "downloaded_by": "Danilo Couto de Souza",
            "tool": "cdsapi",
            "files": [str(out.relative_to(REPO_ROOT))],
            "size_bytes": out.stat().st_size,
            "checksum_md5": _md5(out),
            "purpose": (
                "ERA5 reference for the MPAS-vs-ERA5 added-value comparison at "
                "the P0 and LPI LiDAR sites, and for ERA5-vs-MPAS resource maps. "
                "ERA5 is also the runs' own forcing, which is what makes the "
                "comparison a clean statement about downscaling."
            ),
        }
        meta_path = meta_dir / f"era5_{period}_download.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        print(f"[{period}] wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
        print(f"[{period}] provenance -> {meta_path.relative_to(REPO_ROOT)}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
