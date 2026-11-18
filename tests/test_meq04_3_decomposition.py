"""MEQ-04.3: the MSE decomposition is an exact identity."""
import importlib.util
from pathlib import Path

import numpy as np

_p = Path(__file__).resolve().parents[1] / "scripts" / "04_era5" / "paired_components.py"
_spec = importlib.util.spec_from_file_location("paired_components", _p)
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


def test_decomposition_identity_is_exact():
    rng = np.random.default_rng(0)
    o = rng.gamma(4.0, 2.0, 700)
    m = 0.7 * o + rng.normal(1.0, 1.5, o.size)
    d = pc.decompose(o, m)
    assert abs(d["residual"]) < 1e-10
    assert np.isclose(d["rmse"], np.sqrt(np.mean((m - o) ** 2)))
