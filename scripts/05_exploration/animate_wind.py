#!/usr/bin/env python
"""Animate the 100 m wind field — the fastest way to see what the model is doing.

Statistics compress a month into a number; an animation shows the mechanism.
Over this coast the daily sequence is the whole story: the trade wind offshore,
the sea-breeze front forming in the early afternoon and pushing inland, the
nocturnal land breeze and the low-level jet that follows the boundary layer
decoupling. Any of these being wrong is visible in seconds and invisible in an
RMSE.

Frames are drawn on the native mesh. Rendering is the slow part, so by default
only a few days are animated — enough to see several diurnal cycles — and
`--stride` can thin the frames further.

    python scripts/05_exploration/animate_wind.py --experiment CTL --period 2021 --days 5
    python scripts/05_exploration/animate_wind.py --experiment EXP01 --period 2022 \
        --start 2022-10-10 --days 3 --fps 8

Output: figures/animations/wind100_<EXP>_<period>_<start>_<days>d.mp4  (or .gif)
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

EXTENT = (-46.5, -33.5, -7.5, 1.0)
FFMPEG_CANDIDATES = [
    "/home/danilocs/.conda/envs/cgfd-usp-mpas/bin/ffmpeg",
    "/home/danilocs/.conda/envs/osr11/bin/ffmpeg",
]


def find_ffmpeg(cfg):
    """Locate ffmpeg: config first, then PATH, then the known conda envs."""
    for cand in [cfg.ffmpeg, shutil.which("ffmpeg"), *FFMPEG_CANDIDATES]:
        if cand and Path(cand).exists():
            return cand
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", default="CTL")
    ap.add_argument("--period", default="2021")
    ap.add_argument("--start", default=None, help="default: start of the analysis window")
    ap.add_argument("--days", type=float, default=5.0)
    ap.add_argument("--stride", type=int, default=1, help="use every Nth hour")
    ap.add_argument("--height", type=float, default=100.0)
    ap.add_argument("--fps", type=int, default=6)
    ap.add_argument("--quiver-step", type=int, default=90,
                    help="draw one wind arrow per N cells (higher = sparser)")
    ap.add_argument("--vmax", type=float, default=None)
    args = ap.parse_args()

    import cartopy.crs as ccrs

    cfg = load_config()
    plotting.use_style()
    leg = cfg.leg(args.experiment, args.period)
    index = io.select_window(io.history_index(leg.history_dir, verify=1),
                             leg.analysis_start, leg.analysis_end)
    if len(index) == 0:
        print(f"[{leg.key}] no history in the analysis window", file=sys.stderr)
        return 1

    start = pd.Timestamp(args.start) if args.start else index.index[0]
    end = start + pd.Timedelta(days=args.days)
    index = index.loc[(index.index >= start) & (index.index <= end)][::args.stride]
    if len(index) < 2:
        print("fewer than two frames in the requested window", file=sys.stderr)
        return 1

    static = io.read_static(index.iloc[0])
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    heights = vertical.heights_above_ground(static["zgrid"][0])
    level = int(np.argmin(np.abs(heights - args.height)))
    tri, idx = mesh.triangulation(lat, lon, EXTENT)

    print(f"[{leg.key}] {len(index)} frames, {index.index[0]} -> {index.index[-1]}, "
          f"level {level} ({heights[level]:.1f} m AGL)", flush=True)

    # One pass to load the frames: reading inside the animation callback would
    # make the render time depend on filesystem latency per frame.
    t0 = time.time()
    frames = []
    for i, path in enumerate(index.values):
        with Dataset(path) as ds:
            u = np.asarray(ds.variables["uReconstructZonal"][0, :, level])[idx]
            v = np.asarray(ds.variables["uReconstructMeridional"][0, :, level])[idx]
        frames.append((u, v))
        if (i + 1) % 24 == 0:
            print(f"    loaded {i+1}/{len(index)} "
                  f"({(i+1)/(time.time()-t0):.1f}/s)", flush=True)

    speeds = np.array([np.hypot(u, v) for u, v in frames])
    vmax = args.vmax or float(np.percentile(speeds, 99.5))

    fig, ax = plt.subplots(figsize=(8.6, 5.6),
                           subplot_kw={"projection": ccrs.PlateCarree()})
    pc = ax.tripcolor(tri, np.hypot(*frames[0]), cmap=plotting.CMAP_SPEED,
                      vmin=0, vmax=vmax, shading="gouraud",
                      transform=ccrs.PlateCarree())
    plotting.coastlines(ax)
    plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    cb = fig.colorbar(pc, ax=ax, fraction=0.035, pad=0.02, extend="max")
    cb.set_label(f"{args.height:.0f} m wind speed (m s$^{{-1}}$)")

    q_idx = np.arange(0, len(idx), args.quiver_step)
    quiv = ax.quiver(lon[idx][q_idx], lat[idx][q_idx],
                     frames[0][0][q_idx], frames[0][1][q_idx],
                     scale=350, width=0.0018, color="white", alpha=0.75,
                     transform=ccrs.PlateCarree(), zorder=4)
    title = ax.set_title("")

    def update(i):
        u, v = frames[i]
        pc.set_array(np.hypot(u, v))
        quiv.set_UVC(u[q_idx], v[q_idx])
        t = index.index[i]
        local = t - pd.Timedelta(hours=3)
        title.set_text(f"{args.experiment} — {t:%Y-%m-%d %H:%M} UTC "
                       f"({local:%H:%M} local)")
        return pc, quiv, title

    plotting.provenance_footer(
        fig, f"scripts/05_exploration/animate_wind.py | {leg.mesh}, native mesh | "
             f"arrows every {args.quiver_step} cells | local time = UTC-3", layout=False)
    anim = manim.FuncAnimation(fig, update, frames=len(frames), blit=False)

    tag = f"{index.index[0]:%Y%m%d}_{args.days:g}d"
    ffmpeg = find_ffmpeg(cfg)
    if ffmpeg:
        matplotlib.rcParams["animation.ffmpeg_path"] = ffmpeg
        out = cfg.path("figures", "animations",
                       f"wind{args.height:.0f}_{args.experiment}_{args.period}_{tag}.mp4")
        anim.save(out, writer=manim.FFMpegWriter(fps=args.fps, bitrate=2400))
    else:
        print("ffmpeg not found — falling back to GIF (set `ffmpeg:` in "
              "config/paths.local.yaml for mp4)", file=sys.stderr)
        out = cfg.path("figures", "animations",
                       f"wind{args.height:.0f}_{args.experiment}_{args.period}_{tag}.gif")
        anim.save(out, writer=manim.PillowWriter(fps=args.fps))
    plt.close(fig)
    print(f"-> {out.relative_to(REPO_ROOT)} ({out.stat().st_size/1e6:.1f} MB, "
          f"{len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
