from pathlib import Path
import unittest

from mpas_meqbr.config import load_config
from mpas_meqbr import plotting


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/archive/MPAS-Research/runs/meqbr_05km")
        self.cfg = load_config(runs_root=self.root)

    def test_existing_experiment_path_is_unchanged(self):
        leg = self.cfg.leg("CTL", "2021")
        self.assertEqual(
            leg.history_dir,
            self.root / "CTL" / "20211101_20211201")
        self.assertEqual(leg.mesh, "meqbr_05km")

    def test_oval_uses_portable_sibling_override(self):
        leg = self.cfg.leg("EXP03", "2021")
        self.assertEqual(
            leg.history_dir,
            Path("/archive/MPAS-Research/runs/meqbr_05km_oval_meq02a")
            / "20211101_20211201")
        self.assertEqual(leg.mesh, "meqbr_05km_oval_meq02a")
        self.assertEqual(leg.expected_history_records, 721)
        self.assertTrue(leg.sst_update)

    def test_stable_grid_paths_do_not_use_init_links(self):
        self.assertEqual(
            self.cfg.mesh_file("meqbr_05km_oval_meq02a"),
            Path("/archive/MPAS-Research/grids/meqbr_05km_oval_meq02a")
            / "meqbr_05km_oval_meq02a.grid.nc")
        self.assertEqual(
            self.cfg.leg("EXP02", "2021").mesh_file,
            Path("/archive/MPAS-Research/grids/meqbr_05km_buf")
            / "meqbr_05km_buf.grid.nc")

    def test_oval_metadata_and_visual_identity(self):
        mesh = self.cfg.meshes["meqbr_05km_oval_meq02a"]
        self.assertEqual(mesh["n_cells"], 102_968)
        self.assertEqual(mesh["refined_cells"], 86_109)
        self.assertEqual(len(mesh["sha256"]), 64)
        self.assertEqual(len(self.cfg.meshes["meqbr_05km"]["sha256"]), 64)
        self.assertEqual(len(self.cfg.meshes["meqbr_05km_buf"]["sha256"]), 64)
        self.assertIn("EXP03", plotting.EXPERIMENT_ORDER)
        self.assertIn("EXP03", plotting.EXPERIMENT_COLORS)

    def test_oval_has_only_confirmed_2021_period(self):
        self.assertEqual(
            self.cfg.experiments["EXP03"]["periods"], ["2021", "2022"])
        with self.assertRaises(KeyError):
            self.cfg.leg("UNKNOWN", "2021")

    def test_exp04_to_exp06_use_original_mesh_and_confirmed_physics(self):
        for experiment in ("EXP04", "EXP05", "EXP06"):
            meta = self.cfg.experiments[experiment]
            self.assertEqual(meta["mesh"], "meqbr_05km")
            self.assertEqual(meta["land_surface_scheme"], "sf_noah")
            self.assertEqual(meta["periods"], ["2021", "2022"])
            self.assertIn(experiment, plotting.EXPERIMENT_ORDER)
            self.assertIn(experiment, plotting.EXPERIMENT_COLORS)
        self.assertEqual(self.cfg.experiments["EXP04"]["pbl_scheme"], "bl_mynn")
        self.assertEqual(
            self.cfg.experiments["EXP05"]["convection_scheme"],
            "cu_grell_freitas",
        )
        self.assertTrue(self.cfg.experiments["EXP06"]["sstdiurn_update"])


if __name__ == "__main__":
    unittest.main()
