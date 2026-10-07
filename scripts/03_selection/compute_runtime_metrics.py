#!/usr/bin/env python
"""Summarise observed MPAS runtime cost without touching simulation output.

The primary metric is equivalent single-core machine time per simulated hour:
wall time multiplied by the number of MPI ranks, divided by simulated time.
The same quantity is used to estimate the wall-clock days required to simulate
one 365-day model year on 100 cores, assuming ideal scaling. Wrapper-recorded
wall times are measured values. CTL predates the wrappers, so its values are
clearly labelled as estimates reconstructed from log/file timestamps.

Outputs:
    results/tables/runtime_metrics.csv
    figures/selection/runtime_cost.png
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, plotting  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402

TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
MODEL_YEAR_HOURS = 365.0 * 24.0
REFERENCE_CORES = 100


def wrapper_record(wrapper: Path, period: str) -> dict | None:
    if not wrapper.exists():
        return None
    text = wrapper.read_text(errors="replace")
    rank_match = re.search(r"start \| ranks=(\d+)", text)
    start_match = re.search(
        rf"\[([^]]+)\] ===== START {re.escape(period)} =====", text)
    done_match = re.search(
        rf"\[([^]]+)\] ===== DONE\s+{re.escape(period)} "
        rf"\| rc=(\d+) \| (\d+)s \|", text)
    return {
        "ranks": int(rank_match.group(1)) if rank_match else None,
        "started": datetime.strptime(start_match.group(1), TS_FMT).replace(
            tzinfo=timezone.utc) if start_match else None,
        "finished": datetime.strptime(done_match.group(1), TS_FMT).replace(
            tzinfo=timezone.utc) if done_match else None,
        "rc": int(done_match.group(2)) if done_match else None,
        "wall_seconds": float(done_match.group(3)) if done_match else None,
    }


def linux_birth_and_mtime(path: Path) -> tuple[float, float] | None:
    if not path.exists():
        return None
    proc = subprocess.run(
        ["stat", "-c", "%W %Y", str(path)],
        check=False, capture_output=True, text=True)
    if proc.returncode:
        return None
    birth, modified = (float(x) for x in proc.stdout.split())
    return (birth, modified) if birth > 0 and modified > birth else None


def available_simulated_hours(leg) -> float:
    index = io.history_index(leg.history_dir, verify=0)
    if index.empty:
        return 0.0
    times = index.index[(index.index >= leg.integration_start)
                        & (index.index <= leg.analysis_end)]
    if times.empty:
        return 0.0
    return max(0.0, (times.max() - leg.integration_start).total_seconds() / 3600)


def ctl_estimate(leg) -> dict | None:
    """Best recoverable timing for CTL; both methods are estimates."""
    analysis_hours = (
        leg.analysis_end - leg.analysis_start).total_seconds() / 3600
    log = leg.history_dir / "log.atmosphere.0000.out"
    bounds = linux_birth_and_mtime(log)
    if bounds:
        return {
            "status": "complete_estimated",
            "wall_seconds": bounds[1] - bounds[0],
            "simulated_hours": analysis_hours,
            "method": "log_birth_to_close",
            "quality": "estimated",
            "source": str(log.relative_to(leg.history_dir.parent.parent)),
            "note": "CTL wrapper absent; reconstructed for retained/restart leg",
        }

    index = io.select_window(
        io.history_index(leg.history_dir, verify=0),
        leg.analysis_start, leg.analysis_end)
    if len(index) < 2:
        return None
    first = Path(index.iloc[0]).stat().st_mtime
    last = Path(index.iloc[-1]).stat().st_mtime
    if last <= first:
        return None
    return {
        "status": "complete_estimated",
        "wall_seconds": last - first,
        "simulated_hours": analysis_hours,
        "method": "history_mtime_span",
        "quality": "estimated",
        "source": str(leg.history_dir.relative_to(leg.history_dir.parent.parent)),
        "note": "CTL wrapper/log absent; reconstructed from retained hourly files",
    }


def build_rows(cfg) -> list[dict]:
    rows = []
    now = datetime.now(timezone.utc)
    for experiment in cfg.experiment_keys:
        exp = cfg.experiments[experiment]
        ranks_declared = int(exp["mpi_ranks"])
        wrapper = cfg.runs_root / experiment / f"run_{experiment.lower()}.log"
        for period in exp["periods"]:
            leg = cfg.leg(experiment, str(period))
            if not leg.exists():
                continue
            rec = wrapper_record(wrapper, leg.history_dir.name)
            full_hours = (
                leg.analysis_end - leg.integration_start).total_seconds() / 3600

            timing = None
            if rec and rec["wall_seconds"] is not None:
                timing = {
                    "status": "complete" if rec["rc"] == 0 else "failed",
                    "wall_seconds": rec["wall_seconds"],
                    "simulated_hours": full_hours,
                    "method": "wrapper_elapsed",
                    "quality": "measured",
                    "source": str(wrapper.relative_to(cfg.runs_root)),
                    "note": f"wrapper rc={rec['rc']}",
                }
            elif rec and rec["started"]:
                timing = {
                    "status": "running_provisional",
                    "wall_seconds": (now - rec["started"]).total_seconds(),
                    "simulated_hours": available_simulated_hours(leg),
                    "method": "wrapper_elapsed_to_date",
                    "quality": "provisional",
                    "source": str(wrapper.relative_to(cfg.runs_root)),
                    "note": "updates while the leg is running",
                }
            elif experiment == "CTL":
                timing = ctl_estimate(leg)
            if not timing or timing["simulated_hours"] <= 0:
                continue

            ranks = rec["ranks"] if rec and rec["ranks"] else ranks_declared
            wall_hours = timing["wall_seconds"] / 3600
            sim_hours = timing["simulated_hours"]
            machine_hours_per_sim_hour = wall_hours * ranks / sim_hours
            year_wall_days_100_cores = (
                machine_hours_per_sim_hour * MODEL_YEAR_HOURS
                / REFERENCE_CORES / 24.0
            )
            n_cells = int(cfg.meshes[leg.mesh]["n_cells"])
            steps = sim_hours * 3600 / 30.0
            rows.append({
                "experiment": experiment,
                "period": str(period),
                "status": timing["status"],
                "quality": timing["quality"],
                "mpi_ranks": ranks,
                "n_cells": n_cells,
                "simulated_hours": round(sim_hours, 3),
                "wall_seconds": round(timing["wall_seconds"], 3),
                "wall_hours": round(wall_hours, 3),
                "sim_hours_per_wall_hour": round(sim_hours / wall_hours, 3),
                "core_hours": round(wall_hours * ranks, 3),
                # Explicit name used by the report. The legacy alias is retained
                # so downstream notebooks do not break when the table is refreshed.
                "machine_hours_per_sim_hour_single_core": round(
                    machine_hours_per_sim_hour, 4),
                "wall_days_per_model_year_100_cores": round(
                    year_wall_days_100_cores, 2),
                "core_hours_per_sim_hour": round(
                    machine_hours_per_sim_hour, 4),
                "wall_seconds_per_timestep": round(timing["wall_seconds"] / steps, 4),
                "cell_steps_per_core_second": round(
                    n_cells * steps / (timing["wall_seconds"] * ranks), 3),
                "method": timing["method"],
                "source": timing["source"],
                "note": timing["note"],
            })
    return rows


def plot_cost(df: pd.DataFrame, out: Path) -> None:
    plotting.use_style()
    shown = df[df["quality"].isin(["measured", "provisional"])].copy()
    if shown.empty:
        return
    shown["label"] = shown["experiment"] + " " + shown["period"]
    colors = [plotting.EXPERIMENT_COLORS.get(e, "0.5")
              for e in shown["experiment"]]
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    metric = "machine_hours_per_sim_hour_single_core"
    bars = ax.bar(shown["label"], shown[metric], color=colors)
    for bar, quality in zip(bars, shown["quality"]):
        if quality == "provisional":
            bar.set_hatch("///")
    ax.set_ylabel("Horas de máquina por hora simulada\n(equivalente a 1 núcleo)")
    ax.set_title("Custo observado das integrações MPAS")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=25)
    plotting.provenance_footer(
        fig, "scripts/03_selection/compute_runtime_metrics.py | barra sólida = tempo "
             "concluído; hachura = execução provisória | 1 rank MPI = 1 núcleo")
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    cfg = load_config()
    df = pd.DataFrame(build_rows(cfg))
    if df.empty:
        print("no runtime records recovered", file=sys.stderr)
        return 1
    table = cfg.path("results", "tables", "runtime_metrics.csv")
    df.to_csv(table, index=False)
    figure = cfg.path("figures", "selection", "runtime_cost.png")
    plot_cost(df, figure)
    print(df[["experiment", "period", "status", "quality", "mpi_ranks",
              "wall_hours", "simulated_hours",
              "machine_hours_per_sim_hour_single_core",
              "wall_days_per_model_year_100_cores"]].to_string(index=False))
    print(f"-> {table.relative_to(REPO_ROOT)}")
    print(f"-> {figure.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
