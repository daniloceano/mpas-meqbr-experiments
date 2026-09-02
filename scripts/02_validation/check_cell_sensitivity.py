#!/usr/bin/env python
"""How much of the verification result is an artefact of picking one grid cell?

Every score in this repository comes from a single MPAS cell — the nearest ocean
cell to the instrument, 1-3 km away depending on site and mesh. That is the
conventional choice, but it is a choice, and a point measurement compared
against a ~20 km2 cell average carries a representativeness error that no model
improvement can remove.

This script recomputes the headline scores using each of the five nearest ocean
cells kept by the extraction, so the spread across them can be read as a floor
on what any experiment difference has to beat to be meaningful. If switching
cells moves RMSE by more than the gap between two experiments, the ranking
between those two is not supported by this evidence.

    python scripts/02_validation/check_cell_sensitivity.py

Output: results/tables/cell_sensitivity.csv
        figures/validation/cell_sensitivity.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
import pandas as pd                                        # noqa: E402
import xarray as xr                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing, plotting          # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


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
    rows = []

    for period in (args.period or sorted(cfg.periods)):
        site_key = cfg.periods[period]["validation_site"]
        for exp in experiments:
            path = REPO_ROOT / "results" / "site_timeseries" / f"{exp}_{period}_{site_key}.nc"
            if not path.exists():
                continue
            with xr.open_dataset(path) as ds:
                n_cells = ds.sizes["cell"]
                distances = ds["cell_distance_km"].values
            for cell in range(n_cells):
                frames = pairing.load_paired(cfg, [exp], period, cell=cell, common=False)
                if exp not in frames:
                    continue
                d = frames[exp][frames[exp]["model_height"] == args.height]
                if len(d) < 48:
                    continue
                s = metrics.basic_scores(d["obs_speed"], d["mod_speed"])
                r = metrics.resource_scores(d["obs_speed"], d["mod_speed"])
                rows.append({"experiment": exp, "period": period, "site": site_key,
                             "cell": cell, "distance_km": float(distances[cell]),
                             "n": s["n"], "bias": s["bias"], "rmse": s["rmse"],
                             "r": s["r"], "wpd_rel_bias_pct": r["wpd_rel_bias_pct"]})

    if not rows:
        print("nothing to check — has extract_site_timeseries.py run?", file=sys.stderr)
        return 1

    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", "cell_sensitivity.csv")
    df.to_csv(out, index=False)

    spread = df.groupby(["experiment", "period"]).agg(
        rmse_min=("rmse", "min"), rmse_max=("rmse", "max"),
        bias_min=("bias", "min"), bias_max=("bias", "max"))
    spread["rmse_spread"] = spread["rmse_max"] - spread["rmse_min"]
    spread["bias_spread"] = spread["bias_max"] - spread["bias_min"]
    print(spread.round(3).to_string())
    print(f"\n-> {out.relative_to(REPO_ROOT)}")

    periods = sorted(df["period"].unique())
    fig, axes = plt.subplots(1, len(periods), figsize=(4.6 * len(periods), 3.6),
                             squeeze=False)
    for ax, period in zip(axes[0], periods):
        sub = df[df["period"] == period]
        for exp in plotting.EXPERIMENT_ORDER:
            e = sub[sub["experiment"] == exp].sort_values("distance_km")
            if e.empty:
                continue
            ax.plot(e["distance_km"], e["rmse"], "o-", ms=5,
                    color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        ax.set_xlabel("distance from instrument to cell centre (km)")
        ax.set_title(f"{cfg.periods[period]['label']} — "
                     f"{cfg.periods[period]['validation_site']} — {args.height} m")
        ax.legend(fontsize=7.5)
    axes[0][0].set_ylabel("RMSE (m s$^{-1}$)")
    plotting.provenance_footer(
        fig, "scripts/02_validation/check_cell_sensitivity.py | each point is one of the "
             "five nearest ocean cells | the vertical spread within one colour is the "
             "representativeness floor an experiment difference must exceed")
    fig_out = cfg.path("figures", "validation", "cell_sensitivity.png")
    fig.savefig(fig_out)
    plt.close(fig)
    print(f"-> {fig_out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
