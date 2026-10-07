#!/usr/bin/env python
"""Extract model time series at the LiDAR sites — the pipeline's one heavy step.

Everything downstream (validation, experiment ranking, ERA5 comparison) reads
the small NetCDF files this produces, so the ~700 history files per leg are
traversed exactly once. Re-running is incremental: only timestamps not already
in the output file are read, which is what makes it cheap to refresh while
EXP02 is still integrating.

What is extracted, per (experiment, period):

* the ``--n-cells`` nearest **ocean** cells to the site (default 5). Only the
  first is used by the standard analysis; the rest exist so the sensitivity of
  every conclusion to that single-cell choice can be tested rather than assumed
  (``scripts/02_validation/check_cell_sensitivity.py``).
* full vertical profiles of wind, potential temperature, pressure and relative
  humidity at those cells — the profile, not just the comparison heights, so
  shear and boundary-layer structure can be looked at without another pass.
* the surface and boundary-layer diagnostics that explain *why* experiments
  differ: SST and skin temperature, sensible and latent heat flux, PBL height,
  friction velocity, roughness, and the Monin-Obukhov stability parameter.

    python scripts/01_extract/extract_site_timeseries.py
    python scripts/01_extract/extract_site_timeseries.py --experiments EXP02 --period 2021

Output: results/site_timeseries/<EXP>_<period>_<SITE>.nc
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, mesh, vertical                 # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402

VARS_3D = ["uReconstructZonal", "uReconstructMeridional", "theta", "pressure", "relhum"]
VARS_2D = ["u10", "v10", "t2m", "q2", "surface_pressure", "hpbl", "ust", "znt",
           "zol", "hfx", "lh", "qfx", "sst", "skintemp", "precipw"]


def locate_cells(leg, site, n_cells: int):
    """Nearest ocean cells to the site, on this leg's own mesh.

    The two meshes do not share cell indices, so this is done per leg and the
    result is stored with the output — never reused across experiments.
    """
    sample = io.find_history_files(leg.history_dir)[0]
    static = io.read_static(sample)
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    matches = mesh.nearest_cells(lat, lon, site.lat, site.lon,
                                 landmask=static["landmask"], ocean_only=True,
                                 k=n_cells)
    zgrid = io.read_static(sample, ["zgrid"])["zgrid"]
    heights = np.stack([vertical.heights_above_ground(zgrid[m.index])
                        for m in matches])
    return matches, heights, static


def existing_times(path: Path) -> pd.DatetimeIndex:
    if not path.exists():
        return pd.DatetimeIndex([])
    with xr.open_dataset(path) as ds:
        return pd.DatetimeIndex(ds["time"].values)


def extract_leg(leg, site, cfg, *, n_cells: int, force: bool) -> Path | None:
    out = cfg.path("results", "site_timeseries", f"{leg.key}_{site.key}.nc")
    files = io.find_history_files(leg.history_dir)
    if not files:
        print(f"[{leg.key}] no history files yet — skipping")
        return None

    index = io.select_window(io.history_index(leg.history_dir),
                             leg.analysis_start, leg.analysis_end)
    if len(index) == 0:
        print(f"[{leg.key}] no files inside the analysis window yet — skipping")
        return None

    have = pd.DatetimeIndex([]) if force else existing_times(out)
    todo = index.loc[~index.index.isin(have)]
    if len(todo) == 0:
        print(f"[{leg.key}] up to date ({len(have)} hours) — nothing to do")
        return out

    matches, heights, static = locate_cells(leg, site, n_cells)
    print(f"[{leg.key}] site {site.key} -> nearest ocean cells: " +
          ", ".join(f"#{m.index} ({m.distance_km:.1f} km)" for m in matches))
    print(f"[{leg.key}] reading {len(todo)} new hours "
          f"({len(have)} already present)...", flush=True)

    cells = [m.index for m in matches]
    n_lev = heights.shape[1]
    data3 = {v: np.full((len(todo), len(cells), n_lev), np.nan, np.float32)
             for v in VARS_3D}
    data2 = {v: np.full((len(todo), len(cells)), np.nan, np.float32)
             for v in VARS_2D}

    t0 = time.time()
    for i, path in enumerate(todo.values):
        chunk = io.read_cell_columns(path, VARS_3D + VARS_2D, cells)
        for v in VARS_3D:
            if v in chunk:
                data3[v][i] = chunk[v]
        for v in VARS_2D:
            if v in chunk:
                data2[v][i] = chunk[v]
        if (i + 1) % 100 == 0:
            rate = (i + 1) / (time.time() - t0)
            print(f"    {i+1}/{len(todo)} files ({rate:.1f}/s, "
                  f"{(len(todo)-i-1)/rate:.0f}s left)", flush=True)

    coords = {
        "time": todo.index,
        "cell": np.arange(len(cells)),
        "level": np.arange(n_lev),
    }
    ds = xr.Dataset(
        {v: (("time", "cell", "level"), data3[v]) for v in VARS_3D} |
        {v: (("time", "cell"), data2[v]) for v in VARS_2D},
        coords=coords,
    )
    ds["height_agl"] = (("cell", "level"), heights.astype(np.float32))
    ds["cell_index"] = (("cell",), np.array(cells, np.int32))
    ds["cell_lat"] = (("cell",), np.array([m.lat for m in matches], np.float32))
    ds["cell_lon"] = (("cell",), np.array([m.lon for m in matches], np.float32))
    ds["cell_distance_km"] = (("cell",),
                              np.array([m.distance_km for m in matches], np.float32))

    ds["uReconstructZonal"].attrs["units"] = "m s-1"
    ds["height_agl"].attrs["long_name"] = "layer-center height above local terrain"
    ds["height_agl"].attrs["units"] = "m"
    ds.attrs.update({
        "experiment": leg.experiment,
        "period": leg.period,
        "mesh": leg.mesh,
        "site": site.key,
        "site_label": site.label,
        "site_lat": site.lat,
        "site_lon": site.lon,
        "analysis_start": str(leg.analysis_start),
        "analysis_end": str(leg.analysis_end),
        "history_dir": str(leg.history_dir),
        "cells_are": "nearest OCEAN cells (landmask == 0); cell 0 is the one used by default",
        "created": datetime.now(timezone.utc).isoformat(),
        "created_by": "scripts/01_extract/extract_site_timeseries.py",
    })

    if len(have) and not force:
        with xr.open_dataset(out) as old:
            old = old.load()
        ds = xr.concat(
            [old, ds], dim="time", data_vars="minimal", coords="minimal",
            compat="equals", combine_attrs="override",
        ).sortby("time")
        ds = ds.isel(time=~pd.Index(ds["time"].values).duplicated())
    tmp = out.with_suffix(".tmp.nc")
    ds.to_netcdf(tmp)
    tmp.replace(out)
    print(f"[{leg.key}] -> {out.relative_to(REPO_ROOT)} "
          f"({ds.sizes['time']} hours, {time.time()-t0:.0f}s)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--n-cells", type=int, default=5,
                    help="how many nearest ocean cells to keep (default 5)")
    ap.add_argument("--force", action="store_true",
                    help="re-read everything instead of updating incrementally")
    ap.add_argument("--runs-root", default=None)
    args = ap.parse_args()

    cfg = load_config(runs_root=args.runs_root)
    experiments = args.experiments or cfg.experiment_keys
    rc = 0
    for exp in experiments:
        for period in (args.period or cfg.experiments[exp]["periods"]):
            leg = cfg.leg(exp, period)
            site = cfg.site(leg.validation_site)
            try:
                extract_leg(leg, site, cfg, n_cells=args.n_cells, force=args.force)
            except Exception as exc:                      # noqa: BLE001
                print(f"[{leg.key}] FAILED: {exc}", file=sys.stderr)
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
