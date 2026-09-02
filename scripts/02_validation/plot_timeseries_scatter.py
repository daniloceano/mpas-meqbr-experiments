#!/usr/bin/env python
"""Time series and density scatter of modelled vs observed wind speed.

The first figure to look at, and the one that catches the errors a summary table
hides: a run that is right on average but drifts, a run that misses one synoptic
event badly, an observation gap that the metrics silently absorbed. The scatter
panel underneath gives the same sample as a joint distribution, coloured by
point density so the bulk is visible instead of an ink blot.

    python scripts/02_validation/plot_timeseries_scatter.py [--height 100]

Output: figures/validation/timeseries_<period>_<SITE>_<height>m.png
        figures/validation/scatter_<period>_<SITE>_<height>m.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing, plotting          # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


def density_colors(x, y):
    """Point density by Gaussian KDE, falling back to plain points if it fails."""
    from scipy.stats import gaussian_kde

    try:
        return gaussian_kde(np.vstack([x, y]))(np.vstack([x, y]))
    except Exception:                                      # noqa: BLE001
        return np.zeros_like(x)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--height", type=int, default=100)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--common-period", dest="common", action="store_true", default=True)
    ap.add_argument("--no-common-period", dest="common", action="store_false")
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys
    periods = args.period or sorted(cfg.periods)
    made = []

    for period in periods:
        site_key = cfg.periods[period]["validation_site"]
        site = cfg.site(site_key)
        frames = pairing.load_paired(cfg, experiments, period, common=args.common)
        frames = {k: v[v["model_height"] == args.height] for k, v in frames.items()}
        frames = {k: v for k, v in frames.items() if len(v) > 24}
        if not frames:
            print(f"[{period}] nothing to plot at {args.height} m")
            continue
        era5 = pairing.add_era5(frames, cfg, period)

        # ---- time series -------------------------------------------------
        fig, ax = plt.subplots(figsize=(11, 3.6))
        ref = next(iter(frames.values()))
        ax.plot(ref["time"], ref["obs_speed"], color="k", lw=1.6, label=f"{site_key} LiDAR")
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in frames:
                continue
            d = frames[exp]
            ax.plot(d["time"], d["mod_speed"], lw=1.0, alpha=0.9,
                    color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        if era5 is not None and args.height == 100:
            e = era5[era5["time"].isin(ref["time"])]
            ax.plot(e["time"], e["era5_speed"], lw=1.0, ls="--",
                    color=plotting.EXPERIMENT_COLORS["ERA5"], label="ERA5 100 m")
        ax.set_ylabel("wind speed (m s$^{-1}$)")
        ax.set_title(f"{site.label} — {args.height} m — {cfg.periods[period]['label']}")
        ax.legend(ncol=5, loc="upper left", fontsize=8)
        ax.margins(x=0.01)
        plotting.provenance_footer(
            fig, f"scripts/02_validation/plot_timeseries_scatter.py | "
                 f"{ref['time'].min():%Y-%m-%d} to {ref['time'].max():%Y-%m-%d} | "
                 f"nearest ocean cell | hourly-averaged LiDAR")
        out = cfg.path("figures", "validation",
                       f"timeseries_{period}_{site_key}_{args.height}m.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

        # ---- scatter -----------------------------------------------------
        n = len(frames)
        fig, axes = plt.subplots(1, n, figsize=(3.4 * n, 3.6), sharex=True, sharey=True,
                                 squeeze=False)
        lim = float(np.nanpercentile(
            np.concatenate([ref["obs_speed"].values] +
                           [d["mod_speed"].values for d in frames.values()]), 99.8)) * 1.1
        for ax, (exp, d) in zip(axes[0], frames.items()):
            x, y = d["obs_speed"].values, d["mod_speed"].values
            ax.scatter(x, y, c=density_colors(x, y), s=6, cmap="viridis", lw=0)
            ax.plot([0, lim], [0, lim], color="0.4", lw=0.8)
            s = metrics.basic_scores(x, y)
            r = metrics.resource_scores(x, y)
            ax.set_title(exp, color=plotting.EXPERIMENT_COLORS[exp])
            ax.text(0.04, 0.96,
                    f"N = {s['n']}\nbias = {s['bias']:+.2f}\nRMSE = {s['rmse']:.2f}\n"
                    f"R = {s['r']:.3f}\nWPD = {r['wpd_rel_bias_pct']:+.0f} %",
                    transform=ax.transAxes, va="top", ha="left", fontsize=7.5,
                    bbox=dict(fc="white", ec="0.8", alpha=0.85))
            ax.set_xlim(0, lim)
            ax.set_ylim(0, lim)
            ax.set_aspect("equal")
            ax.set_xlabel("observed (m s$^{-1}$)")
        axes[0][0].set_ylabel("model (m s$^{-1}$)")
        fig.suptitle(f"{site.label} — {args.height} m — {cfg.periods[period]['label']}",
                     y=1.02)
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_timeseries_scatter.py | colour = point density "
                 "(Gaussian KDE) | WPD = relative bias in wind power density")
        out = cfg.path("figures", "validation",
                       f"scatter_{period}_{site_key}_{args.height}m.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
