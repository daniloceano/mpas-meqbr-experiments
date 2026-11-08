"""Regression tests for Matplotlib boxplot label compatibility."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "06_audit"
    / "audit_exp06_sst.py"
)
SPEC = importlib.util.spec_from_file_location("audit_exp06_sst", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LegacyAxes:
    def __init__(self):
        self.labels = None

    def boxplot(self, values, labels=None, showfliers=True, whis=None):
        self.labels = labels
        return values, showfliers, whis


class ModernAxes:
    def __init__(self):
        self.tick_labels = None

    def boxplot(self, values, tick_labels=None, showfliers=True, whis=None):
        self.tick_labels = tick_labels
        return values, showfliers, whis


def test_boxplot_uses_legacy_labels_keyword():
    axes = LegacyAxes()
    MODULE.boxplot_with_compatible_labels(axes, [[1.0]], ["sst"])
    assert axes.labels == ["sst"]


def test_boxplot_uses_modern_tick_labels_keyword():
    axes = ModernAxes()
    MODULE.boxplot_with_compatible_labels(axes, [[1.0]], ["sst"])
