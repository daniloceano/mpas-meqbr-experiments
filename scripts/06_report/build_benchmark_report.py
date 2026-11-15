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
RUNTIME_CSV = REPO_ROOT / "results/tables/runtime_metrics.csv"
HW_SNAPSHOT = REPO_ROOT / "results/benchmark/MEQ-05.2/records/hardware_snapshot.txt"
RECORD_MD = REPO_ROOT / "docs/provenance/MEQ-05.2-benchmark-record.md"
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
OPTIONS = ["A_N056", "B_N112", "C_N060", "D"]   # decision options, this order
PROPOSED = "B_N112"
PROPOSED_LABEL = "recomendação proposta — aguardando decisão do pesquisador"
D_CASES = ("D_N028x2_s0", "D_N028x2_s1")
UNPINNED_CFG = "C_N060"                # production-like launch (no pinning)
PINNED_CFG = "A_N056"                  # pinned comparison for the run chapter

# ---------------------------------------------------------- projection settings
# Assumptions stated by the PI in the MEQ-05.3 revision brief (not measured).
PROJ_RANKS = 90                        # processes of the projected single run
PROJ_YEARS = (1, 5, 10, 20)            # columns of the duration table
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
        "trial_count": len(bench),
    }
    r["hw"] = read_hardware(n_phys, per_socket)
    r["proj"] = project(r)
    r["run"] = run_practice(r)
    return r


def project(r: dict) -> dict:
    """MEQ-06 duration projection (PI's formulas; no configuration measured)."""
    cfg = r["cfg"]

    def s(key: str) -> float:
        return cfg[key]["s_per_step"]

    n_phys, per_socket = r["n_phys"], r["per_socket"]
    corr, spd = r["corr"], r["steps_per_day"]

    f = s("B_N112") / s("A_N056")                      # SMT gain
    lo, hi = cfg[INTERP_LO], cfg[INTERP_HI]
    n_compact = PROJ_RANKS // SMT_THREADS              # 45 physical cores
    w = (n_compact - lo["physical_cores"]) / (hi["physical_cores"] - lo["physical_cores"])
    s_a45 = lo["s_per_step"] + w * (hi["s_per_step"] - lo["s_per_step"])
    n_extra = PROJ_RANKS - n_phys                      # cores with 2 tasks, spread
    k = np.mean([s(d) for d in D_CASES]) / s("A_N028")  # two simultaneous runs
    a28 = "A_N%03d" % per_socket
    if a28 != "A_N028":
        raise SystemExit("per-socket core count no longer matches A_N028")
    pair_small = PROJ_RANKS // 2                       # 45 processes per socket
    pair_big = r["n_logical"] // 2                     # 56 processes per socket
    n_extra_sock = pair_small - per_socket             # 17 cores with 2 tasks

    sps = {
        "90c": s_a45 * f,
        "90e": s("A_N056") - (n_extra / n_phys) * (s("A_N056") - s("B_N112")),
        "4545": (s("A_N028") - (n_extra_sock / per_socket)
                 * (s("A_N028") - s("A_N028") * f)) * k,
        "112": s("B_N112"),
        "5656": s("A_N028") * f * k,
    }

    def days_per_run_year(x: float, c: float = corr) -> float:
        return DAYS_PER_YEAR * spd * x * c / SECONDS_PER_DAY

    def days_for(x: float, years: float, c: float = corr) -> float:
        """Wall days for one continuous run of `years` simulated years + spin-up."""
        return (years * DAYS_PER_YEAR + SPINUP_DAYS) * spd * x * c / SECONDS_PER_DAY

    rows_def = [
        ("90c", f"{PROJ_RANKS} compacto", False, n_phys - n_compact, n_compact,
         f"{PROJ_RANKS} processos em {n_compact} núcleos físicos, com as duas tarefas de cada núcleo"),
        ("90e", f"{PROJ_RANKS} espalhado", False, 0, n_phys,
         f"{PROJ_RANKS} processos nos {n_phys} núcleos: {n_extra} núcleos com duas tarefas, "
         f"{n_phys - n_extra} com uma"),
        ("4545", f"{pair_small}/{pair_small}", True, 0, n_phys,
         f"dois blocos contínuos simultâneos, cada um num soquete com {pair_small} processos "
         f"({n_extra_sock} dos {per_socket} núcleos com duas tarefas)"),
        ("112", f"{r['n_logical']} (referência)", False, 0, n_phys,
         f"{r['n_logical']} processos, um por tarefa, em todos os {n_phys} núcleos (como a B112 medida)"),
        ("5656", f"{pair_big}/{pair_big} (referência)", True, 0, n_phys,
         f"dois blocos contínuos simultâneos, cada um num soquete com {per_socket} núcleos × 2 tarefas"),
    ]
    rows = []
    for key, label, double, free, cores, desc in rows_def:
        blocks = 2 if double else 1
        rows.append({
            "key": key, "label": label, "double": double, "blocks": blocks,
            "free_cores": free, "cores_used": cores, "desc": desc, "s": sps[key],
            "days_run_year": days_per_run_year(sps[key]),
            "days_run_year_raw": days_per_run_year(sps[key], 1.0),
            "durations": [days_for(sps[key], n / blocks) for n in PROJ_YEARS],
            "durations_raw": [days_for(sps[key], n / blocks, 1.0) for n in PROJ_YEARS],
        })
    by_key = {x["key"]: x for x in rows}

    # Worked example: EXAMPLE_YEARS years, continuous vs two simultaneous blocks.
    example = []
    for key, how in (("90e", f"uma rodada contínua de {EXAMPLE_LABEL}"),
                     ("4545", f"dois blocos ao mesmo tempo: {EXAMPLE_BLOCKS[0]} e "
                              f"{EXAMPLE_BLOCKS[1]}, cada um com seu spin-up"),
                     ("90c", f"uma rodada contínua de {EXAMPLE_LABEL}")):
        x = by_key[key]
        example.append({"key": key, "label": x["label"], "how": how,
                        "days": days_for(x["s"], EXAMPLE_YEARS / x["blocks"])})
    ex_ref = example[0]["days"]
    for e in example:
        e["vs_first"] = e["days"] / ex_ref - 1.0

    # Estimated 90-process points for the saturation figure (same formulas).
    s8, base_cores = r["s8"], r["base_cores"]
    est = []
    for key in ("90c", "90e"):
        x = by_key[key]
        sp = s8 / x["s"]
        est.append({"key": key, "label": f"{x['label']} (estimado)",
                    "x": x["cores_used"], "sp": sp,
                    "eff": sp / (x["cores_used"] / base_cores)})

    return {
        "f": f, "s_a45": s_a45, "k": k, "c": corr, "w": w,
        "n_compact": n_compact, "n_extra": n_extra, "pair_small": pair_small,
        "pair_big": pair_big, "n_extra_sock": n_extra_sock,
        "rows": rows, "by_key": by_key, "drop_without_c": 1.0 - 1.0 / corr,
        "example": example, "est": est,
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
    n_compact = r["proj"]["n_compact"]
    socks = hw["sockets"]
    per = [n_compact // len(socks) + (1 if i < n_compact % len(socks) else 0)
           for i in range(len(socks))]
    cpus, free = [], []
    for sk, n in zip(socks, per):
        cpus += sk["phys"][:n] + sk["sib"][:n]
        free += sk["phys"][n:]
    if len(cpus) != PROJ_RANKS or len(set(cpus)) != PROJ_RANKS:
        raise SystemExit("example CPU list is not 90 distinct CPUs")
    b_cmd = cfg["B_N112"]["mpiexec_cmd"]
    b_list = re.search(r"user:([\d,]+)", b_cmd).group(1).split(",")
    full_b = [int(v) for v in b_list]
    expect_b = sum((sk["phys"] + sk["sib"] for sk in socks), [])
    if full_b != expect_b:
        raise SystemExit("B112 list order differs from the snapshot numbering")
    example = (f"mpiexec -n {PROJ_RANKS} -bind-to user:"
               + ",".join(str(c) for c in cpus) + " ./atmosphere_model")
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
            "D": "D (2 × 28)"}.get(key, key)


