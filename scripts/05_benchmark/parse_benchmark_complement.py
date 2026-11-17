#!/usr/bin/env python
"""MEQ-05.5 — extract the complementary EXP03 parallel benchmark (two blocks, same-session references).

Mission code MEQ-05.5; the trial directories on Swell keep the prefix ``MEQ054_`` (see
``docs/provenance/MEQ-05.5-benchmark-complement-record.md``).  Same extraction as
``parse_benchmark_logs.py`` (MEQ-05.2), whose functions are reused unchanged
(``parse_timers``, ``read_outputs_stat``).  The MEQ-05.2 table
``results/tables/meq05_parallel_benchmark.csv`` is only READ (column order, A8 / A56 / B112
references for the informative comparison); it is never written.

Design
------
Each block runs REF_A56 -> P90C -> P90E -> Q45S -> REF_B112 -> Q45C -> Q56 -> E90C -> REF_A56
(block 1 = repetition 1, block 2 = repetition 2).  A block attempt is valid when its two REF_A56
differ <= 3 % (``blocks_validity.tsv``).  Trials flagged ``interferido`` were repeated once at the
end of the block (suffix ``_redo``).  The earlier controls MEQ054_CTRL_A56_r1/r2 are NOT included.

Rows used in statistics (``used_in_stats``): trials of the valid attempt of each block, excluding a
trial flagged ``interferido`` when its ``_redo`` exists (then the redo is used).

Definitions (in addition to those of ``parse_benchmark_logs.py``)
------------------------------------------------------------------
- ``config``: series (+ case s0/s1 for pairs); ``repetition`` = ``block``.
- ``physical_cores``: physical cores holding the ranks of the trial (one case for pairs);
  ``free_whole_cores_node``: physical cores of the node with no rank of any simultaneous case.
- ``ref_A56_mean_s_per_step_block``: mean s/step of the two REF_A56 of the same block attempt
  (redo used when applicable).  ``s_per_step_norm`` = s_per_step / that mean;
  ``sim_days_per_wall_day_integration_norm`` = throughput / REF_A56 throughput of the block.
- Pairs (Q45S, Q45C, Q56): ``pair_partner_*`` = the other simultaneous case;
  ``pair_sim_days_per_node_day_integration`` = sum of 30 / s_per_step of both cases;
  ``pair_sim_days_per_node_day_wrapper`` = 2 x 10800 / pair wall; ``*_norm`` = divided by the
  REF_A56 throughput of the block (30 / ref mean s/step).
- Memory: ``max_rss_kb_largest_process_time_v`` (``/usr/bin/time -v`` around ``timeout mpiexec``:
  the LARGEST single process); ``sum_vmhwm_kb_last_full_sample`` = sum over ranks of VmHWM in the
  last affinity sample that saw all ranks (sampled; per-rank peaks need not be simultaneous).
- Monitor (every ~30 s, 5 s /proc window): ``cpu_mhz_mean_trial_cpus`` / ``cpu_mhz_mean_all``
  = mean of the per-sample means of ``cpu MHz`` (/proc/cpuinfo) over the trial's CPUs / all CPUs;
  ``max_foreign_cpu_pct`` = maximum instantaneous CPU of any other user's process (% of one CPU).
- ``meq052_rel_diff_cfg_s_per_step``: INFORMATIVE only, (cfg mean - MEQ-05.2 A56 or B112 mean) /
  MEQ-05.2 mean, for REF_A56 and REF_B112.
- E90C: ``delta_vs_baseline_*`` = E90C minus P90C of the same block attempt;
  ``io_extrap_*`` as in MEQ-05.2 (EXTRAPOLATION, labelled).  ``delta_vs_A56_*`` stay empty.

Run
---
    python scripts/05_benchmark/parse_benchmark_complement.py \
        --logs results/benchmark/MEQ-05.4/logs --records results/benchmark/MEQ-05.4/records \
        --ref results/tables/meq05_parallel_benchmark.csv \
        --out results/tables/meq05_5_parallel_benchmark_complement.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_benchmark_logs import DT, SIM_SECONDS, TIMERS, parse_timers, read_outputs_stat  # noqa: E402


def R(a: int, b: int) -> list[int]:
    return list(range(a, b + 1))


INTENDED = {
    ("REF_A56", ""): R(0, 27) + R(28, 55),
    ("REF_B112", ""): R(0, 27) + R(56, 83) + R(28, 55) + R(84, 111),
    ("P90C", ""): R(0, 22) + R(56, 78) + R(28, 49) + R(84, 105),
    ("E90C", ""): R(0, 22) + R(56, 78) + R(28, 49) + R(84, 105),
    ("P90E", ""): R(0, 27) + R(56, 72) + R(28, 55) + R(84, 100),
    ("Q45S", "s0"): R(0, 27) + R(56, 72), ("Q45S", "s1"): R(28, 55) + R(84, 100),
    ("Q45C", "s0"): R(0, 22) + R(56, 77), ("Q45C", "s1"): R(28, 50) + R(84, 105),
    ("Q56", "s0"): R(0, 27) + R(56, 83), ("Q56", "s1"): R(28, 55) + R(84, 111),
}
FREE_WHOLE_CORES = {"REF_A56": 0, "REF_B112": 0, "P90C": 11, "E90C": 11, "P90E": 0,
                    "Q45S": 0, "Q45C": 10, "Q56": 0}
PAIRED = {"Q45S", "Q45C", "Q56"}
SAMPLE_RE = re.compile(r"pid=(\d+) psr=(\d+) affinity=(\S+)(?: rss_kb=(\d*) hwm_kb=(\d*))?")
MON_RE = re.compile(r"max_other_pct=([\d.]+) .*mhz_all=([\d.]+|nan) mhz_list=([\d.]+|NA)")


def case_of(trial: str) -> str:
    m = re.search(r"_(s[01])$", trial)
    return m.group(1) if m else ""


def read_samples(path: Path) -> list[list[dict]]:
    samples: list[list[dict]] = []
    if not path.exists():
        return samples
    for line in path.read_text().splitlines():
        if line.startswith("### sample"):
            samples.append([])
            continue
        m = SAMPLE_RE.match(line)
        if m and samples:
            samples[-1].append({"psr": int(m.group(2)), "aff": m.group(3),
                                "hwm": int(m.group(5)) if m.group(5) else np.nan})
    return samples


def check_pinning(samples: list[list[dict]], series: str, case: str, ranks: int) -> str:
    full = [s for s in samples if s]
    if not full:
        return "no_rank_found_in_samples" if samples else "not_sampled"
    aff = [r["aff"] for s in full for r in s]
    single = all(a.isdigit() for a in aff)
    cpus = {int(a) for a in aff if a.isdigit()}
    psr_ok = all(r["psr"] == int(r["aff"]) for s in full for r in s if r["aff"].isdigit())
    counts = [len(s) for s in full]
    ok = single and cpus == set(INTENDED[(series, case)]) and max(counts) == ranks and psr_ok
    return (f"{'verified' if ok else 'MISMATCH'}:samples={len(samples)};samples_with_ranks={len(full)};"
            f"ranks_seen_min={min(counts)};ranks_seen_max={max(counts)};n_cpus={len(cpus)};"
            f"psr_equals_affinity={'yes' if psr_ok else 'no'}")


def read_time_v(path: Path) -> tuple[float, str]:
    if not path.exists():
        return np.nan, "not_available"
    txt = path.read_text()
    m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", txt)
    e = re.search(r"Exit status:\s*(\d+)", txt)
    return (float(m.group(1)) if m else np.nan), (e.group(1) if e else "NA")


def read_monitor(path: Path) -> tuple[float, float, float, int]:
    if not path.exists():
        return np.nan, np.nan, np.nan, 0
    mx, ma, ml = [], [], []
    for line in path.read_text().splitlines():
        m = MON_RE.search(line)
        if m:
            mx.append(float(m.group(1)))
            ma.append(float(m.group(2)))
            if m.group(3) != "NA":
                ml.append(float(m.group(3)))
    f = lambda v: float(np.mean(v)) if v else np.nan  # noqa: E731
    return (max(mx) if mx else np.nan), f(ml), f(ma), len(mx)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", type=Path, default=Path("results/benchmark/MEQ-05.4/logs"))
    ap.add_argument("--records", type=Path, default=Path("results/benchmark/MEQ-05.4/records"))
    ap.add_argument("--ref", type=Path, default=Path("results/tables/meq05_parallel_benchmark.csv"))
    ap.add_argument("--out", type=Path, default=Path("results/tables/meq05_5_parallel_benchmark_complement.csv"))
    args = ap.parse_args()

    ref = pd.read_csv(args.ref)  # MEQ-05.2 table: read only
    base_cols = list(ref.columns)
    a8 = ref[(ref.series == "A") & (ref.ranks == 8)]["time_integration_s"].mean()
    meq052_sps = {"REF_A56": ref[(ref.series == "A") & (ref.ranks == 56)]["s_per_step"].mean(),
                  "REF_B112": ref[(ref.series == "B") & (ref.ranks == 112)]["s_per_step"].mean()}

    trials = pd.read_csv(args.records / "blocks_trials.tsv", sep="\t")
    valid = pd.read_csv(args.records / "blocks_validity.tsv", sep="\t")
    free = pd.read_csv(args.records / "blocks_freecheck.tsv", sep="\t")

    rows = []
    for _, t in trials.iterrows():
        d = args.logs / t["trial"]
        log = d / "log.atmosphere.0000.out"
        timers, calls, med = parse_timers(log) if log.exists() else ({}, 0, np.nan)
        ser, n, case = t["series"], int(t["ranks"]), case_of(t["trial"])
        trial_key = re.sub(r"_s[01]$", "", t["trial"])
        fr = free[free["context"] == f"trial:{trial_key}"]
        load_before = float(fr["load1"].iloc[-1]) if len(fr) else np.nan
        samples = read_samples(d / "pinning_samples.txt")
        full = [s for s in samples if len(s) == n]
        hwm = [r["hwm"] for r in full[-1]] if full else []
        maxrss, tv_exit = read_time_v(d / "time_v.txt")
        mxo, mhz_l, mhz_a, nmon = read_monitor(d / "monitor.txt")
        wall = float(t["wall_s"])
        phys = len({c % 56 for c in INTENDED[(ser, case)]})
        rec = {
            "series": ser, "trial": t["trial"], "config": ser + (f"_{case}" if case else ""),
            "ranks": n, "pinning": t["pinning"], "repetition": int(t["block"]),
            "start_utc": t["start_utc"], "end_utc": t["end_utc"], "load_1min_before": load_before,
            "status": t["status"], "rc": int(t["rc"]),
            **{c: timers.get(c, np.nan) for c in TIMERS.values()},
            "steps": calls,
            "s_per_step": timers.get("time_integration_s", np.nan) / calls if calls else np.nan,
            "median_step_s_from_log": med, "physical_cores": phys, "wrapper_wall_s": wall,
            "core_hours_physical": phys * wall / 3600.0,
            "pinning_check": check_pinning(samples, ser, case, n), "mpiexec_cmd": t["mpiexec_cmd"],
            "block": int(t["block"]), "attempt": int(t["attempt"]), "interferido": t["interferido"],
            "is_redo": "_redo" in t["trial"],
            "free_whole_cores_node": FREE_WHOLE_CORES[ser],
            "smt_second_thread_ranks": sum(1 for c in INTENDED[(ser, case)] if c >= 56),
            "max_rss_kb_largest_process_time_v": maxrss, "time_v_exit_status": tv_exit,
            "sum_vmhwm_kb_last_full_sample": float(np.nansum(hwm)) if hwm else np.nan,
            "max_vmhwm_kb_rank_last_full_sample": float(np.nanmax(hwm)) if hwm else np.nan,
            "n_samples_all_ranks": len(full),
            "cpu_mhz_mean_trial_cpus": mhz_l, "cpu_mhz_mean_all": mhz_a,
            "max_foreign_cpu_pct": mxo, "n_monitor_samples": nmon,
        }
        if ser in PAIRED:
            pw = d / "pair_wall_s.txt"
            rec["pair_wall_s"] = float(pw.read_text()) if pw.exists() else np.nan
        rows.append(rec)

    df = pd.DataFrame(rows)
    df["sim_days_per_wall_day_integration"] = DT / df["s_per_step"]
    df["sim_days_per_wall_day_wrapper"] = SIM_SECONDS / df["wrapper_wall_s"]

    # block validity and REF_A56 normalisation (per block attempt, redo used when present)
    vkey = {(int(r.block), int(r.attempt)): r for r in valid.itertuples()}
    for (b, a), sub in df.groupby(["block", "attempt"]):
        v = vkey.get((b, a))
        idx = sub.index
        df.loc[idx, "block_valid"] = (v.valid if v is not None else "not_evaluated")
        df.loc[idx, "ref_A56_rel_diff_block"] = (v.rel_diff if v is not None else np.nan)
        if v is not None:
            refs = df[df.trial.isin([v.ref_first_trial, v.ref_last_trial])]
            df.loc[idx, "ref_A56_mean_s_per_step_block"] = refs["s_per_step"].mean()

    # rows used in statistics: valid attempt; interfered trials replaced by their redo
    redo_of = {t.replace("_redo", "") for t in df.trial if "_redo" in t}
    df["used_in_stats"] = (df["block_valid"] == "yes") & ~((df["interferido"] == "sim") & df.trial.isin(redo_of))

    df["s_per_step_norm"] = df["s_per_step"] / df["ref_A56_mean_s_per_step_block"]
    df["sim_days_per_wall_day_integration_norm"] = df["ref_A56_mean_s_per_step_block"] / df["s_per_step"]

    u = df[df.used_in_stats]
    g = u.groupby("config")
    for col, src, fn in (("cfg_n_reps", "time_integration_s", "count"),
                         ("cfg_mean_time_integration_s", "time_integration_s", "mean"),
                         ("cfg_mean_s_per_step", "s_per_step", "mean")):
        df[col] = df["config"].map(getattr(g[src], fn)())
    spread = 100 * (g["time_integration_s"].max() - g["time_integration_s"].min()) / g["time_integration_s"].mean()
    df["cfg_rep_spread_pct"] = df["config"].map(spread)
    df["cfg_mean_s_per_step_norm"] = df["config"].map(g["s_per_step_norm"].mean())
    df["speedup_vs_A8"] = a8 / df["cfg_mean_time_integration_s"]
    df["efficiency_vs_A8_ranks"] = df["speedup_vs_A8"] / (df["ranks"] / 8)
    df["efficiency_vs_A8_physcores"] = df["speedup_vs_A8"] / (df["physical_cores"] / 8)
    for s, r in meq052_sps.items():
        m = df.series == s
        df.loc[m, "meq052_rel_diff_cfg_s_per_step"] = (df.loc[m, "cfg_mean_s_per_step"] - r) / r

    # pairs: partner and summed throughput per (series, block, attempt, redo)
    pm = df.series.isin(PAIRED)
    for _, sub in df[pm].groupby(["series", "block", "attempt", "is_redo"]):
        tot = (DT / sub["s_per_step"]).sum()
        for i in sub.index:
            j = [k for k in sub.index if k != i]
            if j:
                df.at[i, "pair_partner_trial"] = df.at[j[0], "trial"]
                df.at[i, "pair_partner_s_per_step"] = df.at[j[0], "s_per_step"]
                df.at[i, "pair_partner_sim_days_per_wall_day_integration"] = DT / df.at[j[0], "s_per_step"]
            refthr = DT / df.at[i, "ref_A56_mean_s_per_step_block"]
            df.at[i, "pair_sim_days_per_node_day_integration"] = tot
            df.at[i, "pair_sim_days_per_node_day_wrapper"] = 2 * SIM_SECONDS / sub["pair_wall_s"].iloc[0]
            df.at[i, "pair_sim_days_per_node_day_integration_norm"] = tot / refthr

    # E90C vs P90C of the same block attempt; I/O extrapolation as in MEQ-05.2
    for i in df.index[df.series == "E90C"]:
        b, a = df.at[i, "block"], df.at[i, "attempt"]
        base = df[(df.series == "P90C") & (df.block == b) & (df.attempt == a) & df.used_in_stats]
        if len(base):
            df.at[i, "nooutput_baseline_config"] = f"P90C block {b} attempt {a}"
            for col in ("total_time_s", "time_integration_s", "stream_output_s", "wrapper_wall_s"):
                df.at[i, f"delta_vs_baseline_{col}"] = df.at[i, col] - base[col].mean()
        st = read_outputs_stat(args.logs / df.at[i, "trial"] / "outputs_stat.tsv")
        if st is not None and len(st) and (st["birth_epoch"] > 0).all():
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

    extra = ["block", "attempt", "block_valid", "ref_A56_rel_diff_block", "interferido", "is_redo",
             "used_in_stats", "max_foreign_cpu_pct", "cpu_mhz_mean_trial_cpus", "cpu_mhz_mean_all",
             "n_monitor_samples", "ref_A56_mean_s_per_step_block", "s_per_step_norm",
             "sim_days_per_wall_day_integration_norm", "cfg_mean_s_per_step_norm",
             "pair_sim_days_per_node_day_integration_norm", "free_whole_cores_node",
             "smt_second_thread_ranks", "pair_partner_trial", "pair_partner_s_per_step",
             "pair_partner_sim_days_per_wall_day_integration", "max_rss_kb_largest_process_time_v",
             "time_v_exit_status", "sum_vmhwm_kb_last_full_sample", "max_vmhwm_kb_rank_last_full_sample",
             "n_samples_all_ranks", "meq052_rel_diff_cfg_s_per_step", "nooutput_baseline_config",
             "delta_vs_baseline_total_time_s", "delta_vs_baseline_time_integration_s",
             "delta_vs_baseline_stream_output_s", "delta_vs_baseline_wrapper_wall_s"]
    for c in base_cols + extra:
        if c not in df.columns:
            df[c] = np.nan
    df = df[base_cols + extra]
    for c in ("max_rss_kb_largest_process_time_v", "sum_vmhwm_kb_last_full_sample", "max_vmhwm_kb_rank_last_full_sample"):
        df[c] = df[c].round().astype("Int64")
    df.to_csv(args.out, index=False, float_format="%.5g")
    print(f"wrote {args.out} ({len(df)} rows)")


if __name__ == "__main__":
    main()
