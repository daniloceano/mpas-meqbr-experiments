"""Observation readers, quality control, and aggregation onto the model clock.

Everything a model is compared against passes through here, so the QC and the
time-averaging are applied identically to every experiment. Two families:

* **LiDAR profilers** (P0, LPI) — the primary evidence. Hub-height wind, 10-min
  resolution, offshore.
* **ISD surface stations** — public 10 m land stations from NOAA NCEI, which is
  where the Brazilian INMET automatic stations and airport reports are
  internationally archived. Automatic INMET stations form the primary surface
  evidence axis; airport/synoptic records are supplementary. This axis remains
  separate from the offshore LiDAR scores.

**The pairing decision.** The 10-min record is averaged into the hour centred on
each model timestamp, requiring at least 4 of the 6 possible samples. The
alternative — taking the single 10-min sample nearest the model hour — is
tempting because it needs no thresholds, but it compares a 10-minute point
measurement against an hourly value representing a ~20 km2 grid cell. The
mismatch in averaging scale shows up as noise that is charged to the model.
Hourly averaging removes the part of that mismatch that can be removed; the
spatial part is irreducible and belongs in the caveats.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MATLAB_EPOCH_OFFSET = 719529   # datenum of 1970-01-01


# --------------------------------------------------------------------------
# LiDAR profilers
# --------------------------------------------------------------------------

def read_p0_lidar(path, *, avail_min_percent: float = 80.0,
                  speed_range=(0.0, 40.0)) -> pd.DataFrame:
    """P0 floating LiDAR (MATLAB struct) -> tidy frame ``[time, height, speed, direction]``.

    QC: per-height ``avail`` (the completeness of that 10-min averaging bin) must
    be at least *avail_min_percent*, and speeds must be inside *speed_range*.
    The availability flag is per height, not per record, so a profile can be
    accepted at 100 m and rejected at 260 m — which is the usual pattern, since
    LiDAR returns degrade with range.

    The met sensor (temp/press/humid) fails after ~140 records and reports exact
    zeros; it is not read here. Only the wind channels are used.
    """
    from scipy.io import loadmat

    L = loadmat(str(path), simplify_cells=True)["L"]
    time = (pd.Timestamp("1970-01-01")
            + pd.to_timedelta(np.asarray(L["mtime"], float) - MATLAB_EPOCH_OFFSET, unit="D"))
    time = pd.DatetimeIndex(time).round("min")     # kill datenum round-off
    heights = np.asarray(L["heights"])[0].astype(float)

    speed = np.asarray(L["wspeed"], float)
    direction = np.asarray(L["wdir"], float)
    avail = np.asarray(L["avail"], float)

    bad = ~np.isfinite(speed) | (avail < avail_min_percent) \
        | (speed < speed_range[0]) | (speed > speed_range[1])
    speed = np.where(bad, np.nan, speed)
    direction = np.where(bad, np.nan, direction)

    n_t, n_h = speed.shape
    return pd.DataFrame({
        "time": np.repeat(time.values, n_h),
        "height": np.tile(heights, n_t),
        "speed": speed.ravel(),
        "direction": direction.ravel(),
    }).dropna(subset=["speed"]).reset_index(drop=True)


def read_lpi_lidar(path, *, speed_range=(0.0, 40.0)) -> pd.DataFrame:
    """LPI fixed LiDAR (preprocessed CSV, time already UTC) -> the same tidy frame.

    LPI carries no per-record availability flag, so QC is the physical range
    check only. That asymmetry with P0 is real and is carried into the caveats
    rather than papered over by inventing a threshold for LPI.
    """
    df = pd.read_csv(path, parse_dates=["time"])
    frames = []
    for col in df.columns:
        if not col.startswith("spd_"):
            continue
        h = float(col.split("_")[1])
        dcol = f"dir_{col.split('_')[1]}"
        sub = pd.DataFrame({
            "time": df["time"],
            "height": h,
            "speed": pd.to_numeric(df[col], errors="coerce"),
            "direction": pd.to_numeric(df[dcol], errors="coerce") if dcol in df else np.nan,
        })
        frames.append(sub)
    out = pd.concat(frames, ignore_index=True)
    out.loc[(out["speed"] < speed_range[0]) | (out["speed"] > speed_range[1]), "speed"] = np.nan
    return out.dropna(subset=["speed"]).reset_index(drop=True)


def read_lidar(site, repo_root: Path) -> pd.DataFrame:
    """Dispatch on the site key. Returns the tidy ``[time, height, speed, direction]``."""
    path = repo_root / site.source_file
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run scripts/00_setup/link_observations.py first")
    qc = site.qc
    rng = tuple(qc.get("speed_range_ms", (0.0, 40.0)))
    if site.key == "P0":
        return read_p0_lidar(path, avail_min_percent=qc.get("avail_min_percent", 80.0),
                             speed_range=rng)
    return read_lpi_lidar(path, speed_range=rng)


# --------------------------------------------------------------------------
# aggregation onto the model clock
# --------------------------------------------------------------------------

def _vector_mean_direction(deg: pd.Series) -> float:
    d = np.deg2rad(deg.dropna().to_numpy(dtype=float))
    if d.size == 0:
        return np.nan
    return float(np.rad2deg(np.arctan2(np.sin(d).mean(), np.cos(d).mean())) % 360.0)


def to_hourly(df: pd.DataFrame, *, min_samples: int = 4) -> pd.DataFrame:
    """10-min tidy frame -> hourly means centred on each whole hour.

    The bin for hour *t* is ``[t - 30 min, t + 30 min)``, so the average is
    centred on the instant the model reports rather than trailing it. Speeds are
    scalar-averaged (the resource-relevant quantity); directions are
    vector-averaged (a scalar mean of 350 deg and 10 deg would give 180 deg).
    Bins with fewer than *min_samples* valid records are dropped.
    """
    d = df.copy()
    d["hour"] = pd.DatetimeIndex(d["time"]).round("h")
    g = d.groupby(["hour", "height"])
    out = g.agg(speed=("speed", "mean"), n=("speed", "size")).reset_index()
    dirs = g["direction"].apply(_vector_mean_direction).reset_index(name="direction")
    out = out.merge(dirs, on=["hour", "height"])
    out = out[out["n"] >= min_samples].drop(columns="n")
    return out.rename(columns={"hour": "time"}).sort_values(["time", "height"]) \
              .reset_index(drop=True)


def observed_at_model_heights(hourly: pd.DataFrame, height_map: dict) -> pd.DataFrame:
    """Collapse observed channels onto the model comparison heights.

    ``height_map`` says which observed channel(s) represent each model height —
    usually one-to-one, except P0's 250 m model level, which has no channel and
    is represented by the mean of the 240 m and 260 m channels. Averaging two
    channels that bracket the target symmetrically assumes the profile is close
    to linear over that 20 m, which at these heights it is.

    A model height is emitted only when **every** channel it maps to is present
    for that hour, so the 240/260 m average never silently degrades to one side.
    """
    frames = []
    for model_h, channels in height_map.items():
        sub = hourly[hourly["height"].isin(channels)]
        if sub.empty:
            continue
        g = sub.groupby("time")
        agg = g.agg(speed=("speed", "mean"), n=("speed", "size"))
        dirs = g["direction"].apply(_vector_mean_direction).rename("direction")
        agg = agg.join(dirs)
        agg = agg[agg["n"] == len(channels)].drop(columns="n")
        agg["model_height"] = model_h
        frames.append(agg.reset_index())
    if not frames:
        return pd.DataFrame(columns=["time", "speed", "direction", "model_height"])
    return pd.concat(frames, ignore_index=True).sort_values(["model_height", "time"]) \
             .reset_index(drop=True)


# --------------------------------------------------------------------------
# ISD surface stations
# --------------------------------------------------------------------------

def parse_isd_wind(df: pd.DataFrame, *, exclude_quality_codes=("2", "3", "6", "7"),
                   speed_range=(0.0, 40.0)) -> pd.DataFrame:
    """Decode the ISD ``WND`` field into ``[time, direction, speed]``.

    ``WND`` is a comma-packed group:
    ``direction, direction-quality, type, speed*10, speed-quality``, with 999
    and 9999 as missing markers. Quality codes 2/3/6/7 flag values the ISD's own
    checks rejected; they are dropped rather than trusted.

    Report type is not filtered here: an INMET automatic station reports hourly
    while an airport SYNOP may report only in daylight hours, and that
    difference is real information about coverage that the caller should see.
    """
    wnd = df["WND"].astype(str).str.split(",", expand=True)
    direction = pd.to_numeric(wnd[0], errors="coerce")
    dq = wnd[1].astype(str)
    speed = pd.to_numeric(wnd[3], errors="coerce") / 10.0
    sq = wnd[4].astype(str)

    direction = direction.where(direction < 999)
    speed = speed.where(speed < 999.0)
    speed = speed.where(~sq.isin(exclude_quality_codes))
    direction = direction.where(~dq.isin(exclude_quality_codes))
    speed = speed.where((speed >= speed_range[0]) & (speed <= speed_range[1]))

    out = pd.DataFrame({
        "time": pd.to_datetime(df["DATE"]),
        "direction": direction,
        "speed": speed,
    }).dropna(subset=["speed"])
    # Several reports can share an hour (routine + special); keep the hourly mean.
    out["time"] = pd.DatetimeIndex(out["time"]).round("h")
    g = out.groupby("time")
    res = g.agg(speed=("speed", "mean")).join(
        g["direction"].apply(_vector_mean_direction).rename("direction"))
    return res.reset_index()
