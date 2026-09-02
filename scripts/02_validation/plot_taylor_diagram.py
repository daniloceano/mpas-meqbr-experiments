#!/usr/bin/env python
"""Taylor diagram — correlation, variance and centred RMSE on one plot.

Useful here precisely because the experiments differ in *how* they are wrong,
not only in how much. A point's angle is the correlation (timing), its radius is
the standard deviation relative to the observations (variability), and its
distance from the reference point on the x-axis is the centred RMSE. Two
experiments with identical RMSE can sit in very different places — one damping
the variability, the other mistiming it — and that distinction changes what you
would try next.

Bias is deliberately *not* on this diagram (it is removed by the centring), so
read it together with `results/tables/site_metrics.csv`.

    python scripts/02_validation/plot_taylor_diagram.py

Output: figures/validation/taylor_<period>_<SITE>.png
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
from mpas_meqbr import pairing, plotting                   # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

HEIGHT_MARKERS = {50: "o", 100: "s", 150: "^", 200: "D", 250: "v"}


def taylor_axes(ax, max_sd: float = 1.6):
    """Draw the polar frame: sd arcs, correlation rays, centred-RMSE arcs."""
    for sd in np.arange(0.25, max_sd + 0.01, 0.25):
        th = np.linspace(0, np.pi / 2, 200)
        ax.plot(sd * np.cos(th), sd * np.sin(th), color="0.85", lw=0.6, zorder=0)
    for corr in [0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 0.99]:
        a = np.arccos(corr)
        ax.plot([0, max_sd * np.cos(a)], [0, max_sd * np.sin(a)],
                color="0.88", lw=0.6, zorder=0)
        ax.text(1.03 * max_sd * np.cos(a), 1.03 * max_sd * np.sin(a), f"{corr}",
                fontsize=6.5, color="0.45", ha="center", va="center")
    for crmse in np.arange(0.25, 1.51, 0.25):
        th = np.linspace(0, np.pi, 300)
        x = 1.0 + crmse * np.cos(th)
        y = crmse * np.sin(th)
        keep = (np.hypot(x, y) <= max_sd) & (y >= 0)
        ax.plot(x[keep], y[keep], color="#B8CBD8", lw=0.6, ls=":", zorder=0)
    ax.plot([1.0], [0.0], marker="*", ms=13, color="k", zorder=5)
    ax.text(1.0, 0.035, "obs", ha="center", va="bottom", fontsize=7.5, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.5))
    ax.set_xlim(0, max_sd * 1.08)
    ax.set_ylim(0, max_sd * 1.08)
    ax.set_aspect("equal")
    ax.set_xlabel("normalised standard deviation")
    ax.grid(False)
    ax.spines["left"].set_visible(True)
    ax.spines["bottom"].set_visible(True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
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
        if not frames:
            continue
        era5 = pairing.add_era5(frames, cfg, period)

        fig, ax = plt.subplots(figsize=(5.6, 5.2))
        taylor_axes(ax)
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in frames:
                continue
            for height, d in frames[exp].groupby("model_height"):
                o, m = d["obs_speed"].values, d["mod_speed"].values
                sd = m.std() / o.std()
                corr = np.corrcoef(o, m)[0, 1]
                a = np.arccos(np.clip(corr, -1, 1))
                ax.plot(sd * np.cos(a), sd * np.sin(a),
                        marker=HEIGHT_MARKERS.get(int(height), "o"), ms=7,
                        color=plotting.EXPERIMENT_COLORS[exp], mec="w", mew=0.6)
        if era5 is not None:
            ref = next(iter(frames.values()))
            ref = ref[ref["model_height"] == 100]
            e = ref.merge(era5, on="time")
            if len(e) > 24:
                sd = e["era5_speed"].std() / e["obs_speed"].std()
                a = np.arccos(np.clip(np.corrcoef(e["obs_speed"], e["era5_speed"])[0, 1], -1, 1))
                ax.plot(sd * np.cos(a), sd * np.sin(a), marker="P", ms=9,
                        color=plotting.EXPERIMENT_COLORS["ERA5"], mec="k", mew=0.6)

        handles = [plt.Line2D([], [], color=plotting.EXPERIMENT_COLORS[e], marker="o",
                              ls="", label=e) for e in plotting.EXPERIMENT_ORDER
                   if e in frames]
        handles += [plt.Line2D([], [], color="0.3", marker=HEIGHT_MARKERS[h], ls="",
                               label=f"{h} m") for h in sorted(HEIGHT_MARKERS)
                    if h in site.model_heights]
        if era5 is not None:
            handles.append(plt.Line2D([], [], color=plotting.EXPERIMENT_COLORS["ERA5"],
                                      marker="P", ls="", label="ERA5 100 m"))
        ax.legend(handles=handles, fontsize=7, loc="upper right", ncol=2)
        ax.set_title(f"{site.label} — {cfg.periods[period]['label']}")
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_taylor_diagram.py | radius = sd(model)/sd(obs), "
                 "angle = correlation, dotted arcs = centred RMSE | bias is NOT shown here")
        out = cfg.path("figures", "validation", f"taylor_{period}_{site_key}.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
