#!/usr/bin/env python
"""Export simplified coastline, land and state boundaries for the report maps.

The report's maps run offline (no tile server), so their geographic context
is embedded as a small GeoJSON-like structure: Natural Earth 1:10m land
polygons, coastline and first-order administrative lines (Brazilian states),
clipped to the union of the experiment domains and simplified for size.

Source: Natural Earth 1:10m (public domain), read from the cartopy cache
(``cartopy.io.shapereader.natural_earth`` downloads it on first use).

    python scripts/06_report/export_report_geography.py

Output: results/interactive/geo/geography.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr.config import REPO_ROOT                   # noqa: E402

# West, south, east, north: covers the buffered EXP02/EXP03 domains.
BBOX = (-62.0, -15.0, -26.0, 14.0)
LAYERS = {
    "land": ("physical", "land", 0.004),
    "coastline": ("physical", "coastline", 0.003),
    "states": ("cultural", "admin_1_states_provinces_lines", 0.004),
    "countries": ("cultural", "admin_0_boundary_lines_land", 0.004),
}


def _round(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [_round(v, nd) for v in obj]
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results/interactive/geo/geography.json")
    args = ap.parse_args()
    import geopandas
    from cartopy.io import shapereader

    clip = box(*BBOX)
    out = {"source": "Natural Earth 1:10m (public domain)",
           "created_by": "scripts/06_report/export_report_geography.py",
           "bbox": list(BBOX), "layers": {}}
    for key, (category, name, tolerance) in LAYERS.items():
        path = shapereader.natural_earth(resolution="10m", category=category, name=name)
        frame = geopandas.read_file(path, bbox=BBOX)
        if key == "states":
            cols = [c for c in frame.columns if c.lower() in {"adm0_name", "adm0_a3"}]
            if cols:
                frame = frame[frame[cols].astype(str).apply(
                    lambda r: r.str.contains("Brazil|BRA").any(), axis=1)]
        geoms = []
        for geom in frame.geometry:
            if geom is None or not geom.intersects(clip):
                continue
            part = geom.intersection(clip).simplify(tolerance, preserve_topology=True)
            if part.is_empty:
                continue
            gj = mapping(part)
            geoms.append({"type": "Feature", "properties": {},
                          "geometry": {"type": gj["type"],
                                       "coordinates": _round(gj["coordinates"])}})
        out["layers"][key] = {"type": "FeatureCollection", "features": geoms}
        print(f"  {key}: {len(geoms)} features")

    target = REPO_ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"-> {target.relative_to(REPO_ROOT)}  ({target.stat().st_size / 1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
