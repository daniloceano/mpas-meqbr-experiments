#!/usr/bin/env python
"""Audit the SST field each experiment was actually forced with.

EXP01's whole premise is that replacing a frozen ERA5 skin temperature with
daily NOAA OISST gives a better sea surface. That premise is worth checking
directly rather than inferring it from wind scores, because the SST enters
through `<mesh>.sfc_update.nc`, produced by `init_atmosphere` case 8 — an
interpolation step whose output nobody normally looks at.

What this script checks, per experiment and period:

* **Land-fill contamination.** OISST is a gridded product with land masked. If
  the mask is not honoured when interpolating to the mesh, coastal ocean cells
  are blended with the land fill value (273.15 K) and end up far too cold. The
  script counts cells at exactly the fill value and cells below a physically
  implausible threshold for this latitude.
* **Distance to the coast.** Genuine coastal upwelling is possible; a
  contamination artefact is not. The two are separated by where the cold cells
  are: upwelling has a physical scale of tens to hundreds of kilometres, an
  interpolation artefact is confined to the first cell or two from land.
* **Value at the validation sites.** Both LiDARs are close inshore, so this is
  the number that decides whether the site-level comparison between CTL and
  EXP01 is testing the SST hypothesis or an interpolation error.

Exits non-zero if contamination is detected in a run that is not already
registered as a known-bad one (``sst_forcing_known_bad: true``). The superseded
EXP01_BADSST/EXP02_BADSST pair is contaminated by definition — that is why it is
kept — so reporting it must not fail the pipeline, while any new occurrence
must. This is a data-integrity gate, not a figure.

    python scripts/03_selection/check_sst_forcing.py

Output: figures/selection/sst_forcing_<period>.png
        results/tables/sst_forcing_check.csv
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
from netCDF4 import Dataset                                # noqa: E402
from scipy.spatial import cKDTree                          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, mesh, plotting                  # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

OISST_LAND_FILL_K = 273.15
# Below this, an SST on the Brazilian equatorial margin is not physical: the
# regional climatological range is roughly 299-303 K and even strong coastal
# upwelling here does not approach 296 K.
IMPLAUSIBLE_K = 296.0


def distance_to_land_km(lat, lon, landmask):
    land = landmask == 1
    ocean = landmask == 0
    if land.sum() == 0:
        return np.full(lat.shape, np.inf)
    scale = 111.195
    tree = cKDTree(np.c_[lon[land] * scale * np.cos(np.deg2rad(lat[land])),
                         lat[land] * scale])
    d = np.full(lat.shape, np.nan)
    d[ocean], _ = tree.query(np.c_[lon[ocean] * scale * np.cos(np.deg2rad(lat[ocean])),
                                   lat[ocean] * scale])
    return d


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
    unexpected = []
    expected = []

    for period in (args.period or sorted(cfg.periods)):
        panels = {}
        for exp in experiments:
            leg = cfg.leg(exp, period)
            sfc = leg.history_dir / f"{leg.mesh}.sfc_update.nc"
            # The first record *inside the analysis window*, not the first file
            # on disk: EXP02's history starts at the integration start, where
            # the SST is still the initial field and the daily update has not
            # been applied yet. Comparing that against another leg's post
            # spin-up record would hide the very thing being checked.
            index = io.select_window(io.history_index(leg.history_dir, verify=1),
                                     leg.analysis_start, leg.analysis_end)
            if len(index) == 0:
                continue
            hist = [index.iloc[0]]
            static = io.read_static(hist[0])
            lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
            landmask = static["landmask"]
            ocean = landmask == 0
            dist = distance_to_land_km(lat, lon, landmask)

            # What the run actually saw: the sst written to history.
            with Dataset(hist[0]) as ds:
                sst_used = np.asarray(ds.variables["sst"][0, :])
            # What init_atmosphere produced from OISST, if this leg has it.
            sst_oisst = None
            if sfc.exists():
                with Dataset(sfc) as ds:
                    sst_oisst = np.asarray(ds.variables["sst"][0, :])

            field = sst_used
            # Cells sitting *exactly* on the OISST land fill are unambiguous
            # contamination — no physical process puts an equatorial Atlantic
            # cell at precisely 273.150 K. `n_below_implausible` is the softer
            # signal: it also catches cells that were partially blended.
            n_fill = int((np.abs(field[ocean] - OISST_LAND_FILL_K) < 1e-3).sum())
            cold = field[ocean] < IMPLAUSIBLE_K
            n_cold = int(cold.sum())
            # The sfc_update file is the *input*; sst_used is what the run
            # applied. They differ when config_sst_update is off, and agreeing
            # when it is on is itself worth recording.
            oisst_fill = (int((np.abs(sst_oisst - OISST_LAND_FILL_K) < 1e-3)[ocean].sum())
                          if sst_oisst is not None else -1)
            row = {
                "experiment": exp, "period": period, "mesh": leg.mesh,
                "sst_update": cfg.experiments[exp]["sst_update"],
                "sfc_update_ocean_cells_at_land_fill": oisst_fill,
                "n_ocean_cells": int(ocean.sum()),
                "n_at_land_fill": n_fill,
                "n_below_implausible": n_cold,
                "pct_below_implausible": round(100.0 * n_cold / ocean.sum(), 2),
                "ocean_mean_K": float(field[ocean].mean()),
                "ocean_min_K": float(field[ocean].min()),
                "cold_median_dist_to_land_km":
                    float(np.median(dist[ocean][cold])) if n_cold else np.nan,
                "cold_max_dist_to_land_km":
                    float(dist[ocean][cold].max()) if n_cold else np.nan,
            }
            for key, site in cfg.sites.items():
                m = mesh.nearest_cells(lat, lon, site.lat, site.lon,
                                       landmask=landmask, ocean_only=True, k=1)[0]
                row[f"sst_at_{key}_K"] = float(field[m.index])
                row[f"dist_to_land_at_{key}_km"] = float(dist[m.index])
            rows.append(row)
            panels[exp] = (lat, lon, field, landmask, dist, row["n_at_land_fill"])
            if n_fill > 0:
                # A run registered with sst_forcing_known_bad is the documented
                # evidence for this very finding, so its contamination is a fact
                # to report, not a reason to fail the pipeline. Anything else is.
                known_bad = bool(cfg.experiments[exp].get("sst_forcing_known_bad"))
                (expected if known_bad else unexpected).append(f"{exp} {period}")

            flag = "  <-- CONTAMINATED" if n_fill else ""
            print(f"[{exp} {period}] ocean SST: mean {row['ocean_mean_K']:.2f} K, "
                  f"min {row['ocean_min_K']:.2f} K, "
                  f"{n_cold} cells (<{IMPLAUSIBLE_K:.0f} K), "
                  f"{n_fill} exactly at the OISST land fill{flag}")
            for key in cfg.sites:
                print(f"    {key}: {row[f'sst_at_{key}_K']:.2f} K "
                      f"({row[f'dist_to_land_at_{key}_km']:.0f} km from land)")

        if not panels:
            continue

        # ---- map -----------------------------------------------------------
        import cartopy.crs as ccrs

        extent = (-46.0, -34.0, -7.0, 0.5)
        fig, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 3.8),
                                 subplot_kw={"projection": ccrs.PlateCarree()},
                                 squeeze=False)
        for ax, (exp, (lat, lon, field, landmask, dist, n_fill)) in zip(
                axes[0], panels.items()):
            tri, idx = mesh.triangulation(lat, lon, extent)
            values = np.where(landmask[idx] == 0, field[idx], np.nan)
            pc = ax.tripcolor(tri, values, cmap="RdYlBu_r", vmin=290, vmax=304,
                              shading="gouraud", transform=ccrs.PlateCarree())
            plotting.coastlines(ax)
            plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
            ax.set_extent(extent, crs=ccrs.PlateCarree())
            title = (f"{exp} — sst_update="
                     f"{cfg.experiments[exp]['sst_update']}"
                     + (f"\n{n_fill} ocean cells at the OISST land fill"
                        if n_fill else "\nno land-fill contamination"))
            ax.set_title(title, fontsize=9, color=plotting.EXPERIMENT_COLORS[exp])
        fig.subplots_adjust(bottom=0.22)
        cax = fig.add_axes([0.30, 0.10, 0.40, 0.035])
        cb = fig.colorbar(pc, cax=cax, orientation="horizontal", extend="both")
        cb.set_label("sea surface temperature seen by the model (K)")
        fig.suptitle(f"SST forcing as used — {cfg.periods[period]['label']}", y=1.02)
        plotting.provenance_footer(
            fig, "scripts/03_selection/check_sst_forcing.py | first history record inside "
                 f"each leg's analysis window | colour floor 290 K: anything below "
                 f"~{IMPLAUSIBLE_K:.0f} K here is not a physical SST for this coast",
            layout=False)
        out = cfg.path("figures", "selection", f"sst_forcing_{period}.png")
        fig.savefig(out)
        plt.close(fig)
        made.append(out)

    if not rows:
        print("no legs to check", file=sys.stderr)
        return 2
    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", "sst_forcing_check.csv")
    df.to_csv(out, index=False)
    for p in made + [out]:
        print(f"-> {p.relative_to(REPO_ROOT)}")

    if expected:
        print("\n" + "-" * 72)
        print("Contamination present, and expected, in: " + ", ".join(expected))
        print("These runs are registered with sst_forcing_known_bad: they are the")
        print("evidence for the OISST coastal land-fill finding and are superseded.")
        print("The gate does not fail on them. See config/experiments.yaml.")
        print("-" * 72)

    if unexpected:
        print("\n" + "=" * 72, file=sys.stderr)
        print("SST FORCING IS CONTAMINATED, UNEXPECTEDLY, in: "
              + ", ".join(unexpected), file=sys.stderr)
        print("Cold cells hug the coastline, which is the signature of the OISST",
              file=sys.stderr)
        print("land mask being blended into coastal ocean cells rather than an",
              file=sys.stderr)
        print("upwelling signal. Any site-level comparison against these runs is",
              file=sys.stderr)
        print("testing the interpolation, not the SST-update hypothesis.",
              file=sys.stderr)
        print("See SCIENTIFIC_NOTES.md, 'Caveats and Limitations'.", file=sys.stderr)
        print("If this run is a deliberately retained bad one, mark it with",
              file=sys.stderr)
        print("sst_forcing_known_bad: true in config/experiments.yaml.",
              file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
