"""Reading MPAS history output without ever loading a whole run into memory.

MPAS writes one timestep per ``history.*.nc`` file (~140-180 MB each here, and
there are ~700-1000 per leg). Two access patterns cover everything this repo
does, and both are cheap:

* **column at one cell, all levels** — the arrays are ``(Time, nCells,
  nVertLevels)`` with the vertical contiguous, so ``[0, icell, :]`` is one
  contiguous read (~0.2 s/file, dominated by the file open).
* **map at one level** — ``[0, :, k]`` is strided but still ~0.06 s/file.

Anything that needs both at once for a whole run is doing something wrong.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from netCDF4 import Dataset

RAD2DEG = 180.0 / np.pi
TIME_FMT = "history.%Y-%m-%d_%H.%M.%S.nc"
CANONICAL_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
CANONICAL_TIME_ENCODING = (
    "ASCII timestamps formatted YYYY-MM-DDTHH:MM:SS, sorted ascending, "
    "joined by LF (\\n), no trailing LF"
)


def validate_time_index(times, *, expected_frequency: str = "1h",
                        require_contiguous: bool = True,
                        label: str = "time index") -> pd.DatetimeIndex:
    """Return a sorted, unique time index and reject ambiguous sampling.

    MPAS histories are hourly for this project. A missing interior hour is not
    repaired by taking a smaller ``min/max`` window: it is an integrity error
    that must be resolved before experiments are compared.
    """
    index = pd.DatetimeIndex(pd.to_datetime(times))
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    if index.hasnans:
        raise ValueError(f"{label} contains NaT")
    duplicated = index[index.duplicated(keep=False)].unique().sort_values()
    if len(duplicated):
        sample = ", ".join(str(value) for value in duplicated[:3])
        raise ValueError(f"{label} contains duplicate timestamps: {sample}")
    index = index.sort_values()
    if require_contiguous and len(index) > 1:
        expected = pd.Timedelta(expected_frequency)
        intervals = index[1:] - index[:-1]
        bad = np.flatnonzero(intervals != expected)
        if bad.size:
            i = int(bad[0])
            raise ValueError(
                f"{label} has an unexpected interval: {index[i]} -> "
                f"{index[i + 1]} ({intervals[i]}; expected {expected})")
    return index


def canonical_time_text(times) -> str:
    """Canonical text hashed for a reproducible temporal identity.

    The representation deliberately has no trailing newline. For the 721
    hourly samples from 2021-11-01 00 through 2021-12-01 00 it yields SHA-256
    ``9896c83795adf1fd3d8cb4606f48efee0c1163ea5a09c5e3b1b44be205cbcde5``.
    """
    index = validate_time_index(times, require_contiguous=False)
    if np.any(index.microsecond) or np.any(index.nanosecond):
        raise ValueError("timestamps with sub-second precision are not canonical")
    return "\n".join(value.strftime(CANONICAL_TIME_FORMAT) for value in index)


def temporal_identity(times) -> dict[str, object]:
    """Count, bounds and SHA-256 for an exact ordered timestamp set."""
    index = validate_time_index(times)
    text = canonical_time_text(index)
    return {
        "time_count": len(index),
        "time_start": index[0].strftime(CANONICAL_TIME_FORMAT) if len(index) else "",
        "time_end": index[-1].strftime(CANONICAL_TIME_FORMAT) if len(index) else "",
        "time_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "time_encoding": CANONICAL_TIME_ENCODING,
    }


def validate_history_index(index: pd.Series, *, label: str = "history index",
                           expected_frequency: str = "1h") -> pd.Series:
    """Validate and chronologically order a ``time -> path`` history index."""
    if len(index) == 0:
        return index.copy()
    times = validate_time_index(
        index.index, expected_frequency=expected_frequency, label=label)
    return index.loc[times]


def common_history_indices(indices: Mapping[str, pd.Series], *,
                           expected_frequency: str = "1h") -> tuple[dict[str, pd.Series], pd.DatetimeIndex]:
    """Align histories to their exact common timestamps.

    Every input is validated before intersection, so duplicate timestamps and
    internal gaps cannot disappear silently. Different leading/trailing
    availability is allowed; every returned series is indexed by the exact
    same common set.
    """
    if not indices:
        return {}, pd.DatetimeIndex([])
    checked = {
        name: validate_history_index(index, label=f"{name} history index",
                                     expected_frequency=expected_frequency)
        for name, index in indices.items()
    }
    common = None
    for index in checked.values():
        common = index.index if common is None else common.intersection(index.index)
    common = validate_time_index(
        common if common is not None else [], expected_frequency=expected_frequency,
        label="common history index")
    if len(common) == 0:
        raise ValueError("history indices have no common timestamps")
    aligned = {name: index.loc[common] for name, index in checked.items()}
    assert_identical_time_indexes(aligned)
    return aligned, common


def assert_identical_time_indexes(indices: Mapping[str, pd.Series]) -> pd.DatetimeIndex:
    """Reject a comparison unless all members have the exact same timestamps."""
    reference_name = None
    reference = None
    for name, series in indices.items():
        current = validate_time_index(series.index, label=f"{name} time index")
        if reference is None:
            reference_name, reference = name, current
        elif not reference.equals(current):
            raise ValueError(
                f"timestamp sets differ between {reference_name} and {name}; "
                "equal start/end bounds are not sufficient")
    return reference if reference is not None else pd.DatetimeIndex([])


def find_history_files(run_dir: str | Path) -> list[Path]:
    """``history.*.nc`` in *run_dir*, sorted (filenames are chronological)."""
    return sorted(Path(run_dir).glob("history.*.nc"))


def time_from_filename(path: str | Path) -> pd.Timestamp:
    """Valid time from the filename — no file open at all.

    MPAS encodes the valid time in the name, so a directory listing already
    gives the full time axis. :func:`read_timestamp` re-reads ``xtime`` when
    the filename must be verified rather than trusted.
    """
    return pd.to_datetime(Path(path).name, format=TIME_FMT)


def read_timestamp(path: str | Path) -> pd.Timestamp:
    """Authoritative valid time, decoded from the ``xtime`` variable."""
    with Dataset(path) as ds:
        raw = ds.variables["xtime"][0]
    text = "".join(np.asarray(raw, dtype="U1")).strip()
    return pd.Timestamp(text.replace("_", " "))


def history_index(run_dir: str | Path, *, verify: int = 3) -> pd.Series:
    """Map valid time -> file path for a run directory.

    Times come from the filenames; *verify* files (first, middle, last by
    default) are opened and checked against ``xtime`` so a mislabelled file
    cannot pass silently.
    """
    files = find_history_files(run_dir)
    if not files:
        return pd.Series(dtype=object)
    times = validate_time_index(
        [time_from_filename(f) for f in files], require_contiguous=False,
        label=f"history filenames in {run_dir}")
    if verify and len(files) >= 1:
        idx = sorted({0, len(files) // 2, len(files) - 1})[:verify]
        for i in idx:
            got = read_timestamp(files[i])
            if got != times[i]:
                raise ValueError(
                    f"{files[i].name}: filename says {times[i]}, xtime says {got}")
    return pd.Series(files, index=times, name="path").sort_index()


def select_window(index: pd.Series, start, end) -> pd.Series:
    """Restrict a :func:`history_index` to ``[start, end]`` inclusive.

    Always use this instead of assuming the file list equals the analysis
    window: EXP02's history still contains its untrimmed spin-up.
    """
    if len(index) == 0:                      # a leg that has not written yet
        return index
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    return index.loc[(index.index >= start) & (index.index <= end)]


def read_cell_columns(path, variables, cells) -> dict:
    """Read ``var[0, cells, :]`` (3D) or ``var[0, cells]`` (2D) from one file.

    Returns ``{name: ndarray}`` with shape ``(len(cells), nlev)`` or
    ``(len(cells),)``. Variables absent from the file are skipped silently so a
    caller can ask for an optional diagnostic without branching.
    """
    cells = np.atleast_1d(np.asarray(cells, dtype=int))
    out: dict = {}
    with Dataset(path) as ds:
        for name in variables:
            if name not in ds.variables:
                continue
            var = ds.variables[name]
            if var.ndim == 3:                     # (Time, nCells, nLev)
                out[name] = np.stack([var[0, int(c), :] for c in cells])
            elif var.ndim == 2 and var.dimensions[0] == "Time":   # (Time, nCells)
                out[name] = np.array([var[0, int(c)] for c in cells])
            elif var.ndim == 2:                   # static (nCells, nLev)
                out[name] = np.stack([var[int(c), :] for c in cells])
            else:                                 # static (nCells,)
                out[name] = np.array([var[int(c)] for c in cells])
    return out


def read_level_map(path, variables, level: int | None = None) -> dict:
    """Read a full-domain horizontal field from one file.

    3D variables are sliced at *level* (a layer-center index); 2D variables are
    returned whole. This is the read pattern behind every map and animation.
    """
    out: dict = {}
    with Dataset(path) as ds:
        for name in variables:
            if name not in ds.variables:
                continue
            var = ds.variables[name]
            if var.ndim == 3:
                if level is None:
                    raise ValueError(f"{name} is 3D — a level index is required")
                out[name] = np.asarray(var[0, :, int(level)])
            elif var.ndim == 2 and var.dimensions[0] == "Time":
                out[name] = np.asarray(var[0, :])
            else:
                out[name] = np.asarray(var[:])
    return out


def read_static(path, variables=("latCell", "lonCell", "areaCell", "landmask", "zgrid")) -> dict:
    """Read the time-invariant mesh fields from any history or init file."""
    out = {}
    with Dataset(path) as ds:
        for name in variables:
            if name in ds.variables:
                out[name] = np.asarray(ds.variables[name][:])
    return out


def cell_lonlat_degrees(lat_rad, lon_rad):
    """(lon, lat) in degrees, longitude wrapped to (-180, 180]."""
    lat = np.asarray(lat_rad) * RAD2DEG
    lon = ((np.asarray(lon_rad) * RAD2DEG + 180.0) % 360.0) - 180.0
    return lon, lat


def list_variables(path) -> list:
    with Dataset(path) as ds:
        return list(ds.variables)
