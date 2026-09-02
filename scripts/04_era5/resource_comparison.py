#!/usr/bin/env python
"""MPAS against ERA5 as a wind-resource map — what the extra resolution buys.

The site validation answers "is the model right at two points". This answers the
question that actually motivates replacing ERA5 with a regional run: *does the
5 km field contain structure that ERA5 cannot represent, and where?*

Three panels per experiment:

**ERA5** mean 100 m wind over the same hours, on its native ~31 km grid. This is
the current baseline for resource screening on this coast.
**MPAS** the same quantity on the 5 km mesh.
**MPAS - ERA5** the difference, which is the added structure. Expect it to be
organised: stronger near capes and headlands, along the coastal sea-breeze
band, and over terrain — all scales ERA5 smooths away. A difference that is
large but spatially unstructured would instead point at a systematic offset,
not at resolved structure.

A fourth panel places the simulated month against the 1990-2020 ERA5
climatological mean for the same calendar month, so the map can be read as
"resource in this month" rather than "resource, full stop".

Both fields are compared on a common 0.25 deg grid — ERA5's own resolution — so
the difference is "what MPAS says at ERA5's scale plus what it adds", not a
regridding artefact. The unaggregated 5 km field is in
`scripts/05_exploration/map_mean_fields.py`.

    python scripts/04_era5/resource_comparison.py

Output: figures/era5/resource_comparison_<EXP>_<period>.png
        results/tables/resource_comparison.csv
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
from mpas_meqbr import era5, fields, mesh, metrics, plotting   # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT           # noqa: E402

EXTENT = (-46.5, -33.5, -7.5, 1.0)
GRID_DEG = 0.25


def era5_period_means(cfg, period, start, end):
    """Mean 100 m speed and WPD from the ERA5 period file over [start, end]."""
    ds = era5.open_periods(cfg.era5_periods_dir, period)
    ds = ds.sel(time=slice(start, end))
    ds = era5.subset_box(ds, EXTENT[2] - 0.5, EXTENT[3] + 0.5,
                         EXTENT[0] - 0.5, EXTENT[1] + 0.5)
    u, v = ds["u100"].values, ds["v100"].values
    speed = np.hypot(u, v)
    out = {
        "lat": ds["latitude"].values, "lon": ds["longitude"].values,
        "speed": speed.mean(axis=0),
        "wpd": 0.5 * metrics.AIR_DENSITY * (speed ** 3).mean(axis=0),
        "n_hours": speed.shape[0],
    }
    ds.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    import cartopy.crs as ccrs

    cfg = load_config()
    plotting.use_style()
    made, rows = [], []

    clim_path = REPO_ROOT / "results" / "fields" / "era5_climatology_map.nc"
    clim = xr.open_dataset(clim_path) if clim_path.exists() else None

    for exp in (args.experiments or cfg.experiment_keys):
        for period in (args.period or cfg.experiments[exp]["periods"]):
            suffix = f"_{args.tag}" if args.tag else ""
            fpath = REPO_ROOT / "results" / "fields" / f"{exp}_{period}_fields{suffix}.nc"
            if not fpath.exists():
                print(f"[{exp} {period}] {fpath.name} not computed — skipping")
                continue
            mds = xr.open_dataset(fpath)
            e = era5_period_means(cfg, period, mds.attrs["window_start"],
                                  mds.attrs["window_end"])

            # ERA5's own grid is the common grid: regridding MPAS *down* to it
            # is an honest "what would ERA5 have seen"; regridding ERA5 up would
            # invent structure it does not have.
            lat_t = np.arange(EXTENT[2], EXTENT[3] + 1e-9, GRID_DEG)
            lon_t = np.arange(EXTENT[0], EXTENT[1] + 1e-9, GRID_DEG)
            mpas_speed = mesh.regrid_to_latlon(
                mds["mean_speed_100"].values, mds["lat"].values, mds["lon"].values,
                lat_t, lon_t, max_distance_km=20.0)
            mpas_wpd = mesh.regrid_to_latlon(
                fields.wind_power_density_field(mds), mds["lat"].values,
                mds["lon"].values, lat_t, lon_t, max_distance_km=20.0)
            era_speed = xr.DataArray(
                e["speed"], coords={"latitude": e["lat"], "longitude": e["lon"]},
                dims=("latitude", "longitude")).interp(
                    latitude=lat_t, longitude=lon_t).values
            era_wpd = xr.DataArray(
                e["wpd"], coords={"latitude": e["lat"], "longitude": e["lon"]},
                dims=("latitude", "longitude")).interp(
                    latitude=lat_t, longitude=lon_t).values

            ok = np.isfinite(mpas_speed) & np.isfinite(era_speed)
            rows.append({
                "experiment": exp, "period": period,
                "window_start": mds.attrs["window_start"],
                "window_end": mds.attrs["window_end"],
                "n_hours_model": mds.attrs["n_hours"], "n_hours_era5": e["n_hours"],
                "domain_mean_speed_mpas": float(np.nanmean(mpas_speed[ok])),
                "domain_mean_speed_era5": float(np.nanmean(era_speed[ok])),
                "domain_mean_speed_diff": float(np.nanmean((mpas_speed - era_speed)[ok])),
                "domain_mean_wpd_mpas": float(np.nanmean(mpas_wpd[ok])),
                "domain_mean_wpd_era5": float(np.nanmean(era_wpd[ok])),
                "domain_wpd_rel_diff_pct": float(
                    100 * (np.nanmean(mpas_wpd[ok]) - np.nanmean(era_wpd[ok]))
                    / np.nanmean(era_wpd[ok])),
                "spatial_sd_mpas": float(np.nanstd(mpas_speed[ok])),
                "spatial_sd_era5": float(np.nanstd(era_speed[ok])),
            })

            month = pd.Timestamp(cfg.periods[period]["analysis_start"]).month
            has_clim = clim is not None and f"mean_speed_100_m{month:02d}" in clim
            n_panels = 4 if has_clim else 3
            fig, axes = plt.subplots(1, n_panels, figsize=(4.4 * n_panels, 3.9),
                                     subplot_kw={"projection": ccrs.PlateCarree()})
            vmin = float(np.nanpercentile(np.concatenate(
                [era_speed[ok], mpas_speed[ok]]), 2))
            vmax = float(np.nanpercentile(np.concatenate(
                [era_speed[ok], mpas_speed[ok]]), 98))

            for ax, (title, field_, cmap, lims) in zip(axes, [
                    (f"ERA5 ({e['n_hours']} h)", era_speed, plotting.CMAP_SPEED, (vmin, vmax)),
                    (f"{exp} at {GRID_DEG}$\\degree$", mpas_speed, plotting.CMAP_SPEED, (vmin, vmax)),
                    (f"{exp} - ERA5", mpas_speed - era_speed, plotting.CMAP_DIFF, None)]):
                if lims is None:
                    lim = plotting.symmetric_limits(field_, 98)
                    lims = (-lim, lim)
                pc = ax.pcolormesh(lon_t, lat_t, field_, cmap=cmap,
                                   vmin=lims[0], vmax=lims[1], shading="auto",
                                   transform=ccrs.PlateCarree())
                plotting.coastlines(ax)
                plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
                ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
                ax.set_title(title, fontsize=9)
                cb = fig.colorbar(pc, ax=ax, orientation="horizontal",
                                  fraction=0.045, pad=0.04, extend="both")
                cb.set_label("mean 100 m wind (m s$^{-1}$)", fontsize=7)
                cb.ax.tick_params(labelsize=7)

            if has_clim:
                ax = axes[3]
                c = clim[f"mean_speed_100_m{month:02d}"].interp(
                    latitude=lat_t, longitude=lon_t).values
                lim = plotting.symmetric_limits(era_speed - c, 98)
                pc = ax.pcolormesh(lon_t, lat_t, era_speed - c,
                                   cmap=plotting.CMAP_DIFF, vmin=-lim, vmax=lim,
                                   shading="auto", transform=ccrs.PlateCarree())
                plotting.coastlines(ax)
                plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
                ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
                ax.set_title(f"this month - ERA5 {clim.attrs['years']} mean", fontsize=9)
                cb = fig.colorbar(pc, ax=ax, orientation="horizontal",
                                  fraction=0.045, pad=0.04, extend="both")
                cb.set_label("anomaly (m s$^{-1}$)", fontsize=7)
                cb.ax.tick_params(labelsize=7)

            fig.suptitle(f"{exp} vs ERA5 — {cfg.periods[period]['label']} "
                         f"({mds.attrs['window_start'][:10]} to "
                         f"{mds.attrs['window_end'][:10]})", y=1.02,
                         color=plotting.EXPERIMENT_COLORS.get(exp, "k"))
            plotting.provenance_footer(
                fig, f"scripts/04_era5/resource_comparison.py | MPAS regridded down to "
                     f"{GRID_DEG}$\\degree$ (ERA5's own grid) so the difference is not a "
                     "regridding artefact | the full 5 km field is in "
                     "figures/exploration/mean_fields_*.png", layout=False)
            out = cfg.path("figures", "era5",
                           f"resource_comparison_{exp}_{period}{suffix}.png")
            fig.savefig(out)
            plt.close(fig)
            mds.close()
            made.append(out)

    if clim is not None:
        clim.close()
    if rows:
        df = pd.DataFrame(rows)
        out = cfg.path("results", "tables", "resource_comparison.csv")
        df.to_csv(out, index=False)
        print(df.round(2).to_string(index=False))
        print(f"-> {out.relative_to(REPO_ROOT)}")
    for p in made:
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main())
