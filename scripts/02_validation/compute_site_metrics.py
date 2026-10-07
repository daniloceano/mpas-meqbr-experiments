#!/usr/bin/env python
"""The metric table — every score, for every experiment, site and height.

This is the quantitative backbone of the repository. Everything else either
feeds it (extraction) or reads it (ranking, figures, the write-up). It produces
one tidy CSV so that a reader can check any number in any figure against a
single source.

Scores come in three groups (see `mpas_meqbr.metrics` for the definitions and
the reasoning): point verification (bias/RMSE/correlation and the Takacs
amplitude-phase split), wind-resource statistics (mean speed, Weibull A and k,
wind power density), and diurnal-cycle skill (amplitude and phase of the mean
daily cycle). Direction is scored with circular statistics, masked below 2 m/s
where a measured direction carries no information.

All experiments are scored over the **same hours** by default
(`--common-period`), which matters while EXP02 is still integrating: scoring it
over a different fortnight than CTL would confound the experiment with the
weather.

    python scripts/02_validation/compute_site_metrics.py
    python scripts/02_validation/compute_site_metrics.py --no-common-period

Output: results/tables/site_metrics.csv
        results/tables/site_metrics_summary.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing                   # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--cell", type=int, default=0,
                    help="which of the extracted nearest ocean cells to use (0 = nearest)")
    ap.add_argument("--common-period", dest="common", action="store_true", default=True)
    ap.add_argument("--no-common-period", dest="common", action="store_false")
    ap.add_argument("--out", default="results/tables/site_metrics.csv")
    args = ap.parse_args()

    cfg = load_config()
    experiments = args.experiments or cfg.experiment_keys
    periods = args.period or sorted(cfg.periods)

    rows = []
    for period in periods:
        site_key = cfg.periods[period]["validation_site"]
        print(f"\n=== {period} / {site_key} ===")
        frames = pairing.load_paired(cfg, experiments, period,
                                     cell=args.cell, common=args.common)
        if not frames:
            continue
        era5 = pairing.add_era5(frames, cfg, period)
        if era5 is None:
            print("  (no ERA5 series yet — skill scores against ERA5 omitted)")
        else:
            ref = next(iter(frames.values()))
            ref = ref[ref["model_height"] == 100][
                ["time", "obs_speed", "obs_dir"]]
            era = ref.merge(era5, on="time", how="inner").sort_values("time")
            if len(era) > 10:
                era_scores = metrics.all_scores(
                    era["time"], era["obs_speed"], era["era5_speed"],
                    era["obs_dir"], era["era5_dir"])
                rows.append({
                    "experiment": "ERA5", "period": period, "site": site_key,
                    "height_m": 100, "window_start": era["time"].min(),
                    "window_end": era["time"].max(), **era_scores,
                    "era5_skill_score": 0.0,
                    "era5_rmse": era_scores["rmse"],
                    "era5_bias": era_scores["bias"],
                })
                print(f"  {'ERA5':6s} {100:>4d} m  N={era_scores['n']:>5d}  "
                      f"bias={era_scores['bias']:+.2f}  "
                      f"RMSE={era_scores['rmse']:.2f}  "
                      f"R={era_scores['r']:.3f}  "
                      f"WPD bias={era_scores['wpd_rel_bias_pct']:+.1f} %")

        for exp, df in frames.items():
            for height, sub in df.groupby("model_height"):
                sub = sub.sort_values("time")
                scores = metrics.all_scores(
                    sub["time"], sub["obs_speed"], sub["mod_speed"],
                    sub["obs_dir"], sub["mod_dir"])
                row = {"experiment": exp, "period": period, "site": site_key,
                       "height_m": int(height),
                       "window_start": sub["time"].min(),
                       "window_end": sub["time"].max(), **scores}

                # ERA5 skill score, at 100 m only (see mpas_meqbr.pairing).
                if era5 is not None and int(height) == 100:
                    merged = sub.merge(era5, on="time", how="inner")
                    if len(merged) > 10:
                        row["era5_skill_score"] = metrics.skill_score(
                            merged["obs_speed"], merged["mod_speed"],
                            merged["era5_speed"])
                        row["era5_rmse"] = metrics.basic_scores(
                            merged["obs_speed"], merged["era5_speed"])["rmse"]
                        row["era5_bias"] = metrics.basic_scores(
                            merged["obs_speed"], merged["era5_speed"])["bias"]
                rows.append(row)
                print(f"  {exp:6s} {int(height):>4d} m  N={scores['n']:>5d}  "
                      f"bias={scores['bias']:+.2f}  RMSE={scores['rmse']:.2f}  "
                      f"R={scores['r']:.3f}  WPD bias={scores['wpd_rel_bias_pct']:+.1f} %")

    if not rows:
        print("nothing to score — has extract_site_timeseries.py run?", file=sys.stderr)
        return 1

    df = pd.DataFrame(rows)
    out = cfg.path(*Path(args.out).parts)
    df.to_csv(out, index=False)
    print(f"\n-> {out.relative_to(REPO_ROOT)}  ({len(df)} rows)")

    # A compact markdown view of the numbers that decide the ranking, so the
    # table can be read without opening a spreadsheet.
    keep = ["experiment", "period", "site", "height_m", "n", "obs_mean",
            "model_mean", "bias", "rmse", "r", "wpd_rel_bias_pct",
            "diurnal_amp_bias", "diurnal_phase_error_h", "dir_bias"]
    md = df[[c for c in keep if c in df]].copy()
    for col in md.select_dtypes("float").columns:
        md[col] = md[col].round(3)
    lines = [
        "# Site metrics",
        "",
        f"Generated by `scripts/02_validation/compute_site_metrics.py` "
        f"({'common' if args.common else 'per-experiment'} evaluation window, "
        f"nearest ocean cell #{args.cell}). Regenerate; do not edit.",
        "",
        "`bias`, `rmse` in m/s; `wpd_rel_bias_pct` is the relative error in wind "
        "power density (proportional to U^3, so it magnifies a speed bias by "
        "roughly a factor of three); `diurnal_phase_error_h` is how many hours "
        "early (-) or late (+) the modelled daily wind maximum is.",
        "",
        md.to_markdown(index=False),
    ]
    md_out = cfg.path("results", "tables", "site_metrics_summary.md")
    md_out.write_text("\n".join(lines) + "\n")
    print(f"-> {md_out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
