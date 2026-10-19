import unittest
from pathlib import Path
import tempfile

import pandas as pd
import xarray as xr

from mpas_meqbr import fields, io


REFERENCE_HASH = "9896c83795adf1fd3d8cb4606f48efee0c1163ea5a09c5e3b1b44be205cbcde5"


def history_series(times, prefix="history"):
    index = pd.DatetimeIndex(times)
    return pd.Series(
        [f"{prefix}-{i}.nc" for i in range(len(index))], index=index, name="path")


def cache(experiment, times):
    index = io.validate_time_index(times)
    identity = io.temporal_identity(index)
    ds = xr.Dataset(coords={"valid_time": ("sample_time", index.values)})
    ds.attrs.update({
        "experiment": experiment,
        "window_start": str(index[0]),
        "window_end": str(index[-1]),
        "n_hours": len(index),
        **identity,
    })
    return ds


class TimeIntegrityTests(unittest.TestCase):
    def test_reference_hash_and_encoding(self):
        times = pd.date_range("2021-11-01 00:00", "2021-12-01 00:00", freq="h")
        identity = io.temporal_identity(times)
        self.assertEqual(identity["time_count"], 721)
        self.assertEqual(identity["time_sha256"], REFERENCE_HASH)
        text = io.canonical_time_text(times)
        self.assertTrue(text.startswith("2021-11-01T00:00:00\n"))
        self.assertTrue(text.endswith("2021-12-01T00:00:00"))
        self.assertFalse(text.endswith("\n"))

    def test_spinup_is_excluded_by_scientific_window(self):
        all_times = pd.date_range("2021-10-21", "2021-11-01 02:00", freq="h")
        selected = io.select_window(
            history_series(all_times), "2021-11-01 00:00", "2021-12-01 00:00")
        self.assertEqual(selected.index[0], pd.Timestamp("2021-11-01 00:00"))
        self.assertEqual(len(selected), 3)

    def test_duplicate_timestamp_is_rejected(self):
        times = pd.DatetimeIndex([
            "2021-11-01 00:00", "2021-11-01 01:00", "2021-11-01 01:00"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            io.validate_time_index(times)

    def test_internal_gap_is_rejected(self):
        times = pd.DatetimeIndex([
            "2021-11-01 00:00", "2021-11-01 01:00", "2021-11-01 03:00"])
        with self.assertRaisesRegex(ValueError, "unexpected interval"):
            io.validate_time_index(times)

    def test_exact_common_index_is_used_not_min_max_slice(self):
        a = history_series(pd.date_range("2021-11-01 00:00", periods=5, freq="h"), "a")
        b = history_series(pd.date_range("2021-11-01 01:00", periods=3, freq="h"), "b")
        aligned, common = io.common_history_indices({"A": a, "B": b})
        expected = pd.date_range("2021-11-01 01:00", periods=3, freq="h")
        self.assertTrue(common.equals(expected))
        self.assertTrue(aligned["A"].index.equals(expected))
        self.assertTrue(aligned["B"].index.equals(expected))

    def test_gap_cannot_disappear_during_intersection(self):
        complete = history_series(pd.date_range("2021-11-01", periods=4, freq="h"))
        gapped = complete.drop(pd.Timestamp("2021-11-01 02:00"))
        with self.assertRaisesRegex(ValueError, "unexpected interval"):
            io.common_history_indices({"complete": complete, "gapped": gapped})

    def test_distinct_sets_are_rejected(self):
        a = history_series(pd.date_range("2021-11-01", periods=3, freq="h"))
        b = history_series(pd.date_range("2021-11-01 01:00", periods=3, freq="h"))
        with self.assertRaisesRegex(ValueError, "timestamp sets differ"):
            io.assert_identical_time_indexes({"A": a, "B": b})

    def test_cache_comparison_requires_exact_identity(self):
        times = pd.date_range("2021-11-01", periods=3, freq="h")
        fields.assert_same_window(cache("A", times), cache("B", times))

        legacy = xr.Dataset()
        legacy.attrs.update({
            "experiment": "legacy",
            "window_start": str(times[0]),
            "window_end": str(times[-1]),
        })
        with self.assertRaisesRegex(ValueError, "lacks exact temporal identity"):
            fields.assert_same_window(cache("A", times), legacy)

    def test_temporal_identity_survives_netcdf_roundtrip(self):
        times = pd.date_range("2021-11-01", periods=4, freq="h")
        original = cache("A", times)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.nc"
            original.to_netcdf(path)
            with xr.open_dataset(path) as restored:
                fields.assert_same_window(original, restored)
                self.assertEqual(restored.attrs["time_count"], 4)
                self.assertEqual(
                    restored.attrs["time_sha256"],
                    io.temporal_identity(times)["time_sha256"])


if __name__ == "__main__":
    unittest.main()
