#!/usr/bin/env python
"""What actually exists on disk for each (experiment, period) leg.

This is the first thing to run and the thing to re-run whenever a simulation
finishes. It answers, per leg: is the directory there, how many history files,
what time span do they cover, how much of the analysis window is present, are
there gaps, does the mesh have the expected number of cells, and are the
variables the analysis needs actually in the output.

It matters more than usual here because the experiment set is *in flight*:
EXP02 is still integrating, its history has not been trimmed of spin-up, and
every downstream script must therefore work from the real time coverage rather
than from an assumed 721/745 files.

    python scripts/00_setup/inventory_experiments.py [--runs-root PATH]

Writes results/tables/experiment_inventory.csv and docs/run_status.md, and
exits non-zero if any leg that claims to be complete is not.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, vertical                       # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402

REQUIRED_VARS = [
    "xtime", "latCell", "lonCell", "zgrid", "landmask",
    "uReconstructZonal", "uReconstructMeridional",
    "u10", "v10", "t2m", "hpbl", "sst", "skintemp", "theta", "pressure",
]


def inspect(leg, cfg) -> dict:
    row = {
        "experiment": leg.experiment,
        "period": leg.period,
        "mesh": leg.mesh,
        "declared_status": cfg.experiments[leg.experiment]["status"],
        "dir_exists": leg.exists(),
        "history_dir": str(leg.history_dir),
    }
    if not leg.exists():
        return row | {"n_files": 0, "complete_pct": 0.0}

    index = io.history_index(leg.history_dir)
    row["n_files"] = int(len(index))
    if len(index) == 0:
        return row | {"complete_pct": 0.0}

    row["first_time"] = index.index[0]
    row["last_time"] = index.index[-1]

    window = io.select_window(index, leg.analysis_start, leg.analysis_end)
    expected = leg.expected_history_records
    row["n_in_window"] = int(len(window))
    row["complete_pct"] = round(100.0 * len(window) / expected, 1)

    # Gaps inside whatever part of the window is present: a missing hour in the
    # middle is a different problem from a run that simply has not got there yet.
    if len(window) > 1:
        step = pd.Series(window.index).diff().dropna()
        row["n_gaps"] = int((step != pd.Timedelta(hours=1)).sum())
        row["max_gap_h"] = float(step.max().total_seconds() / 3600.0)
    else:
        row["n_gaps"], row["max_gap_h"] = 0, np.nan

    # Spin-up still present? (EXP02 writes from the integration start.)
    row["has_untrimmed_spinup"] = bool(index.index[0] < leg.analysis_start)

    sample = index.iloc[-1] if len(window) == 0 else window.iloc[0]
    present = set(io.list_variables(sample))
    missing = [v for v in REQUIRED_VARS if v not in present]
    row["missing_variables"] = ",".join(missing)

    static = io.read_static(sample)
    n_cells = int(static["latCell"].size)
    row["n_cells"] = n_cells
    row["n_cells_expected"] = cfg.meshes[leg.mesh]["n_cells"]
    row["mesh_ok"] = n_cells == cfg.meshes[leg.mesh]["n_cells"]

    # Confirm the vertical grid is the one config/experiments.yaml assumes,
    # on an ocean cell where terrain is flat and the centers should be exact.
    zgrid = static["zgrid"]
    ocean = np.flatnonzero(static["landmask"] == 0)
    heights = vertical.heights_above_ground(zgrid[ocean[0]])
    try:
        matched = vertical.match_heights(heights, cfg.comparison_heights,
                                         cfg.height_tolerance_m)
        row["level_indices"] = ",".join(f"{h}m:k{ i[0] }" for h, i in matched.items())
        row["vertical_ok"] = True
    except ValueError as exc:
        row["level_indices"] = str(exc)
        row["vertical_ok"] = False

    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-root", default=None)
    args = ap.parse_args()

    cfg = load_config(runs_root=args.runs_root)
    rows = [inspect(leg, cfg) for leg in cfg.all_legs()]
    df = pd.DataFrame(rows)

    out_csv = cfg.path("results", "tables", "experiment_inventory.csv")
    df.to_csv(out_csv, index=False)

    cols = ["experiment", "period", "mesh", "n_files", "n_in_window",
            "complete_pct", "n_gaps", "has_untrimmed_spinup", "mesh_ok",
            "vertical_ok", "missing_variables"]
    print(df[[c for c in cols if c in df]].to_string(index=False))
    print(f"\n-> {out_csv.relative_to(REPO_ROOT)}")

    # A human-readable status page, regenerated each run so it cannot go stale.
    lines = [
        "# Run status",
        "",
        f"Generated by `scripts/00_setup/inventory_experiments.py` on "
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Regenerate it rather "
        "than editing it by hand.",
        "",
        "`complete_pct` is the fraction of the *analysis window* present, not of "
        "the integration: a leg still in spin-up reads 0 % even though it is "
        "running normally.",
        "",
        "| Experiment | Period | Mesh | Files | In window | Complete | Gaps | Spin-up still present | First | Last |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['experiment']} | {r['period']} | {r['mesh']} | "
            f"{r.get('n_files', 0)} | {r.get('n_in_window', 0)} | "
            f"{r.get('complete_pct', 0)} % | {r.get('n_gaps', '-')} | "
            f"{'yes' if r.get('has_untrimmed_spinup') else 'no'} | "
            f"{r.get('first_time', '-')} | {r.get('last_time', '-')} |")
    lines += [
        "",
        "## What to do with a partial leg",
        "",
        "Every analysis script takes `--experiments` and restricts itself to the "
        "time range common to the experiments being compared "
        "(`--common-period`, on by default). A partial EXP02 therefore shortens "
        "the comparison window for everyone rather than being compared over a "
        "different set of hours — which would confound the experiment "
        "difference with a difference in weather.",
        "",
        "Re-run this script and then re-run the pipeline "
        "(`scripts/run_all.sh`) when a leg finishes.",
    ]
    status = cfg.path("docs", "run_status.md")
    status.write_text("\n".join(lines) + "\n")
    print(f"-> {status.relative_to(REPO_ROOT)}")

    bad = df[(df["declared_status"] == "complete") & (df["complete_pct"] < 100.0)]
    if len(bad):
        print("\nWARNING: legs declared complete but incomplete on disk:",
              file=sys.stderr)
        print(bad[["experiment", "period", "complete_pct"]].to_string(index=False),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
