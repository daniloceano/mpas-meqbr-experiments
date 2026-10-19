from pathlib import Path
import tempfile
import unittest

from netCDF4 import Dataset
import numpy as np
from shapely.geometry import box

from mpas_meqbr import spatial


def synthetic_mesh(name, domain, lon, spacing, bdy, landmask=None):
    lat = np.ones(len(lon), dtype=float)
    return spatial.MeshGeometry(
        name=name,
        source_path=Path(f"/{name}.grid.nc"),
        source_sha256=name,
        lon=np.asarray(lon, dtype=float),
        lat=lat,
        spacing_km=np.asarray(spacing, dtype=float),
        bdy_mask=np.asarray(bdy, dtype=int),
        domain=domain,
        native_landmask=(None if landmask is None
                         else np.asarray(landmask, dtype=np.int8)),
    )


class SpatialMaskTests(unittest.TestCase):
    def setUp(self):
        self.meshes = {
            "A": synthetic_mesh(
                "A", box(0, 0, 2, 2), [0.5, 1.5], [5.0, 7.0], [0, 1], [0, 1]),
            "B": synthetic_mesh(
                "B", box(1, 0, 3, 2), [1.1, 2.0], [5.0, 5.0], [0, 0], [1, 0]),
        }

    def test_common_domain_is_geometric_and_boundary_inclusive(self):
        geometry = spatial.common_domain(self.meshes, ("A", "B"))
        self.assertEqual(tuple(round(v, 6) for v in geometry.bounds), (1.0, 0.0, 2.0, 2.0))
        covered = spatial.points_covered(
            geometry, np.array([0.999, 1.0, 1.5, 2.0, 2.001]), np.ones(5))
        np.testing.assert_array_equal(covered, [False, True, True, True, False])

    def test_pair_and_four_mesh_domains_are_selectable(self):
        meshes = dict(self.meshes)
        meshes["C"] = synthetic_mesh(
            "C", box(0.5, 0, 2.5, 2), [1.0, 2.0], [5.0, 5.0], [0, 0])
        meshes["D"] = synthetic_mesh(
            "D", box(1.2, 0, 1.8, 2), [1.3, 1.7], [5.0, 5.0], [0, 0])
        pair = spatial.common_domain(meshes, ("A", "B"))
        four = spatial.common_domain(meshes, ("A", "B", "C", "D"))
        self.assertEqual(tuple(round(v, 6) for v in pair.bounds), (1.0, 0.0, 2.0, 2.0))
        self.assertEqual(tuple(round(v, 6) for v in four.bounds), (1.2, 0.0, 1.8, 2.0))

    def test_pair_masks_separate_valid_refined_and_relaxation(self):
        lon = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
        lat = np.ones(5)
        masks = spatial.build_comparison_masks(
            self.meshes, lon, lat, mesh_names=("A", "B"),
            max_distance_km=60.0, refined_threshold_km=5.5)
        np.testing.assert_array_equal(
            masks.common_domain, [False, True, True, True, False])
        np.testing.assert_array_equal(
            masks.valid_all, [False, True, True, True, False])
        self.assertFalse(masks.refined_all[2])
        self.assertTrue(masks.relaxation_any[2])
        self.assertFalse(masks.interior[2])

    def test_distance_limit_prevents_silent_extrapolation(self):
        mapping = spatial.nearest_source_mapping(
            self.meshes["A"], np.array([1.0]), np.array([1.0]),
            max_distance_km=10.0)
        self.assertTrue(mapping.inside_domain[0])
        self.assertFalse(mapping.within_distance[0])
        self.assertFalse(mapping.valid[0])

    def test_destination_land_ocean_coast_and_native_disagreement(self):
        lon = np.array([0.5, 1.0, 1.5])
        lat = np.ones(3)
        surface = spatial.classify_destination_surface(
            lon, lat, box(0, 0, 1, 2), source="synthetic WGS84 land polygon",
            coast_widths_km=(10, 25, 100))
        np.testing.assert_array_equal(surface.land, [True, True, False])
        self.assertTrue(surface.coastal[10.0][1])
        self.assertFalse(surface.coastal[25.0][0])
        self.assertTrue(surface.coastal[100.0][0])

        mapping = spatial.nearest_source_mapping(
            self.meshes["A"], lon, lat, max_distance_km=60.0)
        comparison = spatial.compare_native_surface(
            surface, mapping, native_source="synthetic MPAS landmask")
        self.assertEqual(comparison.disagreement.shape, lon.shape)
        self.assertEqual(comparison.destination_source,
                         "synthetic WGS84 land polygon")
        self.assertTrue(np.any(comparison.disagreement))

    def test_equal_area_grid_has_constant_nonzero_weights(self):
        grid = spatial.equal_area_grid(box(-1, -1, 1, 1), spacing_km=50)
        self.assertTrue(np.any(grid.inside_domain))
        self.assertEqual(grid.cell_area_m2, 2_500_000_000.0)
        self.assertTrue(np.all(grid.area_weights[grid.inside_domain] == grid.cell_area_m2))
        self.assertTrue(np.all(grid.area_weights[~grid.inside_domain] == 0.0))

    def test_read_stable_grid_checks_dimensions_hash_and_masks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.grid.nc"
            with Dataset(path, "w") as ds:
                ds.createDimension("nCells", 1)
                ds.createDimension("nEdges", 4)
                ds.createDimension("nVertices", 4)
                ds.createDimension("TWO", 2)
                ds.createVariable("latCell", "f8", ("nCells",))[:] = np.radians([0.5])
                ds.createVariable("lonCell", "f8", ("nCells",))[:] = np.radians([0.5])
                area = (5_000.0 / spatial.EARTH_RADIUS_M) ** 2 * np.sqrt(3.0) / 2.0
                ds.createVariable("areaCell", "f8", ("nCells",))[:] = [area]
                ds.createVariable("latVertex", "f8", ("nVertices",))[:] = np.radians([0, 0, 1, 1])
                ds.createVariable("lonVertex", "f8", ("nVertices",))[:] = np.radians([0, 1, 1, 0])
                ds.createVariable("verticesOnEdge", "i4", ("nEdges", "TWO"))[:] = [
                    [1, 2], [2, 3], [3, 4], [4, 1]]
                ds.createVariable("cellsOnEdge", "i4", ("nEdges", "TWO"))[:] = [
                    [1, 0], [1, 0], [1, 0], [1, 0]]
                ds.createVariable("bdyMaskCell", "i4", ("nCells",))[:] = [1]
                ds.createVariable("landmask", "i1", ("nCells",))[:] = [0]

            digest = spatial.file_sha256(path)
            mesh = spatial.read_mesh_geometry(
                path, name="synthetic", expected_n_cells=1,
                expected_sha256=digest)
            self.assertEqual(mesh.n_cells, 1)
            self.assertAlmostEqual(mesh.spacing_km[0], 5.0)
            self.assertEqual(mesh.bdy_mask[0], 1)
            self.assertTrue(mesh.domain.covers(box(0.4, 0.4, 0.6, 0.6)))
            with self.assertRaisesRegex(ValueError, "nCells"):
                spatial.read_mesh_geometry(path, expected_n_cells=2)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                spatial.read_mesh_geometry(path, expected_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
