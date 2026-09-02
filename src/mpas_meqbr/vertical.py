"""MPAS vertical grid: where each variable actually lives.

MPAS is vertically staggered. ``zgrid`` and ``w`` are on layer **interfaces**
(``nVertLevelsP1`` = 56); winds, ``theta``, ``rho``, ``pressure`` and ``relhum``
are at layer **centers** (``nVertLevels`` = 55), the midpoint of two adjacent
interfaces.

The interface set (``zeta_wind.txt``) was chosen so that over flat terrain the
centers land exactly on 12.5, 50, 100, 150, 200, 250 m ... — the turbine-relevant
heights. That makes it tempting to hardcode a level index. Do not: over land the
terrain-following coordinate shifts the centers, and the guarantee only holds
where terrain height is zero. Always derive the heights and match, which is what
:func:`match_heights` does (and it asserts the match is within tolerance).
"""

from __future__ import annotations

import numpy as np


def layer_center_heights(zgrid) -> np.ndarray:
    """Layer-center heights (m MSL) from interface heights, last axis vertical."""
    z = np.asarray(zgrid)
    return 0.5 * (z[..., :-1] + z[..., 1:])


def heights_above_ground(zgrid) -> np.ndarray:
    """Layer-center heights above local terrain.

    ``zgrid[..., 0]`` is the surface interface (terrain height), so over ocean
    (terrain 0) this equals the MSL heights.
    """
    z = np.asarray(zgrid)
    return layer_center_heights(z) - z[..., 0:1]


def match_heights(heights_agl, targets, tolerance_m: float = 1.0) -> dict:
    """Map each target height (m AGL) to the nearest layer-center index.

    Raises if any target has no center within *tolerance_m*, which is the point:
    a silent 30 m mismatch would quietly bias every metric computed from it.
    Returns ``{target: (index, actual_height)}``.
    """
    h = np.asarray(heights_agl, dtype=float)
    if h.ndim != 1:
        raise ValueError("expected a 1-D height profile for a single cell")
    out = {}
    bad = []
    for t in targets:
        k = int(np.argmin(np.abs(h - t)))
        if abs(h[k] - t) > tolerance_m:
            bad.append((t, float(h[k])))
        out[t] = (k, float(h[k]))
    if bad:
        detail = "; ".join(f"{t} m -> nearest center {a:.2f} m" for t, a in bad)
        raise ValueError(
            f"no model layer center within {tolerance_m} m of: {detail}. "
            "The vertical grid is not what config/experiments.yaml assumes.")
    return out


def shear_exponent(speed_lower, speed_upper, z_lower, z_upper):
    """Power-law wind shear exponent alpha, from ``U(z) ~ z**alpha``.

    ``alpha = ln(U2/U1) / ln(z2/z1)``. Undefined (NaN) where either speed is
    non-positive — calm periods, where shear is meaningless anyway.
    """
    u1 = np.asarray(speed_lower, dtype=float)
    u2 = np.asarray(speed_upper, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        alpha = np.log(u2 / u1) / np.log(z_upper / z_lower)
    return np.where((u1 > 0.05) & (u2 > 0.05), alpha, np.nan)
