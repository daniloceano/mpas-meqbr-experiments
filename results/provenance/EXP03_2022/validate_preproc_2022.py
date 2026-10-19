#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np


WORK = Path(
    "/p1-swell/danilocs/MPAS-Research/runs/"
    "meqbr_05km_oval_meq02a/preproc_2022/20221001_20221101"
)
MESH = "meqbr_05km_oval_meq02a"
START = datetime(2022, 9, 21)
STOP = datetime(2022, 11, 1)


def text_value(var) -> str:
    value = netCDF4.chartostring(var[:])
    if np.ndim(value) == 0:
        return str(value.item()).strip()
    return str(value.flat[0]).strip()


errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


init_path = WORK / f"{MESH}.init.nc"
sfc_path = WORK / f"{MESH}.sfc_update.nc"
expected_lbc_times = [
    START + timedelta(hours=6 * i)
    for i in range(int((STOP - START).total_seconds() // 21600) + 1)
]
expected_lbc_names = [f"lbc.{t:%Y-%m-%d_%H}.00.00.nc" for t in expected_lbc_times]
lbc_paths = sorted(WORK.glob("lbc.*.nc"))

check(init_path.is_file() and init_path.stat().st_size > 0, "missing or empty init")
check(sfc_path.is_file() and sfc_path.stat().st_size > 0, "missing or empty sfc_update")
check([p.name for p in lbc_paths] == expected_lbc_names, "LBC names/times differ from expected 165-step series")

with netCDF4.Dataset(init_path) as ds:
    dims = {k: len(v) for k, v in ds.dimensions.items()}
    check(dims.get("Time") == 1, "init Time != 1")
    check(dims.get("nCells") == 102968, "init nCells != 102968")
    check(dims.get("nEdges") == 309246, "init nEdges != 309246")
    check(dims.get("nVertices") == 206279, "init nVertices != 206279")
    check(dims.get("nVertLevels") == 55, "init nVertLevels != 55")
    init_xtime = text_value(ds.variables["xtime"])
    check(init_xtime == "2022-09-21_00:00:00", f"unexpected init xtime {init_xtime}")
    stats = {}
    for name in ("theta", "rho", "surface_pressure", "qv"):
        check(name in ds.variables, f"init missing variable {name}")
        if name in ds.variables:
            values = np.asarray(ds.variables[name][:])
            check(bool(np.isfinite(values).all()), f"init {name} has non-finite values")
            stats[name] = (float(np.nanmin(values)), float(np.nanmax(values)))
    landmask = np.asarray(ds.variables["landmask"][:], dtype=np.int8)
    neighbors = np.asarray(ds.variables["cellsOnCell"][:], dtype=np.int64) - 1

opened = 0
for path, when in zip(lbc_paths, expected_lbc_times):
    try:
        with netCDF4.Dataset(path) as ds:
            check(len(ds.dimensions["Time"]) == 1, f"{path.name}: Time != 1")
            check(len(ds.dimensions["nCells"]) == 102968, f"{path.name}: nCells mismatch")
            check(len(ds.dimensions["nEdges"]) == 309246, f"{path.name}: nEdges mismatch")
            check(len(ds.dimensions["nVertLevels"]) == 55, f"{path.name}: levels mismatch")
            xtime = text_value(ds.variables["xtime"])
            expected = when.strftime("%Y-%m-%d_%H:00:00")
            check(xtime == expected, f"{path.name}: xtime {xtime} != {expected}")
            for name in ("lbc_qv", "lbc_u", "lbc_w", "lbc_rho", "lbc_theta"):
                check(name in ds.variables, f"{path.name}: missing {name}")
                if name in ds.variables:
                    var = ds.variables[name]
                    sample = np.asarray(var[(0,) + tuple(0 for _ in var.dimensions[1:])])
                    check(bool(np.isfinite(sample).all()), f"{path.name}: non-finite sample in {name}")
            opened += 1
    except Exception as exc:
        errors.append(f"{path.name}: open/read failed: {exc}")

with netCDF4.Dataset(sfc_path) as ds:
    sfc_times = [str(x).strip() for x in netCDF4.chartostring(ds.variables["xtime"][:])]
    expected_sfc_times = [
        (START + timedelta(days=i)).strftime("%Y-%m-%d_%H:00:00")
        for i in range((STOP - START).days + 1)
    ]
    check(sfc_times == expected_sfc_times, "sfc_update daily times differ from expected 42-day series")
    sst = np.asarray(ds.variables["sst"][:])
    xice = np.asarray(ds.variables["xice"][:])
    check(sst.shape == (42, 102968), f"unexpected sst shape {sst.shape}")
    check(bool(np.isfinite(sst).all()), "sfc SST has non-finite values")
    check(bool(np.isfinite(xice).all()), "sfc sea ice has non-finite values")
    check(float(np.nanmin(xice)) >= 0.0 and float(np.nanmax(xice)) <= 1.0, "sea ice outside 0..1")

ocean = landmask == 0
valid_neighbors = neighbors >= 0
neighbor_is_land = np.zeros(neighbors.shape, dtype=bool)
neighbor_is_land[valid_neighbors] = landmask[neighbors[valid_neighbors]] == 1
coastal = ocean & np.any(neighbor_is_land, axis=1)
ocean_sst = sst[:, ocean]
coastal_sst = sst[:, coastal]

ocean_exact_27315 = int(np.count_nonzero(ocean_sst == np.float32(273.15)))
ocean_below_296 = int(np.count_nonzero(ocean_sst < 296.0))
coastal_exact_27315 = int(np.count_nonzero(coastal_sst == np.float32(273.15)))
coastal_below_296 = int(np.count_nonzero(coastal_sst < 296.0))
check(ocean_exact_27315 == 0, f"ocean SST has {ocean_exact_27315} values at 273.15 K")
check(ocean_below_296 == 0, f"ocean SST has {ocean_below_296} values below 296 K")
check(coastal_exact_27315 == 0, f"coastal SST has {coastal_exact_27315} values at 273.15 K")
check(coastal_below_296 == 0, f"coastal SST has {coastal_below_296} values below 296 K")

print("init_dimensions", dims)
print("init_xtime", init_xtime)
print("init_variable_ranges", stats)
print("lbc_count", len(lbc_paths), "opened", opened)
print("lbc_first", lbc_paths[0].name if lbc_paths else "NONE")
print("lbc_last", lbc_paths[-1].name if lbc_paths else "NONE")
print("sfc_shape", sst.shape)
print("sfc_first", sfc_times[0] if sfc_times else "NONE")
print("sfc_last", sfc_times[-1] if sfc_times else "NONE")
print("ocean_cells", int(ocean.sum()), "coastal_cells", int(coastal.sum()))
print("ocean_exact_27315", ocean_exact_27315, "ocean_below_296", ocean_below_296)
print("ocean_min_K", float(np.nanmin(ocean_sst)), "ocean_max_K", float(np.nanmax(ocean_sst)))
print("coastal_exact_27315", coastal_exact_27315, "coastal_below_296", coastal_below_296)
print("coastal_min_K", float(np.nanmin(coastal_sst)), "coastal_p01_K", float(np.nanpercentile(coastal_sst, 1)))
print("coastal_max_K", float(np.nanmax(coastal_sst)))
print("xice_range", float(np.nanmin(xice)), float(np.nanmax(xice)))
print("errors", len(errors))
for error in errors:
    print("ERROR", error)
print("status", "PASS" if not errors else "FAIL")
sys.exit(0 if not errors else 1)
