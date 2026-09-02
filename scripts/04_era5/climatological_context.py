#!/usr/bin/env python
"""How typical were the two simulated months? — and the ERA5 baseline resource.

Both questions come from the same 1990-2020 ERA5 archive, and both matter for
what the experiment ranking is allowed to claim.

**Representativeness.** The whole experiment set rests on one month per site. If
November 2021 happened to sit in the tail of the November distribution — an
unusually weak or strong trade-wind month — then a configuration tuned to it may
not be the right choice for a multi-year run. Placing each simulated month's
mean 100 m wind against the 31-year distribution of the same calendar month puts
a number on that risk instead of leaving it as an unstated hope. The comparison
is ERA5-against-ERA5, so it is unaffected by any model bias.

**Baseline resource.** The same archive gives the mean 100 m wind and wind power
density that ERA5 currently implies for this coast — the reference an MPAS-based
resource map would be proposed as an improvement on.

The archive stops at 2020, so the simulated months themselves come from the
ERA5 files downloaded for the simulation periods
(`scripts/01_extract/download_era5_periods.py`). Same product, same variables.

    python scripts/04_era5/climatological_context.py                 # target months only
    python scripts/04_era5/climatological_context.py --months all    # + seasonal cycle

Output: results/tables/era5_climatology_sites.csv
        results/fields/era5_climatology_map.nc
        figures/era5/climatological_context.png
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
import xarray as xr                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import era5, metrics, plotting             # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

MAP_BOX = dict(lat_min=-8.0, lat_max=1.0, lon_min=-46.0, lon_max=-34.0)
CLIM_YEARS = range(1990, 2021)
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", default="target",
                    help="'target' (the simulated calendar months only), 'all', "
                         "or a comma-separated list such as 9,10,11")
    ap.add_argument("--years", default=None, help="e.g. 1991-2020 (default 1990-2020)")
    args = ap.parse_args()

    cfg = load_config()
    plotting.use_style()

    # Which calendar month does each simulated period fall in?
    target_months = {}
    for period, meta in cfg.periods.items():
        target_months[period] = pd.Timestamp(meta["analysis_start"]).month

    if args.months == "target":
        months = sorted(set(target_months.values()))
    elif args.months == "all":
        months = list(range(1, 13))
    else:
        months = [int(m) for m in args.months.split(",")]

    years = list(CLIM_YEARS)
    if args.years:
        a, b = args.years.split("-")
        years = list(range(int(a), int(b) + 1))

    clim_dir = cfg.era5_climatology_dir
    if not clim_dir.is_dir():
        print(f"ERA5 climatology archive not found: {clim_dir}", file=sys.stderr)
        return 1

    rows = []
    map_accum, map_count = {}, {}
    t0 = time.time()
    n_files = 0
    for year in years:
        for month in months:
            path = clim_dir / f"ERA5_surface_wind_data_Brazil_{year}_{month:02d}.nc"
            if not path.exists():
                continue
            with xr.open_dataset(path) as ds:
                ds = era5._standardise(ds)
                for key, site in cfg.sites.items():
                    pt = ds[["u100", "v100", "u10", "v10"]].interp(
                        latitude=site.lat, longitude=site.lon).load()
                    speed = np.hypot(pt["u100"].values, pt["v100"].values)
                    rows.append({
                        "site": key, "year": year, "month": month,
                        "mean_speed_100": float(np.nanmean(speed)),
                        "wpd_100": metrics.wind_power_density(speed),
                        "p90_speed_100": float(np.nanpercentile(speed, 90)),
                        "n_hours": int(speed.size),
                        "source": "ERA5 archive 1990-2020",
                    })
                # Regional maps, accumulated only for the simulated months.
                if month in set(target_months.values()):
                    sub = era5.subset_box(ds[["u100", "v100"]], **MAP_BOX).load()
                    s = np.hypot(sub["u100"].values, sub["v100"].values)
                    acc = map_accum.setdefault(month, {
                        "speed": np.zeros(s.shape[1:]), "cube": np.zeros(s.shape[1:]),
                        "lat": sub["latitude"].values, "lon": sub["longitude"].values})
                    acc["speed"] += s.mean(axis=0)
                    acc["cube"] += (s ** 3).mean(axis=0)
                    map_count[month] = map_count.get(month, 0) + 1
            n_files += 1
            if n_files % 20 == 0:
                rate = n_files / (time.time() - t0)
                print(f"  {n_files} files ({rate:.1f}/s)", flush=True)

    if not rows:
        print("no climatology files read", file=sys.stderr)
        return 1

    # The simulated months themselves, from the period downloads.
    for period, meta in cfg.periods.items():
        try:
            ds = era5.open_periods(cfg.era5_periods_dir, period)
        except FileNotFoundError:
            continue
        ds = ds.sel(time=slice(meta["analysis_start"], meta["analysis_end"]))
        for key, site in cfg.sites.items():
            pt = ds[["u100", "v100"]].interp(latitude=site.lat, longitude=site.lon).load()
            speed = np.hypot(pt["u100"].values, pt["v100"].values)
            rows.append({
                "site": key, "year": pd.Timestamp(meta["analysis_start"]).year,
                "month": target_months[period],
                "mean_speed_100": float(np.nanmean(speed)),
                "wpd_100": metrics.wind_power_density(speed),
                "p90_speed_100": float(np.nanpercentile(speed, 90)),
                "n_hours": int(speed.size),
                "source": f"simulated period {period}",
            })
        ds.close()

    df = pd.DataFrame(rows)
    out = cfg.path("results", "tables", "era5_climatology_sites.csv")
    df.to_csv(out, index=False)

    # ---- percentile of each simulated month ------------------------------
    verdicts = []
    for period, month in target_months.items():
        site_key = cfg.periods[period]["validation_site"]
        sim_year = pd.Timestamp(cfg.periods[period]["analysis_start"]).year
        hist = df[(df["site"] == site_key) & (df["month"] == month)
                  & (df["source"] == "ERA5 archive 1990-2020")]
        sim = df[(df["site"] == site_key) & (df["month"] == month)
                 & (df["source"] == f"simulated period {period}")]
        if hist.empty or sim.empty:
            continue
        value = float(sim["mean_speed_100"].iloc[0])
        pct = float((hist["mean_speed_100"] < value).mean() * 100)
        wpd_value = float(sim["wpd_100"].iloc[0])
        wpd_pct = float((hist["wpd_100"] < wpd_value).mean() * 100)
        verdicts.append({
            "period": period, "site": site_key, "month": MONTH_NAMES[month - 1],
            "sim_year": sim_year, "n_climatology_years": int(len(hist)),
            "sim_mean_speed_100": round(value, 3),
            "clim_mean_speed_100": round(float(hist["mean_speed_100"].mean()), 3),
            "clim_sd_speed_100": round(float(hist["mean_speed_100"].std()), 3),
            "percentile_speed": round(pct, 1),
            "percentile_wpd": round(wpd_pct, 1),
            "z_score_speed": round((value - hist["mean_speed_100"].mean())
                                   / hist["mean_speed_100"].std(), 2),
        })
    vdf = pd.DataFrame(verdicts)
    if len(vdf):
        print("\n" + vdf.to_string(index=False))
        vout = cfg.path("results", "tables", "era5_month_representativeness.csv")
        vdf.to_csv(vout, index=False)
        print(f"-> {vout.relative_to(REPO_ROOT)}")

    # ---- climatological maps ---------------------------------------------
    if map_accum:
        data = {}
        coords = None
        for month, acc in map_accum.items():
            n = map_count[month]
            data[f"mean_speed_100_m{month:02d}"] = (("latitude", "longitude"),
                                                    acc["speed"] / n)
            data[f"wpd_100_m{month:02d}"] = (("latitude", "longitude"),
                                             0.5 * metrics.AIR_DENSITY * acc["cube"] / n)
            coords = {"latitude": acc["lat"], "longitude": acc["lon"]}
        clim_map = xr.Dataset(data, coords=coords)
        clim_map.attrs.update({
            "source": "ERA5 hourly 100 m wind, monthly files",
            "years": f"{years[0]}-{years[-1]}",
            "months": ",".join(str(m) for m in sorted(map_accum)),
            "note": "climatological monthly means; wpd = 0.5*rho*mean(U^3), rho=1.15",
            "created_by": "scripts/04_era5/climatological_context.py",
        })
        map_out = cfg.path("results", "fields", "era5_climatology_map.nc")
        clim_map.to_netcdf(map_out)
        print(f"-> {map_out.relative_to(REPO_ROOT)}")

    # ---- figure -----------------------------------------------------------
    sites = list(cfg.sites)
    has_seasonal = df["month"].nunique() > 2
    ncol = 2 if has_seasonal else 1
    fig, axes = plt.subplots(len(sites), ncol,
                             figsize=(5.2 * ncol, 3.2 * len(sites)), squeeze=False)
    for i, key in enumerate(sites):
        period = cfg.site(key).period
        month = target_months[period]
        sim_year = pd.Timestamp(cfg.periods[period]["analysis_start"]).year
        hist = df[(df["site"] == key) & (df["month"] == month)
                  & (df["source"] == "ERA5 archive 1990-2020")].sort_values("year")
        sim = df[(df["site"] == key) & (df["source"] == f"simulated period {period}")]

        ax = axes[i][0]
        ax.bar(hist["year"], hist["mean_speed_100"], color="0.78", width=0.75)
        ax.axhline(hist["mean_speed_100"].mean(), color="0.35", lw=1.0,
                   label=f"1990-2020 mean ({hist['mean_speed_100'].mean():.2f} m/s)")
        if len(sim):
            v = float(sim["mean_speed_100"].iloc[0])
            ax.bar([sim_year], [v], color="#D62728", width=0.75,
                   label=f"{MONTH_NAMES[month-1]} {sim_year} ({v:.2f} m/s)")
            pct = (hist["mean_speed_100"] < v).mean() * 100
            ax.text(0.02, 0.95, f"{pct:.0f}th percentile of {len(hist)} years",
                    transform=ax.transAxes, va="top", fontsize=8,
                    bbox=dict(fc="white", ec="0.8", alpha=0.85))
        ax.set_ylabel("mean 100 m wind (m s$^{-1}$)")
        ax.set_title(f"{key} — {MONTH_NAMES[month-1]} monthly means")
        ax.legend(fontsize=7, loc="lower right")
        ax.set_ylim(bottom=max(0, hist["mean_speed_100"].min() - 1.5))

        if has_seasonal:
            ax = axes[i][1]
            seasonal = df[(df["site"] == key)
                          & (df["source"] == "ERA5 archive 1990-2020")]
            g = seasonal.groupby("month")["mean_speed_100"]
            ax.fill_between(g.mean().index, g.mean() - g.std(), g.mean() + g.std(),
                            color="0.85", lw=0)
            ax.plot(g.mean().index, g.mean().values, "ko-", ms=4)
            ax.axvline(month, color="#D62728", lw=1.2, ls="--",
                       label=f"simulated month ({MONTH_NAMES[month-1]})")
            ax.set_xticks(range(1, 13))
            ax.set_xticklabels(MONTH_NAMES, fontsize=7)
            ax.set_title(f"{key} — seasonal cycle, 1990-2020")
            ax.legend(fontsize=7)
    fig.suptitle("How typical were the simulated months? (ERA5 100 m wind)", y=1.01)
    plotting.provenance_footer(
        fig, "scripts/04_era5/climatological_context.py | ERA5 vs ERA5, so unaffected by "
             "model bias | a month far from the climatological mean limits how far the "
             "experiment ranking generalises to a multi-year run")
    fig_out = cfg.path("figures", "era5", "climatological_context.png")
    fig.savefig(fig_out)
    plt.close(fig)
    for p in (out, fig_out):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
