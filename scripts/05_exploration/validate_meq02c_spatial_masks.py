#!/usr/bin/env python3
"""MEQ-02C/2A: validate comparison masks on the real MPAS meshes.

This is a geometry-only diagnostic.  It reads compact transports containing
grid geometry plus a stable native landmask; no meteorological output, init,
LBC, or post-processed field is opened.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
import pyogrio
from shapely.geometry import box
from shapely.ops import transform as transform_geometry, unary_union
import shapely


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.mpas_meqbr.spatial import (  # noqa: E402
    EARTH_RADIUS_M,
    MeshGeometry,
    build_comparison_masks,
    classify_destination_surface,
    compare_native_surface,
    domain_polygon_from_edges,
    equal_area_grid,
    equivalent_spacing_km,
    file_sha256,
)


REMOTE_GRID_METADATA = {
    "ctl": {
        "grid_path": "/p1-swell/danilocs/MPAS-Research/grids/meqbr_05km/meqbr_05km.grid.nc",
        "grid_sha256": "0d2242b369c5361c9c9319fdc5d3a366910c4e8307e096396853799c56e0ccfa",
        "static_path": "/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km/meqbr_05km.static.nc",
        "static_sha256": "bc0ed5eca0844750678e2c7201f0aadc6b9a1f80221bd4eebeb631625e039e41",
        "n_cells": 76813,
    },
    "exp02": {
        "grid_path": "/p1-swell/danilocs/MPAS-Research/grids/meqbr_05km_buf/meqbr_05km_buf.grid.nc",
        "grid_sha256": "e618a45e058936c14e0b5058d61afe8a1bb4708d5e116c265d0ee8020e85aa74",
        "static_path": "/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km/meqbr_05km_buf.static.nc",
        "static_sha256": "8d3bc40e4762aa09f535c53f26889231e8bcb3c1b7d08b00ff6b1b22436c128f",
        "n_cells": 95138,
    },
    "oval": {
        "grid_path": "/p1-swell/danilocs/MPAS-Research/grids/meqbr_05km_oval_meq02a/meqbr_05km_oval_meq02a.grid.nc",
        "grid_sha256": "ac3e6988dbd7b1d7fff30689393cc7e06e0652ce8e8aea5edd6099222338e271",
        "static_path": "/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meqbr_05km_oval_meq02a.static.nc",
        "static_sha256": "1dbb7c35aad03b4e0b9d497f52260298e6e1c18205538ae59062cc8582e9d8f7",
        "n_cells": 102968,
    },
}

EXPECTED_TRANSPORT_HASHES = {
    "ctl": "f1ffb705307d7fcba3f54307adff307e8cd90534a7544a5263893526513f05e4",
    "exp02": "73aaadf7e20fa335ff7e440620168fbf61a7e2a0f3708404704e9898875397b7",
    "oval": "d3e70e75c127d0938754d5e39d5d5a1ef67bb70d3f7bf770194d40b8a1d9cfdb",
}

NE_METADATA = {
    "dataset": "Natural Earth 1:10m Physical - Land",
    "version": "5.1.1",
    "url": "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip",
    "crs": "EPSG:4326",
    "official_object_last_modified": "2022-05-13",
    "official_object_etag": "be3001f37196d2894e17aacd13ff2cc2",
    "component_sha256": {
        "ne_10m_land.cpg": "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
        "ne_10m_land.dbf": "e422520372e65c6fb8220888580e5331d04699bcd71c27e53ad42e241a531cbd",
        "ne_10m_land.prj": "a02a27b1d1982c8516d83398e85a3c8b1aef1713c13ef4d84d7bde17430c07c4",
        "ne_10m_land.shp": "4cad3a49bc75c1a4c2f3d7efae04f2f8e63151c96764b2658effabf524331fa6",
        "ne_10m_land.shx": "f3b02a190c3020eeafd0f48de982619826b57ecd853cbc68e4fc049652891a04",
    },
}

DOMAIN_SPECS = {
    "A_all_experiments": ("CTL", "EXP01", "EXP02", "EXP03"),
    "B_oval_exp02": ("EXP03", "EXP02"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry-dir", type=Path, required=True)
    parser.add_argument(
        "--land-shapefile", type=Path,
        default=Path.home() / ".local/share/cartopy/shapefiles/natural_earth/physical/ne_10m_land.shp",
    )
    parser.add_argument(
        "--results-dir", type=Path,
        default=REPO_ROOT / "results/diagnostics/meq02c_2a",
    )
    parser.add_argument(
        "--figures-dir", type=Path,
        default=REPO_ROOT / "figures/exploratory/meq02c_2a",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return result.stdout.strip()


def load_mesh(path: Path, key: str, name: str) -> MeshGeometry:
    expected_hash = EXPECTED_TRANSPORT_HASHES[key]
    actual_hash = file_sha256(path)
    if actual_hash != expected_hash:
        raise ValueError(f"{path}: transport SHA-256 {actual_hash} != {expected_hash}")
    with np.load(path) as data:
        required = {
            "latCell", "lonCell", "areaCell", "latVertex", "lonVertex",
            "verticesOnEdge", "cellsOnEdge", "bdyMaskCell", "landmask",
        }
        missing = required.difference(data.files)
        if missing:
            raise ValueError(f"{path}: missing arrays {sorted(missing)}")
        n_cells = data["latCell"].size
        if n_cells != REMOTE_GRID_METADATA[key]["n_cells"]:
            raise ValueError(f"{path}: nCells={n_cells}")
        domain = domain_polygon_from_edges(
            data["latVertex"], data["lonVertex"], data["verticesOnEdge"],
            data["cellsOnEdge"],
        )
        return MeshGeometry(
            name=name,
            source_path=Path(REMOTE_GRID_METADATA[key]["grid_path"]),
            source_sha256=REMOTE_GRID_METADATA[key]["grid_sha256"],
            lon=(np.degrees(data["lonCell"]) + 180.0) % 360.0 - 180.0,
            lat=np.degrees(data["latCell"]),
            spacing_km=equivalent_spacing_km(data["areaCell"]),
            bdy_mask=np.asarray(data["bdyMaskCell"], dtype=np.int16),
            domain=domain,
            native_landmask=np.asarray(data["landmask"], dtype=np.int8),
        )


def load_land_geometry(path: Path, study_bounds: tuple[float, float, float, float]):
    if not path.exists():
        raise FileNotFoundError(path)
    for suffix, expected in NE_METADATA["component_sha256"].items():
        component = path.with_suffix(Path(suffix).suffix)
        actual = file_sha256(component)
        if actual != expected:
            raise ValueError(f"{component}: SHA-256 {actual} != {expected}")
    clip_box = box(*study_bounds).buffer(2.0)
    frame = pyogrio.read_dataframe(path, bbox=clip_box.bounds, read_geometry=True)
    pieces = [geometry.intersection(clip_box) for geometry in frame.geometry
              if geometry is not None and not geometry.is_empty]
    if not pieces:
        raise ValueError("Natural Earth land has no geometry in study bounds")
    land = unary_union(pieces)
    return land.buffer(0) if not land.is_valid else land


def local_laea(geometry):
    centre = geometry.centroid
    crs = CRS.from_proj4(
        f"+proj=laea +lat_0={centre.y} +lon_0={centre.x} "
        "+datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return crs, forward, transform_geometry(forward.transform, geometry)


def geometry_area_km2(geometry) -> float:
    return float(local_laea(geometry)[2].area / 1_000_000.0)


def boundary_is_closed(geometry) -> bool:
    polygons = getattr(geometry, "geoms", [geometry])
    return all(
        polygon.exterior.is_ring
        and all(interior.is_ring for interior in polygon.interiors)
        for polygon in polygons
    )


def unit_xyz(lon, lat) -> np.ndarray:
    lon_rad = np.radians(np.asarray(lon, dtype=float))
    lat_rad = np.radians(np.asarray(lat, dtype=float))
    return np.column_stack((
        np.cos(lat_rad) * np.cos(lon_rad),
        np.cos(lat_rad) * np.sin(lon_rad),
        np.sin(lat_rad),
    ))


def nearest_distance_km(source_lon, source_lat, target_lon, target_lat) -> np.ndarray:
    tree = cKDTree(unit_xyz(source_lon, source_lat))
    chord, _ = tree.query(unit_xyz(np.ravel(target_lon), np.ravel(target_lat)), k=1)
    arc = 2.0 * np.arcsin(np.minimum(np.asarray(chord) / 2.0, 1.0))
    return (arc * EARTH_RADIUS_M / 1000.0).reshape(np.shape(target_lon))


def relaxation_boundary_metrics(mesh: MeshGeometry) -> dict:
    flagged = mesh.bdy_mask > 0
    _, forward, projected_domain = local_laea(mesh.domain)
    x, y = forward.transform(mesh.lon[flagged], mesh.lat[flagged])
    distances = np.asarray(
        shapely.distance(projected_domain.boundary, shapely.points(x, y)),
        dtype=float,
    ) / 1000.0
    levels, counts = np.unique(mesh.bdy_mask[flagged], return_counts=True)
    return {
        "experiment": mesh.name,
        "n_cells": mesh.n_cells,
        "n_relaxation_cells": int(flagged.sum()),
        "relaxation_fraction_pct": float(100.0 * flagged.mean()),
        "relaxation_cell_area_km2": float(
            np.sum((mesh.spacing_km[flagged] * 1000.0) ** 2 * np.sqrt(3.0) / 2.0)
            / 1_000_000.0
        ),
        "boundary_distance_min_km": float(np.min(distances)),
        "boundary_distance_p50_km": float(np.quantile(distances, 0.50)),
        "boundary_distance_p95_km": float(np.quantile(distances, 0.95)),
        "boundary_distance_max_km": float(np.max(distances)),
        "within_25km_pct": float(100.0 * np.mean(distances <= 25.0)),
        "within_50km_pct": float(100.0 * np.mean(distances <= 50.0)),
        "bdy_mask_levels": ";".join(f"{int(a)}:{int(b)}" for a, b in zip(levels, counts)),
    }


def mask_area(mask, cell_area_km2: float) -> float:
    return float(np.count_nonzero(mask) * cell_area_km2)


def add_coverage_rows(rows: list[dict], domain_name: str, masks, surface, grid) -> None:
    area = grid.cell_area_m2 / 1_000_000.0
    denominator = mask_area(grid.inside_domain, area)
    geometric = geometry_area_km2(masks.common_geometry)
    entries = {
        "geometric_common_domain": (None, geometric),
        "sampled_common_domain": (grid.inside_domain, denominator),
        "reference_land": (grid.inside_domain & surface.land, None),
        "reference_ocean": (grid.inside_domain & surface.ocean, None),
        "valid_all": (masks.valid_all, None),
        "invalid_nearest_or_outside": (grid.inside_domain & ~masks.valid_all, None),
        "refined_all": (masks.refined_all, None),
        "coarse_any": (masks.valid_all & ~masks.refined_all, None),
        "relaxation_any": (masks.relaxation_any, None),
        "interior": (masks.interior, None),
        "interior_refined": (masks.interior_refined, None),
        "selected_land": (masks.interior_refined & surface.land, None),
        "selected_ocean": (masks.interior_refined & surface.ocean, None),
    }
    for label, (mask, precomputed) in entries.items():
        value = precomputed if precomputed is not None else mask_area(mask, area)
        rows.append({
            "domain": domain_name,
            "mesh_names": ";".join(masks.mesh_names),
            "metric": label,
            "n_target_cells": "" if mask is None else int(np.count_nonzero(mask)),
            "area_km2": f"{value:.3f}",
            "percent_of_sampled_common": f"{100.0 * value / denominator:.6f}",
            "equal_area_spacing_km": f"{grid.spacing_m / 1000.0:.1f}",
        })
    rows.append({
        "domain": domain_name,
        "mesh_names": ";".join(masks.mesh_names),
        "metric": "sampling_minus_geometric",
        "n_target_cells": "",
        "area_km2": f"{denominator - geometric:.3f}",
        "percent_of_sampled_common": f"{100.0 * (denominator - geometric) / geometric:.6f}",
        "equal_area_spacing_km": f"{grid.spacing_m / 1000.0:.1f}",
    })


def sensitivity_row(domain, factor, value, metric, mask, grid, denominator):
    area = mask_area(mask, grid.cell_area_m2 / 1_000_000.0)
    return {
        "domain": domain,
        "factor": factor,
        "value": value,
        "metric": metric,
        "n_target_cells": int(np.count_nonzero(mask)),
        "area_km2": f"{area:.3f}",
        "percent_of_sampled_common": f"{100.0 * area / denominator:.6f}",
    }


def native_disagreement_rows(domain_name, masks, surface, grid, meshes):
    rows = []
    area = grid.cell_area_m2 / 1_000_000.0
    strata = {
        "all": grid.inside_domain,
        "coastal_le_10km": surface.coastal[10.0],
        "coastal_le_25km": surface.coastal[25.0],
        "coastal_le_50km": surface.coastal[50.0],
        "noncoastal_gt_50km": ~surface.coastal[50.0],
    }
    scopes = {"common_valid": masks.valid_all, "interior_refined": masks.interior_refined}
    for name in masks.mesh_names:
        comparison = compare_native_surface(
            surface, masks.mappings[name],
            native_source=str(meshes[name].source_path).replace("grid.nc", "static.nc"),
        )
        for scope_name, scope in scopes.items():
            for stratum_name, stratum in strata.items():
                denominator = scope & stratum
                disagreement = denominator & comparison.disagreement
                n = int(np.count_nonzero(denominator))
                d = int(np.count_nonzero(disagreement))
                rows.append({
                    "domain": domain_name,
                    "experiment": name,
                    "scope": scope_name,
                    "stratum": stratum_name,
                    "denominator_cells": n,
                    "denominator_area_km2": f"{n * area:.3f}",
                    "disagreement_cells": d,
                    "disagreement_area_km2": f"{d * area:.3f}",
                    "disagreement_pct": f"{100.0 * d / n:.6f}" if n else "nan",
                })
    return rows


def mapping_distance_rows(domain_name, masks) -> list[dict]:
    rows = []
    for name, mapping in masks.mappings.items():
        sample = mapping.distance_km[masks.common_domain]
        rejected = masks.common_domain & ~mapping.within_distance
        rows.append({
            "domain": domain_name,
            "experiment": name,
            "common_points": int(sample.size),
            "distance_p50_km": f"{np.quantile(sample, 0.50):.6f}",
            "distance_p95_km": f"{np.quantile(sample, 0.95):.6f}",
            "distance_p99_km": f"{np.quantile(sample, 0.99):.6f}",
            "distance_max_km": f"{np.max(sample):.6f}",
            "rejected_over_8km": int(np.count_nonzero(rejected)),
            "rejected_over_8km_pct": f"{100.0 * np.mean(rejected[masks.common_domain]):.6f}",
        })
    return rows


def plot_boundary(ax, geometry, transformer, **kwargs):
    projected = transform_geometry(transformer.transform, geometry)
    boundary = projected.boundary
    parts = getattr(boundary, "geoms", [boundary])
    for part in parts:
        if hasattr(part, "xy"):
            x, y = part.xy
            ax.plot(np.asarray(x) / 1000.0, np.asarray(y) / 1000.0, **kwargs)


def make_figure(path: Path, domain_name: str, masks, surface, grid, land, meshes):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    _, forward, _ = local_laea(masks.common_geometry)
    outside = ~grid.inside_domain
    surface_values = np.where(surface.land, 1.0, 0.0)
    surface_values[outside] = np.nan
    selection = np.full(grid.x.shape, np.nan)
    selection[grid.inside_domain] = 0
    selection[masks.interior] = 1
    selection[masks.interior_refined] = 2
    exclusions = np.full(grid.x.shape, np.nan)
    exclusions[masks.interior_refined] = 0
    exclusions[masks.relaxation_any] = 1
    exclusions[masks.valid_all & ~masks.refined_all] = 2
    exclusions[grid.inside_domain & ~masks.valid_all] = 3
    disagreements = np.zeros(grid.x.shape, dtype=float)
    for name in masks.mesh_names:
        comparison = compare_native_surface(
            surface, masks.mappings[name], native_source=f"{name} static")
        disagreements += comparison.disagreement.astype(float)
    disagreements[outside] = np.nan

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.2), constrained_layout=True)
    panels = [
        (surface_values, ListedColormap(["#2b83ba", "#d9a66f"]),
         BoundaryNorm([-0.5, 0.5, 1.5], 2), "Referência independente de superfície",
         [Patch(color="#2b83ba", label="oceano"), Patch(color="#d9a66f", label="terra")]),
        (selection, ListedColormap(["#d73027", "#fee08b", "#1a9850"]),
         BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3), "Máscara comparável",
         [Patch(color="#d73027", label="domínio comum"), Patch(color="#fee08b", label="interior"), Patch(color="#1a9850", label="interior refinado")]),
        (exclusions, ListedColormap(["#1a9850", "#fdae61", "#984ea3", "#d73027"]),
         BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4), "Diagnóstico de exclusões",
         [Patch(color="#1a9850", label="selecionado"), Patch(color="#fdae61", label="relaxação"), Patch(color="#984ea3", label="célula grossa"), Patch(color="#d73027", label=">8 km/fora")]),
        (disagreements, plt.get_cmap("magma", len(masks.mesh_names) + 1),
         BoundaryNorm(np.arange(-0.5, len(masks.mesh_names) + 1.5), len(masks.mesh_names) + 1),
         "Nº de landmasks nativos em desacordo", None),
    ]
    for ax, (values, cmap, norm, title, legend) in zip(axes.flat, panels):
        image = ax.pcolormesh(grid.x / 1000.0, grid.y / 1000.0, values,
                              shading="nearest", cmap=cmap, norm=norm, rasterized=True)
        plot_boundary(ax, land, forward, color="black", linewidth=0.35, alpha=0.75)
        plot_boundary(ax, masks.common_geometry, forward, color="white", linewidth=1.15)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("LAEA x (km)")
        ax.set_ylabel("LAEA y (km)")
        if legend:
            ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.9)
        else:
            fig.colorbar(image, ax=ax, shrink=0.78, label="experimentos")
    fig.suptitle(
        f"MEQ-02C/2A — {domain_name}\n"
        f"malhas: {', '.join(masks.mesh_names)} | LAEA 5 km | limiar refinado <5,5 km | busca ≤8 km",
        fontsize=13,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def product_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_repo_path(path: Path) -> str:
    """Return a repository-relative path when the product lives in the repo."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> None:
    args = parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    args.figures_dir.mkdir(parents=True, exist_ok=True)

    canonical = {
        key: load_mesh(args.geometry_dir / f"{key}_geometry.npz", key, key.upper())
        for key in ("ctl", "exp02", "oval")
    }
    meshes = {
        "CTL": canonical["ctl"],
        "EXP01": MeshGeometry(**{**canonical["ctl"].__dict__, "name": "EXP01"}),
        "EXP02": canonical["exp02"],
        "EXP03": canonical["oval"],
    }
    bounds = unary_union([mesh.domain for mesh in canonical.values()]).bounds
    land = load_land_geometry(args.land_shapefile, bounds)

    coverage_rows = []
    sensitivity_rows = []
    disagreement_rows = []
    mapping_rows = []
    domain_summary = {}
    figure_paths = []

    for domain_name, names in DOMAIN_SPECS.items():
        provisional = build_comparison_masks(
            meshes, np.array([meshes[names[0]].domain.centroid.x]),
            np.array([meshes[names[0]].domain.centroid.y]), mesh_names=names,
            max_distance_km=8.0, refined_threshold_km=5.5,
        )
        grid = equal_area_grid(provisional.common_geometry, spacing_km=5.0)
        masks = build_comparison_masks(
            meshes, grid.lon, grid.lat, mesh_names=names,
            max_distance_km=8.0, refined_threshold_km=5.5,
        )
        surface = classify_destination_surface(
            grid.lon, grid.lat, land,
            source="Natural Earth 1:10m Land v5.1.1 (EPSG:4326)",
            coast_widths_km=(10, 25, 50),
        )
        add_coverage_rows(coverage_rows, domain_name, masks, surface, grid)
        disagreement_rows.extend(
            native_disagreement_rows(domain_name, masks, surface, grid, meshes))
        mapping_rows.extend(mapping_distance_rows(domain_name, masks))
        denominator = mask_area(grid.inside_domain, grid.cell_area_m2 / 1_000_000.0)

        for threshold in (5.0, 5.5, 6.0):
            trial = build_comparison_masks(
                meshes, grid.lon, grid.lat, mesh_names=names,
                max_distance_km=8.0, refined_threshold_km=threshold,
            )
            sensitivity_rows.append(sensitivity_row(
                domain_name, "refined_threshold_km", f"{threshold:.1f}",
                "interior_refined", trial.interior_refined, grid, denominator))

        for max_distance in (4.0, 6.0, 8.0, 10.0):
            trial = build_comparison_masks(
                meshes, grid.lon, grid.lat, mesh_names=names,
                max_distance_km=max_distance, refined_threshold_km=5.5,
            )
            sensitivity_rows.append(sensitivity_row(
                domain_name, "max_source_distance_km", f"{max_distance:.1f}",
                "valid_all", trial.valid_all, grid, denominator))
            sensitivity_rows.append(sensitivity_row(
                domain_name, "max_source_distance_km", f"{max_distance:.1f}",
                "interior_refined", trial.interior_refined, grid, denominator))

        for spacing in (2.5, 5.0, 10.0):
            trial_grid = equal_area_grid(masks.common_geometry, spacing_km=spacing)
            trial = build_comparison_masks(
                meshes, trial_grid.lon, trial_grid.lat, mesh_names=names,
                max_distance_km=8.0, refined_threshold_km=5.5,
            )
            trial_denominator = mask_area(
                trial_grid.inside_domain, trial_grid.cell_area_m2 / 1_000_000.0)
            sensitivity_rows.append(sensitivity_row(
                domain_name, "equal_area_spacing_km", f"{spacing:.1f}",
                "interior_refined", trial.interior_refined, trial_grid,
                trial_denominator))

        distance_to_relax = np.full(grid.lon.shape, np.inf)
        for name in names:
            mesh = meshes[name]
            relax = mesh.bdy_mask > 0
            distance_to_relax = np.minimum(
                distance_to_relax,
                nearest_distance_km(
                    mesh.lon[relax], mesh.lat[relax], grid.lon, grid.lat),
            )
        for buffer_km in (0.0, 25.0, 50.0):
            buffered = masks.interior_refined.copy()
            if buffer_km > 0:
                buffered &= distance_to_relax > buffer_km
            sensitivity_rows.append(sensitivity_row(
                domain_name, "extra_relaxation_buffer_km", f"{buffer_km:.1f}",
                "interior_refined", buffered, grid, denominator))

        for width in (10.0, 25.0, 50.0):
            for surface_name, surface_mask in (("land", surface.land), ("ocean", surface.ocean)):
                for zone_name, zone_mask in (
                    ("coastal", surface.coastal[width]),
                    ("noncoastal", ~surface.coastal[width]),
                ):
                    sensitivity_rows.append(sensitivity_row(
                        domain_name, "coast_width_km", f"{width:.1f}",
                        f"selected_{surface_name}_{zone_name}",
                        masks.interior_refined & surface_mask & zone_mask,
                        grid, denominator))

        figure_name = (
            "meq02c_2a_domain_a_four_experiments.png"
            if domain_name.startswith("A_") else "meq02c_2a_domain_b_oval_exp02.png"
        )
        figure_path = args.figures_dir / figure_name
        make_figure(figure_path, domain_name, masks, surface, grid, land, meshes)
        figure_paths.append(figure_path)
        domain_summary[domain_name] = {
            "mesh_names": list(names),
            "bounds_lonlat": list(masks.common_geometry.bounds),
            "geometry_type": masks.common_geometry.geom_type,
            "is_valid": bool(masks.common_geometry.is_valid),
            "is_empty": bool(masks.common_geometry.is_empty),
            "boundary_is_closed": boundary_is_closed(masks.common_geometry),
            "geometric_area_km2": geometry_area_km2(masks.common_geometry),
            "sampled_area_km2": denominator,
            "target_shape": list(grid.lon.shape),
            "target_points_inside": int(np.count_nonzero(grid.inside_domain)),
            "target_crs_wkt": grid.crs_wkt,
        }

    relaxation_rows = [
        relaxation_boundary_metrics(meshes[name])
        for name in ("CTL", "EXP01", "EXP02", "EXP03")
    ]

    outputs = {
        "domain_coverage": args.results_dir / "meq02c_2a_domain_coverage.csv",
        "sensitivity": args.results_dir / "meq02c_2a_sensitivity.csv",
        "landmask_disagreement": args.results_dir / "meq02c_2a_landmask_disagreement.csv",
        "relaxation_diagnostics": args.results_dir / "meq02c_2a_relaxation_diagnostics.csv",
        "mapping_distances": args.results_dir / "meq02c_2a_mapping_distances.csv",
    }
    write_csv(outputs["domain_coverage"], coverage_rows)
    write_csv(outputs["sensitivity"], sensitivity_rows)
    write_csv(outputs["landmask_disagreement"], disagreement_rows)
    write_csv(outputs["relaxation_diagnostics"], relaxation_rows)
    write_csv(outputs["mapping_distances"], mapping_rows)

    import scipy
    import pyproj
    import matplotlib
    transport_sources = {}
    for key in ("ctl", "exp02", "oval"):
        path = args.geometry_dir / f"{key}_geometry.npz"
        transport_sources[key] = {
            "temporary_transport_path_used": str(path),
            "temporary_transport_sha256": file_sha256(path),
            **REMOTE_GRID_METADATA[key],
            "mesh_geometry": {
                "geometry_type": canonical[key].domain.geom_type,
                "is_valid": bool(canonical[key].domain.is_valid),
                "is_empty": bool(canonical[key].domain.is_empty),
                "boundary_is_closed": boundary_is_closed(canonical[key].domain),
                "bounds_lonlat": list(canonical[key].domain.bounds),
                "geometric_area_km2": geometry_area_km2(canonical[key].domain),
                "spacing_km_min": float(np.min(canonical[key].spacing_km)),
                "spacing_km_p50": float(np.quantile(canonical[key].spacing_km, 0.50)),
                "spacing_km_p95": float(np.quantile(canonical[key].spacing_km, 0.95)),
                "spacing_km_max": float(np.max(canonical[key].spacing_km)),
                "cells_below_5_5_km": int(np.count_nonzero(canonical[key].spacing_km < 5.5)),
                "cells_with_bdy_mask": int(np.count_nonzero(canonical[key].bdy_mask > 0)),
            },
        }
    manifest = {
        "task": "MEQ-02C/Etapa 2A - validacao espacial das malhas reais",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "geometry-only; no meteorological field was read or produced",
        "method": {
            "common_domain": "exact intersection of polygons reconstructed from one-sided MPAS boundary edges",
            "target_grid": "local Lambert azimuthal equal-area centre-point sampling",
            "base_equal_area_spacing_km": 5.0,
            "nearest_mapping": "spherical cKDTree; no extrapolation beyond explicit limit",
            "areaCell_interpretation": "MPAS spherical cell area in steradians; converted with Earth radius 6371229 m",
            "base_max_source_distance_km": 8.0,
            "base_refined_spacing_threshold_km": 5.5,
            "base_selected_mask": "common AND valid_all AND refined_all AND NOT relaxation_any",
            "coast_widths_km": [10, 25, 50],
            "surface_reference": NE_METADATA,
            "map_rendering": "PyProj LAEA + Matplotlib; Cartopy import was unavailable locally (hung beyond 60 s)",
        },
        "domains": domain_summary,
        "sources": transport_sources,
        "products": {
            **{key: {"path": portable_repo_path(path), "sha256": product_sha256(path)}
               for key, path in outputs.items()},
            "figures": [
                {"path": portable_repo_path(path), "sha256": product_sha256(path)}
                for path in figure_paths
            ],
        },
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "shapely": shapely.__version__,
            "pyproj": pyproj.__version__,
            "matplotlib": matplotlib.__version__,
            "pyogrio": pyogrio.__version__,
        },
        "git": {
            "branch": git_text("branch", "--show-current"),
            "head": git_text("rev-parse", "HEAD"),
            "local_main": git_text("rev-parse", "main"),
            "stored_origin_main": git_text("rev-parse", "origin/main"),
            "status_before_manifest": git_text("status", "--short").splitlines(),
            "effective_remote_main_checked_separately": "b7f2fae0649dc36756f27508c6137e78909bf896",
        },
        "execution": {
            "command": (
                "MPLCONFIGDIR=/tmp/meq02c_mplconfig XDG_CACHE_HOME=/tmp/meq02c_cache "
                "python scripts/05_exploration/validate_meq02c_spatial_masks.py "
                f"--geometry-dir {args.geometry_dir}"
            ),
            "working_directory": ".",
        },
        "limitations": [
            "Equal-area totals use centre-point sampling; boundary cells are not fractionally weighted.",
            "Natural Earth 1:10m is independent of MPAS native landmasks but is still a generalized coastline product.",
            "The 5.5 km refined threshold and all tested buffers are diagnostic choices, not scientific ratification.",
            "CTL and EXP01 intentionally remain distinct experiment identities although they share one grid/static artifact.",
        ],
    }
    manifest_path = args.results_dir / "meq02c_2a_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "tables": [str(path) for path in outputs.values()],
        "figures": [str(path) for path in figure_paths],
    }, indent=2))


if __name__ == "__main__":
    main()
