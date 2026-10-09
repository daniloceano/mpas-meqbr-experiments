#!/usr/bin/env python3
"""Prepare compact geospatial evidence for the MEQ-02A mesh atlas.

This script is intended to run on Swell, where the MPAS grids and the basin
shapefiles live.  It reads the three selected meshes, derives their actual
outer and <5.5 km contours from mesh connectivity/``areaCell``, samples every
intersecting basin on a common 1 km equal-area lattice, and writes one compact
JSON asset.  It never modifies a mesh or a simulation product.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess

import netCDF4
import numpy as np
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
import shapefile
from shapely import contains_xy
from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import polygonize, transform as geometry_transform, unary_union


RADIUS_M = 6_371_229.0
DX_THRESHOLD_KM = 5.5
SAMPLE_STEP_M = 1_000.0

MPAS_ROOT = Path("/p1-swell/danilocs/MPAS-Research")
BASIN_ROOT = Path(
    "/p1-swell/danilocs/cyclone_monitor_south_atlantic/data/sedimentary_basins"
)

MESH_SPECS = {
    "ctl": {
        "label": "CTL / EXP01",
        "path": MPAS_ROOT / "grids/meqbr_05km/meqbr_05km.grid.nc",
        "role": "Malha original usada por CTL e EXP01",
        "parameters": "núcleo nominal de 5 km; sem buffer gradual",
    },
    "exp02": {
        "label": "EXP02",
        "path": MPAS_ROOT / "grids/meqbr_05km_buf/meqbr_05km_buf.grid.nc",
        "role": "Malha efetivamente usada pelo EXP02",
        "parameters": "núcleo refinado e tratamento gradual de fronteira",
    },
    "oval": {
        "label": "Oval",
        "path": MPAS_ROOT
        / "grids/meqbr_05km_oval_meq02a/meqbr_05km_oval_meq02a.grid.nc",
        "role": "Candidata geométrica MEQ-02A; ainda sem simulação",
        "parameters": (
            "centro 0,459°S, 44,579°W; 1264 × 430 km; 117°; "
            "5→31 km; smoothstep 325 km"
        ),
    },
}

IDENTITY_CHECKS = {
    "ctl": [
        (
            "CTL/2021",
            MPAS_ROOT
            / "runs/meqbr_05km/CTL/20211101_20211201/"
            "history.2021-11-01_00.00.00.nc",
        ),
        (
            "EXP01/2021",
            MPAS_ROOT
            / "runs/meqbr_05km/EXP01/20211101_20211201/"
            "history.2021-10-21_00.00.00.nc",
        ),
    ],
    "exp02": [
        (
            "EXP02/2021",
            MPAS_ROOT
            / "runs/meqbr_05km/EXP02/20211101_20211201/"
            "history.2021-10-21_00.00.00.nc",
        )
    ],
}

SITES = {
    "P0": {"lat": -2.694107, "lon": -42.554807, "label": "P0 — LiDAR flutuante"},
    "LPI": {
        "lat": -4.8789425,
        "lon": -37.1478801,
        "label": "LPI — LiDAR fixo",
    },
}

PRIORITY_BASINS = [
    "Foz do Amazonas",
    "Pará-Maranhão",
    "Barreirinhas",
    "Ceará",
    "Potiguar",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(repo: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def clean_basin_name(directory: str) -> str:
    name = directory
    for suffix in ("_Mar-zip", "_Mar", "-zip", "_zip"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("SEAL", "Sergipe–Alagoas")


def rounded_geojson(geom, digits: int = 5):
    data = mapping(geom)

    def round_nested(value):
        if isinstance(value, (list, tuple)):
            if value and isinstance(value[0], (int, float)):
                return [round(float(item), digits) for item in value]
            return [round_nested(item) for item in value]
        return value

    data["coordinates"] = round_nested(data["coordinates"])
    return data


def polygon_from_edge_mask(lat_vertex, lon_vertex, vertices_on_edge, mask):
    segments = []
    for edge_index in np.flatnonzero(mask):
        v0, v1 = vertices_on_edge[edge_index] - 1
        if v0 < 0 or v1 < 0:
            continue
        segments.append(
            LineString(
                [
                    (float(lon_vertex[v0]), float(lat_vertex[v0])),
                    (float(lon_vertex[v1]), float(lat_vertex[v1])),
                ]
            )
        )
    polygons = list(polygonize(segments))
    if not polygons:
        raise RuntimeError("edge mask did not form a polygon")
    geom = unary_union(polygons)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def simplify_geographic(geom, tolerance_m: float = 5_000.0):
    centroid = geom.centroid
    local = CRS.from_proj4(
        f"+proj=laea +lat_0={centroid.y} +lon_0={centroid.x} "
        "+datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", local, always_xy=True)
    inverse = Transformer.from_crs(local, "EPSG:4326", always_xy=True)
    projected = geometry_transform(forward.transform, geom)
    simplified = projected.simplify(tolerance_m, preserve_topology=True)
    return geometry_transform(inverse.transform, simplified)


def xyz(lon_deg, lat_deg):
    lon = np.radians(lon_deg)
    lat = np.radians(lat_deg)
    return np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )


def equivalent_spacing_km(area_cell):
    return RADIUS_M / 1000.0 * np.sqrt(2.0 * area_cell / np.sqrt(3.0))


def connectivity_check(dataset, sizes):
    limits = {
        "cellsOnCell": sizes["nCells"],
        "edgesOnCell": sizes["nEdges"],
        "verticesOnCell": sizes["nVertices"],
        "edgesOnEdge": sizes["nEdges"],
        "cellsOnEdge": sizes["nCells"],
        "verticesOnEdge": sizes["nVertices"],
        "cellsOnVertex": sizes["nCells"],
        "edgesOnVertex": sizes["nEdges"],
    }
    result = {}
    for variable, upper in limits.items():
        values = np.asarray(dataset.variables[variable][:], dtype=np.int64)
        bad = int(np.count_nonzero((values < 0) | (values > upper)))
        result[variable] = {"invalid_indices": bad, "upper_bound": int(upper)}
    return result


def mesh_record(key: str, spec: dict):
    path = spec["path"]
    with netCDF4.Dataset(path) as dataset:
        sizes = {name: len(dataset.dimensions[name]) for name in ("nCells", "nEdges", "nVertices")}
        lat_cell = np.asarray(dataset.variables["latCell"][:], dtype=float)
        lon_cell = np.asarray(dataset.variables["lonCell"][:], dtype=float)
        lat_vertex = np.asarray(dataset.variables["latVertex"][:], dtype=float)
        lon_vertex = np.asarray(dataset.variables["lonVertex"][:], dtype=float)
        area_cell = np.asarray(dataset.variables["areaCell"][:], dtype=float)
        cells_on_edge = np.asarray(dataset.variables["cellsOnEdge"][:], dtype=np.int64)
        vertices_on_edge = np.asarray(dataset.variables["verticesOnEdge"][:], dtype=np.int64)
        n_edges_on_cell = np.asarray(dataset.variables["nEdgesOnCell"][:], dtype=np.int64)
        cell_quality = np.asarray(dataset.variables["cellQuality"][:], dtype=float)
        triangle_quality = np.asarray(dataset.variables["triangleQuality"][:], dtype=float)
        obtuse = np.asarray(dataset.variables["obtuseTriangle"][:], dtype=np.int64)
        bdy_mask = np.asarray(dataset.variables["bdyMaskCell"][:], dtype=np.int64)
        connectivity = connectivity_check(dataset, sizes)

    # MPAS commonly stores longitudes in [0, 2π).  Normalise them before
    # constructing browser-facing polygons or performing direct point tests.
    lon_cell_deg = (np.degrees(lon_cell) + 180.0) % 360.0 - 180.0
    lat_cell_deg = np.degrees(lat_cell)
    lon_vertex_deg = (np.degrees(lon_vertex) + 180.0) % 360.0 - 180.0
    lat_vertex_deg = np.degrees(lat_vertex)
    dx = equivalent_spacing_km(area_cell)

    outer_edge = np.any(cells_on_edge == 0, axis=1)
    c0 = cells_on_edge[:, 0] - 1
    c1 = cells_on_edge[:, 1] - 1
    refined = dx < DX_THRESHOLD_KM
    side0 = np.where(c0 >= 0, refined[np.maximum(c0, 0)], False)
    side1 = np.where(c1 >= 0, refined[np.maximum(c1, 0)], False)
    refined_edge = side0 != side1

    domain_geom = polygon_from_edge_mask(
        lat_vertex_deg, lon_vertex_deg, vertices_on_edge, outer_edge
    )
    refined_geom = polygon_from_edge_mask(
        lat_vertex_deg, lon_vertex_deg, vertices_on_edge, refined_edge
    )
    domain_simple = simplify_geographic(domain_geom)
    refined_simple = simplify_geographic(refined_geom)

    tree = cKDTree(xyz(lon_cell_deg, lat_cell_deg))
    quantiles = np.quantile(dx, [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1])
    record = {
        "key": key,
        "label": spec["label"],
        "role": spec["role"],
        "parameters": spec["parameters"],
        "path": str(path),
        "sha256": sha256(path),
        **{name: int(value) for name, value in sizes.items()},
        "spacing_km": {
            name: round(float(value), 4)
            for name, value in zip(
                ["min", "p01", "p05", "p25", "median", "p75", "p95", "p99", "max"],
                quantiles,
            )
        },
        "refined_cells": int(np.count_nonzero(refined)),
        "refined_cell_fraction_pct": round(100.0 * float(np.mean(refined)), 4),
        "cell_area_sum_km2": round(float(np.sum(area_cell) * RADIUS_M**2 / 1e6), 2),
        "bounds_cell_centres": {
            "west": round(float(lon_cell_deg.min()), 5),
            "east": round(float(lon_cell_deg.max()), 5),
            "south": round(float(lat_cell_deg.min()), 5),
            "north": round(float(lat_cell_deg.max()), 5),
        },
        "integrity": {
            "finite_positive_area": bool(np.all(np.isfinite(area_cell)) and np.all(area_cell > 0)),
            "nEdgesOnCell_min": int(n_edges_on_cell.min()),
            "nEdgesOnCell_max": int(n_edges_on_cell.max()),
            "boundary_edges": int(np.count_nonzero(outer_edge)),
            "euler_cells_minus_edges_plus_vertices": int(
                sizes["nCells"] - sizes["nEdges"] + sizes["nVertices"]
            ),
            "obtuse_triangles": int(np.count_nonzero(obtuse)),
            "cell_quality_min": round(float(cell_quality.min()), 6),
            "cell_quality_p01": round(float(np.quantile(cell_quality, 0.01)), 6),
            "triangle_quality_min": round(float(triangle_quality.min()), 6),
            "bdyMaskCell_histogram": {
                str(int(value)): int(count) for value, count in sorted(Counter(bdy_mask).items())
            },
            "connectivity": connectivity,
        },
        "geometry": {
            "domain": rounded_geojson(domain_simple),
            "refined": rounded_geojson(refined_simple),
        },
    }
    return record, {
        "domain_geom": domain_geom,
        "refined_geom": refined_geom,
        "tree": tree,
        "dx": dx,
        "lon": lon_cell_deg,
        "lat": lat_cell_deg,
    }


def identity_check(mesh_path: Path, history_path: Path):
    with netCDF4.Dataset(mesh_path) as mesh, netCDF4.Dataset(history_path) as history:
        result = {"history": str(history_path)}
        for variable in ("latCell", "lonCell"):
            source = np.asarray(mesh.variables[variable][:])
            used = np.asarray(history.variables[variable][:])
            used = np.squeeze(used)
            cast_source = source.astype(used.dtype, copy=False)
            result[f"{variable}_exact_after_dtype_cast"] = bool(
                source.shape == used.shape and np.array_equal(cast_source, used)
            )
            result[f"{variable}_max_abs_difference"] = (
                float(np.max(np.abs(cast_source - used))) if source.shape == used.shape else None
            )
        result["nCells"] = int(len(mesh.dimensions["nCells"]))
        result["history_nCells"] = int(len(history.dimensions["nCells"]))
        return result


def read_basin(path: Path):
    reader = shapefile.Reader(str(path))
    geom = unary_union([shape(item.__geo_interface__) for item in reader.shapes()])
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def sample_basin(geom, step_m=SAMPLE_STEP_M):
    centroid = geom.centroid
    equal_area = CRS.from_proj4(
        f"+proj=laea +lat_0={centroid.y} +lon_0={centroid.x} "
        "+datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs("EPSG:4326", equal_area, always_xy=True)
    inverse = Transformer.from_crs(equal_area, "EPSG:4326", always_xy=True)
    projected = geometry_transform(forward.transform, geom)
    minx, miny, maxx, maxy = projected.bounds
    xs = np.arange(math.floor(minx / step_m) * step_m + 0.5 * step_m, maxx, step_m)
    ys = np.arange(math.floor(miny / step_m) * step_m + 0.5 * step_m, maxy, step_m)
    xx, yy = np.meshgrid(xs, ys)
    inside = contains_xy(projected, xx, yy)
    x = xx[inside]
    y = yy[inside]
    lon, lat = inverse.transform(x, y)
    return {
        "x": x,
        "y": y,
        "lon": np.asarray(lon),
        "lat": np.asarray(lat),
        "equal_area": equal_area,
        "area_km2": float(projected.area / 1e6),
    }


def basin_hash(path: Path):
    files = []
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            files.append({"path": str(candidate), "sha256": sha256(candidate)})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    meshes = {}
    runtime = {}
    for key, spec in MESH_SPECS.items():
        record, internal = mesh_record(key, spec)
        meshes[key] = record
        runtime[key] = internal

    identities = {}
    for key, checks in IDENTITY_CHECKS.items():
        identities[key] = [
            {"experiment": label, **identity_check(MESH_SPECS[key]["path"], path)}
            for label, path in checks
        ]

    site_records = []
    for site_key, site in SITES.items():
        item = {"key": site_key, **site, "meshes": {}}
        point = Point(site["lon"], site["lat"])
        query = xyz(np.array([site["lon"]]), np.array([site["lat"]]))
        for mesh_key in MESH_SPECS:
            internal = runtime[mesh_key]
            _, nearest = internal["tree"].query(query)
            nearest = int(np.asarray(nearest).ravel()[0])
            item["meshes"][mesh_key] = {
                "inside_domain": bool(internal["domain_geom"].covers(point)),
                "spacing_km": round(float(internal["dx"][nearest]), 4),
                "refined": bool(internal["dx"][nearest] < DX_THRESHOLD_KM),
            }
        site_records.append(item)

    basin_paths = sorted(BASIN_ROOT.glob("*/bacias_gishub_db.shp"))
    basin_records = []
    for path in basin_paths:
        name = clean_basin_name(path.parent.name)
        geom = read_basin(path)
        sample = sample_basin(geom)
        query = xyz(sample["lon"], sample["lat"])
        coverages = {}
        for mesh_key in MESH_SPECS:
            internal = runtime[mesh_key]
            transformer = Transformer.from_crs(
                "EPSG:4326", sample["equal_area"], always_xy=True
            )
            domain_projected = geometry_transform(
                transformer.transform, internal["domain_geom"]
            )
            inside_domain = contains_xy(domain_projected, sample["x"], sample["y"])
            refined = np.zeros(inside_domain.shape, dtype=bool)
            if np.any(inside_domain):
                _, nearest = internal["tree"].query(query[inside_domain], workers=-1)
                refined[inside_domain] = internal["dx"][nearest] < DX_THRESHOLD_KM
            coverages[mesh_key] = {
                "domain_pct": round(100.0 * float(np.mean(inside_domain)), 4),
                "refined_pct": round(100.0 * float(np.mean(refined)), 4),
                "inside_coarse_pct": round(
                    100.0 * float(np.mean(inside_domain & ~refined)), 4
                ),
            }
        sensitivity_2km = None
        if name in {"Foz do Amazonas", "Potiguar"}:
            coarse_sample = sample_basin(geom, step_m=2_000.0)
            coarse_query = xyz(coarse_sample["lon"], coarse_sample["lat"])
            sensitivity_2km = {}
            for mesh_key in MESH_SPECS:
                internal = runtime[mesh_key]
                transformer = Transformer.from_crs(
                    "EPSG:4326", coarse_sample["equal_area"], always_xy=True
                )
                domain_projected = geometry_transform(
                    transformer.transform, internal["domain_geom"]
                )
                inside_domain = contains_xy(
                    domain_projected, coarse_sample["x"], coarse_sample["y"]
                )
                refined = np.zeros(inside_domain.shape, dtype=bool)
                if np.any(inside_domain):
                    _, nearest = internal["tree"].query(
                        coarse_query[inside_domain], workers=-1
                    )
                    refined[inside_domain] = (
                        internal["dx"][nearest] < DX_THRESHOLD_KM
                    )
                sensitivity_2km[mesh_key] = {
                    "domain_pct": round(100.0 * float(np.mean(inside_domain)), 4),
                    "refined_pct": round(100.0 * float(np.mean(refined)), 4),
                }
        if not any(value["domain_pct"] > 0 for value in coverages.values()):
            continue
        simple = simplify_geographic(geom, tolerance_m=3_000.0)
        basin_records.append(
            {
                "key": name.lower().replace(" ", "-").replace("–", "-"),
                "name": name,
                "priority": name in PRIORITY_BASINS,
                "source": str(path),
                "source_files": basin_hash(path),
                "geometry": rounded_geojson(simple),
                "area_km2": round(sample["area_km2"], 2),
                "sample_points_1km": int(len(sample["lon"])),
                "coverage": coverages,
                "sensitivity_2km": sensitivity_2km,
                "oval_minus_exp02_refined_pp": round(
                    coverages["oval"]["refined_pct"]
                    - coverages["exp02"]["refined_pct"],
                    4,
                ),
            }
        )

    priority_rank = {name: index for index, name in enumerate(PRIORITY_BASINS)}
    basin_records.sort(
        key=lambda item: (
            0 if item["priority"] else 1,
            priority_rank.get(item["name"], 999),
            item["name"],
        )
    )

    oval_grid_dir = MESH_SPECS["oval"]["path"].parent
    log_path = oval_grid_dir / "meqbr_05km_oval_meq02a_global.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    suspicious = [
        line.strip()
        for line in log_text.splitlines()
        if any(token in line.lower() for token in ("error", "warning", "incomplete", "obtuse"))
    ]

    generator_repo = Path(
        "/p1-swell/danilocs/MPAS-Research-worktrees/fix-oisst-coastal-fill-audit"
    )
    output = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": "MEQ-02A — comparação das malhas da Margem Equatorial Brasileira",
        "threshold_km": DX_THRESHOLD_KM,
        "sampling": {
            "projection": "LAEA local por bacia (WGS84)",
            "step_km": SAMPLE_STEP_M / 1000.0,
            "denominator": "área total do polígono marítimo, aproximada pelos mesmos pontos para todas as malhas",
            "spacing_definition": "d_eq = R sqrt(2 areaCell / sqrt(3)), R = 6371229 m",
            "domain_definition": "polígono reconstruído das arestas reais com cellsOnEdge == 0",
            "refined_definition": f"ponto dentro do domínio e célula MPAS mais próxima com d_eq < {DX_THRESHOLD_KM} km",
        },
        "generator": {
            "repository": str(generator_repo),
            "branch": git_value(generator_repo, "branch", "--show-current"),
            "commit": git_value(generator_repo, "rev-parse", "HEAD"),
            "command": (
                "create_regional_grid.py -r 5 -l 200 --shape ellipse "
                "-clat -0.459 -clon -44.579 --semi-major 1264 --semi-minor 430 "
                "--orientation 117 --buffer-res 31 --buffer-width 325 "
                "--buffer-profile smoothstep --hfun-dlat 0.05 --hfun-float32 "
                "-o meqbr_05km_oval_meq02a -p"
            ),
            "generation_date": datetime.fromtimestamp(
                MESH_SPECS["oval"]["path"].stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds"),
        },
        "meshes": meshes,
        "identity_checks": identities,
        "sites": site_records,
        "basins": basin_records,
        "oval_validation": {
            "predicted_nCells": 102_942,
            "actual_nCells": meshes["oval"]["nCells"],
            "difference_cells": meshes["oval"]["nCells"] - 102_942,
            "predicted_refined_pct": {
                "Foz do Amazonas": 91.88,
                "Potiguar": 76.45,
            },
            "generation_log": str(log_path),
            "suspicious_log_lines": suspicious,
            "generation_note": (
                "A primeira invocação parou antes do JIGSAW porque o executável "
                "do ambiente não estava no PATH; a mesma geração foi retomada "
                "com o PATH do ambiente, sem alterar parâmetros."
            ),
        },
        "limitations": [
            "Cobertura refinada é geométrica; não incorpora máscara terra/oceano dos campos estáticos.",
            "Contornos do atlas são simplificações de 3–5 km das arestas reais, apenas para visualização leve.",
            "A Oval não possui estáticos, IC/LBC, particionamento, simulação ou validação meteorológica.",
            "Percentuais são estimativas areais por amostragem comum de 1 km; diferenças muito pequenas devem ser tratadas com cautela.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(args.output)
    print(f"{args.output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
