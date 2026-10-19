import numpy as np
import pandas as pd
import pytest

from mpas_meqbr import metrics


def test_candidate_blocks_never_cross_a_gap():
    times = pd.DatetimeIndex([
        "2022-10-01 00:00", "2022-10-01 01:00", "2022-10-01 02:00",
        "2022-10-01 06:00", "2022-10-01 07:00", "2022-10-01 08:00",
    ])
    blocks = metrics._contiguous_block_indices(times, block=2)
    assert blocks
    for block in blocks:
        selected = times[block]
        assert np.all(np.diff(selected.asi8) == pd.Timedelta(hours=1).value)


def test_gap_aware_ci_is_reproducible_and_paired():
    times = pd.date_range("2022-10-01", periods=120, freq="h").delete(
        list(range(48, 54)))
    obs = np.linspace(2.0, 8.0, len(times))
    model = obs + 1.0
    statistic = lambda o, m: float(np.mean(m - o))
    first = metrics.gap_aware_block_bootstrap_ci(
        times, obs, model, statistic, n_boot=100, seed=42)
    second = metrics.gap_aware_block_bootstrap_ci(
        times, obs, model, statistic, n_boot=100, seed=42)
    assert first == second
    assert first["value"] == pytest.approx(1.0)
    assert first["lo"] == pytest.approx(1.0)
    assert first["hi"] == pytest.approx(1.0)


def test_gap_aware_skill_has_expected_sign():
    times = pd.date_range("2021-11-01", periods=100, freq="h")
    obs = np.sin(np.arange(100) / 10) + 6
    reference = obs + 2.0
    model = obs + 1.0
    result = metrics.gap_aware_paired_skill_test(
        times, obs, reference, model, n_boot=100, seed=3)
    assert result["delta_mse"] > 0
    assert result["skill"] == pytest.approx(0.75)
    assert result["significant"]
