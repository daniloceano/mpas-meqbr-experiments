#!/usr/bin/env python
"""Validate the four corrected MPAS integrations without changing them.

This audit is intentionally separate from the official analysis pipeline.  It
checks the hourly filename sequence, opens every history file with netCDF4,
checks the scientific-window count, and summarises the model logs.  The 2021
EXP02 restart left its checkpoint-time history file in the preserved
``interrupted_20260909_after_restart`` directory; the validator includes that
file in the logical full-integration sequence but never copies or moves it.

Output: JSON report supplied with ``--out``.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from netCDF4 import Dataset


PERIODS = {
    "2021": {
        "subdir": "20211101_20211201",
        "integration_start": datetime(2021, 10, 21),
        "analysis_start": datetime(2021, 11, 1),
        "end": datetime(2021, 12, 1),
        "scientific_count": 721,
    },
    "2022": {
        "subdir": "20221001_20221101",
        "integration_start": datetime(2022, 9, 21),
        "analysis_start": datetime(2022, 10, 1),
        "end": datetime(2022, 11, 1),
        "scientific_count": 745,
    },
}
EXPERIMENTS = ("EXP01_CORRECTED", "EXP02_CORRECTED")
STAMP_RE = re.compile(r"history\.(\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2})\.nc$")


def stamp(path: Path) -> datetime:
    match = STAMP_RE.search(path.name)
    if not match:
        raise ValueError(f"unexpected history filename: {path.name}")
    return datetime.strptime(match.group(1), "%Y-%m-%d_%H.%M.%S")


def expected_hours(start: datetime, end: datetime) -> list[datetime]:
    n = int((end - start).total_seconds() // 3600)
    return [start + timedelta(hours=i) for i in range(n + 1)]


def log_summary(run_dir: Path) -> dict:
    candidates = sorted(run_dir.glob("log.atmosphere.0000.out"))
    candidates += sorted(run_dir.glob("mpas.out"))
    details = []
    critical_patterns = (
        "critical error", "segmentation fault", "mpi_abort", "floating point exception",
    )
    for path in candidates:
        text = path.read_text(errors="replace")
        lower = text.lower()
        critical_lines = [line.strip() for line in text.splitlines()
                          if any(pattern in line.lower() for pattern in critical_patterns)]
        # MPAS prints the harmless terminal counter "Critical error messages = 0".
        critical_lines = [line for line in critical_lines
                          if not re.search(r"critical error messages\s*=\s*0", line.lower())]
        details.append({
            "file": str(path),
            "finished_marker": "Finished running the atmosphere core" in text,
            "error_messages_zero": bool(re.search(r"Error messages\s*=\s*0", text)),
            "critical_error_messages_zero": bool(
                re.search(r"Critical error messages\s*=\s*0", text)),
            "critical_lines": critical_lines,
            "size_bytes": path.stat().st_size,
        })
    atmosphere_logs = [d for d in details if Path(d["file"]).name == "log.atmosphere.0000.out"]
    # ``log.atmosphere.0000.out`` is the authoritative MPAS log and carries the
    # terminal counters. ``mpas.out`` is only launcher stdout on these runs; it
    # is still scanned for fatal text but is not expected to repeat the MPAS
    # terminal markers.
    atmosphere_clean = bool(atmosphere_logs) and all(
        d["finished_marker"] and d["error_messages_zero"]
        and d["critical_error_messages_zero"] and not d["critical_lines"]
        for d in atmosphere_logs
    )
    auxiliary_clean = all(not d["critical_lines"] for d in details)
    return {
        "files": details,
        "authoritative_log": "log.atmosphere.0000.out",
        "all_clean": atmosphere_clean and auxiliary_clean,
    }


def archived_candidates(run_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for archive in sorted(run_dir.glob("interrupted_*")):
        paths.extend(sorted(archive.glob("history.*.nc")))
    return paths


def check_netcdf(paths: list[Path]) -> dict:
    failures = []
    reference_dims = None
    required = {"uReconstructZonal", "uReconstructMeridional", "sst", "skintemp"}
    for i, path in enumerate(paths):
        try:
            with Dataset(path, "r") as ds:
                dims = {name: len(dim) for name, dim in ds.dimensions.items()}
                if reference_dims is None:
                    reference_dims = {k: dims.get(k) for k in ("nCells", "nVertLevels")}
                missing_vars = sorted(required.difference(ds.variables))
                if missing_vars:
                    failures.append({"file": str(path), "reason": f"missing variables: {missing_vars}"})
                    continue
                if dims.get("nCells") != reference_dims.get("nCells"):
                    failures.append({"file": str(path), "reason": "nCells differs from first file"})
                # Force a real data read from every file, not only a header open.
                var = ds.variables["sst"]
                _ = float(var[0, 0] if var.ndim == 2 else var[0])
        except Exception as exc:  # noqa: BLE001 - audit must record every bad file
            failures.append({"file": str(path), "reason": repr(exc)})
    return {
        "files_checked": len(paths),
        "all_opened": not failures,
        "failures": failures,
        "reference_dimensions": reference_dims,
    }


def validate_leg(root: Path, experiment: str, period: str) -> dict:
    meta = PERIODS[period]
    run_dir = root / experiment / meta["subdir"]
    active = sorted(run_dir.glob("history.*.nc"), key=stamp)
    archived = archived_candidates(run_dir)
    active_by_time = {stamp(path): path for path in active}
    archived_by_time = {stamp(path): path for path in archived}

    expected = expected_hours(meta["integration_start"], meta["end"])
    active_missing = [t for t in expected if t not in active_by_time]
    recovered = {t: archived_by_time[t] for t in active_missing if t in archived_by_time}
    logical = dict(active_by_time)
    logical.update(recovered)
    logical_missing = [t for t in expected if t not in logical]
    extras = sorted(t for t in logical if t not in set(expected))
    scientific = [t for t in logical if meta["analysis_start"] <= t <= meta["end"]]
    ordered_paths = [logical[t] for t in expected if t in logical]

    nc = check_netcdf(ordered_paths)
    result = {
        "experiment": experiment,
        "period": period,
        "run_dir": str(run_dir),
        "active_history_count": len(active),
        "expected_full_count": len(expected),
        "active_missing_timestamps": [t.isoformat() for t in active_missing],
        "recovered_from_preserved_archive": {
            t.isoformat(): str(path) for t, path in sorted(recovered.items())
        },
        "logical_full_count": len(logical),
        "logical_missing_timestamps": [t.isoformat() for t in logical_missing],
        "extra_timestamps": [t.isoformat() for t in extras],
        "scientific_window_count": len(scientific),
        "expected_scientific_count": meta["scientific_count"],
        "first_timestamp": min(logical).isoformat() if logical else None,
        "last_timestamp": max(logical).isoformat() if logical else None,
        "netcdf": nc,
        "logs": log_summary(run_dir),
    }
    result["valid"] = (
        not logical_missing
        and not extras
        and len(logical) == len(expected)
        and len(scientific) == meta["scientific_count"]
        and nc["all_opened"]
        and result["logs"]["all_clean"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    legs = [validate_leg(args.runs_root, exp, period)
            for exp in EXPERIMENTS for period in PERIODS]
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "runs_root": str(args.runs_root),
        "method": (
            "Hourly filename sequence; complete netCDF4 open plus SST value read; "
            "scientific-window count; MPAS terminal/error markers. Preserved restart "
            "outputs are used only to reconstruct the logical sequence and are not moved."
        ),
        "all_valid": all(leg["valid"] for leg in legs),
        "legs": legs,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "all_valid": report["all_valid"],
        "legs": [{
            "experiment": leg["experiment"],
            "period": leg["period"],
            "valid": leg["valid"],
            "active": leg["active_history_count"],
            "logical": leg["logical_full_count"],
            "scientific": leg["scientific_window_count"],
            "netcdf_failures": len(leg["netcdf"]["failures"]),
            "logs_clean": leg["logs"]["all_clean"],
        } for leg in legs],
        "out": str(args.out),
    }, indent=2))
    return 0 if report["all_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
