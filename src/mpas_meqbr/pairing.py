"""Build the paired model-observation samples that every score is computed on.

One module so that the pairing is identical everywhere. Getting this wrong is
the classic way to produce a verification result that is really a statement
about data coverage: if two experiments are scored over different hours, the
difference between them is partly the difference in weather, not in physics.

Two rules enforced here:

* **Restrict to the intersection.** :func:`common_times` trims every experiment
  to the hours all of them have. It matters right now, because EXP02 is still
  integrating and covers roughly half the 2021 window.
* **Pair on the observation clock.** The observed record is aggregated to the
  model's hourly stamps once (in :mod:`mpas_meqbr.obs`) and reused, so all
  experiments see the same observation vector.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from . import obs as obs_mod
from . import vertical


def model_speed_direction(ds: xr.Dataset, cell: int = 0):
    """Wind speed and meteorological direction from the reconstructed winds.

    Direction is where the wind comes *from*, matching the LiDAR and station
    convention.
    """
    u = ds["uReconstructZonal"].isel(cell=cell)
    v = ds["uReconstructMeridional"].isel(cell=cell)
    speed = np.sqrt(u ** 2 + v ** 2)
    direction = (270.0 - np.rad2deg(np.arctan2(v, u))) % 360.0
    return speed, direction


def model_at_heights(path: Path, heights, tolerance_m: float = 1.0,
                     cell: int = 0) -> pd.DataFrame:
    """Read one extracted site file and return ``[time, model_height, speed, direction]``.

    The level index for each target height is derived from the stored
    ``height_agl`` profile and checked against the tolerance — the index is
    never hardcoded, because the terrain-following coordinate makes it a
    property of the cell, not of the model.
    """
    with xr.open_dataset(path) as ds:
        ds = ds.load()
    height_agl = ds["height_agl"].isel(cell=cell)
    if "time" in height_agl.dims:
        # Older incrementally appended caches may carry a redundant time
        # dimension on this static coordinate.  Accept it only when every
        # stored profile is identical; a genuinely time-varying vertical grid
        # would require explicit handling rather than silently taking t=0.
        reference = height_agl.isel(time=0, drop=True)
        if not np.allclose(height_agl.values, reference.values,
                           equal_nan=True):
            raise ValueError(
                f"height_agl varies with time in {path}; expected a static "
                "vertical grid for each extracted cell")
        height_agl = reference
    profile = height_agl.values
    matched = vertical.match_heights(profile, heights, tolerance_m)
    speed, direction = model_speed_direction(ds, cell)
    times = pd.DatetimeIndex(ds["time"].values)

    frames = []
    for target, (k, actual) in matched.items():
        frames.append(pd.DataFrame({
            "time": times,
            "model_height": target,
            "actual_height": actual,
            "speed": speed.isel(level=k).values,
            "direction": direction.isel(level=k).values,
        }))
    return pd.concat(frames, ignore_index=True)


def observed_hourly(site, repo_root: Path, pairing_cfg: dict) -> pd.DataFrame:
    """The site's observations, QC'd, hourly, on the model comparison heights."""
    tidy = obs_mod.read_lidar(site, repo_root)
    hourly = obs_mod.to_hourly(tidy, min_samples=int(pairing_cfg.get("min_samples", 4)))
    return obs_mod.observed_at_model_heights(hourly, site.height_map)


def pair(model: pd.DataFrame, observed: pd.DataFrame) -> pd.DataFrame:
    """Inner join on (time, model_height) -> one row per matched hour and height."""
    return model.merge(
        observed.rename(columns={"speed": "obs_speed", "direction": "obs_dir"}),
        on=["time", "model_height"], how="inner", validate="one_to_one",
    ).rename(columns={"speed": "mod_speed", "direction": "mod_dir"}) \
     .sort_values(["model_height", "time"]).reset_index(drop=True)


def common_times(frames: dict) -> pd.DatetimeIndex:
    """Hours present in *every* frame — the only fair comparison window.

    ``frames`` maps a label (usually an experiment key) to a paired frame.
    """
    idx = None
    for df in frames.values():
        t = pd.DatetimeIndex(sorted(df["time"].unique()))
        idx = t if idx is None else idx.intersection(t)
    return idx if idx is not None else pd.DatetimeIndex([])


def restrict(frames: dict, times: pd.DatetimeIndex) -> dict:
    return {k: df[df["time"].isin(times)].reset_index(drop=True)
            for k, df in frames.items()}


def load_paired(cfg, experiments, period: str, *, cell: int = 0,
                common: bool = True, repo_root: Path | None = None) -> dict:
    """Paired frames for a set of experiments over one period.

    Returns ``{experiment: DataFrame}`` with columns ``time, model_height,
    mod_speed, mod_dir, obs_speed, obs_dir``. Experiments with no extracted file
    yet are skipped with a note rather than aborting the run — this pipeline is
    expected to be executed while a simulation is still going.
    """
    from .config import REPO_ROOT

    repo_root = repo_root or REPO_ROOT
    site = cfg.site(cfg.periods[period]["validation_site"])
    observed = observed_hourly(site, repo_root, cfg.pairing)

    frames = {}
    for exp in experiments:
        path = repo_root / "results" / "site_timeseries" / f"{exp}_{period}_{site.key}.nc"
        if not path.exists():
            print(f"  [skip] {exp} {period}: {path.name} not extracted yet")
            continue
        model = model_at_heights(path, site.model_heights,
                                 cfg.height_tolerance_m, cell=cell)
        p = pair(model, observed)
        if p.empty:
            print(f"  [skip] {exp} {period}: no overlapping hours with {site.key}")
            continue
        frames[exp] = p
    if common and len(frames) > 1:
        times = common_times(frames)
        frames = restrict(frames, times)
    return frames


def add_era5(frames: dict, cfg, period: str, *, height_for_era5: int = 100,
             repo_root: Path | None = None) -> pd.DataFrame | None:
    """The ERA5 reference on the same hours as the paired model frames.

    ERA5 is compared at 100 m only; mapping its 100 m wind onto the LiDAR's 50 m
    or 200 m channel would require a shear assumption that ERA5 does not carry,
    and that assumption would then be doing part of the work the comparison is
    supposed to measure.
    """
    from .config import REPO_ROOT

    repo_root = repo_root or REPO_ROOT
    site_key = cfg.periods[period]["validation_site"]
    path = repo_root / "results" / "site_timeseries" / f"ERA5_{period}_{site_key}.csv"
    if not path.exists():
        return None
    era = pd.read_csv(path, parse_dates=["time"])
    era = era[["time", f"speed_{height_for_era5}", f"dir_{height_for_era5}"]]
    era.columns = ["time", "era5_speed", "era5_dir"]
    return era
