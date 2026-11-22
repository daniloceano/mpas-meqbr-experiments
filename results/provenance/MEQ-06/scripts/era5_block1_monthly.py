#!/usr/bin/env python3
"""MEQ-06.5 — ERA5 for block 1 (2021-10-21 00 -> 2023-07-01 00, 6-hourly), month-batched.

CDS (protection measures, 2026) rejects queued parallel per-time requests, so this
issues ONE pressure-level and ONE single-level request per month, sequentially,
with exactly the variables / levels / box of usp-utils download_era5.py (EXP03:
area 15/-64/-16/-24). Each monthly GRIB is split per valid time with grib_copy
into met_data/era5/<YYYYMMDDHH>/era5_{pl,sl}_<YYYYMMDDHH>.grib and converted with
the unchanged era5_to_intermediate.py. Writes ONLY under the production dir.

Run (cgfd-usp-mpas env): nohup python era5_block1_monthly.py > logs/era5_block1_monthly.log 2>&1 &
"""
import hashlib, json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

P = Path("/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production")
U = Path("/p1-swell/danilocs/MPAS-Research/usp-utils/pre_proc/real_data")
sys.path.insert(0, str(U))
import download_era5 as d5  # same variable/level lists as the per-time downloader

AREA = [15.0, -64.0, -16.0, -24.0]
T0, T1 = datetime(2021, 10, 21), datetime(2023, 7, 1)
MON = P / "met_data/era5_monthly"; MET = P / "met_data/era5"
MON.mkdir(parents=True, exist_ok=True); MET.mkdir(parents=True, exist_ok=True)
LOG = lambda m: print(f"[{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}] {m}", flush=True)
HH = lambda tt: f"{int(tt) // 100:02d}"  # dataTime 0/600/0000/0600 -> HH


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def months():
    y, m = T0.year, T0.month
    while (y, m) <= (T1.year, T1.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def times_in(y, m):
    t = max(T0, datetime(y, m, 1))
    while t <= T1 and t.month == m:
        yield t
        t += timedelta(hours=6)


def convert(t):
    tag = f"{t:%Y%m%d%H}"; d = MET / tag
    if (d / f"ERA5:{t:%Y-%m-%d_%H}").stat().st_size if (d / f"ERA5:{t:%Y-%m-%d_%H}").exists() else 0:
        return tag, "skip"
    r = subprocess.run([sys.executable, str(U / "era5_to_intermediate.py"),
                        "--pl", str(d / f"era5_pl_{tag}.grib"), "--sl", str(d / f"era5_sl_{tag}.grib"),
                        "--outdir", str(d)], capture_output=True, text=True)
    (d / "convert.log").write_text(r.stdout + r.stderr)
    return tag, "ok" if r.returncode == 0 and (d / f"ERA5:{t:%Y-%m-%d_%H}").exists() else "FAIL"


def main():
    import cdsapi
    c = cdsapi.Client()
    records = []
    for y, m in months():
        ts = list(times_in(y, m))
        days = sorted({f"{t:%d}" for t in ts}); hours = sorted({f"{t:%H}:00" for t in ts})
        common = {"product_type": "reanalysis", "year": [f"{y}"], "month": [f"{m:02d}"],
                  "day": days, "time": hours, "data_format": "grib",
                  "download_format": "unarchived", "area": AREA}
        rec = {"month": f"{y}-{m:02d}", "n_times": len(ts), "first": f"{ts[0]:%Y-%m-%d_%H}",
               "last": f"{ts[-1]:%Y-%m-%d_%H}", "files": {}}
        for kind, ds, extra in (("pl", "reanalysis-era5-pressure-levels",
                                 {"variable": d5.PL_VARIABLES, "pressure_level": [str(p) for p in d5.PRESSURE_LEVELS]}),
                                ("sl", "reanalysis-era5-single-levels", {"variable": d5.SL_VARIABLES})):
            f = MON / f"era5_{kind}_{y}{m:02d}.grib"
            t0 = time.time()
            for attempt in range(1, 41):
                if f.exists() and f.stat().st_size > 0:
                    break
                try:
                    LOG(f"GET {kind} {y}-{m:02d} ({len(ts)} times) attempt {attempt}")
                    c.retrieve(ds, {**common, **extra}, str(f) + ".part")
                    Path(str(f) + ".part").rename(f)
                except Exception as e:  # noqa: BLE001
                    LOG(f"ERR {kind} {y}-{m:02d}: {e}"); time.sleep(min(120 * attempt, 900))
            if not f.exists():
                LOG(f"FAIL {kind} {y}-{m:02d} after retries"); return 1
            rec["files"][kind] = {"path": str(f), "bytes": f.stat().st_size, "md5": md5(f),
                                  "download_seconds": round(time.time() - t0, 1), "dataset": ds}
            LOG(f"DONE {kind} {y}-{m:02d} {f.stat().st_size} B {rec['files'][kind]['download_seconds']} s")
            # split per valid time
            tmp = MON / f"split_{kind}_{y}{m:02d}"
            if tmp.exists():
                for g in tmp.glob("*.grib"): g.unlink()
            tmp.mkdir(exist_ok=True)
            subprocess.run(["grib_copy", str(f), str(tmp / "[dataDate]_[dataTime].grib")], check=True)
            for g in tmp.glob("*.grib"):
                dd, tt = g.stem.split("_"); tag = dd + HH(tt)
                (MET / tag).mkdir(exist_ok=True)
                g.rename(MET / tag / f"era5_{kind}_{tag}.grib")
            tmp.rmdir()
        t0 = time.time()
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(convert, ts))
        bad = [t for t, s in res if s == "FAIL"]
        rec["convert_seconds"] = round(time.time() - t0, 1); rec["convert_fail"] = bad
        LOG(f"CONVERT {y}-{m:02d} ok={len(res)-len(bad)} fail={len(bad)} {rec['convert_seconds']} s")
        records.append(rec)
        (P / "records/era5_monthly_requests.json").write_text(json.dumps(
            {"dataset": "ERA5", "source": "Copernicus CDS (cdsapi)", "area_NWSE": AREA,
             "pressure_variables": d5.PL_VARIABLES, "pressure_levels_hpa": d5.PRESSURE_LEVELS,
             "single_variables": d5.SL_VARIABLES, "cadence_h": 6, "months": records}, indent=2))
        if bad:
            LOG("STOP: conversion failures"); return 1
    n = len(list(MET.glob("*/ERA5:*")))
    LOG(f"END intermediates={n}/2473")
    return 0 if n == 2473 else 1


if __name__ == "__main__":
    sys.exit(main())
