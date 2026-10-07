#!/usr/bin/env python
"""Does the 5 km MPAS run beat the reanalysis that drives it?

This is the question that decides whether these simulations are usable as an
ERA5 alternative for wind-resource work on this coast. ERA5 is not an
independent competitor here — it supplies the initial and lateral boundary
conditions — which is exactly what makes the comparison clean: whatever skill
the MPAS run has beyond ERA5's is attributable to the integration on the finer
mesh, and nothing else.

The headline number is the Murphy skill score

    SS = 1 - MSE_MPAS / MSE_ERA5

read directly as the fraction of ERA5's mean-square error that the downscaling
removes. Zero means the 5 km run is no better than its own driver at the site;
negative means it is worse, which is a real and publishable outcome and a
strong argument against spending compute on climatological runs.

Comparison is at 100 m, ERA5's own hub-height diagnostic, so neither side is
extrapolated. Uncertainty is a moving-block bootstrap, for the same
autocorrelation reason as in the experiment ranking.

    python scripts/04_era5/added_value.py

Output: results/tables/era5_added_value.csv
        figures/era5/added_value.png
"""

from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--height", type=int, default=100)
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
    tag = f"_{args.tag}" if args.tag else ""
    rows = []

    for period in (args.period or sorted(cfg.periods)):
        site_key = cfg.periods[period]["validation_site"]
        frames = pairing.load_paired(cfg, experiments, period, common=True)
        era5 = pairing.add_era5(frames, cfg, period, height_for_era5=args.height)
        if not frames or era5 is None:
            print(f"[{period}] missing model or ERA5 series — skipping")
            continue
        print(f"\n=== {period} / {site_key} at {args.height} m ===")

        merged = None
        for exp, d in frames.items():
            d = d[d["model_height"] == args.height][["time", "obs_speed", "mod_speed"]]
            d = d.rename(columns={"mod_speed": exp})
            merged = d if merged is None else merged.merge(
                d.drop(columns="obs_speed"), on="time")
        merged = merged.merge(era5, on="time", how="inner").sort_values("time")
        if len(merged) < 3 * args.block_hours:
            print(f"[{period}] only {len(merged)} common hours — skipping")
            continue

        s_era = metrics.basic_scores(merged["obs_speed"], merged["era5_speed"])
        r_era = metrics.resource_scores(merged["obs_speed"], merged["era5_speed"])
        rows.append({"source": "ERA5", "period": period, "site": site_key,
                     "height_m": args.height, "n": s_era["n"],
                     "rmse": s_era["rmse"], "bias": s_era["bias"], "r": s_era["r"],
                     "wpd_rel_bias_pct": r_era["wpd_rel_bias_pct"],
                     "rmse_reduction_vs_era5": 0.0,
                     "skill_vs_era5": 0.0, "skill_lo": np.nan, "skill_hi": np.nan,
                     "significant": False})
        print(f"  ERA5   N={s_era['n']:>5d}  bias={s_era['bias']:+.2f}  "
              f"RMSE={s_era['rmse']:.2f}  R={s_era['r']:.3f}")

        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in merged:
                continue
            s = metrics.basic_scores(merged["obs_speed"], merged[exp])
            r = metrics.resource_scores(merged["obs_speed"], merged[exp])
            test = metrics.paired_skill_test(
                merged["obs_speed"].values, merged["era5_speed"].values,
                merged[exp].values, block_hours=args.block_hours, n_boot=args.n_boot)
            mse_era = s_era["rmse"] ** 2
            rows.append({
                "source": exp, "period": period, "site": site_key,
                "height_m": args.height, "n": s["n"],
                "rmse": s["rmse"], "bias": s["bias"], "r": s["r"],
                "wpd_rel_bias_pct": r["wpd_rel_bias_pct"],
                "rmse_reduction_vs_era5": 1.0 - s["rmse"] / s_era["rmse"],
                "skill_vs_era5": test["delta_mse"] / mse_era,
                "skill_lo": test["lo"] / mse_era, "skill_hi": test["hi"] / mse_era,
                "significant": test["significant"],
            })
            verdict = ("adds skill" if test["significant"] and test["delta_mse"] > 0
                       else "loses skill" if test["significant"]
                       else "indistinguishable from ERA5")
            print(f"  {exp:6s} N={s['n']:>5d}  bias={s['bias']:+.2f}  "
                  f"RMSE={s['rmse']:.2f}  R={s['r']:.3f}  "
                  f"SS={test['delta_mse']/mse_era:+.3f} "
                  f"[{test['lo']/mse_era:+.3f}, {test['hi']/mse_era:+.3f}] -> {verdict}")

    if not rows:
        print("nothing computed — is the ERA5 download in place?", file=sys.stderr)
        return 1
    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", f"era5_added_value{tag}.csv")
    df.to_csv(out, index=False)

    # ---- figure -----------------------------------------------------------
    site_periods = df[["period", "site"]].drop_duplicates().values.tolist()
    fig, axes = plt.subplots(1, len(site_periods),
                             figsize=(4.4 * len(site_periods), 3.6), squeeze=False)
    for ax, (period, site_key) in zip(axes[0], site_periods):
        s = df[(df["period"] == period) & (df["site"] == site_key)]
        s = s[s["source"] != "ERA5"]
        order = [e for e in plotting.EXPERIMENT_ORDER if e in set(s["source"])]
        x = np.arange(len(order))
        vals = [s[s["source"] == e]["skill_vs_era5"].iloc[0] for e in order]
        los = [s[s["source"] == e]["skill_lo"].iloc[0] for e in order]
        his = [s[s["source"] == e]["skill_hi"].iloc[0] for e in order]
        colors = [plotting.EXPERIMENT_COLORS[e] for e in order]
        ax.bar(x, vals, color=colors, width=0.55)
        ax.errorbar(x, vals, yerr=[np.array(vals) - np.array(los),
                                   np.array(his) - np.array(vals)],
                    fmt="none", ecolor="k", capsize=4, lw=1.0)
        ax.axhline(0, color="k", lw=1.0)
        ax.set_xticks(x)
        ax.set_xticklabels(order)
        n = int(s["n"].max())
        ax.set_title(f"{site_key} — {cfg.periods[period]['label']} (N={n} h)")
    axes[0][0].set_ylabel("skill score vs ERA5\n1 - MSE(MPAS) / MSE(ERA5)")
    fig.suptitle(f"Added value of the {args.height} m MPAS wind over its ERA5 forcing",
                 y=1.03)
    plotting.provenance_footer(
        fig, f"scripts/04_era5/added_value.py | ERA5 100 m wind, bilinearly interpolated to "
             f"the site | 95 % moving-block bootstrap ({args.block_hours} h blocks, "
             f"{args.n_boot} resamples) | SS = 1 - MSE(MPAS)/MSE(ERA5) = "
             "1 - [RMSE(MPAS)/RMSE(ERA5)]^2 | above 0 = downscaling removes ERA5 error, "
             "below 0 = it adds error")
    fig_out = cfg.path("figures", "era5", f"added_value{tag}.png")
    fig.savefig(fig_out)
    plt.close(fig)
    for p in (out, fig_out):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
