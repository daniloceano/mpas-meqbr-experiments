"""Reproducible spatial masks for comparisons between different MPAS meshes.

The comparison domain is the geometric intersection of polygons reconstructed
from actual MPAS boundary edges (``cellsOnEdge == 0``), never the overlap of
bounding boxes. Target points must also pass a maximum nearest-source distance;
there is no silent extrapolation.

The defaults used during MEQ-02C preparation -- 5.5 km equivalent spacing and
10/25/50 km coastal bands -- are configurable method parameters, not ratified
scientific choices. Equal-area grids use centre-point sampling; each retained
point has the same nominal area, while fractional boundary-cell weighting is a
possible later sensitivity analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from netCDF4 import Dataset
import numpy as np
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely import covers, distance, points
from shapely.geometry import LineString
from shapely.ops import polygonize, transform as transform_geometry, unary_union


EARTH_RADIUS_M = 6_371_229.0


@dataclass(frozen=True)
class MeshGeometry:
    """Geometry and comparison masks read from a stable MPAS grid file."""

    name: str
    source_path: Path
    source_sha256: str
    lon: np.ndarray
    lat: np.ndarray
    spacing_km: np.ndarray
    bdy_mask: np.ndarray
    domain: object
    native_landmask: np.ndarray | None = None

    @property
    def n_cells(self) -> int:
        return int(self.lat.size)


@dataclass(frozen=True)
class SourceMapping:
    """Nearest-source diagnostics for every destination point."""

    source_index: np.ndarray
    distance_km: np.ndarray
    inside_domain: np.ndarray
    within_distance: np.ndarray
    valid: np.ndarray
    refined: np.ndarray
    relaxation: np.ndarray
    native_landmask: np.ndarray | None


@dataclass(frozen=True)
class ComparisonMasks:
    """Common-domain masks for either a pair or a larger experiment set."""

    mesh_names: tuple[str, ...]
    common_geometry: object
    mappings: dict[str, SourceMapping]
    common_domain: np.ndarray
    valid_all: np.ndarray
    refined_all: np.ndarray
    relaxation_any: np.ndarray
    interior: np.ndarray
    interior_refined: np.ndarray


@dataclass(frozen=True)
class SurfaceMasks:
    """Destination-grid land/ocean/coast classification and its provenance."""

    source: str
    land: np.ndarray
    ocean: np.ndarray
    distance_to_coast_km: np.ndarray
    coastal: dict[float, np.ndarray]


@dataclass(frozen=True)
class NativeSurfaceComparison:
    """A provenance-labelled comparison to one native MPAS landmask."""

    destination_source: str
    native_source: str
    native_land: np.ndarray
    disagreement: np.ndarray


@dataclass(frozen=True)
class EqualAreaGrid:
    """A local LAEA centre-point grid suitable for area-weighted summaries."""

    x: np.ndarray
    y: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    inside_domain: np.ndarray
    spacing_m: float
    cell_area_m2: float
    crs_wkt: str

    @property
    def area_weights(self) -> np.ndarray:
        return np.where(self.inside_domain, self.cell_area_m2, 0.0)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def equivalent_spacing_km(area_cell, *, radius_m: float = EARTH_RADIUS_M) -> np.ndarray:
    """Hexagon-equivalent spacing from MPAS ``areaCell`` in steradians."""
    area = np.asarray(area_cell, dtype=float)
    if np.any(~np.isfinite(area)) or np.any(area <= 0):
        raise ValueError("areaCell must contain finite positive steradian areas")
    return radius_m / 1000.0 * np.sqrt(2.0 * area / np.sqrt(3.0))


def _degrees_longitude(values) -> np.ndarray:
    return (np.degrees(values) + 180.0) % 360.0 - 180.0


def domain_polygon_from_edges(lat_vertex, lon_vertex, vertices_on_edge,
                              cells_on_edge):
    """Reconstruct the real MPAS outer polygon from one-sided boundary edges."""
    lat = np.degrees(np.asarray(lat_vertex, dtype=float))
    lon = _degrees_longitude(np.asarray(lon_vertex, dtype=float))
    vertices = np.asarray(vertices_on_edge, dtype=np.int64)
    boundary = np.any(np.asarray(cells_on_edge, dtype=np.int64) == 0, axis=1)
    segments = []
    for edge in np.flatnonzero(boundary):
        v0, v1 = vertices[edge] - 1
        if v0 < 0 or v1 < 0:
            continue
        segments.append(LineString([(lon[v0], lat[v0]), (lon[v1], lat[v1])]))
    polygons = list(polygonize(segments))
    if not polygons:
        raise ValueError("MPAS boundary edges do not form a polygon")
    geometry = unary_union(polygons)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError("MPAS boundary polygon is empty")
    return geometry


def read_mesh_geometry(path: str | Path, *, name: str | None = None,
                       expected_n_cells: int | None = None,
                       expected_sha256: str | None = None) -> MeshGeometry:
    """Read only geometry/mask variables from a stable MPAS grid artifact."""
    path = Path(path)
    digest = file_sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            f"{path}: SHA-256 {digest} != expected {expected_sha256}")
    with Dataset(path) as ds:
        required = (
            "latCell", "lonCell", "areaCell", "latVertex", "lonVertex",
            "verticesOnEdge", "cellsOnEdge", "bdyMaskCell",
        )
        missing = [variable for variable in required if variable not in ds.variables]
        if missing:
            raise ValueError(f"{path}: missing MPAS grid variables {missing}")
        n_cells = len(ds.dimensions["nCells"])
        if expected_n_cells is not None and n_cells != expected_n_cells:
            raise ValueError(
                f"{path}: nCells={n_cells}, expected {expected_n_cells}")
        lat = np.degrees(np.asarray(ds.variables["latCell"][:], dtype=float))
        lon = _degrees_longitude(
            np.asarray(ds.variables["lonCell"][:], dtype=float))
        area = np.asarray(ds.variables["areaCell"][:], dtype=float)
        bdy = np.asarray(ds.variables["bdyMaskCell"][:], dtype=np.int64)
        domain = domain_polygon_from_edges(
            ds.variables["latVertex"][:], ds.variables["lonVertex"][:],
            ds.variables["verticesOnEdge"][:], ds.variables["cellsOnEdge"][:])
        landmask = None
        if "landmask" in ds.variables:
            landmask = np.asarray(ds.variables["landmask"][:], dtype=np.int8).squeeze()
    for label, values in (("latCell", lat), ("lonCell", lon),
                          ("areaCell", area), ("bdyMaskCell", bdy)):
        if values.shape != (n_cells,):
            raise ValueError(f"{path}: {label} shape {values.shape} != ({n_cells},)")
    return MeshGeometry(
        name=name or path.stem,
        source_path=path,
        source_sha256=digest,
        lon=lon,
        lat=lat,
        spacing_km=equivalent_spacing_km(area),
        bdy_mask=bdy,
        domain=domain,
        native_landmask=landmask,
    )


def points_covered(geometry, x, y) -> np.ndarray:
    """Vectorised boundary-inclusive point membership with input shape kept."""
    x_arr, y_arr = np.broadcast_arrays(
        np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    result = covers(geometry, points(x_arr.ravel(), y_arr.ravel()))
    return np.asarray(result, dtype=bool).reshape(x_arr.shape)


def common_domain(meshes: Mapping[str, MeshGeometry],
                  mesh_names: Sequence[str] | None = None):
    """Exact polygon intersection for a selected pair or experiment set."""
    names = tuple(mesh_names or meshes.keys())
    if not names:
        raise ValueError("at least one mesh is required")
    geometry = meshes[names[0]].domain
    for name in names[1:]:
        geometry = geometry.intersection(meshes[name].domain)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    if geometry.is_empty:
        raise ValueError(f"meshes {names} have an empty geometric intersection")
    return geometry


def _unit_xyz(lon_deg, lat_deg) -> np.ndarray:
    lon = np.radians(np.asarray(lon_deg, dtype=float))
    lat = np.radians(np.asarray(lat_deg, dtype=float))
    return np.column_stack([
        np.cos(lat) * np.cos(lon),
        np.cos(lat) * np.sin(lon),
        np.sin(lat),
    ])


def nearest_source_mapping(mesh: MeshGeometry, target_lon, target_lat, *,
                           max_distance_km: float,
                           refined_threshold_km: float = 5.5) -> SourceMapping:
    """Map target points to cells while exposing distance and exclusion masks."""
    lon, lat = np.broadcast_arrays(
        np.asarray(target_lon, dtype=float), np.asarray(target_lat, dtype=float))
    tree = cKDTree(_unit_xyz(mesh.lon, mesh.lat))
    chord, source = tree.query(_unit_xyz(lon.ravel(), lat.ravel()), k=1)
    arc = 2.0 * np.arcsin(np.minimum(np.asarray(chord) / 2.0, 1.0))
    distance_km = (arc * EARTH_RADIUS_M / 1000.0).reshape(lon.shape)
    source = np.asarray(source, dtype=np.int64).reshape(lon.shape)
    inside = points_covered(mesh.domain, lon, lat)
    within_distance = distance_km <= float(max_distance_km)
    valid = inside & within_distance
    refined = valid & (mesh.spacing_km[source] < float(refined_threshold_km))
    relaxation = valid & (mesh.bdy_mask[source] > 0)
    native_landmask = None
    if mesh.native_landmask is not None:
        native_landmask = mesh.native_landmask[source]
    return SourceMapping(
        source_index=source,
        distance_km=distance_km,
        inside_domain=inside,
        within_distance=within_distance,
        valid=valid,
        refined=refined,
        relaxation=relaxation,
        native_landmask=native_landmask,
    )


def build_comparison_masks(meshes: Mapping[str, MeshGeometry], target_lon,
                           target_lat, *, mesh_names: Sequence[str] | None = None,
                           max_distance_km: float | Mapping[str, float] = 8.0,
                           refined_threshold_km: float = 5.5) -> ComparisonMasks:
    """Build total/interior/refined/relaxation masks for a pair or all meshes."""
    names = tuple(mesh_names or meshes.keys())
    geometry = common_domain(meshes, names)
    common = points_covered(geometry, target_lon, target_lat)
    mappings = {}
    for name in names:
        limit = max_distance_km[name] if isinstance(max_distance_km, Mapping) \
            else max_distance_km
        mappings[name] = nearest_source_mapping(
            meshes[name], target_lon, target_lat,
            max_distance_km=float(limit),
            refined_threshold_km=refined_threshold_km)
    valid_all = common.copy()
    refined_all = common.copy()
    relaxation_any = np.zeros(common.shape, dtype=bool)
    for mapping in mappings.values():
        valid_all &= mapping.valid
        refined_all &= mapping.refined
        relaxation_any |= mapping.relaxation
    relaxation_any &= valid_all
    interior = valid_all & ~relaxation_any
    interior_refined = refined_all & ~relaxation_any
    return ComparisonMasks(
        mesh_names=names,
        common_geometry=geometry,
        mappings=mappings,
        common_domain=common,
        valid_all=valid_all,
        refined_all=refined_all,
        relaxation_any=relaxation_any,
        interior=interior,
        interior_refined=interior_refined,
    )


def _local_crs(geometry, projection: str) -> CRS:
    centre = geometry.centroid
    return CRS.from_proj4(
        f"+proj={projection} +lat_0={centre.y} +lon_0={centre.x} "
        "+datum=WGS84 +units=m +no_defs")


def classify_destination_surface(target_lon, target_lat, land_geometry, *,
                                 source: str,
                                 coast_widths_km: Sequence[float] = (10, 25, 50)) -> SurfaceMasks:
    """Classify land/ocean and configurable coastal bands on the target grid.

    ``land_geometry`` must be a documented WGS84 land polygon clipped to the
    study region. It is intentionally independent of every native MPAS
    ``landmask``; disagreements can then be measured instead of hidden.
    """
    if not source.strip():
        raise ValueError("a land-reference source description is required")
    widths = tuple(float(value) for value in coast_widths_km)
    if any(value <= 0 for value in widths):
        raise ValueError("coastal widths must be positive")
    lon, lat = np.broadcast_arrays(
        np.asarray(target_lon, dtype=float), np.asarray(target_lat, dtype=float))
    land = points_covered(land_geometry, lon, lat)
    crs = _local_crs(land_geometry, "aeqd")
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    land_projected = transform_geometry(forward.transform, land_geometry)
    x, y = forward.transform(lon.ravel(), lat.ravel())
    point_array = points(np.asarray(x), np.asarray(y))
    coast_distance = np.asarray(
        distance(land_projected.boundary, point_array), dtype=float
    ).reshape(lon.shape) / 1000.0
    return SurfaceMasks(
        source=source,
        land=land,
        ocean=~land,
        distance_to_coast_km=coast_distance,
        coastal={width: coast_distance <= width for width in widths},
    )


def compare_native_surface(surface: SurfaceMasks, mapping: SourceMapping, *,
                           native_source: str,
                           native_landmask=None) -> NativeSurfaceComparison:
    """Compare the destination reference with a provenance-labelled native mask.

    ``native_landmask`` may be a source-cell array loaded from a stable static
    artifact or future field cache. If omitted, the mesh grid's landmask is
    used when one exists. This keeps relaxation geometry tied to the stable
    grid while avoiding any dependence on EXP02's broken init/LBC symlinks.
    """
    if not native_source.strip():
        raise ValueError("a native-landmask source description is required")
    if native_landmask is None:
        if mapping.native_landmask is None:
            raise ValueError("no native landmask was supplied or mapped")
        native = np.asarray(mapping.native_landmask)
    else:
        source = np.asarray(native_landmask)
        if source.ndim != 1 or source.size <= int(np.max(mapping.source_index)):
            raise ValueError("native_landmask is not a complete source-cell array")
        native = source[mapping.source_index]
    native_land = native != 0
    disagreement = mapping.valid & (native_land != surface.land)
    return NativeSurfaceComparison(
        destination_source=surface.source,
        native_source=native_source,
        native_land=native_land,
        disagreement=disagreement,
    )


def equal_area_grid(domain_geometry, *, spacing_km: float = 5.0) -> EqualAreaGrid:
    """Create a local LAEA grid for reproducible area-weighted statistics."""
    if spacing_km <= 0:
        raise ValueError("spacing_km must be positive")
    crs = _local_crs(domain_geometry, "laea")
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inverse = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    projected = transform_geometry(forward.transform, domain_geometry)
    spacing = float(spacing_km) * 1000.0
    minx, miny, maxx, maxy = projected.bounds
    xs = np.arange(np.floor(minx / spacing) * spacing + 0.5 * spacing,
                   maxx, spacing)
    ys = np.arange(np.floor(miny / spacing) * spacing + 0.5 * spacing,
                   maxy, spacing)
    xx, yy = np.meshgrid(xs, ys)
    inside = points_covered(projected, xx, yy)
    lon, lat = inverse.transform(xx, yy)
    return EqualAreaGrid(
        x=xx,
        y=yy,
        lon=np.asarray(lon),
        lat=np.asarray(lat),
        inside_domain=inside,
        spacing_m=spacing,
        cell_area_m2=spacing ** 2,
        crs_wkt=crs.to_wkt(),
    )
