#!/usr/bin/env python
"""Build the compact data bundle used by the interactive validation panel.

The two validation networks remain scientifically separate.  Every comparison
uses identical observation hours across ERA5 and the four current MPAS
experiments.  Confidence intervals use 24 h moving blocks that never bridge an
observational gap.

Outputs:
    results/tables/inmet_added_value.csv
    results/tables/validation_point_metrics.csv
    results/tables/validation_network_summary.csv
    results/interactive/validation_panel.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402


CURRENT = ["CTL", "EXP01", "EXP02", "EXP03"]


def correlation(obs, model) -> float:
    return metrics.basic_scores(obs, model)["r"]


def score_source(times, obs, model, *, reference=None, n_boot=2000,
                 seed=20261018) -> dict:
    statistics = {
        "bias": lambda o, m: float(np.mean(m - o)),
        "rmse": lambda o, m: float(np.sqrt(np.mean((m - o) ** 2))),
        "r": correlation,
    }
    intervals = {
        name: metrics.gap_aware_block_bootstrap_ci(
            times, obs, model, statistic, block_hours=24,
            n_boot=n_boot, seed=seed + offset)
        for offset, (name, statistic) in enumerate(statistics.items())
    }
    out = {
        "n": intervals["rmse"]["n"],
        **{name: interval["value"] for name, interval in intervals.items()},
        **{f"{name}_lo": interval["lo"] for name, interval in intervals.items()},
        **{f"{name}_hi": interval["hi"] for name, interval in intervals.items()},
        "block_hours": 24,
        "n_boot": n_boot,
    }
    if reference is None:
        out.update({
            "rmse_reduction_vs_era5": np.nan, "skill_vs_era5": np.nan,
            "skill_lo": np.nan, "skill_hi": np.nan,
            "significant_vs_era5": False,
        })
    else:
        test = metrics.gap_aware_paired_skill_test(
            times, obs, reference, model, block_hours=24,
            n_boot=n_boot, seed=seed + 10)
        out.update({
            "rmse_reduction_vs_era5": (
                1.0 - test["rmse_model"] / test["rmse_reference"]),
            "skill_vs_era5": test["skill"],
            "skill_lo": test["skill_lo"],
            "skill_hi": test["skill_hi"],
            "significant_vs_era5": test["significant"],
        })
    return out


def build_inmet(cfg, n_boot: int) -> list[dict]:
    path = REPO_ROOT / "results" / "site_timeseries" / "inmet_paired.csv.gz"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; run validate_surface_stations.py first")
    data = pd.read_csv(path, parse_dates=["time"], dtype={"station": str,
                                                            "period": str})
    rows = []
    for (period, station), group in data.groupby(["period", "station"], sort=True):
        metadata = group.iloc[0]
        models = group.pivot(index="time", columns="source", values="model_speed")
        obs = group.groupby("time")["obs_speed"].first()
        common = pd.concat([obs.rename("obs_speed"), models], axis=1).dropna(
            subset=["obs_speed", "ERA5", *CURRENT])
        if len(common) < 72:
            continue
        for source in ["ERA5", *CURRENT]:
            score = score_source(
                common.index, common["obs_speed"], common[source],
                reference=None if source == "ERA5" else common["ERA5"],
                n_boot=n_boot, seed=20261018 + int(period))
            if source == "ERA5":
                score.update({"rmse_reduction_vs_era5": 0.0,
                              "skill_vs_era5": 0.0})
            rows.append({
                "network": "INMET", "point": station,
                "name": metadata["name"], "kind": metadata["kind"],
                "lat": float(metadata["lat"]), "lon": float(metadata["lon"]),
                "period": period, "height_m": 10, "source": source,
                "selection_role": "surface_validation", **score,
            })
    return rows


def build_lidar(cfg, n_boot: int) -> list[dict]:
    rows = []
    for period in sorted(cfg.periods):
        site_key = cfg.periods[period]["validation_site"]
        site = cfg.site(site_key)
        frames = pairing.load_paired(cfg, CURRENT, period, common=True)
        if set(frames) != set(CURRENT):
            continue
        era5 = pairing.add_era5(frames, cfg, period)
        for height in site.model_heights:
            merged = None
            for source in CURRENT:
                piece = frames[source][frames[source]["model_height"] == height][
                    ["time", "obs_speed", "mod_speed"]].rename(
                        columns={"mod_speed": source})
                merged = piece if merged is None else merged.merge(
                    piece.drop(columns="obs_speed"), on="time", how="inner")
            if height == 100 and era5 is not None:
                merged = merged.merge(era5[["time", "era5_speed"]],
                                      on="time", how="inner")
            merged = merged.sort_values("time").dropna(
                subset=["obs_speed", *CURRENT])
            if len(merged) < 72:
                continue
            if height == 100 and "era5_speed" in merged:
                era_score = score_source(
                    merged["time"], merged["obs_speed"], merged["era5_speed"],
                    n_boot=n_boot, seed=20261018 + int(period) + int(height))
                era_score.update({"rmse_reduction_vs_era5": 0.0,
                                  "skill_vs_era5": 0.0})
                rows.append({
                    "network": "LiDAR", "point": site_key, "name": site.label,
                    "kind": "offshore_lidar", "lat": site.lat, "lon": site.lon,
                    "period": period, "height_m": height, "source": "ERA5",
                    "selection_role": "reference_100m", **era_score,
                })
            for source in CURRENT:
                reference = (merged["era5_speed"]
                             if height == 100 and "era5_speed" in merged else None)
                score = score_source(
                    merged["time"], merged["obs_speed"], merged[source],
                    reference=reference, n_boot=n_boot,
                    seed=20261018 + int(period) + int(height))
                rows.append({
                    "network": "LiDAR", "point": site_key, "name": site.label,
                    "kind": "offshore_lidar", "lat": site.lat, "lon": site.lon,
                    "period": period, "height_m": height, "source": source,
                    "selection_role": (
                        "descriptive_only" if site_key == "P0" and height == 250
                        else "selection_height"),
                    **score,
                })
    return rows


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=2000)
    args = parser.parse_args()
    cfg = load_config()
    rows = build_inmet(cfg, args.n_boot) + build_lidar(cfg, args.n_boot)
    if not rows:
        print("no validation points produced", file=sys.stderr)
        return 1
    point_metrics = pd.DataFrame(rows).sort_values(
        ["network", "period", "point", "height_m", "source"], kind="stable")
    point_out = cfg.path("results", "tables", "validation_point_metrics.csv")
    point_metrics.to_csv(point_out, index=False)
    inmet_out = cfg.path("results", "tables", "inmet_added_value.csv")
    point_metrics[point_metrics["network"] == "INMET"].to_csv(
        inmet_out, index=False)

    # Network summaries are deliberately separate and give every station/site
    # the same weight.  LiDAR uses 100 m, the only ERA5-comparable height.
    summary_input = point_metrics[
        (point_metrics["network"] == "INMET")
        | ((point_metrics["network"] == "LiDAR")
           & (point_metrics["height_m"] == 100))]
    summary = summary_input.groupby(["network", "source"], sort=False).agg(
        n_points=("point", "nunique"),
        n_point_periods=("point", "size"),
        paired_hours=("n", "sum"),
        bias=("bias", "mean"), rmse=("rmse", "mean"), r=("r", "mean"),
        rmse_reduction_vs_era5=("rmse_reduction_vs_era5", "mean"),
        skill_vs_era5=("skill_vs_era5", "mean"),
        significant_point_periods=("significant_vs_era5", "sum"),
    ).reset_index()
    summary_out = cfg.path("results", "tables", "validation_network_summary.csv")
    summary.to_csv(summary_out, index=False)

    points = (point_metrics[["network", "point", "name", "kind", "lat", "lon"]]
              .drop_duplicates().to_dict("records"))
    bundle = {
        "schema_version": 1,
        "methods": {
            "pairing": "same observation hours for ERA5 and CTL/EXP01/EXP02/EXP03",
            "confidence_interval": (
                f"95% moving-block bootstrap; 24 h blocks; {args.n_boot} resamples; "
                "blocks never cross data gaps"),
            "networks_combined": False,
            "lidar_250m": (
                "P0 250 m is descriptive only and is excluded from selection tests"),
        },
        "periods": {
            key: {"label": value["label"],
                  "start": value["analysis_start"], "end": value["analysis_end"]}
            for key, value in cfg.periods.items()
        },
        "sources": ["ERA5", *CURRENT],
        "points": points,
        "metrics": point_metrics.to_dict("records"),
        "network_summary": summary.to_dict("records"),
    }
    bundle_out = cfg.path("results", "interactive", "validation_panel.json")
    bundle_out.write_text(json.dumps(json_safe(bundle), ensure_ascii=False,
                                     separators=(",", ":")), encoding="utf-8")
    for output in (inmet_out, point_out, summary_out, bundle_out):
        print(f"-> {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
