#!/usr/bin/env python
"""Rank the experiments, with uncertainty — the decision this repository exists for.

The question is narrow and practical: which configuration should the
climatological runs use? Answering it well needs three things that a table of
RMSEs does not provide on its own.

**1. Paired comparison.** The experiments see the same weather at the same site,
so comparing them through the paired difference of squared errors removes the
shared synoptic variability and leaves only the difference the configuration
makes. This is far more sensitive than comparing two RMSE values that each carry
the full weather variance.

**2. Autocorrelation-aware uncertainty.** Hourly wind errors persist for many
hours. Treating 700 hours as 700 independent samples would produce confidence
intervals several times too narrow and turn noise into "significant"
improvements. A moving-block bootstrap with 24-hour blocks is used instead.

**3. Consistency across independent evidence.** There are two site-periods
(P0/Nov-2021 and LPI/Oct-2022) with different instruments, different months and
different synoptic conditions. An experiment that wins at one and loses at the
other has not demonstrated anything general — and for a climatological run,
generality is the entire point. The summary therefore reports agreement across
site-periods explicitly rather than averaging them into one number.

Cost enters the decision too: EXP02's buffered mesh costs about +24 % in cells
and wall time, which for multi-year runs is a real budget line. A configuration
must earn that.

    python scripts/03_selection/rank_experiments.py [--height 100] [--n-boot 2000]

Output: results/tables/experiment_ranking.csv
        results/tables/pairwise_tests.csv
        results/tables/selection_summary.md
        figures/selection/ranking_<height>m.png
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402
import pandas as pd                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing, plotting          # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


def rmse_stat(o, m):
    return float(np.sqrt(np.mean((m - o) ** 2)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", nargs="*", type=int, default=[50, 100, 150, 200])
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--block-hours", type=int, default=24)
    ap.add_argument("--tag", default="",
                    help="suffix for the output files, to keep a restricted-experiment "
                         "run (e.g. CTL+EXP01 over the full window) beside the default")
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys
    periods = args.period or sorted(cfg.periods)
    tag = f"_{args.tag}" if args.tag else ""

    ranking, tests = [], []
    for period in periods:
        site_key = cfg.periods[period]["validation_site"]
        frames = pairing.load_paired(cfg, experiments, period, common=True)
        if len(frames) < 1:
            continue
        present = [e for e in plotting.EXPERIMENT_ORDER if e in frames]
        print(f"\n=== {period} / {site_key} — {', '.join(present)} ===")

        for height in args.heights:
            subs = {e: frames[e][frames[e]["model_height"] == height].sort_values("time")
                    for e in present}
            subs = {e: d for e, d in subs.items() if len(d) >= 3 * args.block_hours}
            if not subs:
                continue

            for exp, d in subs.items():
                ci = metrics.block_bootstrap_ci(
                    d["obs_speed"].values, d["mod_speed"].values, rmse_stat,
                    block_hours=args.block_hours, n_boot=args.n_boot)
                s = metrics.basic_scores(d["obs_speed"], d["mod_speed"])
                r = metrics.resource_scores(d["obs_speed"], d["mod_speed"])
                dc = metrics.diurnal_scores(d["time"], d["obs_speed"], d["mod_speed"])
                ranking.append({
                    "experiment": exp, "period": period, "site": site_key,
                    "height_m": height, "n": s["n"],
                    "rmse": s["rmse"], "rmse_lo": ci["lo"], "rmse_hi": ci["hi"],
                    "bias": s["bias"], "r": s["r"],
                    "wpd_rel_bias_pct": r["wpd_rel_bias_pct"],
                    "diurnal_phase_error_h": dc["diurnal_phase_error_h"],
                    "diurnal_amp_bias": dc["diurnal_amp_bias"],
                    "window_start": d["time"].min(), "window_end": d["time"].max(),
                })

            # Pairwise: is B better than A on the same hours?
            for a, b in itertools.combinations(subs, 2):
                da, db = subs[a], subs[b]
                merged = da.merge(db[["time", "mod_speed"]], on="time",
                                  suffixes=("_a", "_b"))
                if len(merged) < 3 * args.block_hours:
                    continue
                res = metrics.paired_skill_test(
                    merged["obs_speed"].values, merged["mod_speed_a"].values,
                    merged["mod_speed_b"].values,
                    block_hours=args.block_hours, n_boot=args.n_boot)
                better = b if res["delta_mse"] > 0 else a
                tests.append({
                    "period": period, "site": site_key, "height_m": height,
                    "experiment_a": a, "experiment_b": b, **res,
                    "better": better if res["significant"] else "no difference",
                })
                verdict = (f"{better} better" if res["significant"]
                           else "not distinguishable")
                print(f"  {height:>4d} m  {a} vs {b}: "
                      f"dMSE={res['delta_mse']:+.3f} "
                      f"[{res['lo']:+.3f}, {res['hi']:+.3f}]  "
                      f"RMSE {res['rmse_a']:.2f} / {res['rmse_b']:.2f}  -> {verdict}")

    if not ranking:
        print("nothing to rank", file=sys.stderr)
        return 1

    rank_df = pd.DataFrame(ranking)
    test_df = pd.DataFrame(tests)
    rank_out = cfg.path("results", "tables", f"experiment_ranking{tag}.csv")
    test_out = cfg.path("results", "tables", f"pairwise_tests{tag}.csv")
    rank_df.to_csv(rank_out, index=False)
    test_df.to_csv(test_out, index=False)

    # ---- figure ----------------------------------------------------------
    sub = rank_df[rank_df["height_m"].isin(args.heights)]
    site_periods = sub[["period", "site"]].drop_duplicates().values.tolist()
    fig, axes = plt.subplots(1, len(site_periods),
                             figsize=(4.6 * len(site_periods), 3.8), squeeze=False)
    for ax, (period, site_key) in zip(axes[0], site_periods):
        s = sub[(sub["period"] == period) & (sub["site"] == site_key)]
        heights = sorted(s["height_m"].unique())
        offsets = np.linspace(-0.22, 0.22, max(len(s["experiment"].unique()), 1))
        for off, exp in zip(offsets, [e for e in plotting.EXPERIMENT_ORDER
                                      if e in set(s["experiment"])]):
            e = s[s["experiment"] == exp].set_index("height_m").reindex(heights)
            x = np.arange(len(heights)) + off
            ax.errorbar(x, e["rmse"],
                        yerr=[e["rmse"] - e["rmse_lo"], e["rmse_hi"] - e["rmse"]],
                        fmt="o", ms=5, capsize=3, lw=1.2,
                        color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        ax.set_xticks(np.arange(len(heights)))
        ax.set_xticklabels([f"{h} m" for h in heights])
        n = int(s["n"].max())
        ax.set_title(f"{site_key} — {cfg.periods[period]['label']} (N={n} h)")
        ax.legend(fontsize=7.5)
    axes[0][0].set_ylabel("RMSE (m s$^{-1}$)")
    fig.suptitle("Experiment ranking — RMSE with 95 % moving-block bootstrap interval",
                 y=1.02)
    plotting.provenance_footer(
        fig, f"scripts/03_selection/rank_experiments.py | {args.block_hours} h blocks, "
             f"{args.n_boot} resamples | all experiments scored over the same hours | "
             "overlapping intervals do NOT settle a comparison — see pairwise_tests.csv, "
             "which tests the paired difference directly and is far more sensitive")
    fig_out = cfg.path("figures", "selection", f"ranking{tag}.png")
    fig.savefig(fig_out)
    plt.close(fig)

    # ---- decision summary -------------------------------------------------
    lines = [
        "# Experiment selection",
        "",
        "Generated by `scripts/03_selection/rank_experiments.py`. Regenerate; do not edit.",
        "",
    ]

    # A ranking must not be readable without the data-integrity result. If the
    # SST audit found contamination, say so here, at the top, before any number.
    sst_path = REPO_ROOT / "results" / "tables" / "sst_forcing_check.csv"
    if sst_path.exists():
        sst = pd.read_csv(sst_path)
        bad = sst[sst["n_at_land_fill"] > 0]
        if len(bad):
            affected = sorted(bad["experiment"].unique())
            lines += [
                "> **The SST forcing is contaminated in "
                f"{', '.join(affected)}.** "
                "Coastal ocean cells carry the NOAA OISST land fill value "
                "(273.15 K), and both LiDAR sites sit inside the affected "
                "strip. Any comparison below that involves "
                f"{' or '.join(affected)} is therefore measuring an "
                "interpolation error in the surface forcing, not the "
                "hypothesis that experiment was designed to test. See "
                "`results/tables/sst_forcing_check.csv`, "
                "`figures/selection/sst_forcing_*.png` and "
                "`SCIENTIFIC_NOTES.md` (Result 1).",
                "",
                "| Experiment | Ocean cells at the OISST land fill | SST at P0 | SST at LPI |",
                "|---|---|---|---|",
            ]
            for _, r in sst.drop_duplicates("experiment").iterrows():
                lines.append(
                    f"| {r['experiment']} | {int(r['n_at_land_fill'])} | "
                    f"{r['sst_at_P0_K']:.1f} K | {r['sst_at_LPI_K']:.1f} K |")
            lines.append("")

    lines += [
        "## How to read this",
        "",
        "`pairwise_tests.csv` is the evidence. Each row tests whether one "
        "experiment's squared error is smaller than another's **on the same "
        "hours**, with a 95 % moving-block bootstrap interval "
        f"({args.block_hours} h blocks, {args.n_boot} resamples). A verdict of "
        "`no difference` means the interval spans zero: the data do not "
        "separate the two, which is a real result and not a failure.",
        "",
        "## Pairwise verdicts",
        "",
    ]
    if len(test_df):
        pivot = test_df.pivot_table(
            index=["period", "site", "height_m"],
            columns=["experiment_a", "experiment_b"],
            values="better", aggfunc="first")
        lines.append(pivot.to_markdown())
        lines += ["", "## Agreement across site-periods", ""]
        for (a, b), grp in test_df.groupby(["experiment_a", "experiment_b"]):
            wins = grp["better"].value_counts().to_dict()
            summary = ", ".join(f"{k}: {v}" for k, v in wins.items())
            lines.append(f"- **{a} vs {b}** — {summary} (out of {len(grp)} "
                         "site-period-height comparisons)")
    lines += [
        "",
        "## Cost",
        "",
        "| Experiment | Mesh | Cells | Relative cost |",
        "|---|---|---|---|",
    ]
    for exp in plotting.EXPERIMENT_ORDER:
        if exp not in cfg.experiments:
            continue
        meta = cfg.experiments[exp]
        lines.append(f"| {exp} | {meta['mesh']} | "
                     f"{cfg.meshes[meta['mesh']]['n_cells']:,} | "
                     f"{meta['relative_cost']:.2f}x |")
    lines += [
        "",
        "A configuration that is not *significantly* better does not justify a "
        "higher cost for multi-year runs.",
        "",
        "## Headline numbers",
        "",
        rank_df.drop(columns=["window_start", "window_end"]).round(3).to_markdown(index=False),
        "",
        "## Caveats that limit what this can decide",
        "",
        "- One month per site. Month-to-month and year-to-year variability is "
        "not sampled, so a ranking here is a ranking *for these conditions*. "
        "`scripts/04_era5/climatological_context.py` quantifies how typical the "
        "two months were against the 1990-2020 ERA5 distribution.",
        "- Two sites, both offshore on the same coast. Nothing here constrains "
        "behaviour inland or over complex terrain.",
        "- Every score comes from one grid cell. "
        "`scripts/02_validation/check_cell_sensitivity.py` measures how much of "
        "the spread is attributable to that choice.",
        "- Where EXP02 is still integrating, its comparison window is shorter "
        "and its intervals correspondingly wider. Re-run once it completes.",
    ]
    md = cfg.path("results", "tables", f"selection_summary{tag}.md")
    md.write_text("\n".join(lines) + "\n")

    for p in (rank_out, test_out, md, fig_out):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
