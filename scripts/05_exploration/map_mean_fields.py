#!/usr/bin/env python
"""The resource picture: mean 100 m wind, power density, steadiness, sea breeze.

Four panels per leg, chosen because together they are what a wind-resource
screening actually asks of a model:

**Mean 100 m wind speed** — the first-order resource.
**Wind power density** — the same field cubed, which is what turns into energy.
The cube is accumulated hour by hour rather than taken from the mean speed;
using the cube of the mean understates WPD by 15-30 % for realistic
distributions.
**Directional constancy** — |vector mean| / scalar mean. Near 1 the flow is a
steady trade wind; lower values mean a wind that turns or reverses, which is the
sea breeze's fingerprint and also a siting consideration in its own right.
**Diurnal amplitude** — peak-to-trough of the mean daily cycle in local time.
This is the field a ~31 km reanalysis cannot resolve near the coast and the
clearest visual statement of what the 5 km mesh adds.

Drawn on the native unstructured mesh (Delaunay triangulation of the cell
centres) rather than an interpolated grid, so what is shown is what the model
holds.

    python scripts/05_exploration/map_mean_fields.py [--experiments EXP01]

Output: figures/exploration/mean_fields_<EXP>_<period>.png
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
from mpas_meqbr import fields, mesh, plotting              # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

EXTENT = (-46.5, -33.5, -7.5, 1.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--tag", default="", help="field-file suffix (see compute_field_statistics)")
    ap.add_argument("--extent", nargs=4, type=float, default=None,
                    metavar=("LON0", "LON1", "LAT0", "LAT1"))
    args = ap.parse_args()

    import cartopy.crs as ccrs

    cfg = load_config()
    plotting.use_style()
    extent = tuple(args.extent) if args.extent else EXTENT
    made = []

    for exp in (args.experiments or cfg.experiment_keys):
        for period in (args.period or cfg.experiments[exp]["periods"]):
            suffix = f"_{args.tag}" if args.tag else ""
            path = (REPO_ROOT / "results" / "fields"
                    / f"{exp}_{period}_fields{suffix}.nc")
            if not path.exists():
                print(f"[{exp} {period}] {path.name} not computed — skipping")
                continue
            ds = fields.load_fields(REPO_ROOT, exp, period) if not suffix else \
                __import__("xarray").open_dataset(path)

            lat = ds["lat"].values
            lon = ds["lon"].values
            tri, idx = mesh.triangulation(lat, lon, extent)
            ocean = ds["landmask"].values[idx] == 0

            panels = [
                ("mean 100 m wind speed", ds["mean_speed_100"].values[idx],
                 "m s$^{-1}$", plotting.CMAP_SPEED, None, False),
                ("wind power density at 100 m",
                 fields.wind_power_density_field(ds)[idx], "W m$^{-2}$", "magma", None, True),
                ("directional constancy", ds["constancy_100"].values[idx],
                 "|vector mean| / scalar mean", "cividis", (0.5, 1.0), False),
                ("diurnal amplitude at 100 m", fields.diurnal_amplitude(ds)[idx],
                 "m s$^{-1}$ (peak - trough)", "plasma", None, False),
            ]
            fig, axes = plt.subplots(2, 2, figsize=(11, 8.4),
                                     subplot_kw={"projection": ccrs.PlateCarree()})
            for ax, (title, values, unit, cmap, lims, ocean_only) in zip(axes.ravel(), panels):
                v = np.where(ocean, values, np.nan) if ocean_only else values
                vmin, vmax = lims if lims else (
                    float(np.nanpercentile(v, 1)), float(np.nanpercentile(v, 99)))
                pc = ax.tripcolor(tri, v, cmap=cmap, vmin=vmin, vmax=vmax,
                                  shading="gouraud", transform=ccrs.PlateCarree())
                plotting.coastlines(ax)
                plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
                ax.set_extent(extent, crs=ccrs.PlateCarree())
                ax.set_title(title, fontsize=9)
                cb = fig.colorbar(pc, ax=ax, fraction=0.038, pad=0.02, extend="both")
                cb.set_label(unit, fontsize=7.5)
                cb.ax.tick_params(labelsize=7)
            fig.suptitle(
                f"{exp} — {cfg.periods[period]['label']} "
                f"({ds.attrs['n_hours']} h, {ds.attrs['window_start'][:10]} to "
                f"{ds.attrs['window_end'][:10]})", y=0.98,
                color=plotting.EXPERIMENT_COLORS.get(exp, "k"))
            plotting.provenance_footer(
                fig, "scripts/05_exploration/map_mean_fields.py | native mesh "
                     f"({ds.attrs['mesh']}), Delaunay triangulation of cell centres | "
                     "WPD masked to ocean | diurnal amplitude in local time (UTC-3)",
                layout=False)
            out = cfg.path("figures", "exploration",
                           f"mean_fields_{exp}_{period}{suffix}.png")
            fig.savefig(out)
            plt.close(fig)
            ds.close()
            made.append(out)

    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
