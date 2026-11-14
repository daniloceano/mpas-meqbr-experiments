#!/usr/bin/env python
"""MEQ-05.2 — extract timings of the EXP03 parallel benchmark into one table.

Reads, for every trial directory under ``--logs``, the MPAS timer table at the
end of ``log.atmosphere.0000.out`` plus the small text files written by the
benchmark driver (``wrapper_wall_s.txt``, ``pinning_samples.txt``,
``mpiexec_cmd.txt``), and the driver records ``trials.tsv`` / ``loads.tsv``
under ``--records``.  Writes one CSV row per trial, with derived metrics.

No scientific interpretation is done here: the derived columns are arithmetic
on the measured timers, and every extrapolation is labelled as such.

Definitions
-----------
- MPAS timer values are the ``total`` column (global max over ranks of the
  accumulated time in the timer), in seconds.
- ``s_per_step`` = ``time integration`` / its number of calls (360 steps of
  30 s for 3 h simulated).
- ``physical_cores``: cores allotted to the trial (A/E: N; B: 56, 112 ranks on
  56 cores with SMT; C: 56, 60 unpinned ranks on the 56-core node; D: 28 per
  case).  ``core_hours_physical`` = physical_cores x wrapper wall / 3600.
- Speed-up and efficiency are relative to the mean ``time integration`` of the
  two (or three) repetitions of series A with N = 8, using the mean of the
  repetitions of each configuration (``config`` = trial name without the
  repetition suffix; D sockets s0 and s1 are separate configurations):
  ``speedup = T(A8) / T(cfg)``;
  ``efficiency_ranks = speedup / (ranks / 8)``;
  ``efficiency_physcores = speedup / (physical_cores / 8)``.
- ``sim_days_per_wall_day_integration`` = 30 s / s_per_step (one case);
  ``sim_days_per_wall_day_wrapper`` = 10800 s simulated / wrapper wall.
- Series D: ``pair_sim_days_per_node_day_*`` adds the two simultaneous cases of
  the same repetition (integration-based: sum of 30 / s_per_step;
  wrapper-based: 2 x 10800 / pair wall).
- Series E: differences against the mean of A N = 56 (same ranks and pinning,
  output off); ``io_extrap_s_per_sim_day`` is an EXTRAPOLATION of the I/O cost
  to one simulated day (24 hourly histories + 1 restart), using per-file write
  durations (file birth -> last modification, ``outputs_stat.tsv``) when
  available; see ``io_extrap_method``.

Run
---
    python scripts/05_benchmark/parse_benchmark_logs.py \
        --logs results/benchmark/MEQ-05.2/logs \
        --records results/benchmark/MEQ-05.2/records \
        --out results/tables/meq05_parallel_benchmark.csv
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

TIMERS = {
    "total time": "total_time_s",
    "initialize": "initialize_s",
    "time integration": "time_integration_s",
    "physics driver": "physics_driver_s",
    "atm_compute_dyn_tend": "atm_compute_dyn_tend_s",
    "atm_advance_scalars": "atm_advance_scalars_s",
    "atm_advance_scalars_mono": "atm_advance_scalars_mono_s",
    "stream_output": "stream_output_s",
    "stream_input": "stream_input_s",
}
TIMER_RE = re.compile(
    r"^\s*(\d+)\s+(\S.*?)\s+(-?[\d.]+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)"
    r"\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$"
)
STEP_RE = re.compile(r"Timing for integration step:\s+([\d.]+)\s+s")
SIM_SECONDS = 3 * 3600
DT = 30.0

# intended CPU sets (socket 0 physical 0-27, SMT 56-83; socket 1 physical 28-55, SMT 84-111)
def _a_list(n: int) -> list[int]:
    h = n // 2
    return list(range(0, h)) + list(range(28, 28 + h))

INTENDED = {
    ("A", 8): _a_list(8), ("A", 14): _a_list(14), ("A", 28): _a_list(28),
    ("A", 42): _a_list(42), ("A", 56): _a_list(56), ("E", 56): _a_list(56),
    ("B", 112): list(range(0, 28)) + list(range(56, 84)) + list(range(28, 56)) + list(range(84, 112)),
}


def parse_timers(log: Path) -> tuple[dict, int, float]:
    """Return {column: total seconds}, timer calls of 'time integration', median step time."""
    out: dict[str, float] = {}
    calls = 0
    in_table = False
    steps: list[float] = []
    for line in log.read_text(errors="replace").splitlines():
        m = STEP_RE.search(line)
        if m:
            steps.append(float(m.group(1)))
            continue
        if "Timer information" in line:
            in_table = True
            continue
        if not in_table:
            continue
        m = TIMER_RE.match(line)
        if not m:
            continue
        name = m.group(2).strip()
        if name in TIMERS and TIMERS[name] not in out:
            out[TIMERS[name]] = float(m.group(3))
            if name == "time integration":
                calls = int(m.group(4))
    return out, calls, float(np.median(steps)) if steps else np.nan


def check_pinning(sample_file: Path, series: str, ranks: int) -> str:
    """Summarise the affinity samples taken during the run."""
    if not sample_file.exists():
        return "not_sampled"
    aff, psr, nsamp = [], [], 0
    per_sample: list[list[str]] = []
    for line in sample_file.read_text().splitlines():
        if line.startswith("### sample"):
            nsamp += 1
            per_sample.append([])
        m = re.match(r"pid=(\d+) psr=(\d+) affinity=(\S+)", line)
        if m:
            per_sample[-1].append(m.group(3))
            aff.append(m.group(3))
            psr.append(int(m.group(2)))
    if not aff:
        return "no_rank_found_in_samples"
    counts = [len(s) for s in per_sample]
    if series == "C":
        # psr per sample -> physical core id (cpu % 56 on this node: SMT sibling of c is c+56)
        psr_per_sample: list[list[int]] = []
        for line in sample_file.read_text().splitlines():
            if line.startswith("### sample"):
                psr_per_sample.append([])
            m = re.match(r"pid=\d+ psr=(\d+)", line)
            if m:
                psr_per_sample[-1].append(int(m.group(1)))
        cores = [len({c % 56 for c in s}) for s in psr_per_sample if s]
        smt_shared = [len(s) - len({c % 56 for c in s}) for s in psr_per_sample if s]
        return (f"unpinned:affinity={'|'.join(sorted(set(aff)))};samples={nsamp};"
                f"ranks_seen={max(counts)};distinct_cpus_seen_all_samples={len(set(psr))};"
                f"physical_cores_occupied_per_sample={'/'.join(map(str, cores))};"
                f"ranks_on_shared_physical_core_per_sample={'/'.join(map(str, smt_shared))}")
    if series == "D":
        cpus = sorted({int(a) for a in aff if a.isdigit()})
        single = all(a.isdigit() for a in aff)
        return (f"{'verified' if single else 'NOT_single_cpu'}:samples={nsamp};ranks_seen={max(counts)};"
                f"cpus={cpus[0] if cpus else ''}-{cpus[-1] if cpus else ''};n_cpus={len(cpus)}")
    intended = INTENDED.get((series, ranks))
    single = all(a.isdigit() for a in aff)
    cpus = {int(a) for a in aff if a.isdigit()}
    ok = single and intended is not None and cpus == set(intended) and max(counts) == ranks
    return f"{'verified' if ok else 'MISMATCH'}:samples={nsamp};ranks_seen={max(counts)};n_cpus={len(cpus)}"


def read_outputs_stat(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, sep="\t")
    df["write_s"] = df["mtime_epoch"] - df["birth_epoch"]
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", type=Path, default=Path("results/benchmark/MEQ-05.2/logs"))
    ap.add_argument("--records", type=Path, default=Path("results/benchmark/MEQ-05.2/records"))
    ap.add_argument("--out", type=Path, default=Path("results/tables/meq05_parallel_benchmark.csv"))
    args = ap.parse_args()

    trials = pd.read_csv(args.records / "trials.tsv", sep="\t")
    loads = pd.read_csv(args.records / "loads.tsv", sep="\t")

    rows = []
    for _, t in trials.iterrows():
        d = args.logs / t["trial"]
        log = d / "log.atmosphere.0000.out"
        timers, calls, med = parse_timers(log) if log.exists() else ({}, 0, np.nan)
        ser, n = t["series"], int(t["ranks"])
        load_key = t["trial"] if ser != "D" else f"D_N028x2_r{t['rep']}"
        lrow = loads[loads["trial"] == load_key]
        load_before = float(str(lrow["loadavg"].iloc[-1]).split()[0]) if len(lrow) else np.nan
        phys = {"A": n, "E": n, "B": 56, "C": 56, "D": 28}[ser]
        wall = float(t["wall_s"])
        rec = {
            "series": ser, "trial": t["trial"], "ranks": n, "pinning": t["pinning"],
            "repetition": int(t["rep"]), "start_utc": t["start_utc"], "end_utc": t["end_utc"],
            "load_1min_before": load_before, "status": t["status"], "rc": int(t["rc"]),
            **{c: timers.get(c, np.nan) for c in TIMERS.values()},
            "steps": calls,
            "s_per_step": timers.get("time_integration_s", np.nan) / calls if calls else np.nan,
            "median_step_s_from_log": med,
            "physical_cores": phys,
            "wrapper_wall_s": wall,
            "core_hours_physical": phys * wall / 3600.0,
            "pinning_check": check_pinning(d / "pinning_samples.txt", ser, n),
            "mpiexec_cmd": t["mpiexec_cmd"],
        }
        if ser == "D":
            pw = d / "pair_wall_s.txt"
            rec["pair_wall_s"] = float(pw.read_text()) if pw.exists() else np.nan
        rows.append(rec)

    df = pd.DataFrame(rows)
    df["sim_days_per_wall_day_integration"] = DT / df["s_per_step"]
    df["sim_days_per_wall_day_wrapper"] = SIM_SECONDS / df["wrapper_wall_s"]

    # configuration = trial name without the repetition suffix (series D keeps
    # its two sockets, s0 and s1, as separate configurations)
    df.insert(2, "config", df["trial"].str.replace(r"_r\d+$", "", regex=True))
    g = df.groupby("config")
    df["cfg_n_reps"] = g["time_integration_s"].transform("count")
    df["cfg_mean_time_integration_s"] = g["time_integration_s"].transform("mean")
    df["cfg_mean_s_per_step"] = g["s_per_step"].transform("mean")
    df["cfg_rep_spread_pct"] = 100 * (g["time_integration_s"].transform("max") - g["time_integration_s"].transform("min")) \
        / df["cfg_mean_time_integration_s"]

    a8 = df[(df.series == "A") & (df.ranks == 8)]["time_integration_s"].mean()
    df["speedup_vs_A8"] = a8 / df["cfg_mean_time_integration_s"]
    df["efficiency_vs_A8_ranks"] = df["speedup_vs_A8"] / (df["ranks"] / 8)
    df["efficiency_vs_A8_physcores"] = df["speedup_vs_A8"] / (df["physical_cores"] / 8)

    # series D: pair throughput per repetition
    dmask = df.series == "D"
    if dmask.any():
        for rep, sub in df[dmask].groupby("repetition"):
            idx = sub.index
            df.loc[idx, "pair_sim_days_per_node_day_integration"] = (DT / sub["s_per_step"]).sum()
            df.loc[idx, "pair_sim_days_per_node_day_wrapper"] = 2 * SIM_SECONDS / sub["pair_wall_s"].iloc[0]

    # series E: differences against A56 (output off) and I/O extrapolation
    emask = df.series == "E"
    a56 = df[(df.series == "A") & (df.ranks == 56)]
    if emask.any() and len(a56):
        for col in ("total_time_s", "time_integration_s", "stream_output_s", "wrapper_wall_s"):
            df.loc[emask, f"delta_vs_A56_{col}"] = df.loc[emask, col] - a56[col].mean()
        for i in df.index[emask]:
            st = read_outputs_stat(args.logs / df.at[i, "trial"] / "outputs_stat.tsv")
            if st is not None and (st["birth_epoch"] > 0).all():
                hist = st[st["file"].str.startswith("history.")]
                rst = st[st["file"].str.startswith("restart.")]
                h, r = hist["write_s"].mean(), rst["write_s"].mean()
                df.at[i, "n_history_written"] = len(hist)
                df.at[i, "n_restart_written"] = len(rst)
                df.at[i, "history_write_s_mean_filestat"] = h
                df.at[i, "restart_write_s_filestat"] = r
                df.at[i, "io_extrap_s_per_sim_day"] = 24 * h + 1 * r
                df.at[i, "io_extrap_method"] = ("EXTRAPOLATION: 24 x mean history write + 1 x restart write; "
                                               "write durations = file birth -> last modification (ext4 stat, ns timestamps)")
            else:
                df.at[i, "io_extrap_method"] = "not computed: per-file write durations unavailable"

    df.to_csv(args.out, index=False, float_format="%.5g")
    print(f"wrote {args.out} ({len(df)} rows)")


if __name__ == "__main__":
    main()
