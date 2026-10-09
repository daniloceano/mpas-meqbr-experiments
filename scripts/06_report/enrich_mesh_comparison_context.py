#!/usr/bin/env python3
"""Add lightweight cartographic context and validated stations to the mesh atlas.

This step deliberately leaves every mesh geometry and basin-coverage value
untouched.  It is intended to run in the existing cgfd-usp-mpas environment on
Swell, where the cached Natural Earth shapefiles are already available.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import shapefile
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union


ATLAS_EXTENT = (-65.0, -17.0, -24.0, 16.0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shapefile_hashes(path: Path) -> dict[str, str]:
    hashes = {}
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        component = path.with_suffix(suffix)
        if component.exists():
            hashes[component.name] = sha256(component)
    return hashes


def round_coordinates(value, digits: int = 5):
    if isinstance(value, list):
        if value and isinstance(value[0], (int, float)):
            return [round(float(item), digits) for item in value]
        return [round_coordinates(item, digits) for item in value]
    return value


def rounded_geojson(geometry) -> dict:
    result = mapping(geometry)
    result["coordinates"] = round_coordinates(result["coordinates"])
    return result


def clipped_lines(path: Path, *, brazil_only: bool, tolerance_deg: float):
    clip = box(*ATLAS_EXTENT)
    pieces = []
    reader = shapefile.Reader(str(path))
    fields = [field[0] for field in reader.fields[1:]]
    for item in reader.iterShapeRecords():
        properties = dict(zip(fields, item.record))
        if brazil_only and properties.get("ADM0_A3") != "BRA":
            continue
        geometry = shape(item.shape.__geo_interface__)
        if not geometry.intersects(clip):
            continue
        clipped = geometry.intersection(clip)
        if not clipped.is_empty:
            pieces.append(clipped)
    if not pieces:
        raise RuntimeError(f"No linework found in atlas extent for {path}")
    return unary_union(pieces).simplify(tolerance_deg, preserve_topology=False)


def load_surface_stations(path: Path) -> list[dict]:
    stations = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["kind"] != "inmet_auto":
                continue
            key = row["station"]
            station = stations.setdefault(
                key,
                {
                    "id": key,
                    "name": row["name"],
                    "label": row["name"].split(" (")[0].title(),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "kind": row["kind"],
                    "periods": set(),
                },
            )
            station["periods"].add(row["period"])
    result = []
    for station in stations.values():
        station["periods"] = sorted(station["periods"])
        result.append(station)
    return sorted(result, key=lambda item: item["lon"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--coastline", required=True)
    parser.add_argument("--country-boundaries", required=True)
    parser.add_argument("--states", required=True)
    parser.add_argument("--surface-stations", required=True)
    args = parser.parse_args()

    data_path = Path(args.data)
    coastline_path = Path(args.coastline)
    country_boundaries_path = Path(args.country_boundaries)
    states_path = Path(args.states)
    station_path = Path(args.surface_stations)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    coastline = clipped_lines(
        coastline_path, brazil_only=False, tolerance_deg=0.015
    )
    country_boundaries = clipped_lines(
        country_boundaries_path, brazil_only=False, tolerance_deg=0.01
    )
    state_boundaries = clipped_lines(
        states_path, brazil_only=True, tolerance_deg=0.01
    )

    data["cartography"] = {
        "extent": {"west": -65, "east": -24, "south": -17, "north": 16},
        "coastline": rounded_geojson(coastline),
        "country_boundaries": rounded_geojson(country_boundaries),
        "state_boundaries": rounded_geojson(state_boundaries),
        "provenance": {
            "dataset": "Natural Earth",
            "scale": "1:10m",
            "license": "public domain",
            "coastline_source": str(coastline_path),
            "coastline_hashes": shapefile_hashes(coastline_path),
            "country_boundaries_source": str(country_boundaries_path),
            "country_boundaries_hashes": shapefile_hashes(
                country_boundaries_path
            ),
            "state_boundaries_source": str(states_path),
            "state_boundaries_hashes": shapefile_hashes(states_path),
            "browser_simplification": (
                "recorte ao enquadramento original e simplificação de "
                "aproximadamente 1–2 km em coordenadas geográficas"
            ),
        },
    }
    data["surface_stations"] = load_surface_stations(station_path)
    data["station_provenance"] = {
        "lidars": "config/sites.yaml e data/metadata/observations_provenance.json",
        "surface": "results/tables/inmet_station_metrics.csv",
        "surface_archive": "NOAA NCEI Integrated Surface Database (ISD)",
        "surface_selection": (
            "estações automáticas INMET efetivamente presentes na análise "
            "observacional primária"
        ),
    }

    output = Path(args.output)
    output.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(output)
    print(
        f"coastline={coastline.geom_type}; "
        f"countries={country_boundaries.geom_type}; "
        f"states={state_boundaries.geom_type}"
    )
    print(f"surface_stations={len(data['surface_stations'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
