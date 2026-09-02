"""Verification and wind-resource statistics, plus the uncertainty machinery
used to rank the experiments.

Three groups, deliberately separate because they answer different questions:

1. **Verification** (:func:`basic_scores`) — how close is the model to the
   observation, hour by hour. Standard: bias, MAE, RMSE, centred RMSE,
   correlation, standard-deviation ratio, index of agreement, and the Takacs
   (1985) MSE decomposition into amplitude (dissipative) and phase (dispersive)
   error.

2. **Wind resource** (:func:`resource_scores`) — does the model reproduce the
   *distribution* that a resource assessment integrates over. Mean speed,
   Weibull A and k, and wind power density. WPD goes as U**3, so a +5 % speed
   bias is a +16 % energy bias: a model can have a respectable RMSE and still be
   unusable for resource work. This is the group that matters for the stated
   purpose of the runs.

3. **Uncertainty** (:func:`block_bootstrap_ci`, :func:`paired_skill_test`) —
   hourly wind errors are strongly autocorrelated, so an ordinary bootstrap (or
   a t-test on N=700 hours) would report intervals several times too narrow. A
   moving-block bootstrap with a block long enough to span the synoptic
   correlation scale is the standard fix, and it is what makes "EXP01 beats CTL"
   a defensible statement rather than an eyeball comparison.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AIR_DENSITY = 1.15   # kg m-3, representative of the tropical marine surface layer


# --------------------------------------------------------------------------
# 1. verification
# --------------------------------------------------------------------------

def _clean(obs, model):
    o = np.asarray(obs, dtype=float)
    m = np.asarray(model, dtype=float)
    ok = np.isfinite(o) & np.isfinite(m)
    return o[ok], m[ok]


def basic_scores(obs, model) -> dict:
    """Point-verification scores for a paired sample.

    ``mse`` decomposes exactly as ``bias**2 + mse_dissipative + mse_dispersive``
    (Takacs 1985): amplitude error from the standard-deviation mismatch, phase
    error from the imperfect correlation. The split says *how* a model is wrong
    — an experiment that fixes variance but not timing looks different from one
    that fixes timing but not variance, and they call for different next steps.
    """
    o, m = _clean(obs, model)
    n = o.size
    if n < 3:
        return {k: np.nan for k in (
            "n", "obs_mean", "model_mean", "bias", "mae", "rmse", "crmse", "r",
            "std_obs", "std_model", "std_ratio", "ioa", "mse",
            "mse_dissipative", "mse_dispersive")} | {"n": n}

    err = m - o
    bias = float(err.mean())
    mse = float((err ** 2).mean())
    std_o, std_m = float(o.std()), float(m.std())
    r = float(np.corrcoef(o, m)[0, 1]) if std_o > 0 and std_m > 0 else np.nan
    # Willmott's index of agreement: 1 = perfect, 0 = no agreement.
    denom = float(((np.abs(m - o.mean()) + np.abs(o - o.mean())) ** 2).sum())
    ioa = 1.0 - float((err ** 2).sum()) / denom if denom > 0 else np.nan

    return {
        "n": int(n),
        "obs_mean": float(o.mean()),
        "model_mean": float(m.mean()),
        "bias": bias,
        "mae": float(np.abs(err).mean()),
        "rmse": float(np.sqrt(mse)),
        "crmse": float(np.sqrt(max(mse - bias ** 2, 0.0))),
        "r": r,
        "std_obs": std_o,
        "std_model": std_m,
        "std_ratio": std_m / std_o if std_o > 0 else np.nan,
        "ioa": float(ioa),
        "mse": mse,
        "mse_dissipative": float((std_m - std_o) ** 2),
        "mse_dispersive": float(2.0 * std_m * std_o * (1.0 - r)) if np.isfinite(r) else np.nan,
    }


# --------------------------------------------------------------------------
# 2. wind resource
# --------------------------------------------------------------------------

def weibull_fit(speed) -> tuple:
    """Weibull scale A (m/s) and shape k by maximum likelihood, location fixed at 0.

    Location is fixed because a Weibull with a free lower bound can fit a wind
    distribution better numerically while being physically meaningless (it
    implies a minimum wind speed). Resource practice fixes it at zero.
    """
    from scipy.stats import weibull_min

    s = np.asarray(speed, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    if s.size < 30:
        return np.nan, np.nan
    k, _, A = weibull_min.fit(s, floc=0.0)
    return float(A), float(k)


def wind_power_density(speed, rho: float = AIR_DENSITY) -> float:
    """Mean available wind power density, ``0.5 * rho * mean(U**3)`` [W m-2].

    The cube is taken *before* averaging — using the cube of the mean instead
    understates WPD by 15-30 % for realistic distributions, and is a common and
    silent error.
    """
    s = np.asarray(speed, dtype=float)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return np.nan
    return float(0.5 * rho * np.mean(s ** 3))


def resource_scores(obs, model, rho: float = AIR_DENSITY) -> dict:
    """Distribution-level scores: mean speed, Weibull parameters, WPD.

    Computed on the *paired* sample, so obs and model see the same hours —
    otherwise a difference in data coverage would masquerade as a model error.
    """
    o, m = _clean(obs, model)
    if o.size < 30:
        return {k: np.nan for k in (
            "obs_wpd", "model_wpd", "wpd_bias", "wpd_rel_bias_pct",
            "obs_weibull_A", "obs_weibull_k", "model_weibull_A", "model_weibull_k",
            "speed_rel_bias_pct", "p90_obs", "p90_model")}
    wpd_o = wind_power_density(o, rho)
    wpd_m = wind_power_density(m, rho)
    A_o, k_o = weibull_fit(o)
    A_m, k_m = weibull_fit(m)
    return {
        "obs_wpd": wpd_o,
        "model_wpd": wpd_m,
        "wpd_bias": wpd_m - wpd_o,
        "wpd_rel_bias_pct": 100.0 * (wpd_m - wpd_o) / wpd_o if wpd_o else np.nan,
        "obs_weibull_A": A_o, "obs_weibull_k": k_o,
        "model_weibull_A": A_m, "model_weibull_k": k_m,
        "speed_rel_bias_pct": 100.0 * (m.mean() - o.mean()) / o.mean() if o.mean() else np.nan,
        "p90_obs": float(np.percentile(o, 90)),
        "p90_model": float(np.percentile(m, 90)),
    }


# --------------------------------------------------------------------------
# direction (circular statistics)
# --------------------------------------------------------------------------

def circular_mean(direction_deg) -> float:
    d = np.deg2rad(np.asarray(direction_deg, dtype=float))
    d = d[np.isfinite(d)]
    if d.size == 0:
        return np.nan
    return float(np.rad2deg(np.arctan2(np.sin(d).mean(), np.cos(d).mean())) % 360.0)


def angular_difference(a_deg, b_deg):
    """Signed difference ``a - b`` wrapped to (-180, 180]."""
    return (np.asarray(a_deg, dtype=float) - np.asarray(b_deg, dtype=float) + 180.0) % 360.0 - 180.0


def direction_scores(obs_dir, model_dir, obs_speed=None, speed_threshold: float = 2.0) -> dict:
    """Direction bias and MAE, computed with circular arithmetic.

    Directions are masked below *speed_threshold* m/s: at low wind the measured
    direction is dominated by instrument noise and carries no information about
    the model, so including it just adds scatter.
    """
    o = np.asarray(obs_dir, dtype=float)
    m = np.asarray(model_dir, dtype=float)
    ok = np.isfinite(o) & np.isfinite(m)
    if obs_speed is not None:
        ok &= np.asarray(obs_speed, dtype=float) >= speed_threshold
    if ok.sum() < 10:
        return {"n_dir": int(ok.sum()), "dir_bias": np.nan, "dir_mae": np.nan,
                "dir_obs_mean": np.nan, "dir_model_mean": np.nan}
    diff = angular_difference(m[ok], o[ok])
    return {
        "n_dir": int(ok.sum()),
        "dir_bias": float(np.rad2deg(np.arctan2(
            np.sin(np.deg2rad(diff)).mean(), np.cos(np.deg2rad(diff)).mean()))),
        "dir_mae": float(np.abs(diff).mean()),
        "dir_obs_mean": circular_mean(o[ok]),
        "dir_model_mean": circular_mean(m[ok]),
    }


# --------------------------------------------------------------------------
# diurnal cycle
# --------------------------------------------------------------------------

def diurnal_composite(times, values, tz_offset_hours: float = -3.0) -> pd.DataFrame:
    """Mean and standard deviation by hour of *local* time.

    Local time (UTC-3 on this coast) rather than UTC, because the sea breeze is
    forced by the solar cycle and a UTC composite would shift its phase by three
    hours relative to the physics that drives it.
    """
    t = pd.DatetimeIndex(pd.to_datetime(times)) + pd.Timedelta(hours=tz_offset_hours)
    df = pd.DataFrame({"hour": t.hour, "value": np.asarray(values, dtype=float)})
    g = df.groupby("hour")["value"]
    return pd.DataFrame({"mean": g.mean(), "std": g.std(), "n": g.count()})


def diurnal_scores(times, obs, model, tz_offset_hours: float = -3.0) -> dict:
    """How well the mean diurnal cycle is reproduced: amplitude and phase.

    Amplitude is peak-to-trough of the composite; phase is the local hour of the
    composite maximum. On this coast both are essentially sea-breeze diagnostics,
    which is where a coastal 5 km run is supposed to beat a ~31 km reanalysis.
    """
    co = diurnal_composite(times, obs, tz_offset_hours)
    cm = diurnal_composite(times, model, tz_offset_hours)
    common = co.index.intersection(cm.index)
    co, cm = co.loc[common], cm.loc[common]
    if len(common) < 12:
        return {"diurnal_rmse": np.nan, "diurnal_amp_obs": np.nan,
                "diurnal_amp_model": np.nan, "diurnal_amp_bias": np.nan,
                "diurnal_peak_hour_obs": np.nan, "diurnal_peak_hour_model": np.nan,
                "diurnal_phase_error_h": np.nan}
    amp_o = float(co["mean"].max() - co["mean"].min())
    amp_m = float(cm["mean"].max() - cm["mean"].min())
    ph_o = int(co["mean"].idxmax())
    ph_m = int(cm["mean"].idxmax())
    phase_err = (ph_m - ph_o + 12) % 24 - 12
    return {
        "diurnal_rmse": float(np.sqrt(((cm["mean"] - co["mean"]) ** 2).mean())),
        "diurnal_amp_obs": amp_o,
        "diurnal_amp_model": amp_m,
        "diurnal_amp_bias": amp_m - amp_o,
        "diurnal_peak_hour_obs": ph_o,
        "diurnal_peak_hour_model": ph_m,
        "diurnal_phase_error_h": float(phase_err),
    }


# --------------------------------------------------------------------------
# 3. uncertainty: moving-block bootstrap
# --------------------------------------------------------------------------

def _block_indices(n: int, block: int, rng) -> np.ndarray:
    """Indices for one moving-block bootstrap resample of length ~n."""
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, max(n - block + 1, 1), size=n_blocks)
    return np.concatenate([np.arange(s, min(s + block, n)) for s in starts])[:n]


def block_bootstrap_ci(obs, model, statistic, *, block_hours: int = 24,
                       n_boot: int = 1000, alpha: float = 0.05,
                       seed: int = 20260902) -> dict:
    """Confidence interval for any paired statistic, respecting autocorrelation.

    *statistic* takes ``(obs, model)`` and returns a float. The default block of
    24 h spans the diurnal cycle and most of the hour-to-hour synoptic
    persistence; shorter blocks give intervals that are too narrow, longer ones
    waste sample. The series must be ordered in time and contiguous — pass the
    paired sample as extracted, before any dropna that would create gaps.
    """
    o, m = np.asarray(obs, dtype=float), np.asarray(model, dtype=float)
    n = o.size
    if n < 3 * block_hours:
        return {"value": float(statistic(o, m)), "lo": np.nan, "hi": np.nan,
                "n_boot": 0}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = _block_indices(n, block_hours, rng)
        v = statistic(o[idx], m[idx])
        if np.isfinite(v):
            vals.append(v)
    vals = np.asarray(vals)
    return {
        "value": float(statistic(o, m)),
        "lo": float(np.percentile(vals, 100 * alpha / 2)),
        "hi": float(np.percentile(vals, 100 * (1 - alpha / 2))),
        "n_boot": int(vals.size),
    }


def paired_skill_test(obs, model_a, model_b, *, block_hours: int = 24,
                      n_boot: int = 1000, alpha: float = 0.05,
                      seed: int = 20260902) -> dict:
    """Is model B better than model A, on the same hours?

    Works on the **paired** difference of squared errors, ``e_a**2 - e_b**2``,
    resampled in blocks. Pairing is what gives the test its power: the two
    experiments see the same weather, so the shared synoptic variability
    cancels and only the difference in error is resampled. A positive
    ``delta_mse`` means B has the lower MSE; the comparison is significant at
    the stated level when the interval excludes zero.

    This is a bootstrap analogue of the Diebold-Mariano test for equal
    predictive accuracy, and it is the reason a ranking here can be stated with
    a confidence interval instead of a hunch.
    """
    o = np.asarray(obs, dtype=float)
    a = np.asarray(model_a, dtype=float)
    b = np.asarray(model_b, dtype=float)
    ok = np.isfinite(o) & np.isfinite(a) & np.isfinite(b)
    o, a, b = o[ok], a[ok], b[ok]
    n = o.size
    if n < 3 * block_hours:
        return {"n": int(n), "delta_mse": np.nan, "lo": np.nan, "hi": np.nan,
                "rmse_a": np.nan, "rmse_b": np.nan, "significant": False}
    d = (a - o) ** 2 - (b - o) ** 2          # >0 where B is closer
    rng = np.random.default_rng(seed)
    boot = np.array([d[_block_indices(n, block_hours, rng)].mean()
                     for _ in range(n_boot)])
    lo = float(np.percentile(boot, 100 * alpha / 2))
    hi = float(np.percentile(boot, 100 * (1 - alpha / 2)))
    return {
        "n": int(n),
        "delta_mse": float(d.mean()),
        "lo": lo, "hi": hi,
        "rmse_a": float(np.sqrt(((a - o) ** 2).mean())),
        "rmse_b": float(np.sqrt(((b - o) ** 2).mean())),
        "significant": bool(lo > 0 or hi < 0),
    }


def skill_score(obs, model, reference) -> float:
    """Murphy skill score against a reference forecast: ``1 - MSE_m / MSE_ref``.

    Used here with ERA5 as the reference, so the number reads directly as "the
    fraction of ERA5's mean-square error that the downscaling removes". Zero
    means the 5 km run is no better than its own driving reanalysis at the site;
    negative means it is worse.
    """
    o = np.asarray(obs, dtype=float)
    m = np.asarray(model, dtype=float)
    r = np.asarray(reference, dtype=float)
    ok = np.isfinite(o) & np.isfinite(m) & np.isfinite(r)
    if ok.sum() < 10:
        return np.nan
    mse_m = ((m[ok] - o[ok]) ** 2).mean()
    mse_r = ((r[ok] - o[ok]) ** 2).mean()
    return float(1.0 - mse_m / mse_r) if mse_r > 0 else np.nan


def all_scores(times, obs_speed, model_speed, obs_dir=None, model_dir=None,
               rho: float = AIR_DENSITY) -> dict:
    """Every score group at once, for one (experiment, site, height) sample."""
    out = basic_scores(obs_speed, model_speed)
    out.update(resource_scores(obs_speed, model_speed, rho))
    out.update(diurnal_scores(times, obs_speed, model_speed))
    if obs_dir is not None and model_dir is not None:
        out.update(direction_scores(obs_dir, model_dir, obs_speed))
    return out
