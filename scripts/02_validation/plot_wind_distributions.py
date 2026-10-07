#!/usr/bin/env python
"""Speed distribution, fitted Weibull, and wind rose.

A resource assessment integrates the *distribution*, not the time series: annual
energy production is a weighted integral of the speed histogram against the
turbine power curve. So a model can track the hour-to-hour variation well and
still misstate the resource, if it clips the high-speed tail or narrows the
distribution.

Left: histogram plus the fitted Weibull (scale A, shape k, both by maximum
likelihood with location fixed at zero, as resource practice requires). The
Weibull parameters are printed because they are what a resource report quotes.
Right: wind rose, observed against each experiment — direction matters for
turbine layout and for whether the model is putting the flow in the right
sector, which on this coast means separating the trade wind from the sea breeze.

    python scripts/02_validation/plot_wind_distributions.py [--height 100]

Output: figures/validation/distribution_<period>_<SITE>_<height>m.png
        figures/validation/windrose_<period>_<SITE>_<height>m.png
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

N_SECTORS = 16


def rose_counts(direction, speed, bins):
    """Fraction of time in each (direction sector, speed bin)."""
    edges = np.linspace(0, 360, N_SECTORS + 1)
    shifted = (np.asarray(direction) + 360.0 / N_SECTORS / 2) % 360.0
    sector = np.digitize(shifted, edges) - 1
    out = np.zeros((N_SECTORS, len(bins) - 1))
    for s in range(N_SECTORS):
        sel = sector == s
        if sel.sum():
            out[s], _ = np.histogram(np.asarray(speed)[sel], bins=bins)
    return out / max(len(direction), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--height", type=int, default=100)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys
    made = []

    for period in (args.period or sorted(cfg.periods)):
        site_key = cfg.periods[period]["validation_site"]
        site = cfg.site(site_key)
        frames = pairing.load_paired(cfg, experiments, period, common=True)
        frames = {k: v[v["model_height"] == args.height] for k, v in frames.items()}
        frames = {k: v for k, v in frames.items() if len(v) > 48}
        if not frames:
            continue
        ref = next(iter(frames.values()))
        era5 = pairing.add_era5(frames, cfg, period)
        era5_pair = None
        if era5 is not None and args.height == 100:
            era5_pair = ref[["time", "obs_speed", "obs_dir"]].merge(
                era5, on="time", how="inner")

        # ---- distribution + Weibull --------------------------------------
        from scipy.stats import weibull_min

        fig, ax = plt.subplots(figsize=(6.2, 4.0))
        edges = np.arange(0, np.ceil(ref["obs_speed"].max()) + 1.0, 0.5)
        grid = np.linspace(0.01, edges[-1], 300)
        ax.hist(ref["obs_speed"], bins=edges, density=True, color="0.82",
                edgecolor="0.6", lw=0.4, label="LiDAR")
        A, k = metrics.weibull_fit(ref["obs_speed"])
        ax.plot(grid, weibull_min.pdf(grid, k, 0, A), color="k", lw=2,
                label=f"LiDAR Weibull (A={A:.2f}, k={k:.2f})")
        if era5_pair is not None and len(era5_pair) > 48:
            Ae, ke = metrics.weibull_fit(era5_pair["era5_speed"])
            ax.plot(grid, weibull_min.pdf(grid, ke, 0, Ae),
                    color=plotting.EXPERIMENT_COLORS["ERA5"], lw=1.5, ls="--",
                    label=f"ERA5 (A={Ae:.2f}, k={ke:.2f})")
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in frames:
                continue
            Am, km = metrics.weibull_fit(frames[exp]["mod_speed"])
            ax.plot(grid, weibull_min.pdf(grid, km, 0, Am),
                    color=plotting.EXPERIMENT_COLORS[exp], lw=1.5,
                    label=f"{exp} (A={Am:.2f}, k={km:.2f})")
        ax.set_xlabel("wind speed (m s$^{-1}$)")
        ax.set_ylabel("probability density")
        ax.set_title(f"{site.label} — {args.height} m — {cfg.periods[period]['label']}")
        ax.legend(fontsize=7.5)
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_wind_distributions.py | Weibull by MLE, "
                 "location fixed at 0 | A = scale (m/s), k = shape")
        out = cfg.path("figures", "validation",
                       f"distribution_{period}_{site_key}_{args.height}m.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

        # ---- wind roses ---------------------------------------------------
        panels = [("LiDAR", ref["obs_dir"].values, ref["obs_speed"].values)]
        if era5_pair is not None and len(era5_pair) > 48:
            panels.append(("ERA5", era5_pair["era5_dir"].values,
                           era5_pair["era5_speed"].values))
        panels += [
            (exp, frames[exp]["mod_dir"].values, frames[exp]["mod_speed"].values)
            for exp in plotting.EXPERIMENT_ORDER if exp in frames]
        speed_bins = [0, 4, 6, 8, 10, 100]
        colors = plt.cm.viridis(np.linspace(0.1, 0.95, len(speed_bins) - 1))
        fig, axes = plt.subplots(1, len(panels), figsize=(3.1 * len(panels), 3.6),
                                 subplot_kw={"projection": "polar"})
        axes = np.atleast_1d(axes)
        theta = np.deg2rad(np.arange(0, 360, 360 / N_SECTORS))
        width = 2 * np.pi / N_SECTORS * 0.9
        for ax, (label, d, s) in zip(axes, panels):
            ok = np.isfinite(d) & np.isfinite(s)
            counts = rose_counts(d[ok], s[ok], speed_bins)
            bottom = np.zeros(N_SECTORS)
            for j in range(counts.shape[1]):
                ax.bar(theta, counts[:, j], width=width, bottom=bottom,
                       color=colors[j], edgecolor="none",
                       label=(f"{speed_bins[j]}-{speed_bins[j+1]}"
                              if speed_bins[j + 1] < 100 else f">{speed_bins[j]}")
                       if ax is axes[0] else None)
                bottom += counts[:, j]
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            ax.set_title(label, fontsize=9,
                         color=plotting.EXPERIMENT_COLORS.get(label, "k"))
            ax.set_yticklabels([])
            ax.set_xticks(np.deg2rad([0, 90, 180, 270]))
            ax.set_xticklabels(["N", "E", "S", "W"], fontsize=7)
            ax.grid(alpha=0.3, lw=0.4)
        axes[0].legend(fontsize=6, loc="lower left", bbox_to_anchor=(-0.25, -0.18),
                       title="m s$^{-1}$", title_fontsize=6)
        fig.suptitle(f"{site.label} — {args.height} m — {cfg.periods[period]['label']}",
                     y=1.04)
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_wind_distributions.py | 16 sectors, direction "
                 "the wind blows FROM | radius = fraction of hours | ERA5 included only "
                 "for the directly comparable 100 m diagnostic")
        out = cfg.path("figures", "validation",
                       f"windrose_{period}_{site_key}_{args.height}m.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
