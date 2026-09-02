"""Time-averaged horizontal fields on the native mesh.

Maps and resource statistics need the whole domain, which the site extraction
deliberately does not keep. Rather than re-reading ~700 files every time a map
is drawn, this accumulates the statistics in a single pass and caches them as a
small NetCDF per leg (``results/fields/<EXP>_<period>_fields.nc``).

What is accumulated, and why each one:

``mean_speed_100``   the resource-relevant mean wind at hub height
``mean_cube_100``    mean of U**3 — wind power density needs the cube averaged
                     before the mean, so it has to be accumulated, not derived
                     from ``mean_speed_100`` afterwards
``mean_u/v_100``     vector mean, which with ``mean_speed_100`` also gives the
                     directional constancy (steadiness) of the flow
``diurnal_speed_100`` 24 local-hour means — the sea-breeze signal, and the part
                     of the field a 31 km reanalysis is least able to resolve
``mean_*`` 2D        surface and boundary-layer diagnostics used to explain
                     *why* two experiments differ (SST, fluxes, PBL height)

Averaging window is stored in the file attributes and must be checked before
differencing two legs: EXP02 is still integrating, and a difference between two
different windows is a difference in weather, not in model configuration.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import io, vertical

FIELDS_2D = ["u10", "v10", "t2m", "hpbl", "hfx", "lh", "sst", "skintemp",
             "ust", "znt", "precipw"]
TZ_OFFSET_HOURS = -3          # local solar time on this coast


def compute_leg_fields(leg, index: pd.Series, *, height_m: float = 100.0,
                       tolerance_m: float = 1.0, progress_every: int = 100) -> xr.Dataset:
    """One pass over *index* (time -> file), accumulating the statistics above.

    The level index for *height_m* is derived per cell from ``zgrid``, so over
    terrain the sampled height follows the terrain-following coordinate exactly
    as the model does. Over the ocean, where the resource question lives, the
    centres are the nominal 50/100/150/200 m.
    """
    first = index.iloc[0]
    static = io.read_static(first)
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    n_cells = lat.size

    heights = vertical.heights_above_ground(static["zgrid"])       # (nCells, nLev)
    k_per_cell = np.argmin(np.abs(heights - height_m), axis=1)
    ocean = np.flatnonzero(static["landmask"] == 0)
    vertical.match_heights(heights[ocean[0]], [height_m], tolerance_m)
    # The vertical grid is specified in height *above terrain*, so the layer
    # centres are the same AGL everywhere and one level index serves the whole
    # mesh. Verified rather than assumed: if a future mesh breaks it, the
    # per-cell path below still gives the right answer, just more slowly.
    uniform_level = int(k_per_cell[0]) if np.ptp(k_per_cell) == 0 else None

    acc = {name: np.zeros(n_cells) for name in
           ("speed", "cube", "u", "v", "speed_sq")}
    acc2d = {name: np.zeros(n_cells) for name in FIELDS_2D}
    count2d = {name: 0 for name in FIELDS_2D}
    diurnal_sum = np.zeros((24, n_cells))
    diurnal_n = np.zeros(24)
    n = 0

    local_hours = (pd.DatetimeIndex(index.index)
                   + pd.Timedelta(hours=TZ_OFFSET_HOURS)).hour
    t0 = time.time()
    rows = np.arange(n_cells)

    from netCDF4 import Dataset
    for i, (path, hour) in enumerate(zip(index.values, local_hours)):
        with Dataset(path) as ds:
            if uniform_level is not None:
                u = np.asarray(ds.variables["uReconstructZonal"][0, :, uniform_level])
                v = np.asarray(ds.variables["uReconstructMeridional"][0, :, uniform_level])
            else:
                u = np.asarray(ds.variables["uReconstructZonal"][0, :, :])[rows, k_per_cell]
                v = np.asarray(ds.variables["uReconstructMeridional"][0, :, :])[rows, k_per_cell]
            two_d = {name: np.asarray(ds.variables[name][0, :])
                     for name in FIELDS_2D if name in ds.variables}

        speed = np.hypot(u, v)
        acc["speed"] += speed
        acc["speed_sq"] += speed ** 2
        acc["cube"] += speed ** 3
        acc["u"] += u
        acc["v"] += v
        diurnal_sum[hour] += speed
        diurnal_n[hour] += 1
        for name, values in two_d.items():
            acc2d[name] += values
            count2d[name] += 1
        n += 1
        if progress_every and (i + 1) % progress_every == 0:
            rate = (i + 1) / (time.time() - t0)
            print(f"    {i+1}/{len(index)} ({rate:.1f}/s, "
                  f"{(len(index)-i-1)/rate:.0f}s left)", flush=True)

    mean_speed = acc["speed"] / n
    ds_out = xr.Dataset(
        {
            "mean_speed_100": ("nCells", mean_speed),
            "mean_cube_100": ("nCells", acc["cube"] / n),
            "std_speed_100": ("nCells", np.sqrt(np.maximum(
                acc["speed_sq"] / n - mean_speed ** 2, 0.0))),
            "mean_u_100": ("nCells", acc["u"] / n),
            "mean_v_100": ("nCells", acc["v"] / n),
            "diurnal_speed_100": (("local_hour", "nCells"),
                                  diurnal_sum / np.maximum(diurnal_n, 1)[:, None]),
        } | {
            f"mean_{name}": ("nCells", acc2d[name] / max(count2d[name], 1))
            for name in FIELDS_2D if count2d[name] > 0
        },
        coords={"lat": ("nCells", lat), "lon": ("nCells", lon),
                "local_hour": np.arange(24)},
    )
    ds_out["landmask"] = ("nCells", static["landmask"].astype("int8"))
    ds_out["terrain"] = ("nCells", static["zgrid"][:, 0])
    ds_out["level_index"] = ("nCells", k_per_cell.astype("int16"))

    # Directional constancy: |vector mean| / scalar mean. 1 = perfectly steady
    # trade-wind flow, low values = a wind that reverses (sea breeze, or a
    # site under alternating synoptic regimes).
    ds_out["constancy_100"] = ("nCells", np.hypot(acc["u"], acc["v"]) / np.maximum(acc["speed"], 1e-9))

    ds_out.attrs.update({
        "experiment": leg.experiment,
        "period": leg.period,
        "mesh": leg.mesh,
        "height_m": height_m,
        "window_start": str(index.index[0]),
        "window_end": str(index.index[-1]),
        "n_hours": int(n),
        "tz_offset_hours": TZ_OFFSET_HOURS,
        "created": datetime.now(timezone.utc).isoformat(),
        "created_by": "scripts/01_extract/compute_field_statistics.py",
    })
    return ds_out


def wind_power_density_field(ds: xr.Dataset, rho: float = 1.15) -> np.ndarray:
    """WPD [W m-2] from the accumulated mean cube."""
    return 0.5 * rho * ds["mean_cube_100"].values


def diurnal_amplitude(ds: xr.Dataset) -> np.ndarray:
    """Peak-to-trough of the local-hour composite [m s-1]."""
    d = ds["diurnal_speed_100"].values
    return d.max(axis=0) - d.min(axis=0)


def diurnal_peak_hour(ds: xr.Dataset) -> np.ndarray:
    """Local hour of the diurnal maximum."""
    return ds["diurnal_speed_100"].values.argmax(axis=0).astype(float)


def load_fields(repo_root: Path, experiment: str, period: str) -> xr.Dataset:
    path = repo_root / "results" / "fields" / f"{experiment}_{period}_fields.nc"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/01_extract/compute_field_statistics.py")
    return xr.open_dataset(path)


def assert_same_window(a: xr.Dataset, b: xr.Dataset) -> None:
    """Refuse to difference two legs averaged over different windows."""
    for key in ("window_start", "window_end"):
        if a.attrs[key] != b.attrs[key]:
            raise ValueError(
                f"averaging windows differ ({a.attrs['experiment']} "
                f"{a.attrs[key]} vs {b.attrs['experiment']} {b.attrs[key]}). "
                "Recompute both with the same --start/--end: a difference "
                "between different windows is a difference in weather.")
