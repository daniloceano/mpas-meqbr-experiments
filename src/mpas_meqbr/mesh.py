"""Working with the unstructured MPAS mesh: cell lookup, regridding, plotting.

Two meshes are in play (``meqbr_05km`` for CTL/EXP01, ``meqbr_05km_buf`` for
EXP02) and they do not share cell indices, so:

* a site's nearest cell must be located **per leg**, never cached across
  experiments;
* any experiment-vs-experiment *map* difference has to go through a common
  regular grid (:func:`regrid_to_latlon`), because the cells do not correspond.

Distances use a local-tangent-plane approximation (degrees scaled by
``cos(lat)``). Over the few hundred kilometres these lookups span, near the
equator, the error against a great-circle distance is well under a percent —
far below the ~5 km cell size the answer is quantised to anyway.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

KM_PER_DEG = 111.195


@dataclass(frozen=True)
class CellMatch:
    index: int
    lat: float
    lon: float
    distance_km: float
    is_ocean: bool


def _local_xy(lat, lon, lat0: float):
    """Degrees -> kilometres on a tangent plane centred on latitude *lat0*."""
    x = np.asarray(lon, dtype=float) * KM_PER_DEG * np.cos(np.deg2rad(lat0))
    y = np.asarray(lat, dtype=float) * KM_PER_DEG
    return x, y


def nearest_cells(lat_deg, lon_deg, site_lat: float, site_lon: float,
                  *, landmask=None, ocean_only: bool = True, k: int = 1):
    """The *k* nearest cells to a site, optionally restricted to ocean cells.

    ``ocean_only`` matters: both LiDAR sites are over water, and the nearest
    cell by raw distance can be a land cell whose surface fluxes, roughness and
    diurnal cycle are a different physical regime. Restricting the search is
    the honest comparison; the land/ocean decision is recorded in the result so
    a reader can see it was made.
    """
    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    is_ocean = (np.asarray(landmask) == 0) if landmask is not None else np.ones(lat.shape, bool)

    pool = np.flatnonzero(is_ocean) if (ocean_only and landmask is not None) \
        else np.arange(lat.size)
    x, y = _local_xy(lat[pool], lon[pool], site_lat)
    xs, ys = _local_xy(site_lat, site_lon, site_lat)
    tree = cKDTree(np.column_stack([x, y]))
    dist, idx = tree.query(np.array([[xs, ys]]), k=k)
    dist = np.atleast_1d(np.squeeze(dist))
    idx = np.atleast_1d(np.squeeze(idx))

    out = []
    for d, i in zip(dist, idx):
        c = int(pool[i])
        out.append(CellMatch(index=c, lat=float(lat[c]), lon=float(lon[c]),
                             distance_km=float(d), is_ocean=bool(is_ocean[c])))
    return out


def cell_tree(lat_deg, lon_deg, lat0: float | None = None) -> tuple:
    """A KD-tree over cell centres, for repeated nearest-cell queries."""
    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    lat0 = float(np.mean(lat)) if lat0 is None else lat0
    x, y = _local_xy(lat, lon, lat0)
    return cKDTree(np.column_stack([x, y])), lat0


def regrid_to_latlon(values, lat_deg, lon_deg, target_lat, target_lon,
                     *, max_distance_km: float | None = None, tree=None, lat0=None):
    """Nearest-neighbour interpolation of a cell field onto a regular grid.

    Nearest-neighbour rather than a smoother scheme on purpose: the point of a
    5 km run is its small-scale structure, and any averaging kernel wide enough
    to look smooth would remove exactly what is being evaluated. Choose the
    target grid finer than the mesh (0.05 deg here vs ~0.04 deg cells) so the
    regridding neither aliases nor smooths.

    Points farther than *max_distance_km* from any cell become NaN — this is
    what keeps the buffered mesh's coarse outer ring from being painted over
    the smaller mesh's blank area in a difference map.
    """
    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    if tree is None:
        tree, lat0 = cell_tree(lat, lon)
    glon, glat = np.meshgrid(np.asarray(target_lon), np.asarray(target_lat))
    gx, gy = _local_xy(glat.ravel(), glon.ravel(), lat0)
    dist, idx = tree.query(np.column_stack([gx, gy]), k=1)
    out = np.asarray(values, dtype=float)[idx].reshape(glat.shape)
    if max_distance_km is not None:
        out = np.where(dist.reshape(glat.shape) <= max_distance_km, out, np.nan)
    return out


def triangulation(lat_deg, lon_deg, extent=None):
    """A matplotlib Triangulation over the cell centres, for native-mesh maps.

    MPAS history output carries only cell *centres* (``latCell``/``lonCell``) —
    the Voronoi cell vertices live in the grid file, which is not part of the
    run output here. Delaunay triangulation of the centres is therefore the
    practical way to draw a continuous field on the native mesh, and at ~5 km
    spacing the visual difference from true Voronoi polygons is negligible.

    Pass *extent* ``(lon_min, lon_max, lat_min, lat_max)`` to triangulate only
    a sub-region: this both speeds things up and avoids long, thin triangles
    spanning the coarse outer ring of the buffered mesh.
    """
    from matplotlib.tri import Triangulation

    lat = np.asarray(lat_deg, dtype=float)
    lon = np.asarray(lon_deg, dtype=float)
    if extent is None:
        sel = np.ones(lat.shape, bool)
    else:
        lo0, lo1, la0, la1 = extent
        sel = (lon >= lo0) & (lon <= lo1) & (lat >= la0) & (lat <= la1)
    idx = np.flatnonzero(sel)
    return Triangulation(lon[idx], lat[idx]), idx


def transect_cells(lat_deg, lon_deg, start, end, n_points: int = 400):
    """Cells along a great-circle-ish straight transect from *start* to *end*.

    *start*/*end* are ``(lat, lon)``. Returns ``(cell_indices, along_km)`` with
    consecutive duplicates collapsed, so a transect finer than the mesh does not
    repeat the same cell.
    """
    lat0 = 0.5 * (start[0] + end[0])
    lats = np.linspace(start[0], end[0], n_points)
    lons = np.linspace(start[1], end[1], n_points)
    tree, lat0 = cell_tree(lat_deg, lon_deg, lat0)
    x, y = _local_xy(lats, lons, lat0)
    _, idx = tree.query(np.column_stack([x, y]), k=1)
    keep = np.concatenate([[True], np.diff(idx) != 0])
    cells = idx[keep]
    sx, sy = _local_xy(np.asarray(lat_deg)[cells], np.asarray(lon_deg)[cells], lat0)
    along = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(sx), np.diff(sy)))])
    return cells, along
