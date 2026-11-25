#!/usr/bin/env python
"""MEQ-06.7 — 60 x 90 test: EXP03 Nov/2021 at 60 ranks (validated leg) vs production at 90 ranks.

Hourly history 2021-11-01_01 .. 2021-12-01_00 (720 h; 11-01_00 is the restart instant of the
production and is also compared). Quantities: 10 m wind (u10, v10, speed) and 100 m wind
(uReconstructZonal/Meridional linearly interpolated to 100 m above ground from layer centers
of zgrid, same convention as src/mpas_meqbr/vertical.py). Sites: nearest OCEAN cell to
P0, P1 (SODAR coords), LPI, ANM-1/PPE1A. Domain: all cells.
Reports max |diff| and RMS diff (speed and components). Read-only on both run dirs.
    python compare_60x90.py <ref_dir> <prod_dir> <out_dir>
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

REF, PRD, OUT = map(Path, sys.argv[1:4]); OUT.mkdir(parents=True, exist_ok=True)
SITES = {"P0": (-2.694107, -42.554807), "P1": (-2.724877, -42.575182),
         "LPI": (-4.8789425, -37.1478801), "ANM": (-4.70467, -36.82571)}

with Dataset(PRD / "history.2021-11-01_01.00.00.nc") as d:
    lat, lon = np.degrees(d["latCell"][:]), np.degrees(d["lonCell"][:])
    lon = np.where(lon > 180, lon - 360, lon)
    zg = np.asarray(d["zgrid"][:], dtype=np.float64)
    land = np.asarray(d["landmask"][0]) if "landmask" in d.variables else None
zc = 0.5 * (zg[:, :-1] + zg[:, 1:]) - zg[:, :1]           # layer-center height AGL
k = np.clip((zc < 100.0).sum(axis=1) - 1, 0, zc.shape[1] - 2)
i = np.arange(zc.shape[0]); z0, z1 = zc[i, k], zc[i, k + 1]; w = (100.0 - z0) / (z1 - z0)
cells = {}
for s, (la, lo) in SITES.items():
    dd = (lat - la) ** 2 + ((lon - lo) * np.cos(np.radians(la))) ** 2
    if land is not None: dd = np.where(land == 0, dd, np.inf)
    cells[s] = int(np.argmin(dd))


def fields(f):
    with Dataset(f) as d:
        u10, v10 = np.asarray(d["u10"][0], np.float64), np.asarray(d["v10"][0], np.float64)
        U, V = np.asarray(d["uReconstructZonal"][0], np.float64), np.asarray(d["uReconstructMeridional"][0], np.float64)
    u100 = U[i, k] * (1 - w) + U[i, k + 1] * w; v100 = V[i, k] * (1 - w) + V[i, k + 1] * w
    return {"10m": (u10, v10), "100m": (u100, v100)}


acc = {}  # (scope, level, comp) -> [max, sumsq, n]
rows = ["time\tlevel\tscope\tmax_abs_speed_diff\trms_speed_diff"]
t, te, nid = datetime(2021, 11, 1), datetime(2021, 12, 1), 0
first_diff = None
while t <= te:
    tag = f"{t:%Y-%m-%d_%H}.00.00"
    a, b = fields(REF / f"history.{tag}.nc"), fields(PRD / f"history.{tag}.nc")
    for lev in ("10m", "100m"):
        (ua, va), (ub, vb) = a[lev], b[lev]
        du, dv, ds = ub - ua, vb - va, np.hypot(ub, vb) - np.hypot(ua, va)
        if first_diff is None and (np.any(du) or np.any(dv)): first_diff = tag
        scopes = {"domain": slice(None), **{s: c for s, c in cells.items()}}
        for sc, idx in scopes.items():
            for comp, x in (("speed", ds), ("u", du), ("v", dv)):
                xx = np.atleast_1d(x[idx]); r = acc.setdefault((sc, lev, comp), [0.0, 0.0, 0])
                r[0] = max(r[0], float(np.abs(xx).max())); r[1] += float((xx ** 2).sum()); r[2] += xx.size
            xs = np.atleast_1d(ds[idx])
            rows.append(f"{tag}\t{lev}\t{sc}\t{np.abs(xs).max():.4g}\t{np.sqrt((xs**2).mean()):.4g}")
    t += timedelta(hours=1); nid += 1

(OUT / "compare_60x90_hourly.tsv").write_text("\n".join(rows) + "\n")
lines = [f"60 x 90 test, Nov/2021: {nid} hourly pairs (2021-11-01_00 .. 2021-12-01_00)",
         f"ref (60 ranks): {REF}", f"prod (90 ranks): {PRD}",
         "site cells (nearest ocean): " + ", ".join(f"{s}={c} ({lat[c]:.3f},{lon[c]:.3f})" for s, c in cells.items()),
         f"first hour with any difference: {first_diff}", "",
         "scope\tlevel\tcomp\tmax_abs_diff_m/s\trms_diff_m/s"]
for (sc, lev, comp), (mx, ss, n) in sorted(acc.items(), key=lambda x: (x[0][1], x[0][0] != "domain", x[0][0], x[0][2])):
    lines.append(f"{sc}\t{lev}\t{comp}\t{mx:.4g}\t{np.sqrt(ss / n):.4g}")
(OUT / "compare_60x90_summary.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
