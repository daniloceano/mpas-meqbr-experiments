#!/usr/bin/env python
"""Secondary validation against public 10 m surface stations.

Read the caveat first. These are **land** stations reporting at **10 m**, and
the project's question is about offshore wind at 50-250 m. A 10 m land
anemometer is affected by local roughness, obstacles and mast siting that no
5 km model resolves, so absolute agreement is not expected and a bias here
should not be carried over to a statement about the offshore resource.

**Split them by type before concluding anything.** The INMET automatic masts and
the airport synoptic stations record mean winds differing by roughly a factor of
two in the same region and the same months — a siting and exposure difference,
not a meteorological one. Pooling the two networks produces a model bias with the
wrong sign. The script prints and writes a by-type table for this reason, and the
map encodes the type in the marker shape.

What they are good for is the thing two point LiDARs cannot do: test the
*horizontal* structure and the *diurnal timing* of the coastal wind over several
hundred kilometres of coast. If a model reproduces the along-coast gradient and
the hour at which the sea breeze arrives at a dozen separate places, that is
meaningful evidence about the circulation, independent of the absolute level.

Model values come from the nearest cell of the same land/sea type as the
station (land stations to land cells), because comparing a land anemometer
against an ocean cell would mostly measure the land-sea contrast.

    python scripts/02_validation/validate_surface_stations.py

Output: results/tables/station_metrics.csv
        figures/validation/stations_map.png
        figures/validation/stations_diurnal.png
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402
import pandas as pd                                        # noqa: E402
from netCDF4 import Dataset                                # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, mesh, metrics, plotting         # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402


def extract_station_series(leg, stations, cfg):
    """10 m model wind at each station's nearest same-surface-type cell."""
    index = io.select_window(io.history_index(leg.history_dir, verify=1),
                             leg.analysis_start, leg.analysis_end)
    if len(index) == 0:
        return None, None
    static = io.read_static(index.iloc[0])
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])
    landmask = static["landmask"]

    cells, meta = [], []
    for st in stations:
        # Stations are on land; match to a land cell so the comparison is not
        # dominated by the land-sea contrast.
        m = mesh.nearest_cells(lat, lon, st["lat"], st["lon"],
                               landmask=1 - landmask, ocean_only=True, k=1)[0]
        cells.append(m.index)
        meta.append({**st, "cell": m.index, "cell_distance_km": m.distance_km})

    u = np.full((len(index), len(cells)), np.nan)
    v = np.full((len(index), len(cells)), np.nan)
    t0 = time.time()
    for i, path in enumerate(index.values):
        with Dataset(path) as ds:
            u[i] = ds.variables["u10"][0, cells]
            v[i] = ds.variables["v10"][0, cells]
        if (i + 1) % 200 == 0:
            print(f"    {i+1}/{len(index)} ({(i+1)/(time.time()-t0):.1f}/s)", flush=True)
    frames = []
    for j, st in enumerate(meta):
        frames.append(pd.DataFrame({
            "time": index.index, "station": st["id"],
            "mod_speed": np.hypot(u[:, j], v[:, j]),
            "mod_dir": (270.0 - np.rad2deg(np.arctan2(v[:, j], u[:, j]))) % 360.0,
        }))
    return pd.concat(frames, ignore_index=True), pd.DataFrame(meta)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()
    experiments = args.experiments or cfg.experiment_keys

    obs_path = REPO_ROOT / "data" / "stations" / "isd_hourly.csv.gz"
    if not obs_path.exists():
        print(f"{obs_path} not found — run scripts/01_extract/fetch_isd_stations.py",
              file=sys.stderr)
        return 1
    # station ids are numeric-looking strings ("81752099999"); without an
    # explicit dtype pandas reads them as int64 and every id comparison against
    # config/sites.yaml silently fails to match.
    obs = pd.read_csv(obs_path, parse_dates=["time"],
                      dtype={"station": str, "period": str})

    rows, diurnal_panels, station_meta = [], {}, None
    for period in (args.period or sorted(cfg.periods)):
        period_obs = obs[obs["period"] == period]
        stations = [s for s in cfg.secondary["stations"]
                    if s["id"] in set(period_obs["station"])]
        if not stations:
            print(f"[{period}] no station data in window")
            continue
        for exp in experiments:
            leg = cfg.leg(exp, period)
            if not leg.exists():
                continue
            print(f"[{exp} {period}] {len(stations)} stations", flush=True)
            model, meta = extract_station_series(leg, stations, cfg)
            if model is None:
                continue
            station_meta = meta if station_meta is None else station_meta
            merged = model.merge(period_obs[["time", "station", "speed", "direction"]],
                                 on=["time", "station"], how="inner")
            for sid, d in merged.groupby("station"):
                st = next(s for s in stations if s["id"] == sid)
                if len(d) < 100:
                    continue
                d = d.sort_values("time")
                s = metrics.basic_scores(d["speed"], d["mod_speed"])
                dc = metrics.diurnal_scores(d["time"], d["speed"], d["mod_speed"])
                rows.append({"experiment": exp, "period": period, "station": sid,
                             "name": st["name"], "kind": st["kind"],
                             "lat": st["lat"], "lon": st["lon"], **s, **dc})
                diurnal_panels.setdefault((period, sid, st["name"]), {})
                diurnal_panels[(period, sid, st["name"])]["obs"] = \
                    metrics.diurnal_composite(d["time"], d["speed"])
                diurnal_panels[(period, sid, st["name"])][exp] = \
                    metrics.diurnal_composite(d["time"], d["mod_speed"])

    if not rows:
        print("no station comparisons produced", file=sys.stderr)
        return 1
    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", "station_metrics.csv")
    df.to_csv(out, index=False)
    print("\n" + df[["experiment", "period", "name", "n", "bias", "rmse", "r",
                     "diurnal_phase_error_h"]].round(2).to_string(index=False))

    # Split by station type before drawing any conclusion. The two networks
    # measure very different mean winds in the same region and months (the
    # INMET automatic masts read about half the airports), which is a siting and
    # exposure difference that a ~5 km cell cannot represent. Pooling them
    # produces a bias with the wrong sign; the well-exposed airports are the
    # meaningful comparison.
    by_kind = df.groupby(["kind", "experiment"])[
        ["obs_mean", "model_mean", "bias", "rmse", "r",
         "diurnal_amp_obs", "diurnal_amp_model", "diurnal_phase_error_h"]].mean()
    print("\nBy station type (do not pool these):")
    print(by_kind.round(2).to_string())
    by_kind.round(3).to_csv(
        cfg.path("results", "tables", "station_metrics_by_kind.csv"))

    # ---- diurnal panels ---------------------------------------------------
    keys = sorted(diurnal_panels)
    ncol = 4
    nrow = int(np.ceil(len(keys) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.1 * ncol, 2.5 * nrow),
                             squeeze=False, sharex=True)
    for ax, key in zip(axes.ravel(), keys):
        period, sid, name = key
        panel = diurnal_panels[key]
        ax.plot(panel["obs"].index, panel["obs"]["mean"], "k-", lw=1.8, label="station")
        for exp in plotting.EXPERIMENT_ORDER:
            if exp in panel:
                ax.plot(panel[exp].index, panel[exp]["mean"], lw=1.2,
                        color=plotting.EXPERIMENT_COLORS[exp], label=exp)
        ax.set_title(f"{name[:26]}\n{cfg.periods[period]['label']}", fontsize=7.5)
        ax.set_xticks([0, 6, 12, 18])
        ax.tick_params(labelsize=7)
    for ax in axes.ravel()[len(keys):]:
        ax.axis("off")
    axes[0][0].legend(fontsize=6.5)
    for ax in axes[-1]:
        ax.set_xlabel("local hour", fontsize=7.5)
    for row in axes:
        row[0].set_ylabel("10 m wind (m s$^{-1}$)", fontsize=7.5)
    fig.suptitle("Coastal diurnal cycle at public surface stations (10 m)", y=1.005)
    plotting.provenance_footer(
        fig, "scripts/02_validation/validate_surface_stations.py | NOAA NCEI ISD "
             "(includes the INMET automatic network) | LAND stations at 10 m: secondary "
             "evidence for the coastal circulation, not for the offshore resource")
    fig_out = cfg.path("figures", "validation", "stations_diurnal.png")
    fig.savefig(fig_out)
    plt.close(fig)

    # ---- map of station bias ----------------------------------------------
    import cartopy.crs as ccrs

    exps = [e for e in plotting.EXPERIMENT_ORDER if e in set(df["experiment"])]
    fig, axes = plt.subplots(1, len(exps), figsize=(4.6 * len(exps), 3.8),
                             subplot_kw={"projection": ccrs.PlateCarree()},
                             squeeze=False)
    vmax = float(np.nanpercentile(np.abs(df["bias"]), 95))
    for ax, exp in zip(axes[0], exps):
        s = df[df["experiment"] == exp]
        # Marker shape encodes the station type, because the two networks are
        # not comparable (see the by-type table).
        for kind, marker in (("inmet_auto", "^"), ("synop_airport", "o")):
            k = s[s["kind"] == kind]
            if k.empty:
                continue
            sc = ax.scatter(k["lon"], k["lat"], c=k["bias"], cmap=plotting.CMAP_DIFF,
                            vmin=-vmax, vmax=vmax, s=80, marker=marker,
                            edgecolor="k", lw=0.5,
                            transform=ccrs.PlateCarree(), zorder=5)
        plotting.coastlines(ax)
        plotting.add_site_markers(ax, cfg.sites, transform=ccrs.PlateCarree())
        ax.set_extent([-46, -34, -7.5, 0.5], crs=ccrs.PlateCarree())
        ax.set_title(exp, color=plotting.EXPERIMENT_COLORS[exp])
    cb = fig.colorbar(sc, ax=axes[0], orientation="horizontal", fraction=0.05, pad=0.05)
    cb.set_label("model - station 10 m wind speed bias (m s$^{-1}$)")
    plotting.provenance_footer(
        fig, "scripts/02_validation/validate_surface_stations.py | one point per station, "
             "pooled over both simulation periods where available | triangles = INMET "
             "automatic masts (sheltered siting, model reads high), circles = airport "
             "synoptic (open exposure, model reads low) | LiDAR sites marked for reference",
        layout=False)
    map_out = cfg.path("figures", "validation", "stations_map.png")
    fig.savefig(map_out)
    plt.close(fig)

    for p in (out, fig_out, map_out):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
