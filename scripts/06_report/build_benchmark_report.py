#!/usr/bin/env python3
"""MEQ-05.3 — self-contained HTML report of the MEQ-05.2 parallel benchmark.

Audience: a meteorology researcher without a computing background. Every
technical term is explained in plain words the first time it appears, and each
chapter opens with "O que esta seção mostra" and closes with "O que isso
significa na prática".

Inputs (consolidated tables and benchmark records only):
    results/tables/meq05_parallel_benchmark.csv   one row per trial (MEQ-05.2),
                                                  including the real mpiexec
                                                  command and the pinning check
    results/tables/runtime_metrics.csv            production costs (EXP03 rows
                                                  for the cost correction; all
                                                  rows for the context table)
    results/benchmark/MEQ-05.2/records/hardware_snapshot.txt
                                                  CPU numbering per socket and
                                                  MPICH/Hydra version (lscpu,
                                                  numactl, mpiexec -info)

Output (one file; CSS, Plotly basic, data and JavaScript are inlined):
    results/report/meq05_parallel_benchmark.html

Style is reused from the technical report v2 without modifying it:
    docs/templates/report_v2/report.css       inlined verbatim at build time
    docs/templates/vendor/plotly-basic.min.js inlined verbatim at build time
    Plotly journal defaults (axis/layout/CONFIG/fmt) copied from
    docs/templates/report_v2/report.js; masthead, chapter navigation, captions
    with panel letters, tables and drawers use the existing CSS classes.

No result is typed by hand: every number in the page is computed below from
the inputs. The fixed constants in "Run metadata" and "Projection settings"
are run settings documented in docs/provenance/MEQ-05.2-benchmark-record.md,
or assumptions stated by the PI in the MEQ-05.3 briefs; they are not
measurements.

The MEQ-06 duration chapter is a projection: none of the projected
configurations was measured. The report presents options; it does not decide
the MEQ-06 configuration.

Run:
    python scripts/06_report/build_benchmark_report.py [--output PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

BENCH_CSV = REPO_ROOT / "results/tables/meq05_parallel_benchmark.csv"
COMPL_CSV = REPO_ROOT / "results/tables/meq05_5_parallel_benchmark_complement.csv"
RUNTIME_CSV = REPO_ROOT / "results/tables/runtime_metrics.csv"
HW_SNAPSHOT = REPO_ROOT / "results/benchmark/MEQ-05.2/records/hardware_snapshot.txt"
RECORD_MD = REPO_ROOT / "docs/provenance/MEQ-05.2-benchmark-record.md"
COMPL_RECORD_MD = REPO_ROOT / "docs/provenance/MEQ-05.5-benchmark-complement-record.md"
# MEQ-05.5 records (folder keeps the historical name MEQ-05.4).
HIST_VARS_CSV = REPO_ROOT / "results/benchmark/MEQ-05.4/records/history_variables.csv"
DISK_INV = REPO_ROOT / "results/benchmark/MEQ-05.4/records/disk_inventory.txt"
REPORT_CSS = REPO_ROOT / "docs/templates/report_v2/report.css"
PLOTLY_JS = REPO_ROOT / "docs/templates/vendor/plotly-basic.min.js"
DEFAULT_OUTPUT = REPO_ROOT / "results/report/meq05_parallel_benchmark.html"

# ---------------------------------------------------------------- run metadata
# Source: docs/provenance/MEQ-05.2-benchmark-record.md (namelist and hardware).
DT_S = 30                              # config_dt, unchanged from production
RESTART_LABEL = "2021-11-15 00 UTC"    # restart.2021-11-15_00.00.00.nc (EXP03)
CPU_MODEL = "2× Intel Xeon Gold 5420+"
SMT_THREADS = 2                        # threads per physical core (lscpu)
REP_RULE = 0.03                        # 3rd repetition only if |a-b|/mean > 3 %
# Approved by the PI (MEQ-05.3 brief): efficiency per physical core >= 70 %.
EFFICIENCY_CRITERION = 0.70
DAYS_PER_YEAR = 365                    # simulated days per simulated year
SECONDS_PER_DAY = 86400

BASE_CONFIG = "A_N008"                 # speed-up/efficiency reference (CSV)
EXP03_ID = "EXP03"
OPTIONS = ["A_N056", "B_N112", "C_N060", "D",    # decision options, this order
           "P90C", "P90E", "Q45S", "Q45C", "Q56"]
PROPOSED = "P90C"
PROPOSED_LABEL = "configuração adotada"
PRELIM_DECISION = ("Decisão do pesquisador e do supervisor (17/11/2026): a MEQ-06 começa com uma "
                   "simulação de 1 ano com 90 processos compactos (45 núcleos físicos, cada um com "
                   "suas 2 tarefas; 11 núcleos inteiros livres) — a configuração recomendada por "
                   "este benchmark.")
FREE_SPACE_TB = 126            # /p1-swell, 13/11/2026 (initial MEQ-05 diagnosis; not re-verified)
FREE_SPACE_YEARS = (1, 5, 10, 15)
# MEQ-05.5 configurations (complement CSV). Pairs: (socket 0, socket 1).
COMPL_SINGLE = ("P90C", "P90E", "E90C")
COMPL_PAIRS = {"Q45S": ("Q45S_s0", "Q45S_s1"), "Q45C": ("Q45C_s0", "Q45C_s1"),
               "Q56": ("Q56_s0", "Q56_s1")}
COMPL_REF = "REF_A56"                  # normalisation reference of each block
# Disk chapter
DISK_YEARS = (1, 2, 5, 10, 15)
HOURS_PER_DAY = 24
LBC_PER_DAY = 4                        # lateral boundary files every 6 h
RESTARTS_KEPT = 2                      # "keep only the last 2" scenario
D_CASES = ("D_N028x2_s0", "D_N028x2_s1")
UNPINNED_CFG = "C_N060"                # production-like launch (no pinning)
PINNED_CFG = "A_N056"                  # pinned comparison for the run chapter

# ---------------------------------------------------------- projection settings
# Assumptions stated by the PI in the MEQ-05.3 revision brief (not measured).
PROJ_RANKS = 90                        # processes of the projected single run
PROJ_YEARS = (1, 2, 5, 10, 15, 20)     # columns of the duration table
DAYS_PER_MONTH = 30.4                  # months = days / 30.4
PLAUSIBLE_MARGIN = "±10–15 %"          # plausible margin of the projection
INTERP_LO, INTERP_HI = "A_N042", "A_N056"   # linear interpolation to 45 cores
# Planning hypothesis (MEQ-05.3 revision 2): spin-up per continuous run, in
# simulated days. The adequate spin-up length is a MEQ-06 decision.
SPINUP_DAYS = 10
EXAMPLE_YEARS = 2                      # worked example: 2000–2002
EXAMPLE_LABEL = "2000–2002"
EXAMPLE_BLOCKS = ("2000–2001", "2001–2002")
UNCERTAINTY_DIFF = 0.10                # differences below ~10 % are within uncertainty


# ---------------------------------------------------------------- helpers
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, check=False,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def br(value: float, decimals: int = 2) -> str:
    """pt-BR number: thousands '.', decimal ','."""
    if value is None or not np.isfinite(value):
        return "—"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def pct(value: float, decimals: int = 1) -> str:
    return br(100.0 * value, decimals) + " %"


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def throughput(s_per_step: float, steps_per_day: int) -> float:
    """Simulated days per wall day of the node for one run."""
    return SECONDS_PER_DAY / (s_per_step * steps_per_day)


def parse_ranges(text: str) -> list[list[int]]:
    """'0-27,56-83' -> [[0..27], [56..83]]."""
    out = []
    for part in text.split(","):
        a, _, b = part.partition("-")
        out.append(list(range(int(a), int(b or a) + 1)))
    return out


def compress(cpus: list[int]) -> str:
    """[0,1,2,5] -> '0–2, 5' (display only)."""
    spans, start, prev = [], None, None
    for c in cpus:
        if start is None:
            start = prev = c
        elif c == prev + 1:
            prev = c
        else:
            spans.append((start, prev))
            start = prev = c
    if start is not None:
        spans.append((start, prev))
    return ", ".join(f"{a}–{b}" if a != b else f"{a}" for a, b in spans)


def read_hardware(n_phys: int, per_socket: int) -> dict:
    """CPU numbering per socket and MPICH version from the benchmark snapshot."""
    text = HW_SNAPSHOT.read_text(encoding="utf-8")
    sockets = []
    for node, cpus in re.findall(r"NUMA node(\d+) CPU\(s\):\s+(\S+)", text):
        ranges = parse_ranges(cpus)
        if len(ranges) != 2:
            raise SystemExit(f"unexpected CPU list for NUMA node {node}: {cpus}")
        phys, sib = ranges
        if len(phys) != per_socket or [c - n_phys for c in sib] != phys:
            raise SystemExit(f"NUMA node {node}: SMT numbering is not i / i+{n_phys}")
        sockets.append({"node": int(node), "phys": phys, "sib": sib})
    if len(sockets) * per_socket != n_phys:
        raise SystemExit("socket count in hardware snapshot inconsistent with CSV")
    ver = re.search(r"HYDRA build details:\s*\n\s*Version:\s+(\S+)", text)
    return {"sockets": sockets, "mpich_version": ver.group(1) if ver else "?"}


# ---------------------------------------------------------------- computation
def compute() -> dict:
    bench = pd.read_csv(BENCH_CSV)
    runtime = pd.read_csv(RUNTIME_CSV)

    if not (bench["status"] == "ok").all() or not (bench["rc"] == 0).all():
        raise SystemExit("benchmark table has non-ok trials; stop")
    steps = bench["steps"].unique()
    if len(steps) != 1:
        raise SystemExit(f"trials with different step counts: {steps}")
    steps = int(steps[0])
    window_h = steps * DT_S / 3600.0
    steps_per_day = SECONDS_PER_DAY // DT_S
    if not np.isclose(steps_per_day, steps * 24.0 / window_h):
        raise SystemExit("steps per day inconsistent with the trial window")

    n_phys = int(bench["physical_cores"].max())
    n_logical = int(bench.loc[bench["series"] == "B", "ranks"].max())
    per_socket = int(bench.loc[bench["config"].isin(D_CASES), "ranks"].max())
    n_sockets = n_phys // per_socket
    if n_logical != n_phys * SMT_THREADS:
        raise SystemExit("logical CPU count inconsistent with SMT setting")

    # Per-configuration values, taken from the CSV's own cfg_* columns and
    # checked against the repetitions.
    cfg = {}
    for name, grp in bench.groupby("config", sort=False):
        row = grp.iloc[0]
        mean_sps = float(row["cfg_mean_s_per_step"])
        if not np.isclose(grp["s_per_step"].mean(), mean_sps, atol=1e-3):
            raise SystemExit(f"{name}: cfg_mean_s_per_step != mean of reps")
        cfg[name] = {
            "config": name, "series": row["series"], "ranks": int(row["ranks"]),
            "physical_cores": int(row["physical_cores"]),
            "pinning": row["pinning"], "n_reps": int(row["cfg_n_reps"]),
            "s_per_step": mean_sps,
            "reps_s_per_step": grp["s_per_step"].astype(float).tolist(),
            "spread_pct": float(row["cfg_rep_spread_pct"]),
            "speedup": float(row["speedup_vs_A8"]),
            "eff_phys": float(row["efficiency_vs_A8_physcores"]),
            "eff_ranks": float(row["efficiency_vs_A8_ranks"]),
            "throughput": throughput(mean_sps, steps_per_day),
            "reps_throughput": [throughput(s, steps_per_day)
                                for s in grp["s_per_step"].astype(float)],
            "mpiexec_cmd": str(row["mpiexec_cmd"]),
            "pinning_check": [str(v) for v in grp["pinning_check"]],
        }

    base = cfg[BASE_CONFIG]
    base_cores = base["physical_cores"]
    s8 = base["s_per_step"]
    tp8 = base["throughput"]

    # Repetition-level speed-up/efficiency (points in the saturation figure).
    for c in cfg.values():
        c["reps_speedup"] = [s8 / s for s in c["reps_s_per_step"]]
        c["reps_eff_phys"] = [sp / (c["physical_cores"] / base_cores)
                              for sp in c["reps_speedup"]]
        chk_sp = s8 / c["s_per_step"]
        chk_eff = chk_sp / (c["physical_cores"] / base_cores)
        if not (np.isclose(chk_sp, c["speedup"], rtol=1e-3)
                and np.isclose(chk_eff, c["eff_phys"], rtol=1e-3)):
            raise SystemExit(f"{c['config']}: speed-up/efficiency mismatch")

    # Series D: two simultaneous 28-rank runs; node throughput = sum of both.
    d_rows = bench[bench["config"].isin(D_CASES)]
    d_reps = []
    for rep, grp in d_rows.groupby("repetition"):
        by_case = grp.set_index("config")
        tp_sum = sum(throughput(float(by_case.loc[k, "s_per_step"]),
                                steps_per_day) for k in D_CASES)
        csv_pair = float(by_case["pair_sim_days_per_node_day_integration"].iloc[0])
        if not np.isclose(tp_sum, csv_pair, atol=0.01):
            raise SystemExit("series D pair throughput differs from CSV")
        d_reps.append(tp_sum)
    s0, s1 = (cfg[k] for k in D_CASES)
    d_tp = s0["throughput"] + s1["throughput"]
    cfg["D"] = {
        "config": "D", "series": "D", "ranks": s0["ranks"] + s1["ranks"],
        "physical_cores": s0["physical_cores"] + s1["physical_cores"],
        "pinning": "2 × 28, um soquete cada", "throughput": d_tp,
        "reps_throughput": d_reps,
        "eff_phys": d_tp / (tp8 * (s0["physical_cores"] + s1["physical_cores"])
                            / base_cores),
        "n_reps": s0["n_reps"],
    }
    d_asym = s1["s_per_step"] / s0["s_per_step"] - 1.0

    # Production cost correction: EXP03 production s/step / series C s/step.
    exp03 = runtime[runtime["experiment"] == EXP03_ID].copy()
    if exp03.empty:
        raise SystemExit("no EXP03 rows in runtime_metrics.csv")
    prod_sps = float(exp03["wall_seconds_per_timestep"].mean())
    c_sps = cfg["C_N060"]["s_per_step"]
    corr = prod_sps / c_sps

    compl = load_complement(cfg, steps_per_day, s8, tp8, base_cores, n_phys)

    options = []
    for key in OPTIONS:
        c = cfg[key]
        cost_a = DAYS_PER_YEAR / c["throughput"]
        options.append({
            "key": key, "label": label_of(key), "ranks": c["ranks"],
            "physical_cores": c["physical_cores"], "throughput": c["throughput"],
            "reps_throughput": c["reps_throughput"], "eff_phys": c["eff_phys"],
            "meets": c["eff_phys"] >= EFFICIENCY_CRITERION,
            "cost_a": cost_a, "cost_b": cost_a * corr,
            "proposed": key == PROPOSED,
        })

    # Series E (I/O) against A56 (same ranks and pinning, no output).
    e_rows = bench[bench["series"] == "E"].sort_values("repetition")
    a56_compute_day = cfg["A_N056"]["s_per_step"] * steps_per_day
    io = []
    for _, r in e_rows.iterrows():
        io.append({
            "rep": int(r["repetition"]),
            "stream_output_s": float(r["stream_output_s"]),
            "d_total_s": float(r["delta_vs_A56_total_time_s"]),
            "d_ti_s": float(r["delta_vs_A56_time_integration_s"]),
            "d_wall_s": float(r["delta_vs_A56_wrapper_wall_s"]),
            "n_hist": int(r["n_history_written"]),
            "n_rst": int(r["n_restart_written"]),
            "hist_s": float(r["history_write_s_mean_filestat"]),
            "rst_s": float(r["restart_write_s_filestat"]),
            "extrap_s_day": float(r["io_extrap_s_per_sim_day"]),
            "method": str(r["io_extrap_method"]),
        })
    io_extrap_mean = float(np.mean([x["extrap_s_day"] for x in io]))

    # Historical production costs (context table).
    hist = runtime[["experiment", "period", "mpi_ranks", "n_cells",
                    "wall_seconds_per_timestep", "quality", "method"]].copy()

    spreads = {k: v["spread_pct"] for k, v in cfg.items() if "spread_pct" in v}
    max_spread_cfg = max(spreads, key=spreads.get)

    a_series = sorted((c for c in cfg.values() if c["series"] == "A"),
                      key=lambda c: c["physical_cores"])
    a_meeting = [c for c in a_series if c["eff_phys"] >= EFFICIENCY_CRITERION]

    exp03_cells = int(exp03["n_cells"].iloc[0])
    r = {
        "bench": bench, "runtime": runtime, "cfg": cfg, "steps": steps,
        "window_h": window_h, "steps_per_day": steps_per_day,
        "n_phys": n_phys, "n_logical": n_logical, "per_socket": per_socket,
        "n_sockets": n_sockets, "base_cores": base_cores, "s8": s8, "tp8": tp8,
        "d_asym": d_asym, "prod_sps": prod_sps,
        "prod_rows": exp03[["period", "mpi_ranks", "wall_seconds_per_timestep",
                            "quality", "method"]].to_dict("records"),
        "c_sps": c_sps, "corr": corr, "options": options, "io": io,
        "io_extrap_mean": io_extrap_mean, "a56_compute_day": a56_compute_day,
        "hist": hist, "max_spread_cfg": max_spread_cfg,
        "max_spread": spreads[max_spread_cfg], "a_series": a_series,
        "a_meeting": a_meeting, "exp03_cells": exp03_cells,
        "trial_count": len(bench), "compl": compl,
    }
    r["hw"] = read_hardware(n_phys, per_socket)
    r["proj"] = project(r)
    r["run"] = run_practice(r)
    r["disk"] = disk_facts()
    return r


def cores_of_cmd(cmd: str, n_phys: int) -> list[int]:
    """Physical cores occupied by a '-bind-to user:<list>' command."""
    m = re.search(r"user:([\d,]+)", cmd)
    if not m:
        raise SystemExit(f"no CPU list in command: {cmd[:60]}")
    return sorted({int(v) % n_phys for v in m.group(1).split(",")})


def load_complement(cfg: dict, spd: int, s8: float, tp8: float,
                    base_cores: int, n_phys: int) -> dict:
    """MEQ-05.5 rows, normalised by REF_A56 of the same block (used_in_stats
    rows only) and converted to MEQ-05.2 absolute values by multiplying by the
    mean s/step of A_N056 (MEQ-05.2). Adds one cfg entry per configuration."""
    df = pd.read_csv(COMPL_CSV)
    if not (df["status"] == "ok").all() or not (df["rc"] == 0).all():
        raise SystemExit("complement table has non-ok trials; stop")
    used = df[df["used_in_stats"].astype(bool)].copy()
    blocks = sorted(used["block"].unique())
    a56 = cfg["A_N056"]["s_per_step"]

    def by_cfg(name):
        g = used[used["config"] == name].sort_values("block")
        if g.empty:
            raise SystemExit(f"complement: no used rows for {name}")
        norm = float(g["s_per_step_norm"].mean())
        csv_norm = float(g["cfg_mean_s_per_step_norm"].iloc[0])
        if not np.isclose(norm, csv_norm, atol=2e-4):
            raise SystemExit(f"{name}: mean of s_per_step_norm != cfg_mean ({norm} {csv_norm})")
        return g, norm

    out = {"blocks": blocks, "single": {}, "pairs": {}}
    for name in COMPL_SINGLE:
        g, norm = by_cfg(name)
        s = norm * a56
        cores = cores_of_cmd(str(g["mpiexec_cmd"].iloc[0]), n_phys)
        reps_s = [float(v) * a56 for v in g["s_per_step_norm"]]
        c = {
            "config": name, "series": "MEQ-05.5", "ranks": int(g["ranks"].iloc[0]),
            "physical_cores": len(cores), "cores": cores,
            "free_cores": int(g["free_whole_cores_node"].iloc[0]),
            "pinning": str(g["pinning"].iloc[0]), "n_reps": len(g),
            "norm": norm, "s_per_step": s, "reps_s_per_step": reps_s,
            "throughput": throughput(s, spd),
            "reps_throughput": [throughput(x, spd) for x in reps_s],
            "speedup": s8 / s, "reps_speedup": [s8 / x for x in reps_s],
            "mpiexec_cmd": str(g["mpiexec_cmd"].iloc[0]),
            "block_norm": [float(v) for v in g["s_per_step_norm"]],
            "stream_output_s": [float(v) for v in g["stream_output_s"]],
            "raw_s_per_step": [float(v) for v in g["s_per_step"]],
        }
        c["eff_phys"] = c["speedup"] / (c["physical_cores"] / base_cores)
        if len(cores) + c["free_cores"] != n_phys:
            raise SystemExit(f"{name}: occupied + free cores != {n_phys}")
        cfg[name] = c
        out["single"][name] = c

    for pair, (k0, k1) in COMPL_PAIRS.items():
        g0, n0 = by_cfg(k0)
        g1, n1 = by_cfg(k1)
        pair_norms = [float(v) for v in g0["pair_sim_days_per_node_day_integration_norm"]]
        pair_norm = float(np.mean(pair_norms))
        cores = sorted(set(cores_of_cmd(str(g0["mpiexec_cmd"].iloc[0]), n_phys))
                       | set(cores_of_cmd(str(g1["mpiexec_cmd"].iloc[0]), n_phys)))
        tp_a56 = throughput(a56, spd)
        c = {
            "config": pair, "series": "MEQ-05.5", "ranks": int(g0["ranks"].iloc[0]) * 2,
            "ranks_each": int(g0["ranks"].iloc[0]),
            "physical_cores": len(cores), "free_cores": n_phys - len(cores),
            "n_reps": len(g0), "pair_norm": pair_norm, "pair_norms": pair_norms,
            "throughput": pair_norm * tp_a56,
            "reps_throughput": [v * tp_a56 for v in pair_norms],
            "s0": n0 * a56, "s1": n1 * a56, "norm0": n0, "norm1": n1,
            "s_slow": max(n0, n1) * a56,
            "asym_blocks": [float(b) / float(a) - 1.0 for a, b in
                            zip(g0["s_per_step"], g1["s_per_step"])],
            "cmd0": str(g0["mpiexec_cmd"].iloc[0]), "cmd1": str(g1["mpiexec_cmd"].iloc[0]),
        }
        c["eff_phys"] = c["throughput"] / (tp8 * c["physical_cores"] / base_cores)
        cfg[pair] = c
        out["pairs"][pair] = c

    # Agreement between sessions (raw means, informative).
    def raw_mean(name):
        return float(used.loc[used["config"] == name, "s_per_step"].mean())
    out["agree_a56"] = raw_mean(COMPL_REF) / cfg["A_N056"]["s_per_step"] - 1.0
    out["agree_b112"] = raw_mean("REF_B112") / cfg["B_N112"]["s_per_step"] - 1.0
    out["ref_raw_a56"] = raw_mean(COMPL_REF)
    out["ref_raw_b112"] = raw_mean("REF_B112")
    out["b112_norm"] = by_cfg("REF_B112")[1]
    out["n_used"] = int(len(used))
    out["n_rows"] = int(len(df))
    out["ref_block_means"] = [float(used.loc[(used["config"] == COMPL_REF)
                                             & (used["block"] == b), "s_per_step"].mean())
                              for b in blocks]
    # I/O: E90C against P90C of the same block.
    e = used[used["config"] == "E90C"].sort_values("block")
    p = used[used["config"] == "P90C"].sort_values("block")
    out["io90"] = [{
        "block": int(er["block"]), "stream_output_s": float(er["stream_output_s"]),
        "d_sps": float(er["s_per_step"]) / float(pr["s_per_step"]) - 1.0,
        "n_hist": int(er["n_history_written"]), "n_rst": int(er["n_restart_written"]),
        "hist_s": float(er["history_write_s_mean_filestat"]),
        "rst_s": float(er["restart_write_s_filestat"]),
        "extrap_s_day": float(er["io_extrap_s_per_sim_day"]),
    } for (_, er), (_, pr) in zip(e.iterrows(), p.iterrows())]
    out["io90_mean"] = float(np.mean([x["extrap_s_day"] for x in out["io90"]]))
    return out


def disk_facts() -> dict:
    """Real sizes from the MEQ-05.5 read-only inventory of the EXP03 legs."""
    hv = pd.read_csv(HIST_VARS_CSV)
    text = DISK_INV.read_text(encoding="utf-8")
    m = re.search(r"captured (\S+) on", text)
    captured = m.group(1) if m else "?"

    def size_of(prefix):
        mm = re.search(rf"^{re.escape(prefix)}\S*\tapparent=(\d+)", text, re.M)
        if not mm:
            raise SystemExit(f"disk inventory: no representative {prefix}")
        return int(mm.group(1))

    def fmt_of(prefix):
        mm = re.search(rf"^{re.escape(prefix)}\S*\tapparent=\d+.*\n\s+format\(ncdump -k\)=(\S+)",
                       text, re.M)
        return mm.group(1) if mm else "?"

    hist = size_of("history.")
    sizes = {"history": hist, "restart": size_of("restart."), "lbc": size_of("lbc."),
             "init": size_of("meqbr_05km_oval_meq02a.init"),
             "sfc": size_of("meqbr_05km_oval_meq02a.sfc_update")}
    formats = {k: fmt_of(p) for k, p in (("history", "history."), ("restart", "restart."),
                                          ("lbc", "lbc."))}
    var_bytes = int(hv["bytes_per_file"].sum())
    nlev = None
    rows = []
    for v in hv.itertuples():
        dims = str(v.dimensions)
        if "nVertLevelsP1" in dims:
            kind, lev = "3D", 56
        elif "nVertLevels" in dims:
            kind, lev = "3D", 55
            nlev = 55
        elif "nCells" in dims:
            kind, lev = "2D", 1
        else:
            kind, lev = "texto (data)", "—"
        rows.append({"name": v.variable, "kind": kind, "lev": lev, "units": v.units,
                     "static": "Time" not in dims, "bytes": int(v.bytes_per_file)})
    files_per_year = DAYS_PER_YEAR * HOURS_PER_DAY
    return {
        "captured": captured, "sizes": sizes, "formats": formats,
        "n_vars": len(hv), "var_bytes": var_bytes, "header_bytes": hist - var_bytes,
        "nlev": nlev, "rows": rows,
        "final_tb": [(n, n * files_per_year * hist / 1e12) for n in DISK_YEARS],
        "spinup_tb": SPINUP_DAYS * HOURS_PER_DAY * hist / 1e12,
        "hist_per_day_gb": HOURS_PER_DAY * hist / 1e9,
        "rst_year_tb": DAYS_PER_YEAR * sizes["restart"] / 1e12,
        "rst_keep_gb": RESTARTS_KEPT * sizes["restart"] / 1e9,
        "lbc_year_tb": DAYS_PER_YEAR * LBC_PER_DAY * sizes["lbc"] / 1e12,
        "free_space": FREE_SPACE_TB,  # reported in the initial MEQ-05 diagnosis
    }


def project(r: dict) -> dict:
    """MEQ-06 duration (PI's formulas) from MEASURED s/step where available,
    plus the previous version's estimates for the estimate x measurement table."""
    cfg = r["cfg"]

    def s(key: str) -> float:
        return cfg[key]["s_per_step"]

    n_phys, per_socket = r["n_phys"], r["per_socket"]
    corr, spd = r["corr"], r["steps_per_day"]

    # ---- previous version (MEQ-05.3) estimates, kept only for comparison
    f = s("B_N112") / s("A_N056")                      # SMT gain
    lo, hi = cfg[INTERP_LO], cfg[INTERP_HI]
    n_compact = PROJ_RANKS // SMT_THREADS              # 45 physical cores
    w = (n_compact - lo["physical_cores"]) / (hi["physical_cores"] - lo["physical_cores"])
    s_a45 = lo["s_per_step"] + w * (hi["s_per_step"] - lo["s_per_step"])
    n_extra = PROJ_RANKS - n_phys
    k = np.mean([s(d) for d in D_CASES]) / s("A_N028")
    if "A_N%03d" % per_socket != "A_N028":
        raise SystemExit("per-socket core count no longer matches A_N028")
    pair_small = PROJ_RANKS // 2
    pair_big = r["n_logical"] // 2
    n_extra_sock = pair_small - per_socket
    est_sps = {
        "P90C": s_a45 * f,
        "P90E": s("A_N056") - (n_extra / n_phys) * (s("A_N056") - s("B_N112")),
        "Q45S": (s("A_N028") - (n_extra_sock / per_socket)
                 * (s("A_N028") - s("A_N028") * f)) * k,
        "Q56": s("A_N028") * f * k,
    }
    spd_tp = lambda x: throughput(x, spd)
    est_rows = []
    for key, label, pair in (("P90C", f"{PROJ_RANKS} compacto", False),
                             ("P90E", f"{PROJ_RANKS} espalhado", False),
                             ("Q45S", f"{pair_small}/{pair_small} por soquete", True),
                             ("Q56", f"{pair_big}/{pair_big}", True)):
        m = cfg[key]
        est_tp = spd_tp(est_sps[key]) * (2 if pair else 1)
        meas_s = (m["s0"] + m["s1"]) / 2 if pair else m["s_per_step"]
        est_rows.append({"key": key, "label": label, "pair": pair,
                         "est_s": est_sps[key], "meas_s": meas_s,
                         "est_tp": est_tp, "meas_tp": m["throughput"],
                         "diff": meas_s / est_sps[key] - 1.0})

    # ---- durations from measurements
    def days_for(x: float, years: float, c: float = corr) -> float:
        """Wall days for one continuous run of `years` simulated years + spin-up."""
        return (years * DAYS_PER_YEAR + SPINUP_DAYS) * spd * x * c / SECONDS_PER_DAY

    def days_per_run_year(x: float, c: float = corr) -> float:
        return DAYS_PER_YEAR * spd * x * c / SECONDS_PER_DAY

    P, Q = cfg["P90C"], cfg["P90E"]
    rows_def = [
        ("P90C", f"{PROJ_RANKS} compacto", False, P["s_per_step"], P["free_cores"],
         f"{PROJ_RANKS} processos em {P['physical_cores']} núcleos físicos, com as duas tarefas de cada núcleo"),
        ("P90E", f"{PROJ_RANKS} espalhado", False, Q["s_per_step"], Q["free_cores"],
         f"{PROJ_RANKS} processos nos {n_phys} núcleos: {n_extra} núcleos com duas tarefas, "
         f"{n_phys - n_extra} com uma"),
        ("Q45C", f"{pair_small}/{pair_small} compacto", True, cfg["Q45C"]["s_slow"],
         cfg["Q45C"]["free_cores"],
         f"dois blocos simultâneos de {pair_small} processos, cada um num soquete, em "
         f"{cfg['Q45C']['physical_cores'] // 2} núcleos com as duas tarefas"),
        ("Q45S", f"{pair_small}/{pair_small} por soquete", True, cfg["Q45S"]["s_slow"],
         cfg["Q45S"]["free_cores"],
         f"dois blocos simultâneos de {pair_small} processos, cada um espalhado pelo seu soquete "
         f"({n_extra_sock} dos {per_socket} núcleos com duas tarefas)"),
        ("B_N112", f"{r['n_logical']}", False, s("B_N112"), 0,
         f"{r['n_logical']} processos, um por tarefa, em todos os {n_phys} núcleos"),
        ("Q56", f"{pair_big}/{pair_big}", True, cfg["Q56"]["s_slow"], cfg["Q56"]["free_cores"],
         f"dois blocos simultâneos, cada um num soquete com {per_socket} núcleos × 2 tarefas"),
    ]
    rows = []
    for key, label, double, sx, free, desc in rows_def:
        blocks = 2 if double else 1
        rows.append({
            "key": key, "label": label, "double": double, "blocks": blocks,
            "free_cores": free, "desc": desc, "s": sx,
            "days_run_year": days_per_run_year(sx),
            "days_run_year_raw": days_per_run_year(sx, 1.0),
            "durations": [days_for(sx, n / blocks) for n in PROJ_YEARS],
            "durations_raw": [days_for(sx, n / blocks, 1.0) for n in PROJ_YEARS],
        })
    by_key = {x["key"]: x for x in rows}

    # Brief check (MEQ-05.6): 90 compact, 1 year ~= 17.1 days (15.0 without c).
    i1 = PROJ_YEARS.index(1)
    chk, chk_raw = by_key["P90C"]["durations"][i1], by_key["P90C"]["durations_raw"][i1]
    if abs(chk - 17.1) > 0.3 or abs(chk_raw - 15.0) > 0.3:
        raise SystemExit(f"STOP: 90 compact 1 year = {chk:.2f} ({chk_raw:.2f} raw); "
                         f"expected 17.1 ± 0.3 (15.0)")

    example = []
    for key, how in (("P90C", f"uma rodada contínua de {EXAMPLE_LABEL}"),
                     ("P90E", f"uma rodada contínua de {EXAMPLE_LABEL}"),
                     ("Q45C", f"dois blocos ao mesmo tempo: {EXAMPLE_BLOCKS[0]} e "
                              f"{EXAMPLE_BLOCKS[1]}, cada um com seu spin-up"),
                     ("Q56", f"dois blocos ao mesmo tempo: {EXAMPLE_BLOCKS[0]} e "
                             f"{EXAMPLE_BLOCKS[1]}, cada um com seu spin-up"),
                     ("B_N112", f"uma rodada contínua de {EXAMPLE_LABEL}")):
        x = by_key[key]
        example.append({"key": key, "label": x["label"], "how": how,
                        "days": days_for(x["s"], EXAMPLE_YEARS / x["blocks"]),
                        "days_raw": days_for(x["s"], EXAMPLE_YEARS / x["blocks"], 1.0)})
    ex_ref = example[0]["days"]
    for e in example:
        e["vs_first"] = e["days"] / ex_ref - 1.0

    return {
        "f": f, "s_a45": s_a45, "k": k, "c": corr, "w": w,
        "n_compact": n_compact, "n_extra": n_extra, "pair_small": pair_small,
        "pair_big": pair_big, "n_extra_sock": n_extra_sock,
        "rows": rows, "by_key": by_key, "drop_without_c": 1.0 - 1.0 / corr,
        "example": example, "est_rows": est_rows,
    }


def run_practice(r: dict) -> dict:
    """Facts for the "Como rodar na prática" chapter (from CSV and snapshot)."""
    cfg, hw = r["cfg"], r["hw"]
    unp, pin = cfg[UNPINNED_CFG], cfg[PINNED_CFG]
    shared, occupied = set(), set()
    for chk in unp["pinning_check"]:
        m = re.search(r"ranks_on_shared_physical_core_per_sample=([\d/]+)", chk)
        o = re.search(r"physical_cores_occupied_per_sample=([\d/]+)", chk)
        a = re.search(r"affinity=([\d-]+)", chk)
        if not (m and o and a):
            raise SystemExit(f"unexpected pinning_check for {UNPINNED_CFG}: {chk}")
        shared.update(int(v) for v in m.group(1).split("/"))
        occupied.update(int(v) for v in o.group(1).split("/"))
        affinity = a.group(1)
    if len(shared) != 1 or len(occupied) != 1:
        raise SystemExit("series C sharing varied between samples; update text")

    # Example "90 compacto": n_compact physical cores with both tasks, split as
    # evenly as possible between sockets, same order as the validated B112 list
    # (socket 0 physical, socket 0 siblings, socket 1 physical, socket 1 siblings).
    # Example "90 compacto": exactly the command recorded in the MEQ-05.5 CSV.
    socks = hw["sockets"]
    example = cfg["P90C"]["mpiexec_cmd"]
    cpus = [int(v) for v in re.search(r"user:([\d,]+)", example).group(1).split(",")]
    if len(cpus) != PROJ_RANKS or len(set(cpus)) != PROJ_RANKS:
        raise SystemExit("P90C CPU list is not 90 distinct CPUs")
    used_phys = set(cfg["P90C"]["cores"])
    per = [len([c for c in sk["phys"] if c in used_phys]) for sk in socks]
    free = [c for sk in socks for c in sk["phys"] if c not in used_phys]
    for sk, n in zip(socks, per):
        if set(sk["phys"][:n] + sk["sib"][:n]) - set(cpus):
            raise SystemExit("P90C list is not 'first n cores of each socket with siblings'")
    return {
        "unpinned_cmd": unp["mpiexec_cmd"], "pinned_cmd": pin["mpiexec_cmd"],
        "unpinned_ranks": unp["ranks"], "pinned_ranks": pin["ranks"],
        "shared": shared.pop(), "occupied": occupied.pop(),
        "affinity": affinity,
        "slowdown": unp["s_per_step"] / pin["s_per_step"] - 1.0,
        "example_cmd": example, "per_socket_alloc": per,
        "example_blocks": [compress(sk["phys"][:n]) + " + " + compress(sk["sib"][:n])
                           for sk, n in zip(socks, per)],
        "free_cores": free, "free_txt": compress(free),
    }


def label_of(key: str) -> str:
    return {"A_N056": "A56", "B_N112": "B112", "C_N060": "C60",
            "D": "D (2 × 28)", "P90C": "90 compacto", "P90E": "90 espalhado",
            "Q45S": "45/45 por soquete", "Q45C": "45/45 compacto",
            "Q56": "56/56"}.get(key, key)


# Plain-language x-axis labels for the throughput chart (chapter 4): what each
# bar is, then the question it answers. Codes stay in hover and caption.
THROUGHPUT_TICKS = {
    "A_N056": ("1 rodada, 56 núcleos", "Referência: 1 processo por núcleo"),
    "B_N112": ("1 rodada, 112 tarefas (SMT)", "Vale usar as 2 tarefas de cada núcleo?"),
    "C_N060": ("1 rodada, mpiexec simples", "Quanto se perde sem fixar os processos?"),
    "D": ("2 rodadas ao mesmo tempo", "Vale dividir a máquina em duas simulações?"),
    "P90C": ("1 rodada, 90 em 45 núcleos", "Quanto rende deixando 11 núcleos livres?"),
    "P90E": ("1 rodada, 90 nos 56 núcleos", "Espalhar rende mais que compactar?"),
    "Q45S": ("2 × 45, espalhadas no soquete", "Dois blocos de 45 valem a pena?"),
    "Q45C": ("2 × 45, compactas", "E deixando 10 núcleos livres?"),
    "Q56": ("2 × 56, um soquete cada", "Dois blocos ocupando tudo rendem mais?"),
}


# ---------------------------------------------------------------- page text
def chart_payload(r: dict) -> dict:
    cfg = r["cfg"]
    a_pts = []
    for c in r["a_series"]:
        for k, (sp, ef) in enumerate(zip(c["reps_speedup"], c["reps_eff_phys"])):
            a_pts.append({"x": c["physical_cores"], "sp": sp, "eff": ef,
                          "rep": k + 1, "cfg": c["config"]})
    spd = r["steps_per_day"]

    def views(c, s, cores):
        tp = throughput(s, spd)
        return {"sp": r["s8"] / s, "tp": tp, "tpc": tp / cores,
                "eff": (r["s8"] / s) / (cores / r["base_cores"])}

    for pt in a_pts:
        c = cfg[pt["cfg"]]
        s = r["s8"] / pt["sp"]
        pt.update(views(c, s, c["physical_cores"]))

    def series_pts(key, label):
        c = cfg[key]
        return {"label": label, "x": c["ranks"], "cores": c["physical_cores"],
                **views(c, c["s_per_step"], c["physical_cores"]),
                "reps": [dict(views(c, s, c["physical_cores"]), rep=k + 1)
                         for k, s in enumerate(c["reps_s_per_step"])]}

    return {
        "criterion": EFFICIENCY_CRITERION,
        "base_cores": r["base_cores"], "n_phys": r["n_phys"],
        "a_mean": [{"x": c["physical_cores"], "cfg": c["config"],
                    **views(c, c["s_per_step"], c["physical_cores"])}
                   for c in r["a_series"]],
        "a_pts": a_pts,
        "ext": [series_pts("P90E", f"90 espalhado (56 núcleos)"),
                series_pts("B_N112", f"112 (56 núcleos)")],
        "p90c": series_pts("P90C", "90 compacto"),
        "p90c_free": cfg["P90C"]["free_cores"],
        "options": [{"key": o["key"], "label": o["label"],
                     "pair": o["key"] in ("D",) + tuple(COMPL_PAIRS),
                     "tick": list(THROUGHPUT_TICKS[o["key"]]), "tp": o["throughput"],
                     "reps": o["reps_throughput"], "eff": o["eff_phys"],
                     "cost_a": o["cost_a"], "cost_b": o["cost_b"]}
                    for o in r["options"]],
    }


def shows(text: str) -> str:
    return f'<p class="lead"><b>O que esta seção mostra.</b> {text}</p>'


def means(text: str) -> str:
    return f'<div class="note practice"><b>O que isso significa na prática.</b> {text}</div>'


def build_html(r: dict, meta: dict) -> str:
    cfg = r["cfg"]
    o = {x["key"]: x for x in r["options"]}
    a56, b112, c60 = cfg["A_N056"], cfg["B_N112"], cfg["C_N060"]
    a42 = cfg["A_N042"]
    s0, s1 = cfg[D_CASES[0]], cfg[D_CASES[1]]
    hist = r["hist"]
    ranks_hist = sorted(hist["mpi_ranks"].unique())
    cells_hist = sorted(hist["n_cells"].unique())
    n_est = int((hist["quality"] != "measured").sum())
    multi_rank = [e for e, g in hist.groupby("experiment")
                  if g["mpi_ranks"].nunique() > 1]
    best_a = r["a_meeting"][-1] if r["a_meeting"] else None
    b_vs_a56 = b112["throughput"] / a56["throughput"] - 1.0
    a56_vs_c = a56["throughput"] / c60["throughput"] - 1.0
    io_share = r["io_extrap_mean"] / r["a56_compute_day"]
    a42_to_a56_time = 1.0 - a56["s_per_step"] / a42["s_per_step"]
    a42_to_a56_cores = a56["physical_cores"] / a42["physical_cores"] - 1.0
    smt_gain = 1.0 - b112["s_per_step"] / a56["s_per_step"]
    cost_b_vals = [x["cost_b"] for x in r["options"]]
    p, run, hw = r["proj"], r["run"], r["hw"]
    pk = p["by_key"]
    compl = r["compl"]
    n_phys, n_log, per_socket = r["n_phys"], r["n_logical"], r["per_socket"]

    # --- glossary
    gloss = [
        ("Nó", f"Um computador completo. O Swell é um único nó; tudo neste relatório roda dentro dele."),
        ("Soquete", f"Cada um dos {r['n_sockets']} processadores (chips) do nó. Cada soquete tem "
                    f"{per_socket} núcleos e sua própria memória."),
        ("Núcleo físico", f"Uma unidade de cálculo real do processador. O Swell tem {n_phys}."),
        ("SMT", f"Cada núcleo físico guarda o estado de duas tarefas e alterna entre elas quando uma "
                f"espera dados da memória; o circuito de cálculo é um só, por isso o ganho é de cerca "
                f"de {pct(smt_gain, 0)} (B{n_log} contra A{n_phys}), não o dobro. É como um cozinheiro "
                f"com duas panelas: enquanto uma esquenta, ele mexe a outra, mas continua sendo um só "
                f"cozinheiro. O sistema mostra {n_log} \"CPUs\", mas só {n_phys} são núcleos reais."),
        ("Processo (rank)", "Fatia da malha calculada por um núcleo. Com N processos, o MPAS divide "
                            "as células em N pedaços que são calculados ao mesmo tempo e trocam "
                            "informação nas bordas a cada passo."),
        ("Decomposição / partição", "O corte da malha em N pedaços de tamanho parecido, feito antes "
                                    "da rodada (programa METIS). O MPAS precisa de um arquivo de "
                                    "partição para cada N (<code>graph.info.part.N</code>)."),
        ("Fixação de processos", "Dizer ao sistema em qual núcleo cada processo deve ficar, para que "
                                 "ele não seja movido durante a rodada. Sem fixação, o sistema decide "
                                 "e pode mudar de ideia."),
        ("s/passo", f"Segundos de relógio que o modelo leva para avançar um passo de tempo "
                    f"({DT_S} s de tempo de modelo). Quanto menor, mais rápido."),
        ("Aceleração", f"Quantas vezes a rodada fica mais rápida que a rodada de referência com "
                       f"{r['base_cores']} núcleos. Aceleração 4 = quatro vezes mais rápida."),
        ("Eficiência paralela", "Quanto do ganho ideal se obtém. Dobrar os núcleos e ficar duas vezes "
                                "mais rápido é 100 %; ficar 1,4 vez mais rápido é 70 %."),
        ("Vazão", "Quanto tempo de modelo a máquina produz por dia de relógio. Aqui, em dias simulados "
                  "por dia de máquina; dividindo 365 pela vazão obtém-se quantos dias de máquina "
                  "custa um ano simulado."),
        ("I/O", "Leitura e gravação de arquivos (do inglês <i>input/output</i>). Neste relatório, o "
                "tempo gasto gravando os arquivos de saída e de reinício."),
    ]
    gloss_rows = "".join(f"<tr><th>{t}</th><td>{d}</td></tr>" for t, d in gloss)

    # --- historical table (drawer)
    hist_rows = "".join(
        f"<tr><td>{esc(h.experiment)}</td><td>{esc(h.period)}</td>"
        f"<td>{int(h.mpi_ranks)}</td><td>{br(h.n_cells, 0)}</td>"
        f"<td>{br(h.wall_seconds_per_timestep, 3)}</td>"
        f"<td>{'medido' if h.quality == 'measured' else 'estimado'}</td></tr>"
        for h in hist.itertuples())

    # --- series table
    def cfg_list(series):
        names = [c["config"] for c in cfg.values()
                 if c["series"] == series and c["config"] != "D"]
        return ", ".join(f"<code>{esc(n)}</code>" for n in names)

    a_ns = "/".join(str(c["physical_cores"]) for c in reversed(r["a_series"]))
    series_rows = [
        ("A", f"Quanto o modelo acelera com mais núcleos: {a_ns} processos, metade em cada "
              f"soquete, um processo por núcleo físico.",
         cfg_list("A"), "fixada, só núcleos físicos"),
        ("B", f"Se vale usar a segunda tarefa de cada núcleo (SMT): {b112['ranks']} processos nos "
              f"mesmos {b112['physical_cores']} núcleos físicos.",
         cfg_list("B"), "fixada, um processo por tarefa"),
        ("C", f"Como a produção foi rodada: {c60['ranks']} processos sem fixação, como na EXP03. "
              f"Liga o benchmark aos tempos reais de produção.",
         cfg_list("C"), "sem fixação"),
        ("D", f"Duas rodadas independentes ao mesmo tempo, de {s0['ranks']} processos cada, "
              f"uma em cada soquete.",
         cfg_list("D"), "fixada, um soquete por rodada"),
        ("E", f"Quanto custa gravar arquivos: igual à A{a56['ranks']}, mas gravando a saída da "
              f"produção (arquivos horários e um arquivo de reinício).",
         cfg_list("E"), "fixada, como A56"),
    ]
    series_html = "".join(
        f"<tr><th>{s}</th><td style='text-align:left'>{t}</td>"
        f"<td style='text-align:left'>{c}</td><td>{pp}</td></tr>"
        for s, t, c, pp in series_rows)

    # --- measured table (all configurations)
    meas_rows = "".join(
        f"<tr><td>{esc(c['config'])}</td><td>{c['ranks']}</td>"
        f"<td>{c['physical_cores']}</td><td>{br(c['s_per_step'], 4)}</td>"
        f"<td>{br(c['spread_pct'], 2)}</td><td>{br(c['speedup'], 3)}</td>"
        f"<td>{pct(c['eff_phys'])}</td><td>{br(c['throughput'], 2)}</td></tr>"
        for c in cfg.values() if c["series"] in ("A", "B", "C", "D", "E") and c["config"] != "D")

    # --- I/O table
    io_rows = "".join(
        f"<tr><td>r{x['rep']}</td><td>{br(x['stream_output_s'], 2)}</td>"
        f"<td>{br(x['d_ti_s'], 2)}</td><td>{br(x['d_wall_s'], 0)}</td>"
        f"<td>{x['n_hist']} × {br(x['hist_s'], 3)}</td>"
        f"<td>{x['n_rst']} × {br(x['rst_s'], 2)}</td>"
        f"<td><b>{br(x['extrap_s_day'], 2)}</b></td></tr>"
        for x in r["io"])

    # --- decision table
    def dec_row(x):
        mark = (f"<span class='pill gain'>{esc(PROPOSED_LABEL)}</span>"
                if x["proposed"] else "—")
        meets = ("sim" if x["meets"] else "não")
        return (f"<tr{' class=proposed' if x['proposed'] else ''}>"
                f"<th>{esc(x['label'])}</th>"
                f"<td>{x['ranks']} / {x['physical_cores']}</td>"
                f"<td>{n_phys - x['physical_cores']}</td>"
                f"<td>{br(x['throughput'], 2)}</td>"
                f"<td>{pct(x['eff_phys'])}</td><td>{meets}</td>"
                f"<td>{br(x['cost_a'], 1)}</td><td>{br(x['cost_b'], 1)}</td>"
                f"<td style='text-align:left'>{mark}</td></tr>")
    dec_rows = "".join(dec_row(x) for x in r["options"])

    prod_txt = "média das rodadas " + "; ".join(
        f"{pr['period']}: {br(pr['wall_seconds_per_timestep'], 4)} s/passo, "
        f"{pr['mpi_ranks']} processos, "
        f"{'medido' if pr['quality'] == 'measured' else 'estimado'}"
        for pr in r["prod_rows"])

    sha_rows = "".join(
        f"<tr><th><code>{esc(k)}</code></th><td><code>{esc(v)}</code></td></tr>"
        for k, v in meta["inputs"].items())

    a_eff_txt = "; ".join(f"A{c['physical_cores']}: {pct(c['eff_phys'])}"
                          for c in r["a_series"])

    # --- projection table (measured s/step; c applied; raw value in a sub-line)
    def dur_cell(x, i, n):
        v, raw = x["durations"][i], x["durations_raw"][i]
        txt = f"{br(v, 1)} dias"
        if n >= 10:
            txt += f"<br><span class='sub'>{br(v / DAYS_PER_MONTH, 1)} meses</span>"
        txt += f"<br><span class='sub'>sem c: {br(raw, 1)}</span>"
        return f"<td>{txt}</td>"
    proj_rows = "".join(
        f"<tr{' class=proposed' if x['key'] == PROPOSED else ''}><th>{esc(x['label'])}</th>"
        f"<td class='desc' style='text-align:left'>{esc(x['desc'])}</td>"
        f"<td>{x['free_cores']}</td>"
        + "".join(dur_cell(x, i, n) for i, n in enumerate(PROJ_YEARS)) + "</tr>"
        for x in p["rows"])
    proj_head = "".join(f"<th>{n} {'ano' if n == 1 else 'anos'}</th>" for n in PROJ_YEARS)

    def s_src(key):
        if key in COMPL_PAIRS:
            c = cfg[key]
            return (f"rodada mais lenta do par (soquete 1): {br(c['norm1'], 4)} × "
                    f"{br(a56['s_per_step'], 4)} (MEQ-05.5 normalizada)")
        if key in compl["single"]:
            return (f"{br(cfg[key]['norm'], 4)} × {br(a56['s_per_step'], 4)} (MEQ-05.5 normalizada)")
        return "medido na MEQ-05.2"
    proj_method_rows = "".join(
        f"<tr><th>{esc(x['label'])}</th><td style='text-align:left'>{s_src(x['key'])}</td>"
        f"<td>{br(x['s'], 4)}</td><td>{br(x['days_run_year'], 1)}</td>"
        f"<td>{br(x['days_run_year_raw'], 1)}</td></tr>"
        for x in p["rows"])
    ex_rows = "".join(
        f"<tr><th>{esc(e['label'])}</th><td style='text-align:left'>{esc(e['how'])}</td>"
        f"<td>{br(e['days'], 1)} dias<br><span class='sub'>sem c: {br(e['days_raw'], 1)}</span></td>"
        f"<td>{'—' if i == 0 else ('+' if e['vs_first'] >= 0 else '') + pct(e['vs_first'], 0)}</td></tr>"
        for i, e in enumerate(p["example"]))
    ex = {e["key"]: e for e in p["example"]}
    P90C, P90E = cfg["P90C"], cfg["P90E"]
    ce_diff = P90C["s_per_step"] / P90E["s_per_step"] - 1.0
    compact_vs_spread = (
        f"<p><b>{PROJ_RANKS} compacto × {PROJ_RANKS} espalhado.</b> {PROJ_RANKS} espalhado usa os "
        f"{n_phys} núcleos físicos ({p['n_extra']} com duas tarefas, {n_phys - p['n_extra']} com uma); "
        f"{PROJ_RANKS} compacto usa só {P90C['physical_cores']} núcleos e deixa {P90C['free_cores']} "
        f"inteiros livres para outros usuários. <b>Medidos, os dois empatam</b>: o compacto levou "
        f"{br(P90C['s_per_step'], 4)} s/passo e o espalhado {br(P90E['s_per_step'], 4)} "
        f"({'+' if ce_diff >= 0 else ''}{pct(ce_diff, 1)}), diferença dentro da variação entre "
        f"repetições. Ocupar menos núcleos, neste caso, não custa prazo.</p>")

    # --- estimate x measurement
    est_rows = "".join(
        f"<tr><th>{esc(e['label'])}</th><td>{br(e['est_s'], 4)}</td><td>{br(e['meas_s'], 4)}</td>"
        f"<td>{'+' if e['diff'] >= 0 else ''}{pct(e['diff'], 1)}</td>"
        f"<td>{br(e['est_tp'], 1)}</td><td>{br(e['meas_tp'], 1)}</td></tr>"
        for e in p["est_rows"])
    est = {e["key"]: e for e in p["est_rows"]}

    # --- simultaneous runs (asymmetry)
    pair_list = [("D", f"28/28 (série D, MEQ-05.2)", s0["s_per_step"], s1["s_per_step"],
                  [b / a - 1 for a, b in zip(s0["reps_s_per_step"], s1["reps_s_per_step"])])]
    for k in COMPL_PAIRS:
        c = cfg[k]
        pair_list.append((k, f"{label_of(k)} (MEQ-05.5)", c["s0"], c["s1"], c["asym_blocks"]))
    all_asym = [v for *_, a in pair_list for v in a]
    compl_asym = [v for k, *_, a in pair_list if k != 'D' for v in a]
    d_asym_reps = pair_list[0][-1]
    pair_rows = "".join(
        f"<tr><th>{esc(lbl)}</th><td>{br(a, 3)}</td><td>{br(b, 3)}</td>"
        f"<td>{' · '.join('+' + pct(v, 0) for v in asy)}</td></tr>"
        for _, lbl, a, b, asy in pair_list)

    # --- I/O with 90 compact
    io90_rows = "".join(
        f"<tr><td>bloco {x['block']}</td><td>{br(x['stream_output_s'], 2)}</td>"
        f"<td>{'+' if x['d_sps'] >= 0 else ''}{pct(x['d_sps'], 2)}</td>"
        f"<td>{x['n_hist']} × {br(x['hist_s'], 3)}</td><td>{x['n_rst']} × {br(x['rst_s'], 2)}</td>"
        f"<td><b>{br(x['extrap_s_day'], 2)}</b></td></tr>"
        for x in compl["io90"])
    io90_share = compl["io90_mean"] / (P90C["s_per_step"] * r["steps_per_day"])

    # --- disk
    dk = r["disk"]
    sz = dk["sizes"]
    var_rows = "".join(
        f"<tr><td><code>{esc(v['name'])}</code></td><td>{esc(v['kind'])}"
        f"{' (fixa)' if v['static'] else ''}</td><td>{v['lev']}</td>"
        f"<td>{esc(v['units'])}</td><td>{br(v['bytes'] / 1e6, 1)}</td></tr>"
        for v in dk["rows"])
    final_rows = "".join(f"<td>{br(tb, 2)} TB</td>" for _, tb in dk["final_tb"])
    final_head = "".join(f"<th>{n} {'ano' if n == 1 else 'anos'}</th>" for n, _ in dk["final_tb"])
    n3d = sum(1 for v in dk["rows"] if v["kind"] == "3D")
    n2d = sum(1 for v in dk["rows"] if v["kind"] == "2D")
    bytes3d = sum(v["bytes"] for v in dk["rows"] if v["kind"] == "3D")
    i1 = PROJ_YEARS.index(1)

    # --- core map
    core_map_rows = "".join(
        f"<tr><th>Soquete {sk['node']}</th><td>{compress(sk['phys'])}</td>"
        f"<td>{compress(sk['sib'])}</td></tr>" for sk in hw["sockets"])
    sk0 = hw["sockets"][0]

    pin_check_cmd = (
        "for pid in $(pgrep '^atmosphere_mod'); do\n"
        "  printf \"pid=%s psr=%s %s\\n\" \"$pid\" \"$(ps -o psr= -p \"$pid\" | tr -d ' ')\" "
        "\"$(taskset -cp \"$pid\" | sed 's/.*: /affinity=/')\"\n"
        "done")
    count_cmd = "pgrep -c '^atmosphere_mod'"

    body = f"""
<header class="masthead">
  <div class="masthead-inner">
    <p class="kicker">MPAS-Atmosphere · Margem Equatorial Brasileira · MEQ-05 · benchmark de paralelismo</p>
    <h1>Quantos processos usar no Swell para as integrações da MEQ-06?</h1>
    <p class="meta">Relatório gerado em {esc(meta['generated'])} · análise <code>{esc(meta['commit'])}</code>{' (árvore com alterações não versionadas)' if meta['dirty'] else ''} · dados dos benchmarks MEQ-05.2 ({r['trial_count']} ensaios) e MEQ-05.5 ({compl['n_used']} ensaios usados de {compl['n_rows']}) · atualização MEQ-05.6</p>
  </div>
</header>

<nav class="chapters" id="chapter-nav" aria-label="Capítulos">
  <div class="progress"><span id="progress-bar"></span></div>
  <ol>
    <li><a href="#termos"><span>0</span>Termos</a></li>
    <li><a href="#contexto"><span>1</span>Contexto</a></li>
    <li><a href="#metodo"><span>2</span>Método</a></li>
    <li><a href="#saturacao"><span>3</span>Ganho com mais núcleos</a></li>
    <li><a href="#vazao"><span>4</span>Produção do nó</a></li>
    <li><a href="#io"><span>5</span>Gravação de arquivos</a></li>
    <li><a href="#custo"><span>6</span>Custo por ano simulado</a></li>
    <li><a href="#duracao"><span>7</span>Duração da MEQ-06</a></li>
    <li><a href="#opcoes"><span>8</span>Opções</a></li>
    <li><a href="#como-rodar"><span>9</span>Como rodar</a></li>
    <li><a href="#disco"><span>10</span>Espaço em disco</a></li>
    <li><a href="#limitacoes"><span>11</span>Limitações</a></li>
  </ol>
</nav>

<main>
  <div class="status"><strong>Status:</strong> tempos medidos nos benchmarks MEQ-05.2 e MEQ-05.5 (90
    processos e rodadas em pares agora medidos). Os custos e as durações da MEQ-06 continuam sendo
    estimativas, porque estendem um trecho de {br(r['window_h'], 0)} h para anos. {esc(PRELIM_DECISION)}</div>

  <section id="termos" class="chapter">
    <h2>Termos usados neste relatório</h2>
    <p>Uma linha por termo. Os termos voltam a ser explicados, em poucas palavras, na primeira vez
      em que aparecem no texto.</p>
    <div class="scorecard-wrap"><table class="mini glossary"><tbody>{gloss_rows}</tbody></table></div>
  </section>

  <section id="contexto" class="chapter">
    <p class="chapter-no">Capítulo 1</p>
    <h2>Contexto</h2>
    {shows("Por que foi preciso medir de novo, em que máquina e com que pergunta.")}
    <p>A MEQ-06 vai integrar a EXP03 (malha Oval MEQ-02A, {br(r['exp03_cells'], 0)} células) por
      vários anos. Antes disso é preciso escolher em quantos pedaços dividir a malha (o número de
      processos) e em quais núcleos da máquina colocar cada pedaço. É um compromisso entre prazo e uso
      da máquina, que é compartilhada. Usar todos os núcleos não é, por si só, o objetivo.</p>
    <div class="questions">
      <div><b>A máquina.</b> O Swell é um nó único (um só computador) com {r['n_sockets']} soquetes
        ({esc(CPU_MODEL)}), cada um com {per_socket} núcleos físicos, {n_phys} no total. Com o SMT,
        cada núcleo alterna entre duas tarefas e o sistema mostra {n_log} "CPUs", mas só {n_phys} são
        núcleos reais.</div>
      <div><b>As perguntas.</b> Quanto o modelo acelera com mais núcleos? Vale usar a segunda tarefa
        de cada núcleo? Rende mais uma rodada grande ou duas menores lado a lado? Quanto tempo se perde
        gravando arquivos?</div>
      <div><b>Por que medir de novo.</b> Os tempos das rodadas de produção não respondem a essas
        perguntas: entre uma rodada e outra mudaram ao mesmo tempo o número de processos, a malha e a
        física, e parte dos tempos é estimada.</div>
    </div>
    <p>A tabela <code>runtime_metrics.csv</code> registra {len(hist)} rodadas de produção. Elas usaram
      de {ranks_hist[0]} a {ranks_hist[-1]} processos, em {len(cells_hist)} malhas diferentes
      ({', '.join(br(c, 0) for c in cells_hist)} células). {n_est} desses tempos foram reconstruídos
      ou estimados, não medidos. Alguns experimentos ({', '.join(multi_rank)}) rodaram com números de
      processos diferentes em cada período. Comparar essas rodadas mistura número de processos,
      tamanho de malha, física e estado da máquina. Por isso a MEQ-05.2 repetiu o mesmo trecho da EXP03
      mudando apenas o número de processos e a forma de distribuí-los.</p>
    <details class="drawer">
      <summary>Detalhes: tempos históricos de produção (runtime_metrics.csv)</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Experimento</th><th>Período</th><th>Processos</th><th>Células</th><th>s/passo (relógio)</th><th>Qualidade</th></tr></thead>
        <tbody>{hist_rows}</tbody></table></div>
      <p class="caption">s/passo = tempo de relógio da rodada inteira dividido pelo número de passos
        (inclui a preparação e a gravação de arquivos). Essas rodadas não servem para comparar números
        de processos entre si.</p>
    </details>
    {means("Os tempos antigos não servem para escolher quantos processos usar. Todos os números a seguir vêm de um mesmo trecho da EXP03, rodado de formas diferentes na mesma máquina.")}
    <nav class="pager"><a href="#termos">← Termos</a><a href="#metodo">Método →</a></nav>
  </section>

  <section id="metodo" class="chapter">
    <p class="chapter-no">Capítulo 2</p>
    <h2>Método</h2>
    {shows("Como os ensaios foram feitos e o que cada série de ensaios testa.")}
    <p>Cada ensaio integra {br(r['window_h'], 0)} h ({r['steps']} passos de {DT_S} s) a partir do
      arquivo de reinício (<i>restart</i>) de {RESTART_LABEL} da EXP03 de produção. Física, passo de
      tempo e malha são os da produção. Só mudam o número de processos e os núcleos onde eles ficam.</p>
    <ul>
      <li><b>Repetições.</b> Cada configuração rodou {cfg[BASE_CONFIG]['n_reps']} vezes. Uma terceira
        rodada seria feita se as duas diferissem em mais de {pct(REP_RULE, 0)}. Isso não ocorreu: a maior
        diferença foi {br(r['max_spread'], 2)}&nbsp;% (<code>{esc(r['max_spread_cfg'])}</code>).</li>
      <li><b>Fixação de processos</b> (dizer ao sistema em qual núcleo cada processo fica). Nas séries
        A, B, D e E, cada processo foi preso a uma CPU com <code>mpiexec -bind-to user:&lt;lista&gt;</code>,
        e isso foi conferido três vezes durante cada ensaio. A série C roda sem fixação, como na
        produção: o sistema decide onde cada processo fica.</li>
      <li><b>Tempo usado.</b> O cronômetro interno do MPAS chamado <i>time integration</i>, que mede só
        a integração e deixa de fora a preparação inicial. s/passo = <i>time integration</i> /
        {r['steps']}.</li>
      <li><b>Métricas.</b> Aceleração = s/passo de A{r['base_cores']} ÷ s/passo da configuração.
        Eficiência por núcleo físico = aceleração ÷ (núcleos físicos / {r['base_cores']}). Vazão =
        {br(SECONDS_PER_DAY, 0)} ÷ (s/passo × {br(r['steps_per_day'], 0)} passos por dia simulado), em dias
        simulados por dia de máquina. A referência é a rodada com {r['base_cores']} núcleos, não com um,
        porque uma rodada num só núcleo seria longa demais; a eficiência é, portanto, relativa a
        {r['base_cores']} núcleos.</li>
      <li><b>Segunda sessão (MEQ-05.5) e como ela foi combinada.</b> Em 17/11/2026 o mesmo trecho foi
        rodado de novo com 90 processos (compacto e espalhado), com pares simultâneos de 45 e 56 processos,
        e com 90 compacto gravando arquivos. Os ensaios foram feitos em {len(compl['blocks'])} blocos, e cada
        bloco começou e terminou com uma rodada de referência igual à A56 (<code>{COMPL_REF}</code>). Cada
        tempo da MEQ-05.5 foi dividido pela média da referência <b>do mesmo bloco</b> (valor normalizado) e
        depois multiplicado pelo s/passo médio da A56 da MEQ-05.2 ({br(a56['s_per_step'], 4)}). Assim, uma
        diferença de velocidade da máquina entre os dois dias não entra na comparação. Só entram ensaios
        marcados como válidos ({compl['n_used']} de {compl['n_rows']}). As duas sessões concordam: a referência
        A56 ficou {pct(compl['agree_a56'], 2)} e a B112 {('+' if compl['agree_b112'] >= 0 else '')}{pct(compl['agree_b112'], 2)}
        em relação à MEQ-05.2, sem normalizar.</li>
    </ul>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Série</th><th style="text-align:left">O que testa</th><th style="text-align:left">Configurações</th><th>Fixação</th></tr></thead>
      <tbody>{series_html}</tbody></table></div>
    <details class="drawer">
      <summary>Detalhes: valores medidos por configuração (médias das repetições)</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Configuração</th><th>Processos</th><th>Núcleos físicos</th><th>s/passo</th><th>Diferença entre rep. (%)</th><th>Aceleração</th><th>Efic. por núcleo físico</th><th>Vazão (dias sim./dia)</th></tr></thead>
        <tbody>{meas_rows}</tbody></table></div>
      <p class="caption">Fonte: <code>results/tables/meq05_parallel_benchmark.csv</code>. Os casos D
        aparecem separados (cada um ocupa um soquete). A vazão de cada caso D isolado não é a vazão do nó.</p>
    </details>
    {means(f"As repetições diferiram no máximo {br(r['max_spread'], 2)}&nbsp;%. Diferenças entre configurações maiores que isso são reais, não ruído da máquina.")}
    <nav class="pager"><a href="#contexto">← Contexto</a><a href="#saturacao">Ganho com mais núcleos →</a></nav>
  </section>

  <section id="saturacao" class="chapter">
    <p class="chapter-no">Capítulo 3</p>
    <h2>Quanto o modelo acelera com mais núcleos</h2>
    {shows("Quantas vezes o modelo fica mais rápido (aceleração) ao usar mais núcleos, e quanto do ganho ideal isso representa (eficiência paralela).")}
    <p>Na série A, o tempo por passo continua caindo até {n_phys} núcleos, mas cada núcleo
      acrescentado rende menos, porque os pedaços da malha ficam menores e a troca de informação entre
      eles pesa mais. A eficiência fica em {a_eff_txt}.
      {f"A maior configuração da série A que cumpre o critério de {pct(EFFICIENCY_CRITERION, 0)} é A{best_a['physical_cores']}." if best_a else ""}
      A B{b112['ranks']}, que usa a segunda tarefa de cada núcleo (SMT), chega a uma aceleração de
      {br(b112['speedup'], 2)} nos mesmos {b112['physical_cores']} núcleos físicos
      ({pct(b112['eff_phys'])} por núcleo físico).</p>
    <p>Depois de {n_phys} processos já não há núcleos físicos novos: cada processo a mais passa a dividir
      um núcleo com outro (SMT). A curva estendida mostra o que acontece então: com {PROJ_RANKS} processos
      espalhados nos {n_phys} núcleos, aceleração {br(P90E['speedup'], 2)}; com {n_log},
      {br(b112['speedup'], 2)}. O {PROJ_RANKS} compacto ({P90C['physical_cores']} núcleos, {P90C['free_cores']}
      livres) chega a {br(P90C['speedup'], 2)}, praticamente o mesmo que o espalhado, usando menos máquina.</p>
    <div class="view-switch" role="group" aria-label="Escolha do que o gráfico mostra">
      <button type="button" data-view="sp" class="active">Quantas vezes mais rápido</button>
      <button type="button" data-view="tp">Dias simulados por dia de máquina</button>
      <button type="button" data-view="tpc">Dias simulados por núcleo físico ocupado</button>
    </div>
    <div class="chart" id="chart-speedup" style="height:440px"></div>
    <p class="caption"><b>a</b> Eixo horizontal: número de processos. Círculos pretos e linha cheia: série A
      medida ({r['a_series'][0]['ranks']}–{n_phys} processos, um por núcleo físico; pontos = repetições).
      Depois de {n_phys}, triângulos vazados e linha pontilhada: {PROJ_RANKS} espalhado (MEQ-05.5) e {n_log}
      (MEQ-05.2), medidos, todos nos {n_phys} núcleos. Linha vertical em {n_phys}: a partir daqui, processos
      dividem núcleo físico (SMT). Quadrado vermelho vazado, à parte: {PROJ_RANKS} compacto
      ({PROJ_RANKS} processos em {P90C['physical_cores']} núcleos; {P90C['free_cores']} núcleos livres),
      desenhado um pouco à direita de {PROJ_RANKS} para não cobrir o {PROJ_RANKS} espalhado. Use os botões para trocar a visão: aceleração em relação a {r['base_cores']} processos; vazão (dias
      simulados por dia de máquina); vazão dividida pelos núcleos físicos ocupados. Na primeira visão, o
      tracejado cinza é a aceleração ideal. Valores da MEQ-05.5 combinados por normalização (capítulo 2).</p>
    <div class="chart" id="chart-efficiency" style="height:360px"></div>
    <p class="caption"><b>b</b> Eficiência por núcleo físico ocupado: fração do ganho ideal obtida
      (aceleração ÷ núcleos físicos/{r['base_cores']}), em função do número de processos. Tracejado
      horizontal: critério de {pct(EFFICIENCY_CRITERION, 0)} aprovado pelo pesquisador. {PROJ_RANKS}
      compacto: {pct(P90C['eff_phys'])}; {PROJ_RANKS} espalhado: {pct(P90E['eff_phys'])}; {n_log}:
      {pct(b112['eff_phys'])}.</p>
    {means(f"Até {a42['physical_cores']} núcleos, cada núcleo extra ainda rende bem. De {a42['physical_cores']} para {a56['physical_cores']} núcleos ({pct(a42_to_a56_cores, 0)} a mais), o passo fica só {pct(a42_to_a56_time, 0)} mais rápido. Passando de {n_phys} processos, o SMT ainda tira cerca de {pct(smt_gain, 0)} do tempo por passo, não o dobro. O {PROJ_RANKS} compacto é o que mais rende por núcleo ocupado entre as rodadas de {PROJ_RANKS} processos ou mais, e deixa {P90C['free_cores']} núcleos livres.")}
    <nav class="pager"><a href="#metodo">← Método</a><a href="#vazao">Produção do nó →</a></nav>
  </section>

  <section id="vazao" class="chapter">
    <p class="chapter-no">Capítulo 4</p>
    <h2>Quanto tempo de modelo o nó produz por dia</h2>
    {shows("A vazão: quantos dias simulados a máquina inteira produz em um dia de relógio, em cada forma de ocupá-la.")}
    <p>Para a MEQ-06 importa o que a máquina inteira entrega por dia. A B112 produz
      {br(b112['throughput'], 1)} dias simulados por dia de máquina, {pct(b_vs_a56)} a mais que a A56
      ({br(a56['throughput'], 1)}). A C60, que reproduz a forma como a produção foi rodada, produz
      {br(c60['throughput'], 1)}; a A56 rende {pct(a56_vs_c)} a mais que ela. As duas rodadas
      simultâneas da série D somam {br(o['D']['throughput'], 1)}.</p>
    <p>Medidos na MEQ-05.5: {PROJ_RANKS} compacto produz {br(o['P90C']['throughput'], 1)} e {PROJ_RANKS}
      espalhado {br(o['P90E']['throughput'], 1)}. Nos pares, a soma das duas rodadas dá
      {br(o['Q45S']['throughput'], 1)} (45/45 por soquete), {br(o['Q45C']['throughput'], 1)} (45/45 compacto)
      e {br(o['Q56']['throughput'], 1)} (56/56). {"Nenhum par passa a B112; o 56/56 é o que chega mais perto" if max(o[k]['throughput'] for k in COMPL_PAIRS) < b112['throughput'] else "O 56/56 passa a B112"}
      ({pct(o['Q56']['throughput'] / b112['throughput'] - 1, 0)} em relação a ela).</p>
    <div class="chart" id="chart-throughput" style="height:420px"></div>
    <p class="caption">Dias simulados por dia de máquina = {br(SECONDS_PER_DAY, 0)} ÷ (s/passo × {br(r['steps_per_day'], 0)}).
      Barras, da esquerda para a direita: {'; '.join(f"<b>{esc(label_of(k))}</b> — {esc(THROUGHPUT_TICKS[k][0])}" for k in OPTIONS)}.
      Em telas estreitas, o eixo mostra só o nome curto. Barras cinza: rodada única; barras pretas: pares, com a vazão somada das duas rodadas simultâneas.
      Pontos: repetições (na MEQ-05.5, um ponto por bloco). Na série D, {br(s0['throughput'], 2)} no
      soquete 0 e {br(s1['throughput'], 2)} no soquete 1. Valores da MEQ-05.5 combinados por normalização
      (capítulo 2). O tempo de gravação de arquivos não está incluído (capítulo 5).</p>
    <h3>Rodadas simultâneas: um bloco termina bem depois do outro</h3>
    <p>Em todos os pares medidos, nas duas sessões, a rodada no soquete 1 foi mais lenta que a do soquete 0
      — de {pct(min(compl_asym), 0)} a {pct(max(compl_asym), 0)} nos pares da MEQ-05.5 e {pct(min(d_asym_reps), 0)} na série D da MEQ-05.2. A causa não foi
      investigada. A consequência prática: com dois blocos do mesmo tamanho, o do soquete 0 termina primeiro
      e o nó fica meio ocioso até o outro acabar. Por isso o prazo de um par, no capítulo 7, é o da rodada
      mais lenta. A explicação provável para as rodadas simultâneas renderem pouco é que as duas disputam o
      mesmo limite de acesso à memória; isso não foi medido.</p>
    <div class="scorecard-wrap"><table class="mini">
      <thead><tr><th>Par</th><th>s/passo soquete 0</th><th>s/passo soquete 1</th><th>Soquete 1 mais lento, por repetição/bloco</th></tr></thead>
      <tbody>{pair_rows}</tbody></table></div>
    <p class="caption">s/passo médio de cada membro do par (MEQ-05.5 já convertida para a escala da
      MEQ-05.2). A última coluna compara os dois membros dentro de cada repetição (série D) ou bloco (MEQ-05.5),
      com os tempos brutos.</p>
    {means(f"Em um dia de relógio, a B112 simula cerca de {br(b112['throughput'], 0)} dias de modelo; o {PROJ_RANKS} compacto, cerca de {br(o['P90C']['throughput'], 0)}, deixando {P90C['free_cores']} núcleos livres; o modo usado na produção (C60), cerca de {br(c60['throughput'], 0)}. Dividir a máquina em duas rodadas não traz ganho que compense: a soma dos pares fica perto da B112 e um dos blocos sempre atrasa.")}
    <nav class="pager"><a href="#saturacao">← Ganho com mais núcleos</a><a href="#io">Gravação de arquivos →</a></nav>
  </section>

  <section id="io" class="chapter">
    <p class="chapter-no">Capítulo 5</p>
    <h2>Gravação de arquivos (I/O)</h2>
    {shows("Quanto tempo o modelo gasta gravando arquivos, e se o disco pode atrasar a MEQ-06.")}
    <p>I/O, aqui, é o tempo que o modelo gasta gravando os arquivos de saída (os campos horários,
      <i>history</i>) e os arquivos de reinício (<i>restart</i>), dos quais uma rodada pode continuar.
      A série E repetiu a A56 gravando exatamente a saída da produção e comparou com a A56 sem saída.</p>
    <p>O resultado: gravar os arquivos de um dia simulado leva cerca de <b>{br(r['io_extrap_mean'], 0)} s</b>,
      contra cerca de {br(r['a56_compute_day'], 0)} s de cálculo para o mesmo dia na A56, ou seja,
      {pct(io_share, 2)} do tempo. Esse valor é uma <b>extrapolação</b>: o ensaio de {br(r['window_h'], 0)} h
      gravou {r['io'][0]['n_hist']} arquivos horários e {r['io'][0]['n_rst']} de reinício, e o custo foi
      estendido para um dia inteiro (24 horários + 1 de reinício).</p>
    <details class="drawer">
      <summary>Detalhes técnicos da série E</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Rep.</th><th>stream_output (s)</th><th>Δ time integration vs A56 (s)</th><th>Δ relógio vs A56 (s)</th><th><i>history</i> (n × s)</th><th><i>restart</i> (n × s)</th><th>EXTRAPOLAÇÃO: s por dia simulado</th></tr></thead>
        <tbody>{io_rows}</tbody></table></div>
      <p class="caption">Medido: cronômetro <code>stream_output</code> do MPAS e diferenças em relação à
        média da A56 (mesmos processos e fixação, sem saída). Duração de gravação de cada arquivo = da
        criação à última modificação (ext4). Extrapolação = 24 × <i>history</i> médio + 1 × <i>restart</i>,
        supondo custo constante por arquivo. O cronômetro e as durações por arquivo não foram reconciliados.</p>
    </details>
    <p><b>Com {PROJ_RANKS} compacto (MEQ-05.5).</b> O ensaio E90C repetiu o {PROJ_RANKS} compacto gravando a
      mesma saída e foi comparado com o P90C do mesmo bloco, sem saída. O cronômetro de gravação marcou
      {' e '.join(br(x['stream_output_s'], 1) + ' s' for x in compl['io90'])} nas {br(r['window_h'], 0)} h, e o
      tempo por passo mudou {' e '.join(('+' if x['d_sps'] >= 0 else '') + pct(x['d_sps'], 1) for x in compl['io90'])}
      — diferenças dentro da variação normal entre ensaios. Extrapolado para um dia simulado, dá cerca de
      <b>{br(compl['io90_mean'], 0)} s</b> de gravação, {pct(io90_share, 2)} do tempo de cálculo do dia.</p>
    <details class="drawer">
      <summary>Detalhes técnicos do E90C</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Bloco</th><th>stream_output (s)</th><th>s/passo E90C vs P90C</th><th><i>history</i> (n × s)</th><th><i>restart</i> (n × s)</th><th>EXTRAPOLAÇÃO: s por dia simulado</th></tr></thead>
        <tbody>{io90_rows}</tbody></table></div>
      <p class="caption">Mesmo método da série E (24 × <i>history</i> médio + 1 × <i>restart</i>).
        Fonte: <code>meq05_5_parallel_benchmark_complement.csv</code>.</p>
    </details>
    {means("A gravação de arquivos é desprezível também com " + str(PROJ_RANKS) + " compacto: cerca de " + br(compl['io90_mean'], 0) + " s por dia simulado (extrapolado). O tempo de gravação não limita a MEQ-06; o prazo depende do cálculo. O espaço que os arquivos ocupam é outra questão (capítulo 10).")}
    <nav class="pager"><a href="#vazao">← Produção do nó</a><a href="#custo">Custo por ano simulado →</a></nav>
  </section>

  <section id="custo" class="chapter">
    <p class="chapter-no">Capítulo 6</p>
    <h2>Custo por ano simulado</h2>
    {shows("Quantos dias de máquina custa cada ano simulado em cada forma medida de ocupar o nó.")}
    <p>Custo em dias de máquina por ano simulado ({DAYS_PER_YEAR} dias) = {DAYS_PER_YEAR} ÷ vazão.
      Há duas variantes, e as duas são <b>estimativas</b>.</p>
    <ol>
      <li><b>(a) Pelo trecho medido.</b> Usa a vazão das {br(r['window_h'], 0)} h de benchmark, sem
        preparação inicial e sem gravação de arquivos.</li>
      <li><b>(b) Corrigida pela produção.</b> A produção da EXP03 levou {br(r['prod_sps'], 4)} s/passo
        ({prod_txt}). Esse tempo de relógio inclui preparação, leitura das condições de fronteira,
        gravação de saída e um mês inteiro de meteorologia. A série C repete a mesma forma de rodar
        ({c60['ranks']} processos, sem fixação) e mede {br(r['c_sps'], 4)} s/passo no trecho de
        {br(r['window_h'], 0)} h. A razão {br(r['prod_sps'], 4)} ÷ {br(r['c_sps'], 4)} =
        <b>{br(r['corr'], 3)}</b> resume o que o trecho medido não captura. A variante (b) multiplica (a)
        por essa razão, supondo que ela vale para as outras configurações; isso não foi verificado.</li>
    </ol>
    <div class="chart" id="chart-cost" style="height:440px"></div>
    <p class="caption">Estimativas de dias de máquina por ano simulado. Barras cinza: variante (a), pelo
      trecho medido. Barras pretas: variante (b), corrigida pela razão produção/série C
      ({br(r['corr'], 3)}). Nos pares (D, 45/45, 56/56), o custo supõe duas rodadas independentes ao mesmo
      tempo, uma em cada soquete, e usa a vazão somada; ele não considera que um bloco termina depois do
      outro (isso entra no capítulo 7).</p>
    {means(f"Pela estimativa corrigida (b), um ano simulado custa de {br(min(cost_b_vals), 1)} a {br(max(cost_b_vals), 1)} dias de máquina, conforme a forma de ocupar o nó. O capítulo 7 transforma isso em prazos para 1 a 20 anos.")}
    <nav class="pager"><a href="#io">← Gravação de arquivos</a><a href="#duracao">Duração da MEQ-06 →</a></nav>
  </section>

  <section id="duracao" class="chapter">
    <p class="chapter-no">Capítulo 7</p>
    <h2>Quanto tempo levaria a MEQ-06</h2>
    {shows(f"O prazo da MEQ-06 para 1 a 20 anos simulados, nas configurações agora medidas: {PROJ_RANKS} processos (compacto e espalhado), pares simultâneos e a máquina inteira ({n_log}). Nenhuma simulação longa foi feita: os prazos estendem o trecho medido de {br(r['window_h'], 0)} h.")}
    <p><b>Todas as linhas usam s/passo medido</b> (MEQ-05.2, ou MEQ-05.5 combinada por normalização). Os
      prazos continuam sendo estimativas, porque estendem {br(r['window_h'], 0)} h para anos. O valor principal
      inclui a correção pela produção (c = {br(p['c'], 3)}, capítulo 6); a linha "sem c" mostra o valor sem
      essa correção (cerca de {pct(p['drop_without_c'], 0)} menor). Exemplo: {PROJ_RANKS} compacto com 1 ano,
      {br(pk['P90C']['durations'][i1], 1)} dias com correção e {br(pk['P90C']['durations_raw'][i1], 1)} sem.</p>
    <p><b>Spin-up.</b> Cada rodada contínua começa com {SPINUP_DAYS} dias simulados de spin-up
      (período inicial em que o modelo se ajusta e que não entra na análise). <i>Hipótese de
      planejamento; a duração adequada do spin-up é decisão da MEQ-06.</i></p>
    <p><b>Pares como dois blocos.</b> Nas linhas de pares, o período é dividido em dois blocos contínuos de
      N/2 anos, simulados ao mesmo tempo, um em cada soquete, cada um com o seu spin-up. O prazo é o da
      rodada <b>mais lenta</b> do par (a do soquete 1, capítulo 4).</p>
    <div class="scorecard-wrap"><table class="decision proj">
      <thead><tr><th>Configuração</th><th style="text-align:left">Como o nó é ocupado</th><th>Núcleos inteiros livres</th>{proj_head}</tr></thead>
      <tbody>{proj_rows}</tbody></table></div>
    <p class="caption">Dias de relógio para simular N anos, com {SPINUP_DAYS} dias de spin-up por rodada
      contínua. Valor principal com a correção c; abaixo, "sem c". Para 10 anos ou mais, também em meses
      (dias ÷ {br(DAYS_PER_MONTH, 1)}). Rodada única: dias = (N × {DAYS_PER_YEAR} + {SPINUP_DAYS}) ×
      {br(r['steps_per_day'], 0)} × s × c ÷ {br(SECONDS_PER_DAY, 0)}. Pares: dias = (N/2 × {DAYS_PER_YEAR} +
      {SPINUP_DAYS}) × {br(r['steps_per_day'], 0)} × max(s<sub>soquete 0</sub>, s<sub>soquete 1</sub>) × c ÷
      {br(SECONDS_PER_DAY, 0)}.</p>
    {compact_vs_spread}
    <h3>Estimativa × medição</h3>
    <p>A versão anterior deste relatório estimou as configurações de {PROJ_RANKS} processos e os pares a
      partir dos ensaios da MEQ-05.2. A MEQ-05.5 mediu essas configurações. <b>A estimativa errou ao prever
      o espalhado mais rápido que o compacto</b> ({br(est['P90E']['est_s'], 3)} contra {br(est['P90C']['est_s'], 3)}
      s/passo): medidos, os dois empatam ({br(est['P90E']['meas_s'], 3)} e {br(est['P90C']['meas_s'], 3)}).
      O compacto saiu {pct(-est['P90C']['diff'], 0)} mais rápido que o estimado; o espalhado, quase
      igual. Nos pares, a estimativa errou por pouco.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Configuração</th><th>s/passo estimado</th><th>s/passo medido</th><th>Medido − estimado</th><th>Vazão estimada</th><th>Vazão medida</th></tr></thead>
      <tbody>{est_rows}</tbody></table></div>
    <p class="caption">Estimativas da versão anterior (MEQ-05.3), recalculadas aqui com as mesmas fórmulas;
      medições da MEQ-05.5 combinadas por normalização. Nos pares, o s/passo é a média dos dois membros e a
      vazão é a soma das duas rodadas (dias simulados por dia de máquina). A estimativa de 45/45 era para os
      processos espalhados em cada soquete (a medição correspondente é a 45/45 por soquete).</p>
    <h3>Exemplo resolvido: simular {EXAMPLE_LABEL} ({EXAMPLE_YEARS} anos)</h3>
    <p>Rodar o período inteiro de uma vez em {ex['P90C']['label']} leva cerca de {br(ex['P90C']['days'], 1)}
      dias, quase o mesmo que em {ex['P90E']['label']} ({br(ex['P90E']['days'], 1)}). Dividir em dois blocos
      simultâneos ({EXAMPLE_BLOCKS[0]} e {EXAMPLE_BLOCKS[1]}, um em cada soquete) leva
      {br(ex['Q45C']['days'], 1)} dias em {ex['Q45C']['label']} e {br(ex['Q56']['days'], 1)} em
      {ex['Q56']['label']}; a máquina inteira numa rodada só ({ex['B_N112']['label']}), {br(ex['B_N112']['days'], 1)}.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Configuração</th><th style="text-align:left">Como o período é rodado</th><th>Dias de relógio</th><th>Diferença para a 1.ª linha</th></tr></thead>
      <tbody>{ex_rows}</tbody></table></div>
    <p class="caption">Mesmas hipóteses da tabela acima (c = {br(p['c'], 3)}; {SPINUP_DAYS} dias de spin-up por
      rodada contínua; pares limitados pela rodada mais lenta).</p>
    <p><b>Por que rodar dois blocos juntos não compensa.</b> Cada rodada de um par fica bem mais lenta do que
      seria sozinha, e a do soquete 1 atrasa mais ainda. Com 1 ou 2 anos, o spin-up repetido nos dois blocos
      pesa ainda mais. A causa provável é a disputa pelo acesso à memória, que não foi medida.</p>
    <p><b>Ressalva científica.</b> Dividir o período em blocos interrompe a continuidade da simulação:
      por exemplo, a umidade do solo recomeça em cada bloco. Se isso é aceitável, e com qual spin-up,
      é decisão da MEQ-06.</p>
    <details class="drawer">
      <summary>Método do cálculo: s/passo de cada linha</summary>
      <p>Notação: s = s/passo médio medido; {br(r['steps_per_day'], 0)} passos por dia simulado;
        {DAYS_PER_YEAR} dias por ano; S = {SPINUP_DAYS} dias de spin-up por rodada contínua; c =
        {br(r['prod_sps'], 4)} / {br(r['c_sps'], 4)} = {br(p['c'], 4)}, correção pela produção (capítulo 6),
        aplicada igualmente a todas as linhas. Valores da MEQ-05.5 = valor normalizado pela referência do
        mesmo bloco × s/passo médio da A56 da MEQ-05.2.</p>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Configuração</th><th style="text-align:left">Origem do s/passo</th><th>s/passo</th><th>Dias por ano de rodada (com c)</th><th>Dias por ano de rodada (sem c)</th></tr></thead>
        <tbody>{proj_method_rows}</tbody></table></div>
      <p class="caption">"Dias por ano de rodada" = tempo de relógio para uma rodada avançar um ano
        simulado, sem spin-up. Nos pares, os dois blocos avançam ao mesmo tempo, e conta o mais lento.</p>
    </details>
    {means(f"Com {PROJ_RANKS} processos compactos, 1 ano simulado leva cerca de {br(pk['P90C']['durations'][i1], 0)} dias de relógio e 10 anos cerca de {br(pk['P90C']['durations'][PROJ_YEARS.index(10)] / DAYS_PER_MONTH, 1)} meses, deixando {pk['P90C']['free_cores']} núcleos livres; usando a máquina inteira ({n_log}), 10 anos levam cerca de {br(pk['B_N112']['durations'][PROJ_YEARS.index(10)] / DAYS_PER_MONTH, 1)} meses. Os pares não encurtam o prazo.")}
    <nav class="pager"><a href="#custo">← Custo por ano simulado</a><a href="#opcoes">Opções →</a></nav>
  </section>

  <section id="opcoes" class="chapter">
    <p class="chapter-no">Capítulo 8</p>
    <h2>Opções para decisão</h2>
    {shows("Todas as formas medidas de ocupar o nó, lado a lado, com o critério de eficiência e o custo estimado.")}
    <p>A tabela reúne vazão, eficiência por núcleo físico ocupado, o critério de {pct(EFFICIENCY_CRITERION, 0)}
      e o custo estimado da MEQ-06, agora com as configurações de {PROJ_RANKS} processos e os pares medidos
      na MEQ-05.5. Não há pesos nem nota composta.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Opção</th><th>Processos / núcleos físicos</th><th>Núcleos inteiros livres</th><th>Vazão (dias sim. por dia de máquina)</th><th>Efic. por núcleo físico</th><th>Cumpre {pct(EFFICIENCY_CRITERION, 0)}?</th><th>Custo MEQ-06 (a), dias de máquina/ano</th><th>Custo MEQ-06 (b), dias de máquina/ano</th><th style="text-align:left">Situação</th></tr></thead>
      <tbody>{dec_rows}</tbody></table></div>
    <p class="caption">Vazão e custos com o s/passo médio de cada configuração (MEQ-05.5 combinada por
      normalização); custos são estimativas (capítulo 6). Eficiência relativa a A{r['base_cores']}, pelos
      núcleos físicos ocupados. Nos pares (D, 45/45, 56/56), vazão somada das duas rodadas e eficiência do
      par: vazão somada ÷ (vazão de A{r['base_cores']} × núcleos ocupados/{r['base_cores']}); o custo não
      considera que um bloco termina depois do outro (capítulo 7).
      <b>(a)</b> custo calculado pelo trecho de {br(r['window_h'], 0)} h medido; <b>(b)</b> o mesmo custo
      corrigido pela média da produção da EXP03, que foi cerca de {pct(r['corr'] - 1, 0)} mais lenta que
      esse trecho.</p>
    <div class="conclusion">
      <h3>Decisão</h3>
      <p class="verdict"><b>{esc(PRELIM_DECISION)}</b> O {label_of(PROPOSED)} aparece na tabela como
        <b>{esc(PROPOSED_LABEL)}</b>. A execução da simulação depende de autorização própria na MEQ-06.</p>
    </div>
    {means(f"O {label_of(PROPOSED)} entrega {br(o[PROPOSED]['throughput'], 1)} dias simulados por dia de máquina, {pct(1 - o[PROPOSED]['throughput'] / b112['throughput'], 0)} menos que a B112, cumpre o critério de {pct(EFFICIENCY_CRITERION, 0)} ({pct(o[PROPOSED]['eff_phys'])}) e deixa {n_phys - o[PROPOSED]['physical_cores']} núcleos livres para outros usuários. Um ano simulado leva cerca de {br(pk[PROPOSED]['durations'][i1], 0)} dias de relógio (capítulo 7).")}
    <nav class="pager"><a href="#duracao">← Duração da MEQ-06</a><a href="#como-rodar">Como rodar →</a></nav>
  </section>

  <section id="como-rodar" class="chapter">
    <p class="chapter-no">Capítulo 9</p>
    <h2>Como rodar na prática</h2>
    {shows("A diferença entre rodar com os processos soltos, como sempre foi feito, e rodar com os processos fixados, e como fazer e conferir isso no Swell.")}
    <p><b>Processos soltos.</b> O comando usado até agora, <code>mpiexec -n N ./atmosphere_model</code>,
      sem opções, deixa os processos sem fixação: o sistema decide em qual núcleo cada um fica e pode
      movê-los durante a rodada. Na série C, rodada exatamente assim, os {run['unpinned_ranks']} processos
      se espalharam pelos {run['occupied']} núcleos físicos, {run['shared']} deles dividiram núcleo com
      outro processo, e a rodada foi <b>{pct(run['slowdown'], 0)} mais lenta</b> que a A{run['pinned_ranks']}
      fixada ({br(c60['s_per_step'], 4)} contra {br(a56['s_per_step'], 4)} s/passo). Com {PROJ_RANKS}
      processos soltos, mais processos do que núcleos, todos os {n_phys} núcleos ficam ocupados e
      nenhum núcleo inteiro fica livre para outros usuários.</p>
    {compact_vs_spread}
    <p><b>Processos fixados.</b> Fixar é dizer ao <code>mpiexec</code>, com a opção
      <code>-bind-to user:&lt;lista&gt;</code> do MPICH (versão {esc(hw['mpich_version'])} no Swell),
      a lista de CPUs: o primeiro processo vai para a primeira CPU da lista, o segundo para a segunda,
      e assim por diante. Cada processo fica na sua CPU até o fim da rodada.</p>
    <p>Comandos reais usados no benchmark (coluna <code>mpiexec_cmd</code> do CSV):</p>
    <p class="cmd-label">Série C, soltos ({run['unpinned_ranks']} processos):</p>
    <pre class="cmd">{esc(run['unpinned_cmd'])}</pre>
    <p class="cmd-label">Série A{run['pinned_ranks']}, fixados ({run['pinned_ranks']} processos, um por núcleo físico):</p>
    <pre class="cmd">{esc(run['pinned_cmd'])}</pre>
    <h3>Numeração das CPUs do Swell</h3>
    <div class="scorecard-wrap"><table class="mini cpu-map">
      <thead><tr><th>Soquete</th><th>Núcleos físicos (1.ª tarefa)</th><th>2.ª tarefa dos mesmos núcleos (SMT)</th></tr></thead>
      <tbody>{core_map_rows}</tbody></table></div>
    <p class="caption">Fonte: <code>hardware_snapshot.txt</code> do benchmark (<code>lscpu</code> e
      <code>numactl --hardware</code>). A CPU {sk0['sib'][0]} é a segunda tarefa do núcleo
      {sk0['phys'][0]}, a {sk0['sib'][1]} do núcleo {sk0['phys'][1]}, e assim por diante (núcleo + {n_phys}).</p>
    <h3>Exemplo para "{PROJ_RANKS} compacto"</h3>
    <p>{P90C['physical_cores']} núcleos físicos com as duas tarefas: soquete 0 com {run['per_socket_alloc'][0]}
      núcleos (CPUs {run['example_blocks'][0]}) e soquete 1 com {run['per_socket_alloc'][1]} núcleos (CPUs
      {run['example_blocks'][1]}). Ficam livres os núcleos {run['free_txt']} ({len(run['free_cores'])} núcleos
      inteiros). Como para qualquer N, o MPAS precisa do arquivo de partição para {PROJ_RANKS} processos.</p>
    <div class="status"><strong>Testado no benchmark MEQ-05.5.</strong> É exatamente o comando registrado na
      coluna <code>mpiexec_cmd</code> do CSV de complemento (ensaios P90C e E90C, fixação conferida). Este
      comando é para o Swell, com a numeração de CPUs acima. Em outra máquina, a lista muda.</div>
    <pre class="cmd">{esc(run['example_cmd'])}</pre>
    <h3>Como conferir a fixação durante uma rodada</h3>
    <p>Os mesmos comandos usados na verificação do benchmark, rodados no Swell em outro terminal,
      enquanto o modelo roda:</p>
    <pre class="cmd">{esc(count_cmd)}</pre>
    <p>deve mostrar o número de processos ({PROJ_RANKS} no exemplo). E</p>
    <pre class="cmd">{esc(pin_check_cmd)}</pre>
    <p>mostra uma linha por processo. Numa rodada fixada, cada linha tem <code>affinity=</code> com um
      único número, igual ao <code>psr</code> (a CPU onde o processo está), e o conjunto desses números é
      exatamente a lista do comando. Numa rodada solta aparece <code>affinity={esc(run['affinity'])}</code>
      (qualquer CPU).</p>
    {means(f"Sem fixação, a rodada do benchmark ficou cerca de {pct(run['slowdown'], 0)} mais lenta, mesmo com {run['unpinned_ranks'] - run['pinned_ranks']} processos a mais. Fixar também permite escolher quais núcleos ficam livres. Basta acrescentar <code>-bind-to user:&lt;lista&gt;</code> ao comando de sempre; a lista acima vale só para o Swell e foi a usada no benchmark para o {PROJ_RANKS} compacto.")}
    <nav class="pager"><a href="#opcoes">← Opções</a><a href="#disco">Espaço em disco →</a></nav>
  </section>

  <section id="disco" class="chapter">
    <p class="chapter-no">Capítulo 10</p>
    <h2>Espaço em disco</h2>
    {shows("Quanto espaço a saída da MEQ-06 vai ocupar, a partir dos tamanhos reais dos arquivos da EXP03, e quanto espaço extra a rodada precisa enquanto está em andamento.")}
    <p>Os tamanhos vêm do inventário somente leitura das duas pernas de produção da EXP03, feito em
      {esc(dk['captured'])} (MEQ-05.5). Todos os arquivos estão no formato <b>{esc(dk['formats']['history'].upper())}</b>
      (netCDF clássico), <b>sem compressão</b>. Unidade: TB decimal (10<sup>12</sup> bytes) e GB decimal
      (10<sup>9</sup> bytes).</p>
    <h3>O que tem na saída horária</h3>
    <p>Cada arquivo horário (<i>history</i>) tem {dk['n_vars']} variáveis e ocupa
      <b>{br(sz['history'] / 1e6, 1)} MB</b>. As variáveis 3D guardam um valor em cada um dos
      {dk['nlev']} níveis verticais: o modelo divide a atmosfera em {dk['nlev']} camadas, da superfície até o
      topo, e as variáveis de vento vertical e altura (<code>w</code>, <code>zgrid</code>) usam as
      {dk['nlev'] + 1} superfícies que separam essas camadas. As {n3d} variáveis 3D ocupam
      {pct(bytes3d / dk['var_bytes'], 0)} de cada arquivo; as {n2d} de superfície, o resto.</p>
    <details class="drawer">
      <summary>Detalhes: as {dk['n_vars']} variáveis da saída horária</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Variável</th><th>Tipo</th><th>Níveis</th><th>Unidade</th><th>MB por arquivo</th></tr></thead>
        <tbody>{var_rows}</tbody></table></div>
      <p class="caption">Fonte: <code>history_variables.csv</code> (MEQ-05.5). "fixa": variável sem dimensão de
        tempo (coordenadas, área da célula, máscara de terra), repetida em cada arquivo. Soma das variáveis:
        {br(dk['var_bytes'] / 1e6, 1)} MB; o restante ({br(dk['header_bytes'] / 1e3, 0)} kB) é o cabeçalho.</p>
    </details>
    <h3>Tamanho real de cada tipo de arquivo</h3>
    <div class="scorecard-wrap"><table class="mini">
      <thead><tr><th>Arquivo</th><th style="text-align:left">O que é</th><th>Tamanho</th><th>Frequência</th></tr></thead>
      <tbody>
        <tr><th>history</th><td style="text-align:left">saída horária (campos para análise)</td><td>{br(sz['history'] / 1e6, 1)} MB</td><td>1 por hora</td></tr>
        <tr><th>restart</th><td style="text-align:left">estado completo do modelo, para continuar a rodada</td><td>{br(sz['restart'] / 1e9, 2)} GB</td><td>1 por dia</td></tr>
        <tr><th>lbc</th><td style="text-align:left">forçantes de contorno lateral (vindas da reanálise)</td><td>{br(sz['lbc'] / 1e6, 1)} MB</td><td>1 a cada 6 h</td></tr>
        <tr><th>init</th><td style="text-align:left">condição inicial</td><td>{br(sz['init'] / 1e6, 0)} MB</td><td>1 por rodada</td></tr>
        <tr><th>sfc_update</th><td style="text-align:left">atualização de superfície (TSM e gelo)</td><td>{br(sz['sfc'] / 1e6, 1)} MB</td><td>1 por perna de 1 mês na EXP03</td></tr>
      </tbody></table></div>
    <h3>Armazenamento final: só a saída horária</h3>
    <p>O que fica guardado ao final é só a saída horária; os restarts não entram. Por ano simulado são
      {DAYS_PER_YEAR} × {HOURS_PER_DAY} = {br(DAYS_PER_YEAR * HOURS_PER_DAY, 0)} arquivos
      ({br(dk['hist_per_day_gb'], 2)} GB por dia simulado).</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th></th>{final_head}</tr></thead>
      <tbody><tr><th>Saída horária</th>{final_rows}</tr></tbody></table></div>
    <p class="caption">Bytes reais do arquivo horário × arquivos por ano, em TB decimais (10<sup>12</sup> bytes).
      Sem o spin-up. Se a saída do spin-up ({SPINUP_DAYS} dias) for mantida, cada rodada contínua acrescenta
      {br(dk['spinup_tb'] * 1000, 0)} GB ({br(dk['spinup_tb'], 3)} TB); num par, são duas rodadas.</p>
    <h3>Espaço necessário durante a rodada (não faz parte do armazenamento final)</h3>
    <ul>
      <li><b>Um restart</b> ocupa {br(sz['restart'] / 1e9, 2)} GB.</li>
      <li><b>Restarts de 1 ano:</b> manter todos os restarts diários durante a rodada ocuparia
        {br(dk['rst_year_tb'], 2)} TB; manter só os últimos {RESTARTS_KEPT}, {br(dk['rst_keep_gb'], 1)} GB.</li>
      <li><b>Forçantes de contorno:</b> {br(dk['lbc_year_tb'], 2)} TB por ano simulado
        ({DAYS_PER_YEAR} × {LBC_PER_DAY} arquivos), mais a condição inicial e a atualização de superfície.</li>
      <li><b>Espaço livre em <code>/p1-swell</code>:</b> cerca de {dk['free_space']} TB em 13/11/2026 (diagnóstico inicial
        da frente MEQ-05, relatado pelo Claude Code; não registrado no repositório e não verificado novamente).
        A saída horária ocuparia dessa área: {"; ".join(f"{n} {'ano' if n == 1 else 'anos'}, {br(dict(dk['final_tb'])[n], 1)} TB ({pct(dict(dk['final_tb'])[n] / dk['free_space'])})" for n in FREE_SPACE_YEARS)}.</li>
    </ul>
    {means(f"Cada ano simulado deixa cerca de {br(dk['final_tb'][0][1], 1)} TB de saída horária; 10 anos, cerca de {br(dict(dk['final_tb'])[10], 0)} TB, sem compressão. Durante a rodada, manter todos os restarts de um ano somaria mais {br(dk['rst_year_tb'], 1)} TB; guardar só os últimos {RESTARTS_KEPT} reduz isso a {br(dk['rst_keep_gb'], 0)} GB. Os cerca de {dk['free_space']} TB livres em 13/11/2026 comportam essa saída, mas precisam ser conferidos antes da MEQ-06.")}
    <nav class="pager"><a href="#como-rodar">← Como rodar</a><a href="#limitacoes">Limitações →</a></nav>
  </section>

  <section id="limitacoes" class="chapter">
    <p class="chapter-no">Capítulo 11</p>
    <h2>Limitações</h2>
    {shows("O que não foi verificado nos benchmarks (registros <code>docs/provenance/MEQ-05.2-benchmark-record.md</code> e <code>MEQ-05.5-benchmark-complement-record.md</code>) e o que decorre das escolhas deste relatório.")}
    <ul>
      <li><b>Igualdade numérica não verificada.</b> Não se verificou se o resultado numérico muda com o
        número de processos. Os campos de saída não foram comparados, e os ensaios sem saída não geram arquivos.</li>
      <li><b>Janela única de {br(r['window_h'], 0)} h</b> ({RESTART_LABEL}), nas duas sessões. Não se verificou se
        ela reproduz, na mesma proporção de um dia completo, a frequência de cálculos periódicos, como a radiação.</li>
      <li><b>Duas sessões combinadas por normalização.</b> Os valores da MEQ-05.5 foram divididos pela
        referência A56 do mesmo bloco e multiplicados pela A56 da MEQ-05.2. Isso supõe que uma mudança de
        velocidade da máquina entre os dias afeta todas as configurações na mesma proporção. As referências
        concordaram ({pct(compl['agree_a56'], 2)} na A56 e {('+' if compl['agree_b112'] >= 0 else '')}{pct(compl['agree_b112'], 2)} na B112).</li>
      <li><b>Assimetria entre soquetes.</b> Em todos os pares, nas duas sessões, a rodada no soquete 1 foi
        {pct(min(all_asym), 0)} a {pct(max(all_asym), 0)} mais lenta que a do soquete 0. A causa não foi
        investigada. Numa produção em pares, a rodada mais lenta determina quando o nó fica livre.</li>
      <li><b>Uso e velocidade da memória</b> (banda) não foram medidos; a disputa pela memória como causa da
        perda nas rodadas simultâneas é uma explicação provável, não medida.</li>
      <li><b>Frequência do processador</b> não foi controlada (na MEQ-05.5 ela foi registrada, mas não fixada).</li>
      <li><b>Fixação conferida</b> por amostragem durante cada ensaio, não continuamente.</li>
      <li><b>Cache de arquivos</b> do sistema não foi controlado. O <i>restart</i> de entrada é relido a cada ensaio.</li>
      <li><b>Extrapolação de I/O</b> supõe custo constante por arquivo e não inclui operações anteriores à
        criação do arquivo. O conteúdo dos arquivos gravados nas séries E e E90C não foi inspecionado.</li>
      <li><b>Correção de custo (c).</b> A razão produção/série C ({br(r['corr'], 3)}) foi obtida com
        {c60['ranks']} processos sem fixação. Supõe-se que ela vale para as demais configurações, o que não
        foi verificado.</li>
      <li><b>Prazos da MEQ-06 (capítulo 7).</b> Usam s/passo medido, mas estendem {br(r['window_h'], 0)} h para
        anos. O spin-up de {SPINUP_DAYS} dias por rodada contínua é uma hipótese de planejamento.</li>
      <li><b>Eficiência relativa a A{r['base_cores']}</b>, não a um núcleo.</li>
      <li><b>Rodadas em blocos.</b> Dividir o período em blocos interrompe a continuidade da simulação
        (por exemplo, a umidade do solo recomeça em cada bloco). Se isso é aceitável, e com qual spin-up,
        é decisão da MEQ-06.</li>
      <li><b>Espaço livre em disco</b> varia com o uso do servidor; o valor do capítulo 10 (13/11/2026) deve ser
        conferido antes de rodar. Os volumes do capítulo 10 vêm dos
        tamanhos reais dos arquivos da EXP03 e supõem a mesma lista de variáveis e o mesmo formato sem compressão.</li>
    </ul>
    {means("Os números deste relatório servem para escolher a configuração e estimar prazos e espaço, não para garantir prazos exatos. As configurações de 90 processos e os pares já foram medidos; o que falta conferir antes de uma rodada longa é a igualdade numérica e o espaço livre em disco.")}
    <nav class="pager"><a href="#disco">← Espaço em disco</a><a href="#termos">Início ↑</a></nav>
  </section>

  <footer class="footer">
    <p>Gerado por <code>scripts/06_report/build_benchmark_report.py</code> (MEQ-05.3, atualizado na MEQ-05.6) a partir de tabelas
      consolidadas e registros do benchmark; não edite à mão. Estilo:
      <code>docs/templates/report_v2/report.css</code>, sem modificação; gráficos: Plotly basic
      {esc(meta['plotly_version'])}, embutido. Registro de proveniência:
      <code>docs/provenance/MEQ-05.2-benchmark-record.md</code> e
      <code>docs/provenance/MEQ-05.5-benchmark-complement-record.md</code>.</p>
    <table class="kv"><tbody>{sha_rows}</tbody></table>
  </footer>
</main>
"""
    return body


EXTRA_CSS = """
/* MEQ-05.3 benchmark report: additions only (report.css is inlined above unchanged). */
.chapter ul { max-width: 880px; }
.chapter ul li { margin: 4px 0; }
table.decision tr.proposed th { font-weight: 700; }
table.decision td, table.decision th { border-bottom: 1px solid var(--rule); }
table.proj td .sub { color: var(--muted); font-size: .78rem; }
table.proj td, table.proj thead th { white-space: nowrap; }
table.proj td.desc { white-space: normal; min-width: 220px; }
table.glossary th, table.glossary td { text-align: left; vertical-align: top; }
table.glossary th { white-space: nowrap; padding-right: 14px; }
table.cpu-map td, table.cpu-map th { text-align: left; }
.note.practice { max-width: 880px; }
.cmd-label { margin: 10px 0 2px; font-size: .86rem; }
pre.cmd { background: var(--bg-soft); border-left: 2px solid var(--rule-strong); padding: 6px 10px;
  margin: 4px 0 12px; font-size: .8rem; white-space: pre-wrap; overflow-wrap: anywhere;
  word-break: break-all; max-width: 880px; }
.pager span { flex: 1; }
.view-switch { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 4px; }
.view-switch button { font: inherit; font-size: .82rem; padding: 4px 10px; border: 1px solid var(--rule-strong);
  background: var(--bg-soft); color: inherit; cursor: pointer; border-radius: 2px; }
.view-switch button.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
.footer table.kv { margin-top: 8px; }
.footer table.kv th { width: auto; }
.footer table.kv code { overflow-wrap: anywhere; word-break: break-all; }
"""

# Plotly journal defaults copied from docs/templates/report_v2/report.js
# (fmt, axis, layout, CONFIG, plot, navigation), then the three charts.
REPORT_JS = r"""
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('bench-data').textContent);
  var $ = function (id) { return document.getElementById(id); };
  function fmt(v, d) {
    if (d === undefined) d = 2;
    if (v === null || v === undefined || !isFinite(v)) return '—';
    return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  var FONT = { family: 'Arial, Helvetica, sans-serif', size: 11, color: '#1a1a1a' };
  function axis(o) {
    return Object.assign({
      showline: true, linecolor: '#1a1a1a', linewidth: 0.8, ticks: 'outside', ticklen: 3,
      tickwidth: 0.8, tickcolor: '#1a1a1a', showgrid: false, zeroline: false, automargin: true,
      title: { font: { size: 11 } }
    }, o || {});
  }
  function layout(extra) {
    var base = {
      font: FONT, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      margin: { l: 56, r: 12, t: 12, b: 42 }, showlegend: false, hovermode: 'closest',
      hoverlabel: { font: { family: FONT.family, size: 11 }, bgcolor: '#fff', bordercolor: '#1a1a1a' },
      legend: { orientation: 'h', y: -0.22, x: 0, font: { size: 10 } },
      xaxis: axis(), yaxis: axis()
    };
    extra = extra || {};
    Object.keys(extra).forEach(function (k) {
      if (/^[xy]axis\d*$/.test(k)) base[k] = axis(extra[k]); else base[k] = extra[k];
    });
    return base;
  }
  var CONFIG = {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian', 'hoverClosestCartesian'],
    toImageButtonOptions: { format: 'svg', filename: 'meq05_parallel_benchmark' }
  };
  function plot(id, traces, lay) {
    var node = $(id); if (!node) return;
    if (!window.Plotly) { node.innerHTML = '<div class="empty">Biblioteca de gráficos indisponível.</div>'; return; }
    Plotly.react(node, traces, layout(lay), CONFIG);
  }
  function pick(a, k) { return a.map(function (p) { return p[k]; }); }

  function initNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll('#chapter-nav a'));
    var sections = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
    function onScroll() {
      var y = window.scrollY + window.innerHeight * 0.3, current = 0;
      sections.forEach(function (s, i) { if (s && s.offsetTop <= y) current = i; });
      links.forEach(function (a, i) { a.classList.toggle('active', i === current); });
      var h = document.documentElement.scrollHeight - window.innerHeight;
      $('progress-bar').style.width = (h > 0 ? 100 * window.scrollY / h : 0) + '%';
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  var VIEWS = {
    sp: { title: 'quantas vezes mais rápido que ' + D.base_cores + ' processos', f: '.2f', unit: 'vezes' },
    tp: { title: 'dias simulados por dia de máquina', f: '.1f', unit: 'dias simulados por dia de máquina' },
    tpc: { title: 'dias simulados por dia, por núcleo físico ocupado', f: '.2f', unit: 'dias simulados por dia, por núcleo físico ocupado' }
  };
  var SMT_TXT = 'a partir daqui, processos dividem núcleo físico (SMT)';
  function smtShape(ymax) {
    return { type: 'line', xref: 'x', yref: 'paper', x0: D.n_phys, x1: D.n_phys, y0: 0, y1: 1,
             line: { color: '#7a7a7a', width: 1, dash: 'dot' } };
  }
  function smtNote() {
    return { xref: 'x', yref: 'paper', x: D.n_phys, y: 1, xanchor: 'left', yanchor: 'top',
             text: ' a partir daqui, processos<br> dividem núcleo físico (SMT)', showarrow: false, font: { size: 10, color: '#4a4a4a' }, align: 'left' };
  }
  function extTraces(key, f, unit) {
    var last = D.a_mean[D.a_mean.length - 1];
    var ex = D.ext, pc = D.p90c;
    var ext = [last].concat(ex);
    var tr = [];
    tr.push({ type: 'scatter', mode: 'lines', x: pick(ext, 'x'), y: pick(ext, key), name: 'além de ' + D.n_phys + ' (SMT), medido',
      line: { color: '#1a1a1a', width: 1.2, dash: 'dot' }, hoverinfo: 'skip', showlegend: false });
    var px = [], py = [], pt = [];
    ex.forEach(function (e) { e.reps.forEach(function (r) { px.push(e.x); py.push(r[key]); pt.push(e.label + ' r' + r.rep); }); });
    tr.push({ type: 'scatter', mode: 'markers', x: pick(ex, 'x'), y: pick(ex, key),
      name: 'além de ' + D.n_phys + ': 90 espalhado e 112 (medidos, 56 núcleos)',
      marker: { symbol: 'triangle-up-open', color: '#1a1a1a', size: 10, line: { width: 1.5 } },
      customdata: pick(ex, 'label'), hovertemplate: '%{customdata}: %{y:' + f + '} ' + unit + '<extra></extra>' });
    tr.push({ type: 'scatter', mode: 'markers', x: px, y: py, showlegend: false,
      marker: { color: '#1a1a1a', size: 4 }, customdata: pt,
      hovertemplate: '%{customdata}: %{y:' + f + '}<extra></extra>' });
    var PX = pc.x + 2.5;   // drawn slightly to the right so it does not hide 90 espalhado
    tr.push({ type: 'scatter', mode: 'markers+text', x: [PX], y: [pc[key]], text: ['90 compacto'],
      textposition: 'middle right', textfont: { size: 10, color: '#883007' }, cliponaxis: false,
      name: '90 processos em ' + pc.cores + ' núcleos; ' + D.p90c_free + ' núcleos livres (90 compacto)',
      marker: { symbol: 'square-open', color: '#883007', size: 11, line: { width: 1.8 } },
      hovertemplate: '90 compacto (' + pc.cores + ' núcleos, ' + D.p90c_free + ' livres): %{y:' + f + '} ' + unit + '<extra></extra>' });
    tr.push({ type: 'scatter', mode: 'markers', x: pc.reps.map(function () { return PX; }), y: pick(pc.reps, key), showlegend: false,
      marker: { color: '#883007', size: 4 }, hovertemplate: '90 compacto (bloco): %{y:' + f + '}<extra></extra>' });
    return tr;
  }

  function initSaturation() {
    var b0 = D.base_cores, xmax = 120;
    var ticks = pick(D.a_mean, 'x').concat([90, 112]);
    var common = { xaxis: { title: { text: 'número de processos' }, range: [0, xmax], tickvals: ticks },
                   showlegend: true, legend: { orientation: 'h', yanchor: 'bottom', y: 1.04, x: 0, font: { size: 10 } },
                   margin: { l: 60, r: 12, t: 78, b: 42 } };
    function draw(view) {
      var V = VIEWS[view];
      var tr = [];
      if (view === 'sp') {
        tr.push({ type: 'scatter', mode: 'lines', x: [b0, D.n_phys], y: [1, D.n_phys / b0], name: 'ideal',
          line: { color: '#8c8c8c', width: 1, dash: 'dash' }, hoverinfo: 'skip' });
      }
      tr.push({ type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, view), name: 'série A (1 processo por núcleo, média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: %{y:' + V.f + '} ' + V.unit + '<extra></extra>' });
      tr.push({ type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, view), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:' + V.f + '}<extra></extra>' });
      tr = tr.concat(extTraces(view, V.f, V.unit));
      plot('chart-speedup', tr, Object.assign({}, common, {
        yaxis: { title: { text: V.title }, rangemode: 'tozero' },
        shapes: [smtShape()], annotations: [smtNote()] }));
    }
    var btns = Array.prototype.slice.call(document.querySelectorAll('.view-switch button'));
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        btns.forEach(function (o) { o.classList.toggle('active', o === b); o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
        draw(b.getAttribute('data-view'));
      });
    });
    draw('sp');

    var efTr = [
      { type: 'scatter', mode: 'lines', x: [0, xmax], y: [D.criterion, D.criterion],
        name: 'critério ' + fmt(100 * D.criterion, 0) + ' %', line: { color: '#883007', width: 1, dash: 'dash' }, hoverinfo: 'skip' },
      { type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, 'eff'), name: 'série A (média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: %{y:.1%}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, 'eff'), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:.1%}<extra></extra>' }
    ].concat(extTraces('eff', '.1%', 'por núcleo físico'));
    plot('chart-efficiency', efTr, Object.assign({}, common, {
      yaxis: { title: { text: 'eficiência por núcleo físico ocupado' }, tickformat: '.0%', range: [0, 1.08] },
      shapes: [smtShape()], annotations: [smtNote()] }));
  }

  function initThroughput() {
    var O = D.options, labels = pick(O, 'label');
    var tr = [
      { type: 'bar', x: labels, y: pick(O, 'tp'), width: 0.55,
        marker: { color: O.map(function (o) { return o.pair ? '#1a1a1a' : '#8c8c8c'; }) },
        customdata: O.map(function (o) { return o.pair ? 'soma das duas rodadas' : 'rodada única'; }),
        name: 'média', hovertemplate: '%{x} (%{customdata}): %{y:.2f} dias simulados por dia de máquina<extra></extra>' }
    ];
    var px = [], py = [];
    O.forEach(function (o) { o.reps.forEach(function (v) { px.push(o.label); py.push(v); }); });
    tr.push({ type: 'scatter', mode: 'markers', x: px, y: py, name: 'repetições',
      marker: { color: '#ffffff', size: 6, line: { color: '#1a1a1a', width: 1.2 } },
      hovertemplate: '%{x} (repetição/bloco): %{y:.2f}<extra></extra>' });
    // Two-line plain-language tick labels; on narrow screens each line is
    // wrapped again so neighbouring labels do not overlap.
    var node = $('chart-throughput');
    var narrow = node && node.clientWidth / O.length < 200;
    var maxc = node ? Math.max(14, Math.floor(node.clientWidth / O.length / 6.2)) : 40;
    function wrap(line) {
      if (!narrow) return line;
      var out = [], cur = '';
      line.split(' ').forEach(function (w) {
        if (cur && (cur + ' ' + w).length > maxc) { out.push(cur); cur = w; } else { cur = cur ? cur + ' ' + w : w; }
      });
      if (cur) out.push(cur);
      return out.join('<br>');
    }
    var tiny = node && node.clientWidth < 700;
    var ticktext = O.map(function (o) {
      if (tiny) return '<b>' + o.label + '</b>';
      return '<b>' + wrap(o.tick[0]) + '</b><br>' + wrap(o.tick[1]);
    });
    var nlines = Math.max.apply(null, ticktext.map(function (t) { return t.split('<br>').length; }));
    if (tiny) nlines = 6;
    if (narrow && node) node.style.height = (300 + 14 * nlines) + 'px';
    plot('chart-throughput', tr, { yaxis: { title: { text: 'dias simulados por dia de máquina' }, rangemode: 'tozero' },
      xaxis: { type: 'category', tickmode: 'array', tickvals: labels, ticktext: ticktext, tickfont: { size: 10 },
               tickangle: tiny ? -50 : 0 },
      margin: { l: 56, r: 12, t: 12, b: 16 + 14 * nlines } });
  }

  function initCost() {
    var O = D.options, labels = pick(O, 'label');
    var tr = [
      { type: 'bar', orientation: 'h', y: labels, x: pick(O, 'cost_a'), name: '(a) pelo trecho medido — estimativa',
        marker: { color: '#b8b8b8' },
        hovertemplate: '%{y} (a): %{x:.1f} dias de máquina por ano simulado<extra></extra>' },
      { type: 'bar', orientation: 'h', y: labels, x: pick(O, 'cost_b'), name: '(b) corrigida pela produção — estimativa',
        marker: { color: '#1a1a1a' },
        hovertemplate: '%{y} (b): %{x:.1f} dias de máquina por ano simulado<extra></extra>' }
    ];
    plot('chart-cost', tr, { barmode: 'group', showlegend: true, legend: { orientation: 'h', y: 1.16, x: 0 },
      xaxis: { title: { text: 'dias de máquina por ano simulado (estimativa)' }, rangemode: 'tozero' },
      yaxis: { type: 'category', autorange: 'reversed' }, margin: { l: 80, r: 12, t: 34, b: 42 } });
  }

  function safe(fn, name) {
    try { fn(); } catch (err) { if (window.console) console.error('[benchmark report] ' + name, err); }
  }
  function boot() {
    safe(initNav, 'nav');
    safe(initSaturation, 'saturation');
    safe(initThroughput, 'throughput');
    safe(initCost, 'cost');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
"""


def assemble(body: str, payload: dict) -> str:
    css = REPORT_CSS.read_text(encoding="utf-8")
    plotly = PLOTLY_JS.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    for chunk in (plotly, REPORT_JS):
        if "</script" in chunk.lower():
            raise SystemExit("inline script contains '</script'")
    return (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<link rel=\"icon\" href=\"data:,\">\n"
        "<title>MPAS MEQ-Br — Benchmark de paralelismo (MEQ-05)</title>\n"
        f"<style>\n{css}\n{EXTRA_CSS}\n</style>\n</head>\n<body>\n{body}\n"
        f"<script>\n{plotly}\n</script>\n"
        f"<script type=\"application/json\" id=\"bench-data\">{data}</script>\n"
        f"<script>\n{REPORT_JS}\n</script>\n</body>\n</html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    results = compute()
    plotly_head = PLOTLY_JS.read_text(encoding="utf-8")[:200]
    plotly_version = next((tok for tok in plotly_head.split() if tok.startswith("v2.")),
                          "unknown")
    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_value("rev-parse", "--short", "HEAD"),
        "dirty": bool(git_value("status", "--porcelain")),
        "plotly_version": plotly_version,
        "inputs": {str(p.relative_to(REPO_ROOT)) + " (sha256)": sha256(p)
                   for p in (BENCH_CSV, COMPL_CSV, RUNTIME_CSV, HW_SNAPSHOT, RECORD_MD,
                             COMPL_RECORD_MD, HIST_VARS_CSV, DISK_INV)},
    }
    page = assemble(build_html(results, meta), chart_payload(results))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size / 1e6:.2f} MB)")
    for o in results["options"]:
        print(f"  {o['label']:<11} tp={o['throughput']:.3f} eff={o['eff_phys']:.4f} "
              f"meets={o['meets']} cost_a={o['cost_a']:.2f} cost_b={o['cost_b']:.2f}")
    print(f"  correction ratio = {results['corr']:.4f}")
    p = results["proj"]
    print(f"  projection: f={p['f']:.4f} s(A45)={p['s_a45']:.4f} k={p['k']:.4f} c={p['c']:.4f}")
    for x in p["rows"]:
        durs = ", ".join("—" if v is None else f"{v:.1f}" for v in x["durations"])
        print(f"  {x['label']:<20} s={x['s']:.4f} days/run-year={x['days_run_year']:.2f} "
              f"[{durs}]")
    print(f"  run: C slowdown vs A56 = {results['run']['slowdown']:.4f}; "
          f"free cores (90 compact) = {results['run']['free_txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
