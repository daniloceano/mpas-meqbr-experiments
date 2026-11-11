#!/usr/bin/env python
"""Export lightweight, correctly georeferenced layers for the HTML viewer.

Each PNG is a data-only raster on the same Plate Carrée grid and extent.  The
HTML places it in an SVG coordinate system together with an embedded coastline,
so zoom, pan and cursor coordinates remain geographic rather than merely
enlarging a decorated figure.  Colour limits are fixed per variable across all
experiments and both periods.

Output: results/interactive/meteorological_viewer.json
        results/interactive/layers/*.png
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors                       # noqa: E402
import matplotlib.pyplot as plt                            # noqa: E402
import numpy as np                                         # noqa: E402
import xarray as xr                                        # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import era5, fields, mesh, metrics, plotting  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config       # noqa: E402


EXTENT = (-46.5, -33.5, -7.5, 1.0)
RESOLUTION = 0.04
CURRENT = ["CTL", "EXP01", "EXP02", "EXP03", "EXP04", "EXP05", "EXP06"]
VARIABLES = {
    "wind100_mean": {
        "label": "Vento médio a 100 m", "unit": "m s⁻¹",
        "cmap": plotting.CMAP_SPEED,
        "values": lambda ds: ds["mean_speed_100"].values,
        "mask": None,
    },
    "wpd100_mean": {
        "label": "Densidade de potência eólica a 100 m", "unit": "W m⁻²",
        "cmap": plotting.CMAP_WPD, "values": fields.wind_power_density_field,
        "mask": "ocean",
    },
    "constancy100": {
        "label": "Constância direcional a 100 m",
        "unit": "|vetor médio| / média escalar", "cmap": plotting.CMAP_CONSTANCY,
        "values": lambda ds: ds["constancy_100"].values,
        "mask": None, "limits": (0.5, 1.0),
    },
    "diurnal_amplitude100": {
        "label": "Amplitude diurna a 100 m", "unit": "m s⁻¹",
        "cmap": plotting.CMAP_AMPLITUDE, "values": fields.diurnal_amplitude,
        "mask": None,
    },
    "sst_mean": {
        "label": "Temperatura média da superfície", "unit": "K",
        "cmap": plotting.CMAP_SST, "values": lambda ds: ds["mean_sst"].values,
        "mask": "ocean",
    },
}


ERA5_VARIABLES = ("wind100_mean", "wpd100_mean")
ERA5_NATIVE_DEG = 0.25


def era5_layers(cfg, loaded, scales, lat_grid, lon_grid, layer_dir) -> list[dict]:
    """ERA5 100 m speed and WPD on the viewer lattice, on the MPAS colour scale.

    Same hourly window as the MPAS caches of each period (taken from their
    attributes), same WPD formula as scripts/04_era5/resource_comparison.py
    (0.5 * rho * mean(U^3)), nearest-neighbour onto the 0.04 deg lattice with
    no smoothing. vmin/vmax come from the MPAS layers only, so ERA5 values
    outside that range saturate; the fraction that does is recorded.
    """
    entries = []
    for period in sorted({p for _, p in loaded}):
        refs = [ds for (e, p), ds in loaded.items() if p == period]
        windows = {(ds.attrs["window_start"], ds.attrs["window_end"]) for ds in refs}
        if len(windows) != 1:
            print(f"WARNING: [ERA5 {period}] MPAS caches disagree on the window "
                  f"{sorted(windows)} — ERA5 layer skipped", file=sys.stderr)
            continue
        start, end = windows.pop()
        try:
            ds = era5.open_periods(cfg.era5_periods_dir, period)
        except FileNotFoundError as exc:
            print(f"WARNING: [ERA5 {period}] {exc} — ERA5 layer skipped",
                  file=sys.stderr)
            continue
        ds = ds.sel(time=slice(start, end))
        ds = era5.subset_box(ds, EXTENT[2] - 0.5, EXTENT[3] + 0.5,
                             EXTENT[0] - 0.5, EXTENT[1] + 0.5)
        speed = np.hypot(ds["u100"].values, ds["v100"].values)
        n_hours = int(speed.shape[0])
        values = {
            "wind100_mean": speed.mean(axis=0),
            "wpd100_mean": 0.5 * metrics.AIR_DENSITY * (speed ** 3).mean(axis=0),
        }
        lat_e = ds["latitude"].values
        lon_e = ds["longitude"].values
        ds.close()
        # Nearest ERA5 cell centre for every lattice point (regular grid).
        iy = np.abs(lat_grid[:, None] - lat_e[None, :]).argmin(axis=1)
        ix = np.abs(lon_grid[:, None] - lon_e[None, :]).argmin(axis=1)
        # Ocean mask for WPD: the MPAS landmask of this period's first cache,
        # nearest cell on the same lattice, so both sides of the swipe hide
        # the same land.
        ref = refs[0]
        land = mesh.regrid_to_latlon(
            ref["landmask"].values.astype(float), ref["lat"].values,
            ref["lon"].values, lat_grid, lon_grid, max_distance_km=8.0)
        for variable in ERA5_VARIABLES:
            spec = VARIABLES[variable]
            grid = values[variable][np.ix_(iy, ix)].astype(float)
            if spec["mask"] == "ocean":
                grid = np.where(land == 0, grid, np.nan)
            vmin, vmax = scales[variable]
            finite = grid[np.isfinite(grid)]
            below = float((finite < vmin).mean()) if finite.size else 0.0
            above = float((finite > vmax).mean()) if finite.size else 0.0
            normal = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
            rgba = plotting.get_cmap(spec["cmap"])(normal(grid))
            rgba[..., 3] = np.where(np.isfinite(grid), 0.94, 0.0)
            output = layer_dir / f"{variable}_ERA5_{period}.png"
            plt.imsave(output, rgba, origin="lower")
            entries.append({
                "experiment": "ERA5", "period": period,
                "variable": variable, "variable_label": spec["label"],
                "kind": "georaster", "source": output.relative_to(REPO_ROOT).as_posix(),
                "unit": spec["unit"], "vmin": float(vmin), "vmax": float(vmax),
                "colour_stops": colour_stops(spec["cmap"]),
                "window_start": start, "window_end": end, "n_hours": n_hours,
                "projection": "EPSG:4326 / Plate Carrée", "extent": EXTENT,
                "georeferenced": True, "reference": True,
                "native_resolution_deg": ERA5_NATIVE_DEG,
                "scale_source": "MPAS (CTL–EXP06) only",
                "saturation": {"below_vmin": below, "above_vmax": above},
                "limitation": (
                    "ERA5 0.25° shown by nearest ERA5 cell on the 0.04° lattice "
                    "(no smoothing); colour scale from the MPAS layers only, so "
                    f"{100 * below:.1f}% of cells saturate low and "
                    f"{100 * above:.1f}% saturate high."
                    + (" Land masked with the MPAS landmask." if spec["mask"] == "ocean" else "")),
            })
    return entries


def colour_stops(cmap_name: str) -> list[dict]:
    cmap = plotting.get_cmap(cmap_name)
    return [{"fraction": fraction, "colour": mcolors.to_hex(cmap(fraction))}
            for fraction in np.linspace(0, 1, 9)]


def coastline() -> list[list[list[float]]]:
    """Natural Earth coastline clipped to the viewer extent."""
    import cartopy.io.shapereader as shpreader
    from shapely.geometry import LineString, MultiLineString, box

    path = shpreader.natural_earth(
        resolution="10m", category="physical", name="coastline")
    clip = box(*EXTENT)
    lines = []
    for geometry in shpreader.Reader(path).geometries():
        clipped = geometry.intersection(clip).simplify(0.015)
        parts = ([clipped] if isinstance(clipped, LineString)
                 else list(clipped.geoms) if isinstance(clipped, MultiLineString)
                 else [])
        for part in parts:
            coords = [[round(float(lon), 5), round(float(lat), 5)]
                      for lon, lat in part.coords]
            if len(coords) > 1:
                lines.append(coords)
    return lines


def discover_diagnostic_media(entries: list[dict]) -> None:
    patterns = [
        (REPO_ROOT / "figures" / "animations", re.compile(
            r"wind100_(CTL|EXP01|EXP02|EXP03|EXP04|EXP05|EXP06)_(2021|2022)_(\d{8})_([0-9.]+)d\.(mp4|gif)$"),
         "wind100_animation", "Vento a 100 m — animação", "animation"),
        (REPO_ROOT / "figures" / "animations", re.compile(
            r"xsection_(P0|LPI)_(CTL|EXP01|EXP02|EXP03|EXP04|EXP05|EXP06)_(2021|2022)_(\d{8})_([0-9.]+)d\.(mp4|gif)$"),
         "xsection_animation", "Seção vertical — animação", "animation"),
        (REPO_ROOT / "figures" / "exploration", re.compile(
            r"xsection_(P0|LPI)_(CTL|EXP01|EXP02|EXP03|EXP04|EXP05|EXP06)_(2021|2022)_composite_15local\.png$"),
         "xsection_composite", "Seção vertical — composto 15 h local", "image"),
        (REPO_ROOT / "figures" / "era5", re.compile(
            r"resource_comparison_(CTL|EXP01|EXP02|EXP03|EXP04|EXP05|EXP06)_(2021|2022)\.png$"),
         "resource_vs_era5", "Comparação espacial com ERA5", "image"),
        (REPO_ROOT / "figures" / "exploration", re.compile(
            r"diff_(EXP01|EXP02|EXP03)_vs_CTL_(2021|2022)(?:_common)?\.png$"),
         "difference_vs_ctl", "Diferença espacial em relação ao CTL", "image"),
    ]
    for directory, pattern, variable, label, kind in patterns:
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            match = pattern.match(path.name)
            if not match:
                continue
            groups = match.groups()
            if variable.startswith("xsection"):
                site, experiment, period = groups[:3]
            else:
                site = None
                experiment, period = groups[:2]
            start = groups[2] if variable == "wind100_animation" else (
                groups[3] if variable == "xsection_animation" else None)
            days = groups[3] if variable == "wind100_animation" else (
                groups[4] if variable == "xsection_animation" else None)
            entries.append({
                "experiment": experiment, "period": period,
                "variable": variable, "variable_label": label,
                "kind": kind, "source": path.relative_to(REPO_ROOT).as_posix(),
                "unit": ("m s⁻¹" if variable == "wind100_animation"
                         else "diagnóstico composto"),
                "site": site, "start": start, "days": float(days) if days else None,
                "fps": 6 if kind == "animation" else None,
                "frame_hours": 1 if kind == "animation" else None,
                "georeferenced": False,
                "limitation": (
                    "Mídia diagnóstica pré-renderizada; não permite consulta de "
                    "coordenadas no interior da imagem."),
            })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", nargs="*", default=CURRENT)
    parser.add_argument("--period", nargs="*", default=["2021", "2022"])
    args = parser.parse_args()
    cfg = load_config()
    loaded = {}
    for experiment in args.experiments:
        for period in args.period:
            path = REPO_ROOT / "results" / "fields" / f"{experiment}_{period}_fields.nc"
            if path.exists():
                loaded[(experiment, period)] = xr.open_dataset(path).load()
            else:
                # Never drop an experiment silently: a missing cache once removed
                # EXP03 from every map of the published report (commit 37d2f56).
                print(f"WARNING: [{experiment} {period}] {path.relative_to(REPO_ROOT)} "
                      "not found — experiment/period skipped in the viewer",
                      file=sys.stderr)
    if not loaded:
        print("no field caches found", file=sys.stderr)
        return 1

    scales = {}
    for key, spec in VARIABLES.items():
        if "limits" in spec:
            scales[key] = spec["limits"]
            continue
        values = []
        for dataset in loaded.values():
            if key == "sst_mean" and "mean_sst" not in dataset:
                continue
            value = np.asarray(spec["values"](dataset), dtype=float)
            if spec["mask"] == "ocean":
                value = value[dataset["landmask"].values == 0]
            values.append(value[np.isfinite(value)])
        combined = np.concatenate(values)
        scales[key] = tuple(np.percentile(combined, [1, 99]))

    lon_grid = np.arange(EXTENT[0], EXTENT[1] + 1e-9, RESOLUTION)
    lat_grid = np.arange(EXTENT[2], EXTENT[3] + 1e-9, RESOLUTION)
    layer_dir = REPO_ROOT / "results" / "interactive" / "layers"
    layer_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for (experiment, period), dataset in loaded.items():
        for variable, spec in VARIABLES.items():
            if variable == "sst_mean" and "mean_sst" not in dataset:
                continue
            native = np.asarray(spec["values"](dataset), dtype=float)
            if spec["mask"] == "ocean":
                native = np.where(dataset["landmask"].values == 0, native, np.nan)
            grid = mesh.regrid_to_latlon(
                native, dataset["lat"].values, dataset["lon"].values,
                lat_grid, lon_grid, max_distance_km=8.0)
            vmin, vmax = scales[variable]
            normal = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
            rgba = plotting.get_cmap(spec["cmap"])(normal(grid))
            rgba[..., 3] = np.where(np.isfinite(grid), 0.94, 0.0)
            output = layer_dir / f"{variable}_{experiment}_{period}.png"
            plt.imsave(output, rgba, origin="lower")
            entries.append({
                "experiment": experiment, "period": period,
                "variable": variable, "variable_label": spec["label"],
                "kind": "georaster", "source": output.relative_to(REPO_ROOT).as_posix(),
                "unit": spec["unit"], "vmin": float(vmin), "vmax": float(vmax),
                "colour_stops": colour_stops(spec["cmap"]),
                "window_start": dataset.attrs["window_start"],
                "window_end": dataset.attrs["window_end"],
                "n_hours": int(dataset.attrs["n_hours"]),
                "projection": "EPSG:4326 / Plate Carrée", "extent": EXTENT,
                "georeferenced": True,
                "limitation": (
                    "Nearest-cell display on a 0.04° lattice; blank beyond 8 km "
                    "from a model cell; no temporal interpolation."),
            })

    entries.extend(era5_layers(cfg, loaded, scales, lat_grid, lon_grid, layer_dir))
    discover_diagnostic_media(entries)
    # Old untagged difference figures may coexist with the rigorously matched
    # ``_common`` products.  Keep one product per selector combination and
    # prefer the file whose exact common-hour identity was verified.
    deduplicated = {}
    for entry in entries:
        key = (entry["experiment"], entry["period"], entry["variable"],
               entry.get("site"))
        previous = deduplicated.get(key)
        if previous is None or ("_common" in entry["source"]
                                and "_common" not in previous["source"]):
            deduplicated[key] = entry
    entries = list(deduplicated.values())
    variables = {}
    for entry in entries:
        variables.setdefault(entry["variable"], {
            "label": entry["variable_label"], "unit": entry["unit"],
            "kind": entry["kind"],
        })
    manifest = {
        "schema_version": 1,
        "extent": EXTENT,
        "projection": "EPSG:4326 / Plate Carrée",
        "experiments": args.experiments,
        "references": sorted({e["experiment"] for e in entries if e.get("reference")}),
        "periods": {
            key: {"label": cfg.periods[key]["label"],
                  "start": cfg.periods[key]["analysis_start"],
                  "end": cfg.periods[key]["analysis_end"]}
            for key in args.period
        },
        "variables": variables,
        "coastline": coastline(),
        "entries": entries,
    }
    output = cfg.path("results", "interactive", "meteorological_viewer.json")
    output.write_text(json.dumps(manifest, ensure_ascii=False,
                                 separators=(",", ":")), encoding="utf-8")
    for dataset in loaded.values():
        dataset.close()
    print(f"-> {output.relative_to(REPO_ROOT)} ({len(entries)} products)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
