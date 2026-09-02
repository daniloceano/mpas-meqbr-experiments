#!/usr/bin/env python
"""Does the boundary treatment act where the theory says it should?

`EXP02`'s only claim is spatial: by ramping the mesh from 5 km to 32 km outward,
it moves the lateral relaxation zone from ~190-230 km from the LiDAR sites to
~600 km, so the model has room to develop its own mesoscale structure before the
flow reaches the area of interest. That claim makes a testable prediction: the
`EXP02 − EXP01` difference should be **organised by distance from `EXP01`'s
relaxation zone** — large near it, decaying inland — and not a uniform offset.

If the difference is unstructured, the buffered mesh changed the answer for some
other reason and the extra 24 % of compute buys nothing attributable.

Distance is measured from the relaxation cells themselves (`bdyMaskCell > 0` in
each mesh's `init.nc`), not from the mesh edge, because the relaxation zone is
several cells wide and it is the relaxation, not the edge, that does the damage.

Both experiments are regridded to a common lattice first; the reference distance
is `EXP01`'s (the tighter mesh), since the hypothesis is about escaping *its*
boundary.

    python scripts/03_selection/boundary_influence.py --period 2021 --tag common

Output: results/tables/boundary_influence.csv
        figures/selection/boundary_influence_<period>.png
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
from netCDF4 import Dataset                                # noqa: E402
from scipy.spatial import cKDTree                          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import fields, io, mesh, plotting          # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

# The whole meqbr_05km footprint, not just the coastal box: the hypothesis is
# about escaping the relaxation zone, so the analysis needs the full range of
# distances from it, including the parts of the domain nobody would map.
EXTENT = (-55.0, -32.5, -7.7, 6.8)
BINS_KM = [0, 50, 100, 200, 300, 500, 10000]


def relaxation_distance_km(leg, lat, lon):
    """Distance from every cell to the nearest lateral-relaxation cell."""
    with Dataset(leg.init_file) as ds:
        bdy = np.asarray(ds.variables["bdyMaskCell"][:])
    relax = np.flatnonzero(bdy > 0)
    if relax.size == 0:
        return np.full(lat.shape, np.inf), 0
    scale = 111.195
    tree = cKDTree(np.c_[lon[relax] * scale * np.cos(np.deg2rad(lat[relax])),
                         lat[relax] * scale])
    d, _ = tree.query(np.c_[lon * scale * np.cos(np.deg2rad(lat)), lat * scale])
    return d, int(relax.size)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", default="2021")
    ap.add_argument("--reference", default="EXP01",
                    help="the experiment whose relaxation zone defines the distance")
    ap.add_argument("--other", default="EXP02")
    ap.add_argument("--tag", default="common")
    ap.add_argument("--resolution", type=float, default=0.05)
    ap.add_argument("--extent", nargs=4, type=float, default=None,
                    metavar=("LON0", "LON1", "LAT0", "LAT1"))
    args = ap.parse_args()

    import cartopy.crs as ccrs

    cfg = load_config()
    plotting.use_style()
    suffix = f"_{args.tag}" if args.tag else ""

    paths = {e: REPO_ROOT / "results" / "fields" / f"{e}_{args.period}_fields{suffix}.nc"
             for e in (args.reference, args.other)}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        print(f"missing field files: {missing}\n"
              "run scripts/01_extract/compute_field_statistics.py "
              f"--period {args.period} --window common --tag common", file=sys.stderr)
        return 1

    dsets = {e: xr.open_dataset(p) for e, p in paths.items()}
    fields.assert_same_window(dsets[args.reference], dsets[args.other])

    # Distance field on the reference mesh, then onto the common lattice.
    ref_leg = cfg.leg(args.reference, args.period)
    ref = dsets[args.reference]
    dist_cells, n_relax = relaxation_distance_km(
        ref_leg, ref["lat"].values, ref["lon"].values)
    print(f"{args.reference}: {n_relax} relaxation cells "
          f"({ref_leg.mesh}); site distances from config: "
          f"{cfg.boundary_distance_km.get(ref_leg.mesh)}")

    extent = tuple(args.extent) if args.extent else EXTENT
    lat_t = np.arange(extent[2], extent[3] + 1e-9, args.resolution)
    lon_t = np.arange(extent[0], extent[1] + 1e-9, args.resolution)
    grid = {}
    for e, ds in dsets.items():
        grid[e] = mesh.regrid_to_latlon(
            ds["mean_speed_100"].values, ds["lat"].values, ds["lon"].values,
            lat_t, lon_t, max_distance_km=8.0)
    dist_grid = mesh.regrid_to_latlon(dist_cells, ref["lat"].values,
                                      ref["lon"].values, lat_t, lon_t,
                                      max_distance_km=8.0)
    diff = grid[args.other] - grid[args.reference]

    ok = np.isfinite(diff) & np.isfinite(dist_grid)
    binned = pd.cut(dist_grid[ok], BINS_KM)
    table = pd.DataFrame({"distance_bin": binned, "diff": diff[ok]}) \
        .groupby("distance_bin", observed=True)["diff"] \
        .agg(["count", "mean", "std",
              lambda s: float(np.mean(np.abs(s)))])
    table.columns = ["n_points", "mean_diff", "sd_diff", "mean_abs_diff"]
    table = table.reset_index()
    table.insert(0, "other", args.other)
    table.insert(0, "reference", args.reference)
    table.insert(0, "period", args.period)
    out = cfg.path("results", "tables", "boundary_influence.csv")
    table.to_csv(out, index=False)
    print("\n" + table.round(3).to_string(index=False))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4),
                             gridspec_kw={"width_ratios": [1.3, 1], "wspace": 0.32})
    ax = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
    axes[0].remove()
    lim = plotting.symmetric_limits(diff, 99)
    pc = ax.pcolormesh(lon_t, lat_t, diff, cmap=plotting.CMAP_DIFF,
                       vmin=-lim, vmax=lim, shading="auto",
                       transform=ccrs.PlateCarree())
    cs = ax.contour(lon_t, lat_t, dist_grid, levels=[100, 200, 300, 600],
                    colors="k", linewidths=0.7, transform=ccrs.PlateCarree())
    ax.clabel(cs, fmt="%d km", fontsize=6)
    plotting.coastlines(ax)
    plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.set_title(f"{args.other} - {args.reference}: mean 100 m wind\n"
                 f"contours = distance from {args.reference}'s relaxation zone",
                 fontsize=9)
    # Horizontal, under the map: a vertical bar here collides with the right
    # panel's y label.
    cb = fig.colorbar(pc, ax=ax, orientation="horizontal", fraction=0.05,
                      pad=0.04, extend="both")
    cb.set_label("mean 100 m wind difference (m s$^{-1}$)", fontsize=8)
    cb.ax.tick_params(labelsize=7)

    ax2 = axes[1]
    centres = [(BINS_KM[i] + min(BINS_KM[i + 1], 1200)) / 2
               for i in range(len(BINS_KM) - 1)]
    ax2.bar(range(len(table)), table["mean_abs_diff"], color="#D62728", width=0.6)
    ax2.set_xticks(range(len(table)))
    ax2.set_xticklabels([str(b) for b in table["distance_bin"]], rotation=35,
                        ha="right", fontsize=7)
    ax2.set_xlabel(f"distance from {args.reference}'s relaxation zone (km)")
    ax2.set_ylabel("mean |difference| (m s$^{-1}$)")
    ax2.set_title("is the difference organised by distance?", fontsize=9)
    for i, (n, v) in enumerate(zip(table["n_points"], table["mean_abs_diff"])):
        ax2.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=6.5)

    fig.suptitle(f"Boundary influence — {cfg.periods[args.period]['label']} "
                 f"({dsets[args.reference].attrs['n_hours']} h)", y=1.02)
    plotting.provenance_footer(
        fig, "scripts/03_selection/boundary_influence.py | distance measured from "
             f"{args.reference}'s relaxation cells (bdyMaskCell > 0), not the mesh edge | "
             "a difference that decays with distance supports the boundary-treatment "
             "hypothesis; a flat one does not", layout=False)
    fig_out = cfg.path("figures", "selection", f"boundary_influence_{args.period}.png")
    fig.savefig(fig_out)
    plt.close(fig)
    for ds in dsets.values():
        ds.close()
    for p in (out, fig_out):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
