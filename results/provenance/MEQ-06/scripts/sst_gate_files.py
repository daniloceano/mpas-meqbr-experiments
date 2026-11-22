#!/usr/bin/env python
"""MEQ-06.5 SST gate on raw forcing files (every record).

check_sst_forcing.py audits experiment legs through their history output and
reads one record; production forcings have no history yet. This wrapper imports
that script's criterion unchanged (OISST_LAND_FILL_K, |sst - fill| < 1e-3 on
ocean cells, landmask from the static/init file) and applies it to EVERY time
record of each file given. Exit 0 = PASS (zero ocean cells at the fill value).

    python sst_gate_files.py <repo> <static_or_init.nc> <file.nc> [...]
"""
import sys, importlib.util
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("csf", repo / "scripts/03_selection/check_sst_forcing.py")
csf = importlib.util.module_from_spec(spec); spec.loader.exec_module(csf)
FILL, IMPL = csf.OISST_LAND_FILL_K, csf.IMPLAUSIBLE_K
with Dataset(sys.argv[2]) as ds:
    ocean = np.asarray(ds["landmask"][:]).ravel() == 0
print(f"criterion from check_sst_forcing.py: fill={FILL} K, implausible<{IMPL} K; ocean cells={ocean.sum()}")
bad = 0
for f in sys.argv[3:]:
    with Dataset(f) as ds:
        sst = ds["sst"]; n = sst.shape[0] if sst.ndim == 2 else 1
        times = ["".join(t.astype(str)).strip() for t in ds["xtime"][:]] if "xtime" in ds.variables else ["-"] * n
        nfill_tot, ncold_max, mn, mx, worst = 0, 0, 1e9, -1e9, None
        for i in range(n):
            x = np.asarray(sst[i] if sst.ndim == 2 else sst[:])[ocean]
            nf = int((np.abs(x - FILL) < 1e-3).sum()); nc = int((x < IMPL).sum())
            nfill_tot += nf; mn, mx = min(mn, x.min()), max(mx, x.max())
            if nc > ncold_max: ncold_max, worst = nc, times[i]
            if nf: print(f"  FILL {Path(f).name} {times[i]}: {nf} ocean cells")
        bad += nfill_tot
        print(f"{Path(f).name}: records={n} ({times[0]} .. {times[-1]}) ocean_at_fill_total={nfill_tot} "
              f"ocean_min={mn:.2f} K ocean_max={mx:.2f} K max_cells<{IMPL:.0f}K={ncold_max} (at {worst})")
print("GATE:", "PASS" if bad == 0 else f"FAIL ({bad} ocean cell-records at fill)")
sys.exit(0 if bad == 0 else 1)
