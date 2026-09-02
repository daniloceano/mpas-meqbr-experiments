"""ERA5 access — two datasets that answer two different questions.

**Periods** (``data/era5/``, downloaded by
``scripts/01_extract/download_era5_periods.py``): hourly 10 m and 100 m wind
covering the two simulation windows. ERA5 is the model's own initial and lateral
forcing, so comparing MPAS against ERA5 at the LiDAR sites is the sharpest
possible framing of the question the project actually asks: *does integrating
the 5 km mesh add skill over the reanalysis it was driven by?* A skill score
above zero is added value; at or below zero, the downscaling is not earning its
cost at that site.

**Climatology** (``/p1-sto-swell/.../ERA5_surface_wind_data_Brazil``, 1990-2020,
monthly files, hourly, 0.25 deg): the same variables over three decades. Used for
two things only — establishing how typical the two simulated months were (a
single month can sit in the tail of the distribution, which would limit what any
one-month evaluation can say about a climatological run), and drawing the ERA5
baseline resource map that MPAS is proposed as an alternative to.

The 100 m wind is the relevant level: it is ERA5's own diagnostic at
turbine-hub height, so no shear extrapolation is imposed on either side of the
comparison.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

WIND_VARS = ["u10", "v10", "u100", "v100"]


def _standardise(ds: xr.Dataset) -> xr.Dataset:
    """Normalise ERA5 coordinate names across CDS vintages.

    Files retrieved before and after the CDS-Beta migration name the time
    coordinate ``time`` or ``valid_time`` and may carry a length-1 ``expver`` or
    ``number`` dimension. Standardising once here keeps every caller from having
    to know.
    """
    if "valid_time" in ds.dims or "valid_time" in ds.coords:
        ds = ds.rename({"valid_time": "time"})
    for extra in ("expver", "number"):
        if extra in ds.dims:
            ds = ds.isel({extra: 0}, drop=True)
        elif extra in ds.coords:
            ds = ds.drop_vars(extra)
    return ds


def open_periods(era5_dir, period: str) -> xr.Dataset:
    """Open the downloaded ERA5 file for one simulation period."""
    path = Path(era5_dir) / f"era5_wind_{period}.nc"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/01_extract/download_era5_periods.py")
    return _standardise(xr.open_dataset(path))


def open_climatology(clim_dir, years, months) -> xr.Dataset:
    """Open the 1990-2020 monthly archive for the requested years and months."""
    clim_dir = Path(clim_dir)
    files = [clim_dir / f"ERA5_surface_wind_data_Brazil_{y}_{m:02d}.nc"
             for y in years for m in months]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"missing ERA5 climatology files: {missing[:5]}")
    ds = xr.open_mfdataset([str(f) for f in files], combine="nested",
                           concat_dim="valid_time", parallel=False)
    return _standardise(ds)


def speed_direction(u, v):
    """Wind speed and meteorological direction (degrees the wind blows *from*)."""
    speed = np.sqrt(np.asarray(u) ** 2 + np.asarray(v) ** 2)
    direction = (270.0 - np.rad2deg(np.arctan2(np.asarray(v), np.asarray(u)))) % 360.0
    return speed, direction


def at_point(ds: xr.Dataset, lat: float, lon: float, *, method: str = "linear") -> pd.DataFrame:
    """ERA5 time series at a site, as ``[time, speed_10, dir_10, speed_100, dir_100]``.

    Bilinear interpolation, not nearest neighbour: at 0.25 deg (~28 km) the
    nearest grid point can be 15 km from the site, and near a coastline the
    neighbouring points can straddle the land-sea contrast. Interpolating is the
    conventional choice and avoids making the result depend on which side of a
    grid box the site happens to fall.
    """
    point = ds.interp(latitude=lat, longitude=lon, method=method)
    out = {"time": pd.DatetimeIndex(point["time"].values)}
    for level in (10, 100):
        u, v = point[f"u{level}"].values, point[f"v{level}"].values
        s, d = speed_direction(u, v)
        out[f"speed_{level}"] = s
        out[f"dir_{level}"] = d
    return pd.DataFrame(out)


def subset_box(ds: xr.Dataset, lat_min, lat_max, lon_min, lon_max) -> xr.Dataset:
    """Spatial subset that works whichever way the latitude axis runs.

    ERA5 stores latitude decreasing; a plain ``slice(lat_min, lat_max)`` silently
    returns an empty selection when it does.
    """
    lat = ds["latitude"].values
    lat_slice = slice(lat_max, lat_min) if lat[0] > lat[-1] else slice(lat_min, lat_max)
    return ds.sel(latitude=lat_slice, longitude=slice(lon_min, lon_max))
