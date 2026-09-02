#!/usr/bin/env python
"""Where in space do the experiments differ, and does the pattern make sense?

Two point measurements cannot show *where* a configuration change acts. These
maps can, and the spatial pattern is what makes an attribution credible: a
change caused by the SST should follow the SST anomaly, and one caused by the
lateral boundary should be organised by distance from that boundary. A
difference that is spatially unstructured is noise, however large it is at a
point.

**Crossing meshes.** EXP02 uses a different mesh, so its cells do not correspond
to EXP01's and the fields cannot be subtracted directly. Both are regridded to a
common 0.05 deg lattice by nearest neighbour — finer than either mesh, so no
smoothing is introduced — and points farther than `--max-distance-km` from any
cell of either mesh are left blank rather than extrapolated.

**Same hours, or nothing.** The script refuses to difference two legs averaged
over different windows. While EXP02 is still integrating, produce the inputs
with `compute_field_statistics.py --window common --tag common` first, and pass
`--tag common` here.

    python scripts/05_exploration/map_experiment_differences.py --period 2021
    python scripts/05_exploration/map_experiment_differences.py --period 2021 --tag common

Output: figures/exploration/diff_<A>_vs_<B>_<period>.png
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402
import xarray as xr                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import fields, mesh, plotting              # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

EXTENT = (-46.5, -33.5, -7.5, 1.0)


def load(exp, period, tag):
    suffix = f"_{tag}" if tag else ""
    path = REPO_ROOT / "results" / "fields" / f"{exp}_{period}_fields{suffix}.nc"
    return xr.open_dataset(path) if path.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--resolution", type=float, default=0.05,
                    help="target lattice spacing in degrees (default 0.05, finer than "
                         "either mesh so the regridding does not smooth)")
    ap.add_argument("--max-distance-km", type=float, default=8.0)
    ap.add_argument("--allow-different-windows", action="store_true",
                    help="override the same-window check (the result is then a "
                         "difference in weather as much as in configuration)")
    args = ap.parse_args()

    import cartopy.crs as ccrs

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys
    lon_t = np.arange(EXTENT[0], EXTENT[1] + 1e-9, args.resolution)
    lat_t = np.arange(EXTENT[2], EXTENT[3] + 1e-9, args.resolution)
    made = []

    for period in (args.period or sorted(cfg.periods)):
        loaded = {e: load(e, period, args.tag) for e in experiments}
        loaded = {e: d for e, d in loaded.items() if d is not None}
        if len(loaded) < 2:
            print(f"[{period}] fewer than two field files — skipping")
            continue

        grids = {}
        for exp, ds in loaded.items():
            grids[exp] = {
                "speed": mesh.regrid_to_latlon(
                    ds["mean_speed_100"].values, ds["lat"].values, ds["lon"].values,
                    lat_t, lon_t, max_distance_km=args.max_distance_km),
                "wpd": mesh.regrid_to_latlon(
                    fields.wind_power_density_field(ds), ds["lat"].values,
                    ds["lon"].values, lat_t, lon_t, max_distance_km=args.max_distance_km),
                "amp": mesh.regrid_to_latlon(
                    fields.diurnal_amplitude(ds), ds["lat"].values, ds["lon"].values,
                    lat_t, lon_t, max_distance_km=args.max_distance_km),
                "sst": mesh.regrid_to_latlon(
                    ds["mean_sst"].values if "mean_sst" in ds
                    else np.full(ds.sizes["nCells"], np.nan),
                    ds["lat"].values, ds["lon"].values, lat_t, lon_t,
                    max_distance_km=args.max_distance_km),
                "land": mesh.regrid_to_latlon(
                    ds["landmask"].values.astype(float), ds["lat"].values,
                    ds["lon"].values, lat_t, lon_t,
                    max_distance_km=args.max_distance_km),
            }

        order = [e for e in plotting.EXPERIMENT_ORDER if e in loaded]
        for a, b in itertools.combinations(order, 2):
            if not args.allow_different_windows:
                try:
                    fields.assert_same_window(loaded[a], loaded[b])
                except ValueError as exc:
                    print(f"[{period}] {a} vs {b}: {exc}")
                    continue

            panels = [
                ("mean 100 m wind speed", "speed", "m s$^{-1}$", None),
                ("wind power density", "wpd", "W m$^{-2}$", None),
                ("diurnal amplitude", "amp", "m s$^{-1}$", None),
                ("sea surface temperature", "sst", "K", "ocean"),
            ]
            fig, axes = plt.subplots(2, 2, figsize=(11, 8.0),
                                     subplot_kw={"projection": ccrs.PlateCarree()})
            for ax, (title, key, unit, maskmode) in zip(axes.ravel(), panels):
                diff = grids[b][key] - grids[a][key]
                if maskmode == "ocean":
                    ocean = (grids[a]["land"] < 0.5) & (grids[b]["land"] < 0.5)
                    diff = np.where(ocean, diff, np.nan)
                if not np.isfinite(diff).any():
                    ax.axis("off")
                    continue
                lim = plotting.symmetric_limits(diff, 99.0)
                pc = ax.pcolormesh(lon_t, lat_t, diff, cmap=plotting.CMAP_DIFF,
                                   vmin=-lim, vmax=lim, shading="auto",
                                   transform=ccrs.PlateCarree())
                plotting.coastlines(ax)
                plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
                ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
                ax.set_title(f"{title}: {b} - {a}", fontsize=9)
                cb = fig.colorbar(pc, ax=ax, fraction=0.038, pad=0.02, extend="both")
                cb.set_label(unit, fontsize=7.5)
                cb.ax.tick_params(labelsize=7)
            delta = cfg.experiments[b]["delta"]
            fig.suptitle(f"{b} - {a} — {cfg.periods[period]['label']}\n"
                         f"{delta[:110]}", y=1.0, fontsize=9)
            plotting.provenance_footer(
                fig, f"scripts/05_exploration/map_experiment_differences.py | both legs "
                     f"regridded to {args.resolution} deg by nearest neighbour, blank "
                     f"beyond {args.max_distance_km:.0f} km from a cell | window "
                     f"{loaded[a].attrs['window_start'][:13]} to "
                     f"{loaded[a].attrs['window_end'][:13]} "
                     f"({loaded[a].attrs['n_hours']} h) | colour limits are the 99th "
                     "percentile of |difference|", layout=False)
            suffix = f"_{args.tag}" if args.tag else ""
            out = cfg.path("figures", "exploration",
                           f"diff_{b}_vs_{a}_{period}{suffix}.png")
            fig.savefig(out)
            plt.close(fig)
            made.append(out)

        for ds in loaded.values():
            ds.close()

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
