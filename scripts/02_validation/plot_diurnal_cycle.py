#!/usr/bin/env python
"""Mean diurnal cycle of wind speed — the sea-breeze test.

On this coast the daily cycle is not a detail: the land-sea thermal contrast
drives a large diurnal swing in the near-coastal wind, and resolving it is the
main physical argument for running a 5 km mesh instead of using a ~31 km
reanalysis. A model can have an excellent RMSE and still get the daily cycle's
amplitude or timing wrong, which for wind-energy purposes matters because the
diurnal phase controls when the resource is available.

Composites are built in **local time** (UTC-3), because the forcing is solar.
Shading is +/- one standard deviation across days, so the reader can see whether
a difference between experiments is larger than the day-to-day spread.

    python scripts/02_validation/plot_diurnal_cycle.py [--height 100]

Output: figures/validation/diurnal_<period>_<SITE>.png
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heights", nargs="*", type=int, default=[50, 100, 200])
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
        heights = [h for h in args.heights if h in site.model_heights]

        fig, axes = plt.subplots(1, len(heights), figsize=(3.6 * len(heights), 3.4),
                                 sharey=True, squeeze=False)
        for ax, height in zip(axes[0], heights):
            ref = None
            for exp in plotting.EXPERIMENT_ORDER:
                if exp not in frames:
                    continue
                d = frames[exp][frames[exp]["model_height"] == height]
                if len(d) < 24:
                    continue
                if ref is None:
                    ref = d
                    co = metrics.diurnal_composite(d["time"], d["obs_speed"])
                    ax.fill_between(co.index, co["mean"] - co["std"], co["mean"] + co["std"],
                                    color="0.75", alpha=0.35, lw=0)
                    ax.plot(co.index, co["mean"], color="k", lw=2.0, label="LiDAR")
                cm = metrics.diurnal_composite(d["time"], d["mod_speed"])
                sc = metrics.diurnal_scores(d["time"], d["obs_speed"], d["mod_speed"])
                ax.plot(cm.index, cm["mean"], color=plotting.EXPERIMENT_COLORS[exp],
                        lw=1.4,
                        label=f"{exp} (amp {sc['diurnal_amp_bias']:+.1f}, "
                              f"phase {sc['diurnal_phase_error_h']:+.0f} h)")
            if era5 is not None and height == 100 and ref is not None:
                e = era5[era5["time"].isin(ref["time"])]
                ce = metrics.diurnal_composite(e["time"], e["era5_speed"])
                ax.plot(ce.index, ce["mean"], color=plotting.EXPERIMENT_COLORS["ERA5"],
                        ls="--", lw=1.3, label="ERA5 100 m")
            ax.set_title(f"{height} m")
            ax.set_xlabel("local hour (UTC-3)")
            ax.set_xticks(np.arange(0, 24, 6))
            ax.set_xlim(0, 23)
            ax.legend(fontsize=6.5, loc="best")
        axes[0][0].set_ylabel("wind speed (m s$^{-1}$)")
        fig.suptitle(f"{site.label} — mean diurnal cycle — {cfg.periods[period]['label']}",
                     y=1.02)
        plotting.provenance_footer(
            fig, "scripts/02_validation/plot_diurnal_cycle.py | composites in local time "
                 "(UTC-3) | shading = +/- 1 sd across days | legend: amplitude bias (m/s) "
                 "and phase error (h, + = model peaks late)")
        out = cfg.path("figures", "validation", f"diurnal_{period}_{site_key}.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
