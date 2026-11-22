#!/usr/bin/env python
"""MEQ-06.6 — compare continuous run C with restarted run R (R1 day 1 + R2 day 2).

History: every hour 2021-10-21_00 .. 2021-10-23_00 (49 files). For hours up to
2021-10-22_00 R = R1; after that R = R2. R2's own 2021-10-22_00 file (written at
restart) is also compared against C. Restart: C vs R2 at 2021-10-23_00.
Per variable: bit-identical?, max |diff|, RMS diff, first differing hour.
    python compare_restart.py <test_dir>   -> <test_dir>/records/restart_comparison.{tsv,txt}
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

T = Path(sys.argv[1])
out = T / "records"; out.mkdir(exist_ok=True)


def cmp(fa, fb):
    res = {}
    with Dataset(fa) as a, Dataset(fb) as b:
        for v in a.variables:
            x = np.asarray(a[v][:]); y = np.asarray(b[v][:])
            if x.dtype.kind in "SUO":
                res[v] = (bool(np.array_equal(x, y)), 0.0, 0.0, x.size)
                continue
            same = x.shape == y.shape and x.tobytes() == y.tobytes()
            if same:
                res[v] = (True, 0.0, 0.0, x.size)
            else:
                d = x.astype(np.float64) - y.astype(np.float64)
                res[v] = (False, float(np.nanmax(np.abs(d))), float(np.sqrt(np.nanmean(d * d))), x.size)
    return res


rows, summary = [], {}
t, t_end, t_mid = datetime(2021, 10, 21), datetime(2021, 10, 23), datetime(2021, 10, 22)
pairs = []
while t <= t_end:
    tag = f"{t:%Y-%m-%d_%H}.00.00"
    pairs.append((f"history {tag}", T / "C" / f"history.{tag}.nc",
                  T / ("R1" if t <= t_mid else "R2") / f"history.{tag}.nc"))
    t += timedelta(hours=1)
pairs.append(("restart 2021-10-23_00", T / "C/restart.2021-10-23_00.00.00.nc",
              T / "R2/restart.2021-10-23_00.00.00.nc"))
missing = [p for _, a, b in pairs for p in (a, b) if not p.exists()]
if missing:
    print("MISSING:", *missing, sep="\n  "); sys.exit(2)

for label, a, b in pairs:
    kind = label.split()[0]
    for v, (same, mx, rms, n) in cmp(a, b).items():
        rows.append(f"{label}\t{v}\t{int(same)}\t{mx:.6g}\t{rms:.6g}")
        k = (kind, v)
        s = summary.setdefault(k, {"same": True, "max": 0.0, "rms_max": 0.0, "first": None})
        if not same:
            s["same"] = False; s["max"] = max(s["max"], mx); s["rms_max"] = max(s["rms_max"], rms)
            s["first"] = s["first"] or label

(out / "restart_comparison.tsv").write_text("pair\tvariable\tbit_identical\tmax_abs_diff\trms_diff\n" + "\n".join(rows) + "\n")
lines = []
for kind in ("history", "restart"):
    ks = sorted(k for k in summary if k[0] == kind)
    nd = [k for k in ks if not summary[k]["same"]]
    lines.append(f"{kind}: {len(ks)} variables compared, {len(ks) - len(nd)} bit-identical, {len(nd)} differ")
    for k in nd:
        s = summary[k]
        lines.append(f"  {k[1]}: max|diff|={s['max']:.6g} max_hourly_RMS={s['rms_max']:.6g} first={s['first']}")
verdict = "IDENTICAL (bit for bit)" if all(s["same"] for s in summary.values()) else "DIFFERENT"
lines.append(f"history pairs compared: {sum(1 for p in pairs if p[0].startswith('history'))}; restart pairs: 1")
lines.append(f"VERDICT: {verdict}")
(out / "restart_comparison.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
