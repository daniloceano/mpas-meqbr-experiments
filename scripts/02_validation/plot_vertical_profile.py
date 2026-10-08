#!/usr/bin/env python
"""Mean wind profile and shear across the LiDAR's measured heights.

Wind-resource work is done at a hub height that usually falls between measured
levels, so the *shape* of the profile matters as much as the value at any one
level. Two failure modes this figure separates, which a single-height score
cannot:

* a **level-independent offset** — the model is uniformly too fast or slow,
  typically a surface-roughness or stability problem;
* a **shear error** — the model gets 50 m right and 200 m wrong, meaning the
  boundary-layer scheme is mixing too much or too little. Extrapolating such a
  model to an unmeasured hub height would compound the error.

The right panel shows the power-law exponent alpha (``U ~ z**alpha``) between
the lowest and highest common levels, which is the number a resource assessment
would actually use to extrapolate.

    python scripts/02_validation/plot_vertical_profile.py

Output: figures/validation/profile_<period>_<SITE>.png
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
from mpas_meqbr import pairing, plotting, vertical         # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


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

        fig, axes = plt.subplots(1, 3, figsize=(11, 4),
                                 gridspec_kw={"width_ratios": [1, 1, 1.2]})

        # -- mean profile ---------------------------------------------------
        ax = axes[0]
        ref = next(iter(frames.values()))
        obs_prof = ref.groupby("model_height")["obs_speed"].mean()
        ax.plot(obs_prof.values, obs_prof.index, "ko-", lw=2, ms=5, label="LiDAR")
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in frames:
                continue
            prof = frames[exp].groupby("model_height")["mod_speed"].mean()
            ax.plot(prof.values, prof.index, "o-", ms=4,
                    color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        era5_pair = None
        if era5 is not None:
            at_100 = ref[ref["model_height"] == 100][
                ["time", "obs_speed", "obs_dir"]]
            era5_pair = at_100.merge(era5, on="time", how="inner")
            if len(era5_pair) > 24:
                ax.plot([era5_pair["era5_speed"].mean()], [100], marker="P", ms=8,
                        ls="", color=plotting.EXPERIMENT_COLORS["ERA5"],
                        mec="k", mew=0.5, label="ERA5 (100 m)")
        ax.set_xlabel("mean wind speed (m s$^{-1}$)")
        ax.set_ylabel("height above sea level (m)")
        ax.set_title("mean profile")
        ax.legend(fontsize=7.5)

        # -- bias profile ---------------------------------------------------
        ax = axes[1]
        ax.axvline(0, color="0.4", lw=0.8)
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in frames:
                continue
            d = frames[exp]
            bias = d.groupby("model_height").apply(
                lambda g: (g["mod_speed"] - g["obs_speed"]).mean(),
                include_groups=False)
            ax.plot(bias.values, bias.index, "o-", ms=4,
                    color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        if era5_pair is not None and len(era5_pair) > 24:
            ax.plot([(era5_pair["era5_speed"] - era5_pair["obs_speed"]).mean()],
                    [100], marker="P", ms=8, ls="",
                    color=plotting.EXPERIMENT_COLORS["ERA5"], mec="k", mew=0.5)
        ax.set_xlabel("model - observed (m s$^{-1}$)")
        ax.set_title("bias by height")

        # -- shear exponent -------------------------------------------------
        ax = axes[2]
        heights = sorted(ref["model_height"].unique())
        z_lo, z_hi = heights[0], heights[-1]
        rows = []
        for label, frame, cols in [("LiDAR", ref, ("obs_speed", "obs_speed"))] + [
                (exp, frames[exp], ("mod_speed", "mod_speed"))
                for exp in plotting.EXPERIMENT_ORDER if exp in frames]:
            col = cols[0]
            wide = frame.pivot_table(index="time", columns="model_height", values=col)
            if z_lo not in wide or z_hi not in wide:
                continue
            alpha = vertical.shear_exponent(wide[z_lo], wide[z_hi], z_lo, z_hi)
            rows.append(pd.Series(alpha, name=label).dropna())
        if rows:
            # `labels=` was renamed `tick_labels=` in matplotlib 3.9; set the
            # tick labels afterwards so the script runs on either version.
            ax.boxplot([r.values for r in rows], showfliers=False, widths=0.6)
            ax.set_xticks(np.arange(1, len(rows) + 1))
            ax.set_xticklabels([r.name for r in rows])
            for i, r in enumerate(rows, start=1):
                ax.text(i, np.nanmedian(r.values), f"{np.nanmedian(r.values):.3f}",
                        ha="center", va="bottom", fontsize=7)
        ax.set_ylabel(r"shear exponent $\alpha$")
        ax.set_title(fr"$U \propto z^\alpha$, {z_lo}-{z_hi} m")
        ax.tick_params(axis="x", labelrotation=30)

        fig.suptitle(f"{site.label} — vertical structure — {cfg.periods[period]['label']}",
                     y=1.01)
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_vertical_profile.py | heights are the model "
                 "layer centres matched to LiDAR channels | shear from the lowest and "
                 "highest common levels, alpha = ln(U_high/U_low) / ln(z_high/z_low); "
                 "calm hours (<0.05 m/s) excluded | ERA5 has one directly comparable "
                 "hub-height diagnostic (100 m), so no ERA5 alpha is inferred")
        out = cfg.path("figures", "validation", f"profile_{period}_{site_key}.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
