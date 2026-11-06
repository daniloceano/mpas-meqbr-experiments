#!/usr/bin/env python
"""Validate raw and extracted EXP04--EXP06 outputs before scientific use.

Checks raw history/restart counts, exact scientific-window timestamps, required
variables, mesh size, ocean-cell correspondence, vertical levels, units and
finite wind values.  The same-mesh candidates must select the same five ocean
cells as EXP01 for a given site/period.

Output: results/audit/exp04_06_output_validation.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, vertical  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402


EXPERIMENTS = ("EXP04", "EXP05", "EXP06")
REFERENCE = "EXP01"
REQUIRED = {
    "uReconstructZonal", "uReconstructMeridional", "height_agl",
    "cell_index", "cell_distance_km", "sst", "skintemp",
}


def main() -> int:
    cfg = load_config()
    records = []
    failures = []
    references = {}
    candidate_cells = {}

    for period in sorted(cfg.periods):
        site = cfg.periods[period]["validation_site"]
        ref_path = REPO_ROOT / "results" / "site_timeseries" / f"{REFERENCE}_{period}_{site}.nc"
        with xr.open_dataset(ref_path) as source:
            references[(period, site)] = source["cell_index"].values.astype(int).tolist()

        for experiment in EXPERIMENTS:
            leg = cfg.leg(experiment, period)
            history = io.history_index(leg.history_dir)
            window = io.select_window(history, leg.analysis_start, leg.analysis_end)
            restarts = sorted(leg.history_dir.glob("restart.*.nc"))
            cache = REPO_ROOT / "results" / "site_timeseries" / f"{experiment}_{period}_{site}.nc"
            record = {
                "experiment": experiment,
                "period": period,
                "site": site,
                "history_count": len(history),
                "restart_count": len(restarts),
                "window_count": len(window),
                "window_expected": leg.expected_history_records,
                "window_time_sha256": io.temporal_identity(window.index)["time_sha256"],
                "cache": str(cache.relative_to(REPO_ROOT)),
            }
            with xr.open_dataset(window.iloc[0], decode_times=False) as raw:
                record["raw_n_cells"] = int(raw.sizes["nCells"])
            expected_n_cells = int(cfg.meshes[leg.mesh]["n_cells"])
            record["expected_n_cells"] = expected_n_cells
            if record["raw_n_cells"] != expected_n_cells:
                failures.append(
                    f"{experiment}/{period}: nCells {record['raw_n_cells']} "
                    f"!= registry {expected_n_cells}"
                )
            if len(history) != 985:
                failures.append(f"{experiment}/{period}: history {len(history)} != 985")
            if len(restarts) != 41:
                failures.append(f"{experiment}/{period}: restarts {len(restarts)} != 41")
            if len(window) != leg.expected_history_records:
                failures.append(
                    f"{experiment}/{period}: window {len(window)} != {leg.expected_history_records}"
                )
            if not cache.exists():
                failures.append(f"{experiment}/{period}: missing {cache.name}")
                records.append(record)
                continue
            with xr.open_dataset(cache) as source:
                ds = source.load()
            missing = sorted(REQUIRED - set(ds.variables))
            cells = ds["cell_index"].values.astype(int).tolist()
            reference_cells = references[(period, site)]
            reference_is_prefix = cells[:len(reference_cells)] == reference_cells
            first_candidate = candidate_cells.setdefault((period, site), cells)
            record.update({
                "cache_time_count": int(ds.sizes["time"]),
                "cache_cell_count": int(ds.sizes["cell"]),
                "cache_level_count": int(ds.sizes["level"]),
                "cell_indices": cells,
                "cell_distances_km": [float(value) for value in ds["cell_distance_km"].values],
                "missing_variables": missing,
                "history_dir_attr": ds.attrs.get("history_dir"),
                "cells_are_attr": ds.attrs.get("cells_are"),
                "zonal_wind_units": ds["uReconstructZonal"].attrs.get("units"),
                "meridional_wind_units": ds["uReconstructMeridional"].attrs.get("units"),
                "sst_units": ds["sst"].attrs.get("units"),
                "skintemp_units": ds["skintemp"].attrs.get("units"),
            })
            cache_times = io.validate_time_index(
                ds["time"].values, label=f"{experiment}/{period} extracted times"
            )
            record["cache_time_sha256"] = io.temporal_identity(cache_times)["time_sha256"]
            record["cache_times_match_raw_window"] = (
                record["cache_time_sha256"] == record["window_time_sha256"]
            )
            record["exp01_cell_count"] = len(reference_cells)
            record["exp01_cells_are_prefix"] = reference_is_prefix
            record["candidate_cells_identical"] = cells == first_candidate
            record["finite_wind_fraction"] = float(np.mean(np.isfinite(
                ds["uReconstructZonal"].values
            ) & np.isfinite(ds["uReconstructMeridional"].values)))
            try:
                matched = vertical.match_heights(
                    ds["height_agl"].isel(cell=0).values,
                    [50, 100, 150, 200], cfg.height_tolerance_m,
                )
                record["matched_heights_m"] = {
                    str(height): float(actual) for height, (_, actual) in matched.items()
                }
            except ValueError as exc:
                record["matched_heights_m"] = {}
                failures.append(f"{experiment}/{period}: {exc}")
            if missing:
                failures.append(f"{experiment}/{period}: missing variables {missing}")
            if len(cache_times) != leg.expected_history_records:
                failures.append(
                    f"{experiment}/{period}: cache {len(cache_times)} != {leg.expected_history_records}"
                )
            if not record["cache_times_match_raw_window"]:
                failures.append(
                    f"{experiment}/{period}: extracted timestamps differ from raw window"
                )
            if record["cache_cell_count"] != 5:
                failures.append(
                    f"{experiment}/{period}: cache has {record['cache_cell_count']} "
                    "cells; expected five nearest ocean cells"
                )
            if not record["exp01_cells_are_prefix"]:
                failures.append(
                    f"{experiment}/{period}: shared ocean cells differ from EXP01"
                )
            if not record["candidate_cells_identical"]:
                failures.append(
                    f"{experiment}/{period}: five ocean cells differ among EXP04--EXP06"
                )
            if record["finite_wind_fraction"] != 1.0:
                failures.append(
                    f"{experiment}/{period}: non-finite wind fraction "
                    f"{1.0 - record['finite_wind_fraction']:.6g}"
                )
            expected_units = {
                "zonal_wind_units": "m s-1",
                "meridional_wind_units": "m s-1",
                "sst_units": "K",
                "skintemp_units": "K",
            }
            for field, expected in expected_units.items():
                if record[field] != expected:
                    failures.append(
                        f"{experiment}/{period}: unexpected {field} "
                        f"{record[field]!r}; expected {expected!r}"
                    )
            records.append(record)

    document = {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "checks": records,
        "failures": failures,
        "interpretation": (
            "The historical EXP01 cache may contain only its primary ocean cell. "
            "Every cell available there must be an identical prefix of each new "
            "cache, and all five cells must match across EXP04--EXP06 because the "
            "four experiments share the same mesh and LiDAR site. EXP03 is exempt "
            "because it uses a different geometry."
        ),
    }
    output = REPO_ROOT / "results" / "audit" / "exp04_06_output_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(json.dumps(document, indent=2))
    print(f"-> {output.relative_to(REPO_ROOT)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
