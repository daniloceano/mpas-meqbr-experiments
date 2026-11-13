#!/usr/bin/env python
"""Read-only check of the temporal overlap between the EOSOLAR P1 SODAR and the P0 LiDAR.

Context: ``DEC-MEQ-003`` (``research/MEQ-03-selection-decision.md``) excluded the
SODAR citing, among other reasons, an hourly 100 m wind-speed correlation with
P0 of r = 0.87 (n = 771). That number came from a temporary script that was
never versioned. This script reproduces it independently and reports, per
instrument, the time span and sampling interval, plus the simultaneous hours by
month, how continuous they are, and the lag correlation.

The script only reads the input files and prints to stdout. It writes nothing:
no file under ``results/``, ``data/`` or anywhere else.

Inputs (paths are arguments; nothing is hardcoded):

* ``--sodar``     ``P1_SODAR.mat`` (struct ``SD``), as received from the operator.
                  Not linked into this repository (see ``docs/data_sources.md``).
* ``--p0``        ``P0_LIDAR_matrix.mat`` (struct ``L``). Defaults to
                  ``data/obs/P0_LIDAR_matrix.mat`` (populated by
                  ``scripts/00_setup/link_observations.py``).
* ``--p1-lidar``  optional ``P1_LIDAR_matrix.mat`` (struct ``L``), only to print
                  its span next to the other two (campaign FC1).

Pairing used to reproduce ``DEC-MEQ-003`` (method ``floor``, the default):

* MATLAB datenum -> naive timestamp, rounded to the minute; no time-zone
  conversion (P0 is UTC per the operator; SODAR UTC by inference).
* SODAR 100 m ``speed``: duplicated timestamps dropped (first kept); no QC other
  than discarding NaN. P0 100 m ``wspeed``: ``avail >= 80`` and 0-40 m/s, as in
  ``src/mpas_meqbr/obs.py:read_p0_lidar``. The QC is therefore asymmetric.
* Hourly mean over ``floor('h')`` with at least 4 valid 10-min samples, then an
  inner join on the hourly stamps.

``--method round`` uses instead the bin of ``src/mpas_meqbr/obs.py:to_hourly``
(``round('h')``, at least 4 valid samples), for comparison.

Expected output with the files received on 2022-10 (MD5 SODAR
``dfb33de066d7778e3397bdb0da969bb7``, P0 ``2ae6c60b0a72ebc40ab58b34e7c68e0c``):
``floor``: 771 simultaneous hours (Nov 473, Dec 298), r = 0.8689;
``round``: 770 hours, r = 0.8695.

Run::

    python scripts/06_audit/verify_sodar_p0_overlap.py \\
        --sodar ~/Downloads/EOSOLAR_P1_Maranhao_LIDAR_SODAR/P1_SODAR.mat \\
        --p0 /path/to/P0_LIDAR_matrix.mat \\
        [--p1-lidar ~/Downloads/EOSOLAR_P1_Maranhao_LIDAR_SODAR/P1_LIDAR_matrix.mat]
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[2]
MATLAB_EPOCH_OFFSET = 719529   # datenum of 1970-01-01, as in src/mpas_meqbr/obs.py
HEIGHT_M = 100
LAGS_H = [-24, -4, -3, -2, -1, 0, 1, 2, 3, 4, 24]


def datenum_to_index(mtime) -> pd.DatetimeIndex:
    """MATLAB datenum -> naive DatetimeIndex rounded to the minute (no zone applied)."""
    t = pd.Timestamp("1970-01-01") + pd.to_timedelta(
        np.asarray(mtime, float) - MATLAB_EPOCH_OFFSET, unit="D")
    return pd.DatetimeIndex(t).round("min")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_sodar(path: Path) -> tuple[pd.DatetimeIndex, pd.Series]:
    """SODAR struct ``SD`` -> (raw time index, 100 m speed with duplicates dropped)."""
    sd = loadmat(str(path), simplify_cells=True)["SD"]
    mtime = np.asarray(sd["mtime"], float)
    t = datenum_to_index(mtime[0])          # mtime is identical on every level
    levels = np.asarray(sd["levels"]).astype(int)
    i = int(np.where(levels == HEIGHT_M)[0][0])
    s = pd.Series(np.asarray(sd["speed"], float)[i], index=t)
    s = s[~s.index.duplicated(keep="first")].sort_index()
    return t, s


def read_lidar(path: Path, *, qc: bool) -> tuple[pd.DatetimeIndex, pd.Series]:
    """LiDAR struct ``L`` -> (time index, 100 m speed); P0 QC when ``qc``."""
    L = loadmat(str(path), simplify_cells=True)["L"]
    t = datenum_to_index(L["mtime"])
    heights = np.asarray(L["heights"])[0].astype(int)
    j = int(np.where(heights == HEIGHT_M)[0][0])
    w = np.asarray(L["wspeed"], float)[:, j]
    if qc:
        avail = np.asarray(L["avail"], float)[:, j]
        w = np.where(np.isfinite(w) & (avail >= 80) & (w >= 0) & (w <= 40), w, np.nan)
    return t, pd.Series(w, index=t)


def hourly(s: pd.Series, method: str, min_samples: int = 4) -> pd.Series:
    s = s.dropna()
    key = s.index.floor("h") if method == "floor" else s.index.round("h")
    g = s.groupby(key)
    m, n = g.mean(), g.size()
    return m[n >= min_samples]


def describe(name: str, t: pd.DatetimeIndex) -> None:
    d = pd.Series(np.diff(t.asi8) / 60e9)
    print(f"  {name:9s} {t.min()} -> {t.max()}  n={len(t)}  "
          f"interval mode={d.mode().iloc[0]:.0f} min ({(d == 10).sum()} of {len(d)} at 10 min)  "
          f"duplicated stamps={int(t.duplicated().sum())}")


def pair(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    return pd.concat([a.rename("sodar"), b.rename("p0")], axis=1, join="inner").dropna()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sodar", type=Path, required=True, help="P1_SODAR.mat")
    ap.add_argument("--p0", type=Path, default=REPO_ROOT / "data/obs/P0_LIDAR_matrix.mat",
                    help="P0_LIDAR_matrix.mat (default: data/obs/P0_LIDAR_matrix.mat)")
    ap.add_argument("--p1-lidar", type=Path, default=None, help="optional P1_LIDAR_matrix.mat")
    ap.add_argument("--method", choices=["floor", "round"], default="floor",
                    help="hourly bin: floor('h') as in DEC-MEQ-003 (default) or "
                         "round('h') as in src/mpas_meqbr/obs.py:to_hourly")
    args = ap.parse_args()

    print("Inputs (read only):")
    for label, p in [("SODAR", args.sodar), ("P0", args.p0), ("P1 LiDAR", args.p1_lidar)]:
        if p is not None:
            print(f"  {label:9s} {p}  md5={md5(p)}")

    ts, sodar = read_sodar(args.sodar)
    tp, p0 = read_lidar(args.p0, qc=True)
    print("\nSpan and sampling (timestamps as stored; no zone conversion):")
    describe("SODAR", ts)
    describe("P0", tp)
    if args.p1_lidar is not None:
        t1, _ = read_lidar(args.p1_lidar, qc=False)
        describe("P1 LiDAR", t1)

    ten = pair(sodar, p0)
    print(f"\n10-min stamps with both valid at {HEIGHT_M} m: {len(ten)}  "
          f"(identical values: {int((ten.sodar == ten.p0).sum())}); r = {ten.corr().iloc[0, 1]:.4f}")

    hs, hp = hourly(sodar, args.method), hourly(p0, args.method)
    J = pair(hs, hp)
    r = J.corr().iloc[0, 1]
    print(f"\nHourly pairing (method={args.method}, >=4 valid samples): "
          f"{len(J)} simultaneous hours, r = {r:.4f}")
    print("  by month:", {str(k): int(v) for k, v in J.groupby(J.index.to_period("M")).size().items()})

    idx = J.index
    span = pd.date_range(idx.min(), idx.max(), freq="h")
    breaks = np.where(np.diff(idx.asi8) / 3.6e12 > 1)[0]
    starts, ends = np.r_[0, breaks + 1], np.r_[breaks, len(idx) - 1]
    seg_len = ends - starts + 1
    gaps = [int((idx[k + 1] - idx[k]) / pd.Timedelta("1h")) - 1 for k in breaks]
    print(f"  span {idx.min()} -> {idx.max()}: {len(span)} h, {100 * len(idx) / len(span):.1f}% paired; "
          f"{len(seg_len)} contiguous segments, longest {seg_len.max()} h; "
          f"largest gap {max(gaps) if gaps else 0} h")

    anom = J - J.groupby(J.index.floor("D")).transform("mean")
    print(f"  r after removing each series' daily mean: {anom.corr().iloc[0, 1]:.4f}")

    print("\nLag correlation (SODAR stamps shifted by +lag h):")
    for lag in LAGS_H:
        a = hs.copy()
        a.index = a.index + pd.Timedelta(hours=lag)
        Jl = pair(a, hp)
        print(f"  {lag:+3d} h  r = {Jl.corr().iloc[0, 1]:.4f}  n = {len(Jl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