# ---------------------------------------------------------------- page text
def chart_payload(r: dict) -> dict:
    cfg = r["cfg"]
    a_pts = []
    for c in r["a_series"]:
        for k, (sp, ef) in enumerate(zip(c["reps_speedup"], c["reps_eff_phys"])):
            a_pts.append({"x": c["physical_cores"], "sp": sp, "eff": ef,
                          "rep": k + 1, "cfg": c["config"]})
    b = cfg["B_N112"]
    return {
        "criterion": EFFICIENCY_CRITERION,
        "base_cores": r["base_cores"], "n_phys": r["n_phys"],
        "a_mean": [{"x": c["physical_cores"], "sp": c["speedup"],
                    "eff": c["eff_phys"], "cfg": c["config"]}
                   for c in r["a_series"]],
        "a_pts": a_pts,
        "b_pts": [{"x": b["physical_cores"], "sp": sp, "eff": ef, "rep": k + 1}
                  for k, (sp, ef) in enumerate(zip(b["reps_speedup"],
                                                   b["reps_eff_phys"]))],
        "b_mean": {"x": b["physical_cores"], "sp": b["speedup"],
                   "eff": b["eff_phys"], "ranks": b["ranks"]},
        "est": [{"label": e["label"], "x": e["x"], "sp": e["sp"], "eff": e["eff"]}
                for e in r["proj"]["est"]],
        "options": [{"key": o["key"], "label": o["label"], "tp": o["throughput"],
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
    n_phys, n_log, per_socket = r["n_phys"], r["n_logical"], r["per_socket"]

    # --- glossary
    gloss = [
        ("Nó", f"Um computador completo. O Swell é um único nó; tudo neste relatório roda dentro dele."),
        ("Soquete", f"Cada um dos {r['n_sockets']} processadores (chips) do nó. Cada soquete tem "
                    f"{per_socket} núcleos e sua própria memória."),
        ("Núcleo físico", f"Uma unidade de cálculo real do processador. O Swell tem {n_phys}."),
        ("SMT", f"Cada núcleo alterna entre duas tarefas; o sistema mostra {n_log}, mas só {n_phys} "
                f"são reais. A segunda tarefa aproveita os momentos em que o núcleo ficaria parado, "
                f"por isso rende bem menos que um núcleo a mais."),
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
        for c in cfg.values() if c["config"] != "D")

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

    # --- projection table
    def dur_cell(x, i, n):
        v = x["durations"][i]
        txt = f"{br(v, 1)} dias"
        if n >= 10:
            txt += f"<br><span class='sub'>{br(v / DAYS_PER_MONTH, 1)} meses</span>"
        return f"<td>{txt}</td>"
    proj_rows = "".join(
        f"<tr><th>{esc(x['label'])}</th><td class='desc' style='text-align:left'>{esc(x['desc'])}</td>"
        f"<td>{x['free_cores']}</td>"
        + "".join(dur_cell(x, i, n) for i, n in enumerate(PROJ_YEARS)) + "</tr>"
        for x in p["rows"])
    proj_head = "".join(f"<th>{n} {'ano' if n == 1 else 'anos'}</th>" for n in PROJ_YEARS)

    formula = {
        "90c": f"s(A{p['n_compact']}) × f",
        "90e": f"s(A{n_phys}) − ({p['n_extra']}/{n_phys}) × [s(A{n_phys}) − s(B{n_log})]",
        "4545": f"[s(A{per_socket}) − ({p['n_extra_sock']}/{per_socket}) × (s(A{per_socket}) − s(A{per_socket}) × f)] × k",
        "112": f"s(B{n_log})",
        "5656": f"s(A{per_socket}) × f × k",
    }
    proj_method_rows = "".join(
        f"<tr><th>{esc(x['label'])}</th><td style='text-align:left'>{formula[x['key']]}</td>"
        f"<td>{br(x['s'], 4)}</td><td>{br(x['days_run_year'], 1)}</td>"
        f"<td>{br(x['days_run_year_raw'], 1)}</td></tr>"
        for x in p["rows"])
    lo, hi = cfg[INTERP_LO], cfg[INTERP_HI]
    ex_rows = "".join(
        f"<tr><th>{esc(e['label'])}</th><td style='text-align:left'>{esc(e['how'])}</td>"
        f"<td>{br(e['days'], 1)} dias</td>"
        f"<td>{'—' if i == 0 else ('+' if e['vs_first'] >= 0 else '') + pct(e['vs_first'], 0)}</td></tr>"
        for i, e in enumerate(p["example"]))
    ex = {e["key"]: e for e in p["example"]}
    compact_vs_spread = (
        f"<p><b>{PROJ_RANKS} compacto × {PROJ_RANKS} espalhado.</b> {PROJ_RANKS} espalhado usa os "
        f"{n_phys} núcleos físicos ({p['n_extra']} com duas tarefas, {n_phys - p['n_extra']} com uma) "
        f"e por isso é mais rápido; {PROJ_RANKS} compacto usa só {p['n_compact']} núcleos e deixa "
        f"{pk['90c']['free_cores']} inteiros livres para outros usuários — é mais lento por rodada, "
        f"mas ocupa menos a máquina. Os dois têm {PROJ_RANKS} processos, mas não a mesma quantidade "
        f"de hardware.</p>")
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
    <p class="meta">Relatório gerado em {esc(meta['generated'])} · análise <code>{esc(meta['commit'])}</code>{' (árvore com alterações não versionadas)' if meta['dirty'] else ''} · dados do benchmark MEQ-05.2 ({r['trial_count']} ensaios)</p>
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
    <li><a href="#limitacoes"><span>10</span>Limitações</a></li>
  </ol>
</nav>

<main>
  <div class="status"><strong>Status:</strong> tempos medidos no benchmark MEQ-05.2. Os custos e as
    durações da MEQ-06 são estimativas, e as configurações do capítulo 7 não foram medidas. A
    configuração para a MEQ-06 ainda não foi decidida: este relatório apresenta opções.</div>

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
    <div class="grid-2">
      <div>
        <div class="chart" id="chart-speedup" style="height:430px"></div>
        <p class="caption"><b>a</b> Aceleração em relação à rodada com {r['base_cores']} núcleos, em
          função do número de núcleos físicos. Pontos: repetições. Linha cheia: média da série A.
          Tracejado: aceleração ideal (dobrar os núcleos = dobrar a velocidade). Losango vazado: série B
          ({b112['ranks']} processos com SMT), fora da curva A.</p>
      </div>
      <div>
        <div class="chart" id="chart-efficiency" style="height:430px"></div>
        <p class="caption"><b>b</b> Eficiência por núcleo físico: fração do ganho ideal obtida
          (aceleração ÷ núcleos/{r['base_cores']}). Tracejado horizontal: critério de
          {pct(EFFICIENCY_CRITERION, 0)} aprovado pelo pesquisador. Pontos acima da linha cumprem o critério.</p>
      </div>
    </div>
    <p class="caption">Círculo e quadrado cinza vazados: <b>{PROJ_RANKS} compacto (estimado)</b> e
      <b>{PROJ_RANKS} espalhado (estimado)</b> — estimado a partir dos pontos medidos, não medido. O eixo
      usa os núcleos físicos efetivamente usados ({p['est'][0]['x']} e {p['est'][1]['x']}). O s/passo vem
      das mesmas fórmulas do capítulo 7 (sem a correção c), e daí aceleração e eficiência são calculadas
      como para os pontos medidos: {p['est'][0]['label']}, aceleração {br(p['est'][0]['sp'], 2)} e
      eficiência {pct(p['est'][0]['eff'])}; {p['est'][1]['label']}, aceleração {br(p['est'][1]['sp'], 2)}
      e eficiência {pct(p['est'][1]['eff'])}.</p>
    {means(f"Até {a42['physical_cores']} núcleos, cada núcleo extra ainda rende bem. De {a42['physical_cores']} para {a56['physical_cores']} núcleos ({pct(a42_to_a56_cores, 0)} a mais), o passo fica só {pct(a42_to_a56_time, 0)} mais rápido. Usar a segunda tarefa de cada núcleo ainda tira mais {pct(smt_gain, 0)} do tempo por passo em relação à A{a56['ranks']}.")}
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
    <div class="chart" id="chart-throughput" style="height:280px"></div>
    <p class="caption">Dias simulados por dia de máquina = {br(SECONDS_PER_DAY, 0)} ÷ (s/passo × {br(r['steps_per_day'], 0)}).
      Barras cinza: valor calculado com o s/passo médio de cada configuração. Pontos pretos: repetições. Na série D,
      a vazão é a soma das duas rodadas simultâneas ({br(s0['throughput'], 2)} no soquete 0 e
      {br(s1['throughput'], 2)} no soquete 1). O tempo de gravação de arquivos não está incluído (capítulo 5).</p>
    {means(f"Em um dia de relógio, a B112 simula cerca de {br(b112['throughput'], 0)} dias de modelo; o modo usado na produção (C60), cerca de {br(c60['throughput'], 0)}. A forma de ocupar a máquina muda o prazo em cerca de {pct(b112['throughput'] / c60['throughput'] - 1, 0)}, sem mudar nada no modelo.")}
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
    {means("A gravação de arquivos é desprezível: cerca de " + br(r['io_extrap_mean'], 0) + " s por dia simulado (extrapolado). O disco não limita a MEQ-06; o prazo depende do cálculo.")}
    <nav class="pager"><a href="#vazao">← Produção do nó</a><a href="#custo">Custo por ano simulado →</a></nav>
  </section>

  <section id="custo" class="chapter">
    <p class="chapter-no">Capítulo 6</p>
    <h2>Custo por ano simulado</h2>
    {shows("Quantos dias de máquina custa cada ano simulado nas quatro formas medidas de ocupar o nó.")}
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
    <div class="chart" id="chart-cost" style="height:280px"></div>
    <p class="caption">Estimativas de dias de máquina por ano simulado. Barras cinza: variante (a), pelo
      trecho medido. Barras pretas: variante (b), corrigida pela razão produção/série C
      ({br(r['corr'], 3)}). Na série D, o custo supõe duas rodadas independentes (por exemplo, dois anos)
      ao mesmo tempo, uma em cada soquete.</p>
    {means(f"Pela estimativa corrigida (b), um ano simulado custa de {br(min(cost_b_vals), 1)} a {br(max(cost_b_vals), 1)} dias de máquina, conforme a forma de ocupar o nó. O capítulo 7 transforma isso em prazos para 1 a 20 anos.")}
    <nav class="pager"><a href="#io">← Gravação de arquivos</a><a href="#duracao">Duração da MEQ-06 →</a></nav>
  </section>

  <section id="duracao" class="chapter">
    <p class="chapter-no">Capítulo 7</p>
    <h2>Quanto tempo levaria a MEQ-06</h2>
    {shows(f"Uma projeção do prazo da MEQ-06 para 1, 5, 10 e 20 anos simulados, em configurações com {PROJ_RANKS} processos que deixam parte do nó para outros usuários, comparadas às de {n_log}, incluindo rodadas divididas em dois blocos simultâneos. Nenhuma simulação nova foi feita: tudo vem dos ensaios medidos, com as hipóteses declaradas abaixo.")}
    <p><b>Nenhuma destas configurações foi medida diretamente.</b> Os prazos combinam ensaios medidos
      com hipóteses simples; a margem plausível é de {PLAUSIBLE_MARGIN}. Os valores já incluem a correção
      pela produção (c = {br(p['c'], 3)}, capítulo 6). Sem essa correção, todos cairiam
      {pct(p['drop_without_c'], 1)} (por exemplo, {PROJ_RANKS} compacto com 1 ano: de
      {br(pk['90c']['durations'][i1], 1)} para {br(pk['90c']['durations_raw'][i1], 1)} dias).</p>
    <p><b>Spin-up.</b> Cada rodada contínua começa com {SPINUP_DAYS} dias simulados de spin-up
      (período inicial em que o modelo se ajusta e que não entra na análise). <i>Hipótese de
      planejamento; a duração adequada do spin-up é decisão da MEQ-06.</i></p>
    <p><b>Rodadas duplas como dois blocos.</b> Nas linhas {pk['4545']['label']} e
      {pk['5656']['label'].split(' ')[0]}, o período é dividido em dois blocos contínuos de N/2 anos,
      simulados ao mesmo tempo, um em cada soquete, cada um com o seu spin-up. Isso vale também para
      1 ano (dois semestres) e para N ímpar.</p>
    <div class="scorecard-wrap"><table class="decision proj">
      <thead><tr><th>Configuração</th><th style="text-align:left">Como o nó é ocupado</th><th>Núcleos inteiros livres</th>{proj_head}</tr></thead>
      <tbody>{proj_rows}</tbody></table></div>
    <p class="caption">Dias de relógio para simular N anos (projeção, variante corrigida, com
      {SPINUP_DAYS} dias de spin-up por rodada contínua). Para 10 e 20 anos, também em meses
      (dias ÷ {br(DAYS_PER_MONTH, 1)}). Rodada única: dias = (N × {DAYS_PER_YEAR} + {SPINUP_DAYS}) ×
      {br(r['steps_per_day'], 0)} × s × c ÷ {br(SECONDS_PER_DAY, 0)}. Rodadas duplas: dois blocos de
      N/2 anos ao mesmo tempo, dias = (N/2 × {DAYS_PER_YEAR} + {SPINUP_DAYS}) × {br(r['steps_per_day'], 0)}
      × s<sub>rodada</sub> × c ÷ {br(SECONDS_PER_DAY, 0)}.</p>
    {compact_vs_spread}
    <p>Na prática, o espalhado impede que outra pessoa use a máquina sem atrasar a rodada; o compacto
      custa {pct(pk['90c']['durations'][i1] / pk['90e']['durations'][i1] - 1, 0)} a mais de prazo.</p>
    <h3>Exemplo resolvido: simular {EXAMPLE_LABEL} ({EXAMPLE_YEARS} anos)</h3>
    <p>Rodar o período inteiro de uma vez em {ex['90e']['label']} leva cerca de
      {br(ex['90e']['days'], 1)} dias. Dividir em dois blocos simultâneos ({ex['4545']['label']}:
      {EXAMPLE_BLOCKS[0]} e {EXAMPLE_BLOCKS[1]} ao mesmo tempo, um em cada soquete) leva cerca de
      {br(ex['4545']['days'], 1)} dias, e uma rodada contínua em {ex['90c']['label']}, cerca de
      {br(ex['90c']['days'], 1)} dias. Diferenças menores que ~{pct(UNCERTAINTY_DIFF, 0)} estão dentro
      da incerteza da projeção.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Configuração</th><th style="text-align:left">Como o período é rodado</th><th>Dias de relógio</th><th>Diferença para a 1.ª linha</th></tr></thead>
      <tbody>{ex_rows}</tbody></table></div>
    <p class="caption">Projeção com as mesmas hipóteses da tabela acima (c = {br(p['c'], 3)};
      {SPINUP_DAYS} dias de spin-up por rodada contínua).</p>
    <p><b>Por que rodar dois blocos juntos não compensa.</b> As duas rodadas simultâneas disputam o
      nó: na série D, cada uma ficou cerca de {pct(p['k'] - 1, 0)} mais lenta que a mesma rodada de
      {per_socket} processos sozinha (k = {br(p['k'], 3)}), o que anula a vantagem de dividir o período.
      A causa provável é a disputa pela memória, cuja banda não foi medida.</p>
    <p><b>Ressalva científica.</b> Dividir o período em blocos interrompe a continuidade da simulação:
      por exemplo, a umidade do solo recomeça em cada bloco. Se isso é aceitável, e com qual spin-up,
      é decisão da MEQ-06.</p>
    <p>Se uma configuração de {PROJ_RANKS} processos compactos for adotada, um ensaio curto com ela
      (o mesmo trecho de {br(r['window_h'], 0)} h) confirmaria o número antes de uma rodada longa.</p>
    <details class="drawer">
      <summary>Método da projeção: hipóteses e fórmulas</summary>
      <p>Notação: s(X) = s/passo médio da configuração X medida; {br(r['steps_per_day'], 0)} passos por dia
        simulado; {DAYS_PER_YEAR} dias por ano; S = {SPINUP_DAYS} dias de spin-up por rodada contínua.
        Rodada única com N anos: dias = (N × {DAYS_PER_YEAR} + S) × {br(r['steps_per_day'], 0)} × s × c ÷
        {br(SECONDS_PER_DAY, 0)}. Rodadas duplas: dois blocos contínuos de N/2 anos ao mesmo tempo, dias =
        (N/2 × {DAYS_PER_YEAR} + S) × {br(r['steps_per_day'], 0)} × s<sub>rodada</sub> × c ÷
        {br(SECONDS_PER_DAY, 0)}.</p>
      <ul>
        <li><b>S = {SPINUP_DAYS} dias simulados</b> — spin-up de cada rodada contínua. Hipótese de
          planejamento; a duração adequada do spin-up é decisão da MEQ-06.</li>
        <li><b>f = s(B{n_log}) / s(A{n_phys}) = {br(p['f'], 4)}</b> — ganho do SMT: com a segunda tarefa
          de cada núcleo, o passo leva {br(p['f'], 3)} vez o tempo.</li>
        <li><b>s(A{p['n_compact']}) = {br(p['s_a45'], 4)} s/passo</b> — interpolação linear entre
          {esc(INTERP_LO)} ({br(lo['s_per_step'], 4)}) e {esc(INTERP_HI)} ({br(hi['s_per_step'], 4)}) em
          {p['n_compact']} processos. A curva real é levemente curva; a interpolação pode errar por pouco.</li>
        <li><b>k = média(s(D_s0), s(D_s1)) / s(A{per_socket}) = {br(p['k'], 4)}</b> — perda por duas
          rodadas simultâneas, uma em cada soquete. Inclui a diferença de posição (A{per_socket} usa
          metade de cada soquete; cada rodada D usa um soquete inteiro) e a assimetria entre soquetes
          da série D.</li>
        <li><b>c = {br(r['prod_sps'], 4)} / {br(r['c_sps'], 4)} = {br(p['c'], 4)}</b> — correção pela
          produção (capítulo 6), aplicada igualmente a todas as linhas.</li>
        <li><b>Ganho parcial do SMT.</b> Quando só parte dos núcleos recebe duas tarefas
          ({PROJ_RANKS} espalhado: {p['n_extra']} de {n_phys}; {pk['4545']['label']}: {p['n_extra_sock']}
          de {per_socket} por soquete), supõe-se que o ganho do SMT é proporcional a essa fração.</li>
      </ul>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Configuração</th><th style="text-align:left">s/passo projetado</th><th>s/passo</th><th>Dias por ano de rodada (com c)</th><th>Dias por ano de rodada (sem c)</th></tr></thead>
        <tbody>{proj_method_rows}</tbody></table></div>
      <p class="caption">"Dias por ano de rodada" = tempo de relógio para uma rodada avançar um ano
        simulado, sem spin-up. Nas rodadas duplas, os dois blocos avançam ao mesmo tempo, cada um nesse ritmo.</p>
    </details>
    {means(f"Com {PROJ_RANKS} processos compactos, 10 anos simulados levariam cerca de {br(pk['90c']['durations'][PROJ_YEARS.index(10)] / DAYS_PER_MONTH, 1)} meses, deixando {pk['90c']['free_cores']} núcleos livres; usando a máquina inteira ({pk['112']['label'].split(' ')[0]}), cerca de {br(pk['112']['durations'][PROJ_YEARS.index(10)] / DAYS_PER_MONTH, 1)} meses. São projeções com margem de {PLAUSIBLE_MARGIN}; nenhuma configuração foi decidida.")}
    <nav class="pager"><a href="#custo">← Custo por ano simulado</a><a href="#opcoes">Opções →</a></nav>
  </section>

  <section id="opcoes" class="chapter">
    <p class="chapter-no">Capítulo 8</p>
    <h2>Opções para decisão</h2>
    {shows("As quatro formas medidas de ocupar o nó, lado a lado, com o critério de eficiência e o custo estimado.")}
    <p>A tabela reúne vazão, eficiência por núcleo físico, o critério de {pct(EFFICIENCY_CRITERION, 0)}
      e o custo estimado da MEQ-06. Não há pesos nem nota composta. As configurações com
      {PROJ_RANKS} processos do capítulo 7 não estão aqui porque não foram medidas.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Opção</th><th>Processos / núcleos físicos</th><th>Vazão (dias sim. por dia de máquina)</th><th>Efic. por núcleo físico</th><th>Cumpre {pct(EFFICIENCY_CRITERION, 0)}?</th><th>Custo MEQ-06 (a), dias de máquina/ano</th><th>Custo MEQ-06 (b), dias de máquina/ano</th><th style="text-align:left">Situação</th></tr></thead>
      <tbody>{dec_rows}</tbody></table></div>
    <p class="caption">Vazão e custos com o s/passo médio de cada configuração; custos são estimativas
      (capítulo 6). Eficiência relativa a A{r['base_cores']}. Na D, a eficiência é a do par:
      vazão somada ÷ (vazão de A{r['base_cores']} × {n_phys}/{r['base_cores']}).
      <b>(a)</b> custo calculado pelo trecho de {br(r['window_h'], 0)} h medido; <b>(b)</b> o mesmo custo
      corrigido pela média da produção da EXP03, que foi cerca de {pct(r['corr'] - 1, 0)} mais lenta que
      esse trecho.</p>
    <div class="conclusion">
      <h3>Situação da decisão</h3>
      <p class="verdict">A B112 aparece como <b>{esc(PROPOSED_LABEL)}</b>. Nenhuma configuração foi
        decidida neste relatório. A escolha cabe ao pesquisador, considerando também as limitações
        abaixo, em especial a igualdade numérica entre números de processos, que não foi verificada.</p>
    </div>
    {means(f"Entre as opções medidas, só a B112 cumpre o critério de {pct(EFFICIENCY_CRITERION, 0)} e é também a de menor custo, mas ocupa a máquina inteira. Se for importante deixar núcleos para outros usuários, o capítulo 7 mostra quanto isso custa em prazo.")}
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
    <p>{p['n_compact']} núcleos físicos com as duas tarefas, divididos de forma equilibrada entre os
      soquetes: soquete 0 com {run['per_socket_alloc'][0]} núcleos (CPUs {run['example_blocks'][0]}) e
      soquete 1 com {run['per_socket_alloc'][1]} núcleos (CPUs {run['example_blocks'][1]}), na mesma ordem
      da B112 medida. Ficam livres os núcleos {run['free_txt']} ({len(run['free_cores'])} núcleos inteiros).
      Como para qualquer N, o MPAS precisa do arquivo de partição para {PROJ_RANKS} processos.</p>
    <div class="status critical"><strong>Não testado no benchmark; confira a fixação antes de uma rodada longa.</strong>
      Este comando é para o Swell, com a numeração de CPUs acima. Em outra máquina, a lista muda.</div>
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
    {means(f"Sem fixação, a rodada do benchmark ficou cerca de {pct(run['slowdown'], 0)} mais lenta, mesmo com {run['unpinned_ranks'] - run['pinned_ranks']} processos a mais. Fixar também permite escolher quais núcleos ficam livres. Basta acrescentar <code>-bind-to user:&lt;lista&gt;</code> ao comando de sempre; a lista acima vale só para o Swell e o exemplo de {PROJ_RANKS} processos ainda precisa ser conferido numa rodada curta.")}
    <nav class="pager"><a href="#opcoes">← Opções</a><a href="#limitacoes">Limitações →</a></nav>
  </section>

  <section id="limitacoes" class="chapter">
    <p class="chapter-no">Capítulo 10</p>
    <h2>Limitações</h2>
    {shows("O que não foi verificado no benchmark (registro <code>docs/provenance/MEQ-05.2-benchmark-record.md</code>, seção “O que não foi verificado”) e o que decorre das escolhas deste relatório.")}
    <ul>
      <li><b>Igualdade numérica não verificada.</b> Não se verificou se o resultado numérico muda com o
        número de processos. Os campos de saída não foram comparados, e os ensaios sem saída não geram arquivos.</li>
      <li><b>Janela única de {br(r['window_h'], 0)} h</b> ({RESTART_LABEL}). Não se verificou se ela
        reproduz, na mesma proporção de um dia completo, a frequência de cálculos periódicos, como a radiação.</li>
      <li><b>Assimetria entre soquetes na série D.</b> Com as duas rodadas simultâneas, a do soquete 1 levou
        {br(s1['s_per_step'], 4)} s/passo e a do soquete 0, {br(s0['s_per_step'], 4)} s/passo
        ({pct(r['d_asym'])} mais lenta). A causa não foi investigada. Numa produção em pares, a rodada mais
        lenta determina quando o nó fica livre, salvo se a carga for redistribuída.</li>
      <li><b>Frequência do processador</b> (modo de energia, turbo, temperatura) não foi registrada nem controlada.</li>
      <li><b>Uso e velocidade da memória</b> não foram medidos.</li>
      <li><b>Fixação conferida</b> só três vezes por ensaio, até 330 s. Nos ensaios mais longos (A28, A14,
        A8, D), o restante da execução não foi conferido.</li>
      <li><b>Cache de arquivos</b> do sistema não foi controlado. O <i>restart</i> de entrada é relido a cada ensaio.</li>
      <li><b>Extrapolação de I/O</b> supõe custo constante por arquivo e não inclui operações anteriores à
        criação do arquivo. O cronômetro <code>stream_output</code> e as durações por arquivo não foram reconciliados.
        O conteúdo dos arquivos gravados na série E não foi inspecionado.</li>
      <li><b>Correção de custo (variante b).</b> A razão produção/série C ({br(r['corr'], 3)}) foi obtida
        com {c60['ranks']} processos sem fixação. Supõe-se que ela vale para as demais configurações, o que
        não foi verificado.</li>
      <li><b>Eficiência relativa a A{r['base_cores']}</b>, não a um núcleo. A perda de eficiência de 1 a
        {r['base_cores']} núcleos não está medida.</li>
      <li><b>Projeção da MEQ-06 (capítulo 7).</b> Nenhuma das configurações projetadas foi medida. As
        fórmulas supõem interpolação linear entre A{lo['physical_cores']} e A{hi['physical_cores']},
        ganho do SMT proporcional à fração de núcleos com duas tarefas, e a perda por rodadas simultâneas
        medida com {per_socket} processos por soquete. O spin-up de {SPINUP_DAYS} dias por rodada contínua
        é uma hipótese de planejamento. Margem plausível: {PLAUSIBLE_MARGIN}. Os pontos de {PROJ_RANKS}
        processos no capítulo 3 usam as mesmas fórmulas e também não foram medidos.</li>
      <li><b>Rodadas em blocos.</b> Dividir o período em blocos interrompe a continuidade da simulação
        (por exemplo, a umidade do solo recomeça em cada bloco). Se isso é aceitável, e com qual spin-up,
        é decisão da MEQ-06.</li>
      <li><b>Comando de exemplo "{PROJ_RANKS} compacto"</b> (capítulo 9) não foi executado no benchmark.</li>
    </ul>
    {means("Os números deste relatório servem para escolher a configuração e estimar prazos, não para garantir prazos exatos. Antes de uma rodada longa numa configuração não medida, um ensaio curto confirma a velocidade e a fixação.")}
    <nav class="pager"><a href="#como-rodar">← Como rodar</a><a href="#termos">Início ↑</a></nav>
  </section>

  <footer class="footer">
    <p>Gerado por <code>scripts/06_report/build_benchmark_report.py</code> (MEQ-05.3) a partir de tabelas
      consolidadas e registros do benchmark; não edite à mão. Estilo:
      <code>docs/templates/report_v2/report.css</code>, sem modificação; gráficos: Plotly basic
      {esc(meta['plotly_version'])}, embutido. Registro de proveniência:
      <code>docs/provenance/MEQ-05.2-benchmark-record.md</code>.</p>
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

  // Estimated (not measured) 90-process points: open grey markers.
  var EST_SYMBOLS = ['circle-open', 'square-open'];
  function estTraces(key, f) {
    return D.est.map(function (e, i) {
      return { type: 'scatter', mode: 'markers', x: [e.x], y: [e[key]], name: e.label,
        legendgroup: 'est', legendgrouptitle: { text: 'estimado a partir dos pontos medidos, não medido', font: { size: 10 } },
        marker: { symbol: EST_SYMBOLS[i % EST_SYMBOLS.length], color: '#7a7a7a', size: 10, line: { width: 1.6 } },
        hovertemplate: e.label + ': %{y:' + f + '}<br>estimado a partir dos pontos medidos, não medido<extra></extra>' };
    });
  }

  function initSaturation() {
    var b0 = D.base_cores, xmax = D.n_phys;
    var xs = [b0, xmax];
    var ticks = pick(D.a_mean, 'x');
    var common = { xaxis: { title: { text: 'núcleos físicos' }, range: [0, xmax + 4], tickvals: ticks },
                   showlegend: true, legend: { orientation: 'h', yanchor: 'bottom', y: 1.04, x: 0, font: { size: 10 } },
                   margin: { l: 56, r: 12, t: 58, b: 42 } };
    var spTr = [
      { type: 'scatter', mode: 'lines', x: xs, y: xs.map(function (x) { return x / b0; }), name: 'ideal',
        line: { color: '#8c8c8c', width: 1, dash: 'dash' }, hoverinfo: 'skip' },
      { type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, 'sp'), name: 'série A (média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: aceleração %{y:.3f}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, 'sp'), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:.3f}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.b_pts, 'x'), y: pick(D.b_pts, 'sp'),
        name: 'série B (' + D.b_mean.ranks + ' processos, SMT)',
        marker: { symbol: 'diamond-open', color: '#1a1a1a', size: 9, line: { width: 1.4 } },
        customdata: pick(D.b_pts, 'rep'), hovertemplate: 'B r%{customdata}: %{y:.3f}<extra></extra>' }
    ].concat(estTraces('sp', '.3f'));
    plot('chart-speedup', spTr, Object.assign({}, common, {
      yaxis: { title: { text: 'aceleração em relação a ' + b0 + ' núcleos' }, rangemode: 'tozero' } }));

    var efTr = [
      { type: 'scatter', mode: 'lines', x: [0, xmax + 4], y: [D.criterion, D.criterion],
        name: 'critério ' + fmt(100 * D.criterion, 0) + ' %', line: { color: '#883007', width: 1, dash: 'dash' }, hoverinfo: 'skip' },
      { type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, 'eff'), name: 'série A (média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: %{y:.1%}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, 'eff'), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:.1%}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.b_pts, 'x'), y: pick(D.b_pts, 'eff'),
        name: 'série B (' + D.b_mean.ranks + ' processos, SMT)',
        marker: { symbol: 'diamond-open', color: '#1a1a1a', size: 9, line: { width: 1.4 } },
        customdata: pick(D.b_pts, 'rep'), hovertemplate: 'B r%{customdata}: %{y:.1%}<extra></extra>' }
    ].concat(estTraces('eff', '.1%'));
    plot('chart-efficiency', efTr, Object.assign({}, common, {
      yaxis: { title: { text: 'eficiência por núcleo físico' }, tickformat: '.0%', range: [0, 1.08] } }));
  }

  function initThroughput() {
    var O = D.options, labels = pick(O, 'label');
    var tr = [
      { type: 'bar', x: labels, y: pick(O, 'tp'), marker: { color: '#8c8c8c' }, width: 0.55,
        name: 'média', hovertemplate: '%{x}: %{y:.2f} dias simulados por dia de máquina<extra></extra>' }
    ];
    var px = [], py = [];
    O.forEach(function (o) { o.reps.forEach(function (v) { px.push(o.label); py.push(v); }); });
    tr.push({ type: 'scatter', mode: 'markers', x: px, y: py, name: 'repetições',
      marker: { color: '#1a1a1a', size: 6 },
      hovertemplate: '%{x} (repetição): %{y:.2f}<extra></extra>' });
    plot('chart-throughput', tr, { yaxis: { title: { text: 'dias simulados por dia de máquina' }, rangemode: 'tozero' },
      xaxis: { type: 'category' } });
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
                   for p in (BENCH_CSV, RUNTIME_CSV, HW_SNAPSHOT, RECORD_MD)},
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
