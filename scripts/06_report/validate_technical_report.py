#!/usr/bin/env python3
"""Validate the portable MEQ-Br technical report without recomputing science."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_SECTIONS = [
    "introducao",
    "resultados-modelo",
    "rede-observacional",
    "validacao",
    "valor-adicionado",
    "mecanismos",
    "sintese",
]
EXPERIMENTS = {"CTL", "EXP01", "EXP02", "EXP03"}
PERIODS = {"2021", "2022"}


def finite_mean(values: list[object]) -> float | None:
    valid = []
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            valid.append(numeric)
    return sum(valid) / len(valid) if valid else None


def winner_sources(rows: list[dict], key: str, mode: str) -> list[str]:
    available = [row for row in rows
                 if row.get(key) is not None and math.isfinite(float(row[key]))]
    if not available:
        return []
    transformed = lambda row: abs(float(row[key])) if mode == "abs" else float(row[key])
    target = max(map(transformed, available)) if mode == "max" else min(map(transformed, available))
    return [row["source"] for row in available
            if abs(transformed(row) - target) < 1e-10]


def skill_class(row: dict) -> str:
    values = [row.get("skill_vs_era5"), row.get("skill_lo"), row.get("skill_hi")]
    if any(value is None or not math.isfinite(float(value)) for value in values):
        return "not_evaluated"
    if float(row["skill_lo"]) > 0:
        return "gain"
    if float(row["skill_hi"]) < 0:
        return "loss"
    return "not_detected"


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.section_ids: list[str] = []
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.append(element_id)
            if tag == "section":
                self.section_ids.append(element_id)
        for attribute in ("src", "href"):
            value = values.get(attribute)
            if value:
                self.references.append((attribute, value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def embedded_json(html: str, element_id: str) -> dict:
    pattern = rf'<script[^>]*id="{re.escape(element_id)}"[^>]*>(.*?)</script>'
    match = re.search(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        raise AssertionError(f"missing embedded JSON: {element_id}")
    return json.loads(match.group(1))


def validate_record(record: dict, root: Path) -> None:
    path = root / record["path"]
    assert path.is_file(), f"missing manifest file: {record['path']}"
    assert path.stat().st_size == record["bytes"], f"size mismatch: {record['path']}"
    assert sha256(path) == record["sha256"], f"hash mismatch: {record['path']}"


def validate_javascript(html: str) -> None:
    scripts = [
        body for attrs, body in re.findall(
            r"<script([^>]*)>(.*?)</script>", html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if "application/json" not in attrs.lower()
    ]
    node = shutil.which("node")
    if node:
        process = subprocess.run(
            [node, "--check", "-"], input="\n".join(scripts), text=True,
            capture_output=True, check=False,
        )
        assert process.returncode == 0, process.stderr


def validate_report(report_dir: Path) -> dict:
    index = report_dir / "index.html"
    manifest_path = report_dir / "report_manifest.json"
    assert index.is_file(), f"missing {index}"
    assert manifest_path.is_file(), f"missing {manifest_path}"
    html = index.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    parser = ReportParser()
    parser.feed(html)
    duplicates = [key for key, count in Counter(parser.ids).items() if count > 1]
    assert not duplicates, f"duplicate HTML ids: {duplicates}"
    assert parser.section_ids == MAIN_SECTIONS, parser.section_ids

    external = []
    missing = []
    for attribute, value in parser.references:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https", "//"}:
            external.append(value)
            continue
        if parsed.scheme or value.startswith("#"):
            continue
        target = report_dir / unquote(parsed.path)
        if not target.exists():
            missing.append((attribute, value))
    assert not external, f"external runtime dependencies: {external}"
    assert not missing, f"broken local references: {missing}"

    assert manifest.get("editorial_schema_version") == 2
    validate_record(manifest["index"], REPO_ROOT)
    for record in manifest.get("table_files", []):
        validate_record(record, REPO_ROOT)
    for record in manifest.get("interactive_data", []):
        validate_record(record, REPO_ROOT)
    for asset in manifest.get("assets", []):
        bundled = report_dir / asset["bundled_as"]
        assert bundled.is_file(), f"missing asset: {asset['bundled_as']}"
        assert bundled.stat().st_size == asset["bytes"], asset["bundled_as"]
        assert sha256(bundled) == asset["sha256"], asset["bundled_as"]

    tables = embedded_json(html, "table-data")
    assert len(tables) == len(manifest["table_files"])
    for table_id, table in tables.items():
        assert table["id"] == table_id
        assert table["rows"], f"empty table: {table_id}"
        assert table["columns"], f"no columns: {table_id}"
        for row in table["rows"]:
            assert set(row["values"]) == set(table["columns"]), table_id
            assert set(row["raw"]) == set(table["columns"]), table_id

    validation = embedded_json(html, "validation-data")
    assert set(validation["sources"]) == EXPERIMENTS | {"ERA5"}
    assert set(validation["periods"]) == PERIODS
    assert {point["network"] for point in validation["points"]} == {"LiDAR", "INMET"}
    assert {point["point"] for point in validation["points"]} >= {"P0", "LPI"}
    for point in validation["points"]:
        assert point["available_periods"], point["point"]
        assert point["available_heights_m"], point["point"]
    for item in validation["media"]:
        assert (report_dir / item["url"]).is_file(), item["url"]
        assert item["kind"] == "pre_rendered_image"

    grouped_metrics: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for row in validation["metrics"]:
        grouped_metrics[(row["point"], row["period"], int(row["height_m"]))].append(row)
    for key, rows in grouped_metrics.items():
        sources = {row["source"] for row in rows}
        assert EXPERIMENTS <= sources, f"incomplete MPAS metric group: {key}: {sources}"

    # P0/2021/150 m is the regression case for highlights hidden by display filters.
    regression = grouped_metrics[("P0", "2021", 150)]
    mpas_regression = [row for row in regression if row["source"] in EXPERIMENTS]
    rmse_winner = min(mpas_regression, key=lambda row: row["rmse"])
    assert rmse_winner["source"] == "EXP02"
    assert abs(float(rmse_winner["rmse"]) - 1.875137722760282) < 1e-12
    visible_without_winner = [row for row in mpas_regression if row["source"] != "EXP02"]
    assert min(visible_without_winner, key=lambda row: row["rmse"])["source"] == "EXP03"
    # The scientific winner remains EXP02; EXP03 is only the best visible card.
    assert min(mpas_regression, key=lambda row: row["rmse"])["source"] == "EXP02"
    # Synthetic edge cases: ties, missing values and distinct metric directions.
    synthetic = [
        {"source": "CTL", "rmse": 2.0, "bias": -1.0, "r": None},
        {"source": "EXP01", "rmse": 2.0, "bias": 0.5, "r": 0.7},
        {"source": "EXP02", "rmse": None, "bias": -0.5, "r": 0.8},
    ]
    assert winner_sources(synthetic, "rmse", "min") == ["CTL", "EXP01"]
    assert winner_sources(synthetic, "bias", "abs") == ["EXP01", "EXP02"]
    assert winner_sources(synthetic, "r", "max") == ["EXP02"]

    lidar_rows = [row for row in validation["metrics"]
                  if row["network"] == "LiDAR" and row["source"] in EXPERIMENTS]
    aggregate_checks = {}
    gain_loss_checks = {}
    for source in sorted(EXPERIMENTS):
        source_rows = [row for row in lidar_rows if row["source"] == source]
        aggregate_checks[source] = {
            "units": len(source_rows),
            "mean_bias": finite_mean([row["bias"] for row in source_rows]),
            "mean_rmse": finite_mean([row["rmse"] for row in source_rows]),
            "mean_r": finite_mean([row["r"] for row in source_rows]),
            "mean_skill": finite_mean([row["skill_vs_era5"] for row in source_rows]),
        }
        counts = Counter(skill_class(row) for row in source_rows)
        assert sum(counts.values()) == len(source_rows)
        gain_loss_checks[source] = dict(counts)

    lidar_100m_checks = {}
    expected_lidar_100m = {
        "CTL": (-1.0998710769131232, 2.243655841897017,
                0.5666795634591967, 0.17934137420982305),
        "EXP01": (-0.7497034378720098, 2.0453162744981945,
                  0.5837790732296919, 0.3188172872931303),
        "EXP02": (-0.6906099989170389, 1.970932961688233,
                  0.6038525946755653, 0.3669892068107167),
        "EXP03": (-0.6331600752682179, 1.9035545340734696,
                  0.6138644525013789, 0.4101478739203668),
    }
    for source in sorted(EXPERIMENTS):
        source_rows = [row for row in lidar_rows
                       if row["source"] == source and int(row["height_m"]) == 100]
        assert {(row["point"], row["period"]) for row in source_rows} == {
            ("P0", "2021"), ("LPI", "2022")}
        values = (
            finite_mean([row["bias"] for row in source_rows]),
            finite_mean([row["rmse"] for row in source_rows]),
            finite_mean([row["r"] for row in source_rows]),
            finite_mean([row["skill_vs_era5"] for row in source_rows]),
        )
        assert all(value is not None for value in values)
        assert all(abs(float(value) - expected) < 1e-12
                   for value, expected in zip(values, expected_lidar_100m[source]))
        lidar_100m_checks[source] = {
            "units": len(source_rows), "mean_bias": values[0],
            "mean_rmse": values[1], "mean_r": values[2],
            "mean_skill": values[3],
        }

    p0_250 = [row for row in lidar_rows
              if row["point"] == "P0" and int(row["height_m"]) == 250]
    assert len(p0_250) == 4
    assert {row["selection_role"] for row in p0_250} == {"descriptive_only"}

    independent_csv = REPO_ROOT / "results/tables/validation_point_metrics.csv"
    with independent_csv.open(newline="", encoding="utf-8") as handle:
        csv_rows = list(csv.DictReader(handle))
    csv_lidar = [row for row in csv_rows
                 if row["network"] == "LiDAR" and row["source"] in EXPERIMENTS]
    for source in sorted(EXPERIMENTS):
        source_rows = [row for row in csv_lidar if row["source"] == source]
        expected = aggregate_checks[source]
        assert len(source_rows) == expected["units"]
        for key, csv_key in (("mean_bias", "bias"), ("mean_rmse", "rmse"),
                             ("mean_r", "r"), ("mean_skill", "skill_vs_era5")):
            observed = finite_mean([row[csv_key] for row in source_rows])
            assert observed is not None and expected[key] is not None
            assert abs(observed - expected[key]) < 1e-12, (source, key, observed, expected[key])

    selection_rows = [row["raw"] for row in tables["selection"]["rows"]]
    first_pair = selection_rows[0]
    assert float(first_pair["delta_mse"]) > 0
    reversed_delta = -float(first_pair["delta_mse"])
    reversed_lo = -float(first_pair["hi"])
    reversed_hi = -float(first_pair["lo"])
    assert reversed_delta < 0 and reversed_lo < reversed_hi
    assert abs(reversed_lo + float(first_pair["hi"])) < 1e-12
    assert abs(reversed_hi + float(first_pair["lo"])) < 1e-12

    meteo = embedded_json(html, "meteo-data")
    assert set(meteo["experiments"]) == EXPERIMENTS
    assert set(meteo["periods"]) == PERIODS
    coverage: dict[str, set[tuple[str, str]]] = defaultdict(set)
    scales: dict[str, set[tuple[float, float]]] = defaultdict(set)
    animation_windows: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    available = [entry for entry in meteo["entries"] if entry.get("available", True)]
    assert available, "no available meteorological entries"
    for entry in available:
        assert entry["experiment"] in EXPERIMENTS
        assert entry["period"] in PERIODS
        assert (report_dir / entry["url"]).is_file(), entry["url"]
        coverage[entry["variable"]].add((entry["experiment"], entry["period"]))
        if entry["kind"] == "georaster":
            scales[entry["variable"]].add((entry["vmin"], entry["vmax"]))
        if entry["kind"] == "animation":
            animation_windows[(entry["variable"], entry["period"])].append(
                (entry["experiment"], float(entry["days"])))
    for variable, values in scales.items():
        assert len(values) == 1, f"inconsistent georaster scale for {variable}: {values}"
    shorter_windows = []
    for (variable, period), windows in animation_windows.items():
        longest = max(days for _, days in windows)
        for experiment, days in windows:
            if days < longest:
                shorter_windows.append(
                    f"{experiment}/{period}/{variable}: {days:g} d vs {longest:g} d"
                )
                entry = next(item for item in available if
                             item["experiment"] == experiment and
                             item["period"] == period and
                             item["variable"] == variable)
                assert "coverage_note" in entry, f"unmarked short animation: {experiment}/{period}/{variable}"

    for required in (
        "Não avaliado nesta altura",
        "Ganho detectável",
        "Perda detectável",
        "Diferença não detectável",
        "Exportar CSV filtrado",
        "PNG pré-renderizado",
        "Melhor resultado oculto pelos filtros",
        "Média aritmética dos RMSEs individuais",
        "MSE(A) − MSE(B)",
        "Ao inverter A e B, sinal e limites do IC são invertidos",
        "Murphy skill médio (adimensional)",
        "0,41 significa redução de 41% do MSE",
        "média das reduções relativas de MSE",
        "P0/250 m é descritivo",
    ):
        assert required in html, f"missing required wording: {required}"
    assert "new Set(['100'])" in html, "LiDAR default height is not 100 m"
    for required_id in (
        "resumo-descritivo", "summary-results", "gain-loss-results",
        "comparacao-direta", "pair-result", "network-to-validation",
    ):
        assert required_id in html, f"missing interactive component: {required_id}"
    validate_javascript(html)

    return {
        "sections": len(parser.section_ids),
        "ids": len(parser.ids),
        "local_references": len(parser.references),
        "tables": len(tables),
        "assets": len(manifest["assets"]),
        "validation_points": len(validation["points"]),
        "validation_metrics": len(validation["metrics"]),
        "highlight_regression": {
            "point": "P0", "period": "2021", "height_m": 150,
            "winner": rmse_winner["source"], "rmse": rmse_winner["rmse"],
        },
        "lidar_aggregate_checks": aggregate_checks,
        "lidar_100m_aggregate_checks": lidar_100m_checks,
        "lidar_gain_loss_checks": gain_loss_checks,
        "meteorological_entries": len(meteo["entries"]),
        "meteorological_available": len(available),
        "meteorological_variables": len(meteo["variables"]),
        "shorter_animation_windows": shorter_windows,
        "index_sha256": manifest["index"]["sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default="results/report")
    args = parser.parse_args()
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = REPO_ROOT / report_dir
    summary = validate_report(report_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
