"""Regression test for the portable report's linked companion bundle."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "06_report"
    / "build_technical_report.py"
)
SPEC = importlib.util.spec_from_file_location("build_technical_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_copy_companion_report_preserves_nested_files(tmp_path, monkeypatch):
    source = tmp_path / "results" / "report" / "sst-fix-comparison"
    (source / "figures").mkdir(parents=True)
    (source / "index.html").write_text("comparison", encoding="utf-8")
    (source / "figures" / "plot.png").write_bytes(b"png")
    report_dir = tmp_path / "results" / "candidate"
    report_dir.mkdir(parents=True)
    monkeypatch.setattr(MODULE, "REPO_ROOT", tmp_path)

    records = MODULE.copy_companion_report(report_dir)

    assert (report_dir / "sst-fix-comparison" / "index.html").read_text(
        encoding="utf-8"
    ) == "comparison"
    assert (report_dir / "sst-fix-comparison" / "figures" / "plot.png").read_bytes() == b"png"
    assert {record["bundled_as"] for record in records} == {
        "sst-fix-comparison/index.html",
        "sst-fix-comparison/figures/plot.png",
    }
