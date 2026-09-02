#!/usr/bin/env python
"""Vertical cross-section across the coast — the sea breeze in the vertical.

The site metrics say whether the wind speed is right at one point; this says
whether the *circulation* producing it has the right shape. A sea breeze has a
specific vertical signature — an onshore layer a few hundred metres deep, a
return flow above it, ascent at the front and a sharp horizontal gradient in
potential temperature at the coast. A model can produce a plausible 100 m wind
speed with none of that structure, and such a model would not be trustworthy at
a different height, a different distance offshore, or a different season.

The transect runs perpendicular to the local coastline through the chosen site,
sampled at the nearest mesh cells. Colours are the transect-normal wind
(positive = onshore); contours are potential temperature; arrows combine the
along-transect and vertical wind, with the vertical component exaggerated
because the aspect ratio of the section is roughly 100:1 and true-scale vertical
arrows would be invisible.

    python scripts/05_exploration/plot_cross_section.py --site P0 --experiment CTL \
        --time 2021-11-15T18:00
    python scripts/05_exploration/plot_cross_section.py --site LPI --experiment EXP01 \
        --time-of-day 15    # composite over the whole period at 15 local

Output: figures/exploration/xsection_<SITE>_<EXP>_<label>.png
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, mesh, plotting, vertical        # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

P0_PA = 100000.0
RD_CP = 0.286
# The coast runs roughly WNW-ESE here, so a transect along a meridian is close
# to coast-normal at P0; at LPI the coast turns, so its transect is rotated.
TRANSECT_HALF_LENGTH_DEG = 1.6
TRANSECT_BEARING = {"P0": 0.0, "LPI": 25.0}   # degrees east of north, offshore-pointing


def transect_endpoints(site, bearing_deg, half_deg):
    b = np.deg2rad(bearing_deg)
    dlat = half_deg * np.cos(b)
    dlon = half_deg * np.sin(b) / max(np.cos(np.deg2rad(site.lat)), 1e-6)
    return ((site.lat - dlat, site.lon - dlon), (site.lat + dlat, site.lon + dlon))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="P0", choices=["P0", "LPI"])
    ap.add_argument("--experiment", default="CTL")
    ap.add_argument("--period", default=None, help="default: the site's own period")
    ap.add_argument("--time", default=None, help="a single instant, e.g. 2021-11-15T18:00")
    ap.add_argument("--time-of-day", type=int, default=None,
                    help="composite over every day at this LOCAL hour (UTC-3)")
    ap.add_argument("--max-height", type=float, default=3000.0)
    ap.add_argument("--w-scale", type=float, default=100.0,
                    help="vertical-wind exaggeration in the arrows")
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    site = cfg.site(args.site)
    period = args.period or site.period
    leg = cfg.leg(args.experiment, period)
    index = io.select_window(io.history_index(leg.history_dir, verify=1),
                             leg.analysis_start, leg.analysis_end)
    if len(index) == 0:
        print(f"[{leg.key}] no history in the analysis window", file=sys.stderr)
        return 1

    if args.time_of_day is not None:
        local = pd.DatetimeIndex(index.index) - pd.Timedelta(hours=3)
        sel = index[local.hour == args.time_of_day]
        label = f"composite_{args.time_of_day:02d}local"
        title_time = (f"composite at {args.time_of_day:02d}:00 local "
                      f"({len(sel)} days)")
    else:
        t = pd.Timestamp(args.time) if args.time else index.index[len(index) // 2]
        nearest = index.index[np.argmin(np.abs(index.index - t))]
        sel = index.loc[[nearest]]
        label = f"{nearest:%Y%m%d_%H}"
        title_time = f"{nearest:%Y-%m-%d %H:%M} UTC ({nearest - pd.Timedelta(hours=3):%H:%M} local)"
    if len(sel) == 0:
        print("no times selected", file=sys.stderr)
        return 1

    static = io.read_static(sel.iloc[0])
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    start, end = transect_endpoints(site, TRANSECT_BEARING[args.site],
                                    TRANSECT_HALF_LENGTH_DEG)
    cells, along = mesh.transect_cells(lat, lon, start, end, n_points=500)
    terrain = static["zgrid"][cells, 0]
    centers = vertical.layer_center_heights(static["zgrid"][cells])   # (n, nLev)
    keep = centers[0] - terrain[0] <= args.max_height
    n_lev = int(keep.sum())

    bearing = np.deg2rad(TRANSECT_BEARING[args.site])
    # The transect is laid out coast-normal, pointing offshore, so the
    # *along-transect* component is the onshore/offshore (sea-breeze) component
    # and the perpendicular one is the along-coast (trade-wind) component.
    along_x, along_y = np.sin(bearing), np.cos(bearing)

    acc = {k: np.zeros((len(cells), n_lev)) for k in ("u", "v", "theta", "w", "pressure")}
    for path in sel.values:
        with Dataset(path) as ds:
            acc["u"] += np.asarray(ds.variables["uReconstructZonal"][0, cells, :n_lev])
            acc["v"] += np.asarray(ds.variables["uReconstructMeridional"][0, cells, :n_lev])
            acc["theta"] += np.asarray(ds.variables["theta"][0, cells, :n_lev])
            acc["pressure"] += np.asarray(ds.variables["pressure"][0, cells, :n_lev])
            w_if = np.asarray(ds.variables["w"][0, cells, :n_lev + 1])
            acc["w"] += 0.5 * (w_if[:, :-1] + w_if[:, 1:])
    for k in acc:
        acc[k] /= len(sel)

    u_cross = acc["u"] * along_x + acc["v"] * along_y      # + offshore
    u_alongcoast = acc["u"] * along_y - acc["v"] * along_x

    z = centers[:, :n_lev]
    x = np.tile(along[:, None], (1, n_lev))

    fig, ax = plt.subplots(figsize=(10, 4.4))
    lim = float(np.nanpercentile(np.abs(u_cross), 99))
    pc = ax.pcolormesh(x, z, u_cross, cmap=plotting.CMAP_DIFF, vmin=-lim, vmax=lim,
                       shading="gouraud")
    cs = ax.contour(x, z, acc["theta"], levels=np.arange(295, 330, 1.0),
                    colors="k", linewidths=0.45, alpha=0.65)
    ax.clabel(cs, fmt="%d", fontsize=6, inline=True)
    ax.fill_between(along, 0, terrain, color="0.35", zorder=5)

    step_x, step_z = max(len(cells) // 32, 1), max(n_lev // 14, 1)
    ax.quiver(x[::step_x, ::step_z], z[::step_x, ::step_z],
              u_cross[::step_x, ::step_z], acc["w"][::step_x, ::step_z] * args.w_scale,
              scale=260, width=0.0022, color="0.15", alpha=0.8, zorder=4)

    ax.axvline(along[len(along) // 2], color="k", ls=":", lw=1.0)
    ax.annotate(args.site, (along[len(along) // 2], args.max_height * 0.94),
                ha="center", fontsize=8,
                bbox=dict(fc="white", ec="0.7", alpha=0.85))
    ax.set_xlabel(f"distance along transect (km), bearing "
                  f"{TRANSECT_BEARING[args.site]:.0f}$\\degree$ (right = offshore)")
    ax.set_ylabel("height (m MSL)")
    ax.set_ylim(0, args.max_height)
    ax.set_xlim(along[0], along[-1])
    cb = fig.colorbar(pc, ax=ax, fraction=0.035, pad=0.015, extend="both")
    cb.set_label("coast-normal wind (m s$^{-1}$, + offshore)")
    ax.text(0.012, 0.94, f"mean along-coast wind: {np.nanmean(u_alongcoast):+.1f} "
            r"m s$^{-1}$", transform=ax.transAxes, fontsize=7,
            bbox=dict(fc="white", ec="0.8", alpha=0.85))
    ax.set_title(f"{args.experiment} — {site.label} — {title_time}",
                 color=plotting.EXPERIMENT_COLORS.get(args.experiment, "k"))
    plotting.provenance_footer(
        fig, f"scripts/05_exploration/plot_cross_section.py | contours: potential "
             f"temperature (K) | arrows: along-transect wind with vertical velocity "
             f"exaggerated {args.w_scale:.0f}x (the section is ~100:1) | terrain is "
             f"the model's own "
             f"({leg.mesh}), not an external DEM")
    out = cfg.path("figures", "exploration",
                   f"xsection_{args.site}_{args.experiment}_{period}_{label}.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"-> {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
