#!/usr/bin/env python
"""Audit EXP06 prescribed SST and prognostic skin temperature.

The effective ocean mask is ``landmask == 0`` from the MPAS history file; a
finite SST value is never used as a surface-type proxy.  Complete local days
(UTC-3) are scanned hourly to separate the daily prescribed-SST update from the
subdaily skin-temperature response.  Five nearest ocean cells at each LiDAR
are also summarized from the standard extracted site caches.

Outputs:
    results/tables/exp06_sst_spatial_summary.csv
    results/tables/exp06_sst_site_cycle.csv
    results/tables/exp06_sst_audit.md
    figures/selection/exp06_sst_audit.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, plotting  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402


VARIABLES = ("sst", "skintemp")
PERCENTILES = (50, 90, 95, 99)


def complete_local_days(index: pd.Series) -> list[tuple[pd.Timestamp, pd.Series]]:
    local = index.index - pd.Timedelta(hours=3)
    frame = pd.DataFrame({"path": index.values, "local_time": local})
    days = []
    for date, group in frame.groupby(frame["local_time"].dt.normalize()):
        group = group.sort_values("local_time")
        if len(group) == 24 and set(group["local_time"].dt.hour) == set(range(24)):
            days.append((pd.Timestamp(date), pd.Series(
                group["path"].values, index=pd.DatetimeIndex(group["local_time"])
            )))
    return days


def summarize_amplitudes(values: np.ndarray, mask: np.ndarray) -> dict:
    selected = values[:, mask].ravel()
    selected = selected[np.isfinite(selected)]
    row = {f"p{p}_K": float(np.percentile(selected, p)) for p in PERCENTILES}
    row.update({
        "mean_K": float(np.mean(selected)),
        "max_K": float(np.max(selected)),
        "fraction_gt_3K": float(np.mean(selected > 3.0)),
        "fraction_gt_5K": float(np.mean(selected > 5.0)),
        "n_cell_days": int(selected.size),
    })
    return row


def scan_period(cfg, period: str) -> tuple[list[dict], dict]:
    leg = cfg.leg("EXP06", period)
    index = io.select_window(
        io.history_index(leg.history_dir), leg.analysis_start, leg.analysis_end
    )
    days = complete_local_days(index)
    if not days:
        raise RuntimeError(f"EXP06/{period}: no complete UTC-3 days")
    static = io.read_static(index.iloc[0], ["landmask", "latCell", "lonCell"])
    landmask = np.asarray(static["landmask"]).squeeze()
    ocean = landmask == 0
    land = landmask != 0
    lon, lat = io.cell_lonlat_degrees(static["latCell"], static["lonCell"])

    amplitudes = {name: [] for name in VARIABLES}
    extrema = {}
    for day_number, (date, paths) in enumerate(days, start=1):
        stacks = {name: [] for name in VARIABLES}
        for path in paths.values:
            fields = io.read_level_map(path, VARIABLES)
            for name in VARIABLES:
                stacks[name].append(np.asarray(fields[name], dtype=np.float32))
        for name in VARIABLES:
            data = np.stack(stacks[name])
            amplitude = np.nanmax(data, axis=0) - np.nanmin(data, axis=0)
            amplitudes[name].append(amplitude.astype(np.float32))
            for surface, mask in (("ocean", ocean), ("land", land)):
                masked = np.where(mask, amplitude, np.nan)
                cell = int(np.nanargmax(masked))
                value = float(masked[cell])
                key = (name, surface)
                if key not in extrema or value > extrema[key]["amplitude_K"]:
                    extrema[key] = {
                        "amplitude_K": value,
                        "date_local": date.strftime("%Y-%m-%d"),
                        "cell_index": cell,
                        "lat": float(lat[cell]),
                        "lon": float(lon[cell]),
                    }
        print(f"EXP06/{period}: {day_number}/{len(days)} complete local days", flush=True)

    rows = []
    arrays = {name: np.stack(items) for name, items in amplitudes.items()}
    for name, values in arrays.items():
        for surface, mask in (("ocean", ocean), ("land", land)):
            rows.append({
                "period": period,
                "variable": name,
                "surface": surface,
                "complete_local_days": len(days),
                **summarize_amplitudes(values, mask),
                **{f"extreme_{key}": value
                   for key, value in extrema[(name, surface)].items()},
            })
    return rows, {"arrays": arrays, "ocean": ocean, "land": land}


def site_cycles(cfg) -> pd.DataFrame:
    rows = []
    for period in sorted(cfg.periods):
        site = cfg.periods[period]["validation_site"]
        path = REPO_ROOT / "results" / "site_timeseries" / f"EXP06_{period}_{site}.nc"
        if not path.exists():
            raise FileNotFoundError(f"missing extracted site cache: {path}")
        with xr.open_dataset(path) as source:
            ds = source[["sst", "skintemp", "cell_index", "cell_distance_km"]].load()
        times = pd.DatetimeIndex(ds["time"].values) - pd.Timedelta(hours=3)
        for cell in range(ds.sizes["cell"]):
            frame = pd.DataFrame({
                "local_hour": times.hour,
                "sst_K": ds["sst"].isel(cell=cell).values,
                "skintemp_K": ds["skintemp"].isel(cell=cell).values,
            })
            cycle = frame.groupby("local_hour").mean()
            for hour, values in cycle.iterrows():
                rows.append({
                    "period": period,
                    "site": site,
                    "cell_rank": cell,
                    "cell_index": int(ds["cell_index"].isel(cell=cell).item()),
                    "distance_km": float(
                        ds["cell_distance_km"].isel(cell=cell).item()
                    ),
                    "local_hour": int(hour),
                    "sst_K": float(values["sst_K"]),
                    "skintemp_K": float(values["skintemp_K"]),
                    "skin_minus_sst_K": float(values["skintemp_K"] - values["sst_K"]),
                })
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    cfg = load_config()
    plotting.use_style()

    rows, diagnostics = [], {}
    for period in sorted(cfg.periods):
        period_rows, period_diagnostics = scan_period(cfg, period)
        rows.extend(period_rows)
        diagnostics[period] = period_diagnostics
    summary = pd.DataFrame(rows)
    summary_out = cfg.path("results", "tables", "exp06_sst_spatial_summary.csv")
    summary.to_csv(summary_out, index=False)

    cycles = site_cycles(cfg)
    cycle_out = cfg.path("results", "tables", "exp06_sst_site_cycle.csv")
    cycles.to_csv(cycle_out, index=False)

    periods = sorted(cfg.periods)
    fig, axes = plt.subplots(2, len(periods), figsize=(6.2 * len(periods), 7.5),
                             squeeze=False)
    for column, period in enumerate(periods):
        ax = axes[0, column]
        arrays = diagnostics[period]["arrays"]
        ocean = diagnostics[period]["ocean"]
        values = [arrays[name][:, ocean].ravel() for name in VARIABLES]
        ax.boxplot(values, tick_labels=["prescribed sst", "skintemp"],
                   showfliers=False, whis=(1, 99))
        ax.set_ylabel("daily amplitude over ocean (K)")
        ax.set_title(f"EXP06/{period}: effective ocean mask")

        ax = axes[1, column]
        subset = cycles[(cycles["period"] == period)]
        site = subset["site"].iloc[0]
        pivot = subset.pivot(index="local_hour", columns="cell_rank",
                             values="skin_minus_sst_K")
        ax.fill_between(pivot.index, pivot.min(axis=1), pivot.max(axis=1),
                        color=plotting.EXPERIMENT_COLORS["EXP06"], alpha=0.18,
                        label="range, 5 nearest ocean cells")
        ax.plot(pivot.index, pivot[0], color=plotting.EXPERIMENT_COLORS["EXP06"],
                lw=2, label="nearest ocean cell")
        ax.axhline(0, color="0.35", lw=0.8)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xlabel("local hour (UTC-3)")
        ax.set_ylabel("skintemp − prescribed sst (K)")
        ax.set_title(f"{site}: mean diurnal skin-temperature anomaly")
        ax.legend(fontsize=7.5)
    plotting.provenance_footer(
        fig,
        "scripts/06_audit/audit_exp06_sst.py | ocean = landmask == 0 | hourly "
        "scan of complete UTC-3 days | site envelope = five nearest ocean cells | "
        "prescribed sst and prognostic skintemp are diagnosed separately",
        layout=False,
    )
    figure_out = cfg.path("figures", "selection", "exp06_sst_audit.png")
    fig.savefig(figure_out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    ocean_skin = summary[
        (summary["variable"] == "skintemp") & (summary["surface"] == "ocean")
    ]
    land_skin = summary[
        (summary["variable"] == "skintemp") & (summary["surface"] == "land")
    ]
    lines = [
        "# EXP06 diurnal SST audit",
        "",
        "Generated by `scripts/06_audit/audit_exp06_sst.py`; do not edit.",
        "",
        "The surface mask is the model `landmask` (`0` = ocean), independent "
        "of SST finiteness. Amplitudes use complete local days (UTC−3).",
        "",
        summary.round(5).to_markdown(index=False),
        "",
        "## Interpretation gate",
        "",
        f"- Maximum ocean `skintemp` daily amplitude: "
        f"{ocean_skin['max_K'].max():.3f} K.",
        f"- Maximum land `skintemp` daily amplitude: "
        f"{land_skin['max_K'].max():.3f} K.",
        "- The earlier approximately 24 K maximum is attributable to land-cell "
        "skin temperature admitted by a finite-SST proxy if the land maximum "
        "reproduces that magnitude; it must not be interpreted as ocean SST.",
        "- `sst` is the prescribed daily field. `skintemp` is the prognostic "
        "surface skin state and carries the subdaily cycle.",
        "- Ocean extremes above 5 K are flagged for scientific review rather "
        "than silently accepted; site series and adjacent cells remain visible "
        "in `exp06_sst_site_cycle.csv`.",
    ]
    markdown_out = cfg.path("results", "tables", "exp06_sst_audit.md")
    markdown_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for output in (summary_out, cycle_out, markdown_out, figure_out):
        print(f"-> {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
