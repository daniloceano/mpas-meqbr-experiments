#!/usr/bin/env python
"""Why the experiments differ — the mechanism behind the score differences.

A ranking says which configuration wins; it does not say whether the win is for
the reason the experiment was designed to test. Without that check, a score
difference could come from anything, and there would be no basis for expecting
it to hold in a different month or a different year — which is exactly what a
climatological run assumes.

The two interventions have specific, checkable signatures at the site:

**EXP01 (daily SST update).** CTL holds the sea surface at the ERA5 *skin
temperature* of the initial instant for 41 days. Switching to daily OISST
changes both the mean SST and its evolution, so the first panel shows the SST
each run actually saw. If the wind difference is caused by the SST, it should
track the SST difference through the surface heat fluxes and the boundary-layer
depth — panels 2 and 3. If the wind changes while the fluxes do not, something
other than the SST is responsible and the attribution fails.

**EXP02 (boundary treatment).** The buffered mesh moves the lateral relaxation
zone from ~190-230 km to ~600 km from the sites. Its signature is not local:
it should show up as a change in how closely the run tracks its ERA5 forcing,
and in the wind field between the site and the old boundary. The site-level
panels here can only show that *something* changed; the spatial evidence is in
`scripts/05_exploration/map_experiment_differences.py`.

    python scripts/03_selection/attribution_diagnostics.py

Output: figures/selection/attribution_<period>_<SITE>.png
        results/tables/attribution_summary.csv
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
import xarray as xr                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import plotting                            # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


def load_site(exp: str, period: str, site_key: str, cell: int = 0):
    path = REPO_ROOT / "results" / "site_timeseries" / f"{exp}_{period}_{site_key}.nc"
    if not path.exists():
        return None
    with xr.open_dataset(path) as ds:
        ds = ds.isel(cell=cell).load()
    return ds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys
    rows, made = [], []

    for period in (args.period or sorted(cfg.periods)):
        site_key = cfg.periods[period]["validation_site"]
        site = cfg.site(site_key)
        datasets = {e: load_site(e, period, site_key) for e in experiments}
        datasets = {e: d for e, d in datasets.items() if d is not None}
        if not datasets:
            continue
        # Same hours for every panel, so a difference is never a coverage artefact.
        common = None
        for d in datasets.values():
            t = pd.DatetimeIndex(d["time"].values)
            common = t if common is None else common.intersection(t)
        datasets = {e: d.sel(time=common) for e, d in datasets.items()}

        panels = [
            ("sst", "sea surface temperature (K)", 1.0),
            ("hfx", "sensible heat flux (W m$^{-2}$)", 1.0),
            ("lh", "latent heat flux (W m$^{-2}$)", 1.0),
            ("hpbl", "PBL height (m)", 1.0),
        ]
        fig, axes = plt.subplots(len(panels) + 1, 1, figsize=(10, 11), sharex=True)
        for ax, (var, label, scale) in zip(axes, panels):
            for exp in plotting.EXPERIMENT_ORDER:
                if exp not in datasets or var not in datasets[exp]:
                    continue
                d = datasets[exp]
                ax.plot(common, d[var].values * scale, lw=1.1,
                        color=plotting.EXPERIMENT_COLORS[exp], label=exp)
            ax.set_ylabel(label, fontsize=8)
            if ax is axes[0]:
                ax.legend(ncol=3, fontsize=8, loc="upper left")

        # Hub-height wind, so the mechanism panels can be read against the effect.
        ax = axes[-1]
        for exp in plotting.EXPERIMENT_ORDER:
            if exp not in datasets:
                continue
            d = datasets[exp]
            k = int(np.argmin(np.abs(d["height_agl"].values - 100.0)))
            speed = np.hypot(d["uReconstructZonal"].isel(level=k).values,
                             d["uReconstructMeridional"].isel(level=k).values)
            ax.plot(common, speed, lw=1.1, color=plotting.EXPERIMENT_COLORS[exp],
                    label=exp)
        ax.set_ylabel("100 m wind speed\n(m s$^{-1}$)", fontsize=8)
        ax.set_xlabel("time (UTC)")

        fig.suptitle(f"Mechanism check at {site.label} — {cfg.periods[period]['label']}",
                     y=0.995)
        plotting.provenance_footer(
            fig, "scripts/03_selection/attribution_diagnostics.py | nearest ocean cell | "
                 "a wind difference should be traceable through SST -> surface fluxes -> "
                 "PBL depth; if it is not, the score difference is not attributable to "
                 "the experiment's stated change")
        out = cfg.path("figures", "selection", f"attribution_{period}_{site_key}.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

        # Numbers for the write-up: means and the pairwise deltas.
        for exp, d in datasets.items():
            k = int(np.argmin(np.abs(d["height_agl"].values - 100.0)))
            speed = np.hypot(d["uReconstructZonal"].isel(level=k).values,
                             d["uReconstructMeridional"].isel(level=k).values)
            rows.append({
                "experiment": exp, "period": period, "site": site_key,
                "n_hours": len(common),
                "mean_sst_K": float(np.nanmean(d["sst"].values)) if "sst" in d else np.nan,
                "sst_range_K": float(np.nanmax(d["sst"].values) - np.nanmin(d["sst"].values))
                if "sst" in d else np.nan,
                "mean_hfx_Wm2": float(np.nanmean(d["hfx"].values)) if "hfx" in d else np.nan,
                "mean_lh_Wm2": float(np.nanmean(d["lh"].values)) if "lh" in d else np.nan,
                "mean_hpbl_m": float(np.nanmean(d["hpbl"].values)) if "hpbl" in d else np.nan,
                "mean_ust_ms": float(np.nanmean(d["ust"].values)) if "ust" in d else np.nan,
                "mean_speed100_ms": float(np.nanmean(speed)),
            })

    if not rows:
        print("nothing to diagnose", file=sys.stderr)
        return 1
    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", "attribution_summary.csv")
    df.to_csv(out, index=False)
    print(df.round(2).to_string(index=False))
    for p in made + [out]:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
