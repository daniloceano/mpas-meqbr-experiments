#!/usr/bin/env python
"""Animate a coast-normal MPAS cross-section through a LiDAR site.

The layout follows the cross-section figure used in the EarthSyMS analysis:
colour is air temperature, arrows combine the horizontal wind along the
transect with vertical velocity, and circles/crosses show the sign and
magnitude of the wind perpendicular to the section.  A location inset makes
the transect geometry explicit.

    python scripts/05_exploration/animate_cross_section.py \
        --site P0 --experiment CTL --period 2021 --days 3

Output: figures/animations/xsection_<SITE>_<EXP>_<period>_<start>_<days>d.mp4
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as manim                       # noqa: E402
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402
import pandas as pd                                        # noqa: E402
from netCDF4 import Dataset                                # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, mesh, plotting, vertical        # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

P0_PA = 100000.0
RD_CP = 0.286
TRANSECT_HALF_LENGTH_DEG = 1.6
TRANSECT_BEARING = {"P0": 0.0, "LPI": 25.0}  # degrees east of north, offshore
FFMPEG_CANDIDATES = [
    "/home/danilocs/.conda/envs/cgfd-usp-mpas/bin/ffmpeg",
    "/home/danilocs/.conda/envs/osr11/bin/ffmpeg",
]


def find_ffmpeg(cfg):
    for candidate in [cfg.ffmpeg, shutil.which("ffmpeg"), *FFMPEG_CANDIDATES]:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def transect_endpoints(site, bearing_deg: float, half_deg: float):
    bearing = np.deg2rad(bearing_deg)
    dlat = half_deg * np.cos(bearing)
    dlon = half_deg * np.sin(bearing) / max(np.cos(np.deg2rad(site.lat)), 1e-6)
    return ((site.lat - dlat, site.lon - dlon),
            (site.lat + dlat, site.lon + dlon))


def load_frame(path: Path, cells: np.ndarray, n_levels: int,
               along_x: float, along_y: float) -> dict[str, np.ndarray]:
    with Dataset(path) as ds:
        u = np.asarray(ds.variables["uReconstructZonal"][0, cells, :n_levels])
        v = np.asarray(ds.variables["uReconstructMeridional"][0, cells, :n_levels])
        theta = np.asarray(ds.variables["theta"][0, cells, :n_levels])
        pressure = np.asarray(ds.variables["pressure"][0, cells, :n_levels])
        w_if = np.asarray(ds.variables["w"][0, cells, :n_levels + 1])
    w = 0.5 * (w_if[:, :-1] + w_if[:, 1:])
    temperature_c = theta * (pressure / P0_PA) ** RD_CP - 273.15
    return {
        "temperature_c": temperature_c,
        "along": u * along_x + v * along_y,
        "cross": u * along_y - v * along_x,
        "w": w,
    }


def add_location_inset(ax, site, start, end):
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    inset = ax.inset_axes([0.715, 0.665, 0.255, 0.285],
                          projection=ccrs.PlateCarree(), zorder=20)
    inset.set_facecolor("#cfe8f3")
    inset.add_feature(cfeature.LAND.with_scale("10m"), facecolor="0.75",
                      edgecolor="none", zorder=1)
    inset.coastlines(resolution="10m", linewidth=0.7, color="black", zorder=2)
    inset.plot([start[1], end[1]], [start[0], end[0]], color="black", lw=1.8,
               transform=ccrs.PlateCarree(), zorder=3)
    inset.plot(site.lon, site.lat, marker="*", ms=10, mfc="black", mec="white",
               mew=0.8, transform=ccrs.PlateCarree(), zorder=4)
    margin_lon = 2.1
    margin_lat = 2.1
    inset.set_extent([site.lon - margin_lon, site.lon + margin_lon,
                      site.lat - margin_lat, site.lat + margin_lat],
                     crs=ccrs.PlateCarree())
    inset.set_xticks([])
    inset.set_yticks([])
    return inset


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="P0", choices=["P0", "LPI"])
    ap.add_argument("--experiment", default="CTL")
    ap.add_argument("--period", default=None, help="default: the site's period")
    ap.add_argument("--start", default=None, help="default: analysis-window start")
    ap.add_argument("--days", type=float, default=3.0)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--max-height", type=float, default=1200.0)
    ap.add_argument("--w-scale", type=float, default=100.0)
    ap.add_argument("--fps", type=int, default=6)
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style(scale=1.05)
    site = cfg.site(args.site)
    period = args.period or site.period
    leg = cfg.leg(args.experiment, period)
    index = io.select_window(io.history_index(leg.history_dir, verify=1),
                             leg.analysis_start, leg.analysis_end)
    if len(index) == 0:
        print(f"[{leg.key}] no history in the analysis window", file=sys.stderr)
        return 1
    start_time = pd.Timestamp(args.start) if args.start else index.index[0]
    end_time = start_time + pd.Timedelta(days=args.days)
    index = index.loc[(index.index >= start_time) & (index.index <= end_time)][::args.stride]
    if len(index) < 2:
        print("fewer than two frames in the requested window", file=sys.stderr)
        return 1

    static = io.read_static(index.iloc[0])
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    start, end = transect_endpoints(site, TRANSECT_BEARING[args.site],
                                    TRANSECT_HALF_LENGTH_DEG)
    cells, along = mesh.transect_cells(lat, lon, start, end, n_points=500)
    center_cell = int(np.argmin((lat[cells] - site.lat) ** 2
                                + (lon[cells] - site.lon) ** 2))
    distance = along - along[center_cell]
    terrain = static["zgrid"][cells, 0]
    centers = vertical.layer_center_heights(static["zgrid"][cells])
    n_levels = int(np.sum((centers[center_cell] - terrain[center_cell])
                          <= args.max_height))
    centers = centers[:, :n_levels]
    x = np.tile(distance[:, None], (1, n_levels))

    bearing = np.deg2rad(TRANSECT_BEARING[args.site])
    along_x, along_y = np.sin(bearing), np.cos(bearing)
    print(f"[{leg.key}] loading {len(index)} cross-section frames, "
          f"{len(cells)} columns x {n_levels} levels", flush=True)
    frames = []
    load_start = time.time()
    for i, path in enumerate(index.values):
        frames.append(load_frame(path, cells, n_levels, along_x, along_y))
        if (i + 1) % 24 == 0:
            print(f"    loaded {i + 1}/{len(index)} "
                  f"({(i + 1) / (time.time() - load_start):.1f} frames/s)", flush=True)

    all_temperature = np.concatenate([f["temperature_c"].ravel() for f in frames])
    vmin = float(np.floor(np.nanpercentile(all_temperature, 1)))
    vmax = float(np.ceil(np.nanpercentile(all_temperature, 99)))

    fig, ax = plt.subplots(figsize=(11.4, 6.4))
    pc = ax.pcolormesh(x, centers, frames[0]["temperature_c"], cmap="RdYlBu_r",
                       vmin=vmin, vmax=vmax, shading="gouraud")
    ax.fill_between(distance, 0, terrain, color="0.38", zorder=7)
    ax.axvline(0, color="k", ls=":", lw=1.1, zorder=8)
    ax.text(0, args.max_height * 0.96, args.site, ha="center", va="top",
            fontsize=9, bbox=dict(fc="white", ec="0.6", alpha=0.85, pad=2), zorder=9)

    step_x = max(len(cells) // 26, 1)
    step_z = max(n_levels // 10, 1)
    qx = x[::step_x, ::step_z]
    qz = centers[::step_x, ::step_z]
    quiv = ax.quiver(qx, qz,
                     frames[0]["along"][::step_x, ::step_z],
                     frames[0]["w"][::step_x, ::step_z] * args.w_scale,
                     scale=220, width=0.0022, color="0.12", alpha=0.82, zorder=5)

    marker_x = qx.ravel()
    marker_z = qz.ravel()
    circles = ax.scatter([], [], marker="o", facecolors="none", edgecolors="0.15",
                         linewidths=0.8, zorder=6)
    crosses = ax.scatter([], [], marker="x", c="0.15", linewidths=0.9, zorder=6)

    def update_cross_markers(values):
        values = values[::step_x, ::step_z].ravel()
        positive = values >= 0
        circles.set_offsets(np.column_stack([marker_x[positive], marker_z[positive]]))
        circles.set_sizes(7.0 + 5.0 * np.abs(values[positive]))
        crosses.set_offsets(np.column_stack([marker_x[~positive], marker_z[~positive]]))
        crosses.set_sizes(7.0 + 5.0 * np.abs(values[~positive]))

    update_cross_markers(frames[0]["cross"])
    add_location_inset(ax, site, start, end)
    cb = fig.colorbar(pc, ax=ax, fraction=0.035, pad=0.02, extend="both")
    cb.set_label("Air temperature (°C)")
    ax.set_xlim(distance[0], distance[-1])
    ax.set_ylim(0, args.max_height)
    ax.set_xlabel("Distance from LiDAR along the coast-normal transect (km; right = offshore)")
    ax.set_ylabel("Height above mean sea level (m)")
    title = ax.set_title("")

    def update(frame_number):
        frame = frames[frame_number]
        pc.set_array(frame["temperature_c"].ravel())
        quiv.set_UVC(frame["along"][::step_x, ::step_z],
                     frame["w"][::step_x, ::step_z] * args.w_scale)
        update_cross_markers(frame["cross"])
        utc = index.index[frame_number]
        local = utc - pd.Timedelta(hours=3)
        title.set_text(f"{args.experiment} — {args.site} cross-section — "
                       f"{utc:%Y-%m-%d %H:%M} UTC ({local:%H:%M} local)")
        return pc, quiv, circles, crosses, title

    plotting.provenance_footer(
        fig,
        "scripts/05_exploration/animate_cross_section.py | colour: air temperature | "
        f"arrows: along-section wind + vertical velocity exaggerated {args.w_scale:.0f}x | "
        "circles/crosses: positive/negative cross-section wind, size proportional to "
        "magnitude | transect follows the nearest MPAS cells",
        fontsize=6.5, layout=True)
    animation = manim.FuncAnimation(fig, update, frames=len(frames), blit=False)

    tag = f"{index.index[0]:%Y%m%d}_{args.days:g}d"
    ffmpeg = find_ffmpeg(cfg)
    if ffmpeg:
        matplotlib.rcParams["animation.ffmpeg_path"] = ffmpeg
        output = cfg.path("figures", "animations",
                          f"xsection_{args.site}_{args.experiment}_{period}_{tag}.mp4")
        animation.save(output, writer=manim.FFMpegWriter(fps=args.fps, bitrate=2600))
    else:
        output = cfg.path("figures", "animations",
                          f"xsection_{args.site}_{args.experiment}_{period}_{tag}.gif")
        animation.save(output, writer=manim.PillowWriter(fps=args.fps))
    plt.close(fig)
    print(f"-> {output.relative_to(REPO_ROOT)} ({output.stat().st_size / 1e6:.1f} MB, "
          f"{len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
