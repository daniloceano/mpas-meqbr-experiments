#!/usr/bin/env python
"""MEQ-04.3 — error decomposition and paired component tests at 100 m.

Where does the MPAS gain over ERA5 come from? For every source (ERA5, CTL,
EXP01–EXP06) on exactly the hours of ``era5_added_value_current.csv`` the MSE
is split exactly (population standard deviations) as

    MSE = bias**2 + (sigma_m - sigma_o)**2 + 2 sigma_m sigma_o (1 - r)

and paired moving-block bootstrap intervals are computed for the differences
B − A in |bias|, r, |1 − sigma_m/sigma_o|, RMSE and skill vs ERA5
(= ΔMSE / MSE_ERA5), drawing the *same* indices for both sources in every
resample.

Resamplers are those of the tables being audited, so that the ΔRMSE/Δskill
verdicts can be compared one-to-one:

* experiment vs ERA5 — ``metrics._block_indices`` (as in
  ``metrics.paired_skill_test``, used by ``added_value.py``);
* experiment vs experiment — ``metrics._gap_aware_resample_indices`` (as in
  ``metrics.gap_aware_paired_skill_test``, used by ``rank_experiments.py``).

Both: block_hours=24, n_boot=2000, seed=20260902, 95 % percentile interval.
Pairing reuses ``pairing.load_paired`` / ``pairing.add_era5`` unchanged
(``obs.to_hourly`` as is — DEC-MEQ-004 limitation).

    python scripts/04_era5/paired_components.py

Outputs (new): results/tables/meq04_3_error_decomposition.csv
               results/tables/meq04_3_paired_components.csv
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import metrics, pairing                    # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT       # noqa: E402

EXPERIMENTS = ["CTL", "EXP01", "EXP02", "EXP03", "EXP04", "EXP05", "EXP06"]
TOL_RMSE = 1e-9


def decompose(obs, model) -> dict:
    """Exact MSE decomposition with population (ddof=0) standard deviations."""
    o = np.asarray(obs, float)
    m = np.asarray(model, float)
    bias = float(np.mean(m - o))
    so, sm = float(np.std(o)), float(np.std(m))
    r = float(np.corrcoef(o, m)[0, 1])
    mse = float(np.mean((m - o) ** 2))
    t_bias = bias ** 2
    t_amp = (sm - so) ** 2
    t_phase = 2.0 * sm * so * (1.0 - r)
    return {"n": int(o.size), "bias": bias, "r": r, "sigma_obs": so,
            "sigma_model": sm, "sigma_ratio": sm / so, "mse": mse,
            "rmse": float(np.sqrt(mse)), "term_bias2": t_bias,
            "term_amplitude": t_amp, "term_correlation": t_phase,
            "residual": mse - (t_bias + t_amp + t_phase)}


def components(o, a, b, mse_era5) -> np.ndarray:
    """B − A for |bias|, r, |1 − sigma ratio|, RMSE, skill vs ERA5."""
    out = []
    so = np.std(o)
    for m in (a, b):
        e = m - o
        out.append([abs(e.mean()), np.corrcoef(o, m)[0, 1],
                    abs(1.0 - np.std(m) / so), np.sqrt(np.mean(e ** 2)),
                    np.mean(e ** 2)])
    ca, cb = out
    return np.array([cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2],
                     cb[3] - ca[3], (ca[4] - cb[4]) / mse_era5])


METRICS = ["abs_bias", "r", "amplitude", "rmse", "skill_vs_era5"]
HIGHER_IS_BETTER = {"abs_bias": False, "r": True, "amplitude": False,
                    "rmse": False, "skill_vs_era5": True}


def paired_test(t, o, a, b, mse_era5, *, gap_aware, block, n_boot, seed):
    n = o.size
    rng = np.random.default_rng(seed)
    cand = metrics._contiguous_block_indices(t, block) if gap_aware else None
    boot = np.empty((n_boot, len(METRICS)))
    for k in range(n_boot):
        idx = (metrics._gap_aware_resample_indices(t, block, rng, cand)
               if gap_aware else metrics._block_indices(n, block, rng))
        boot[k] = components(o[idx], a[idx], b[idx], mse_era5)
    return components(o, a, b, mse_era5), np.percentile(boot, [2.5, 97.5], axis=0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--block-hours", type=int, default=24)
    ap.add_argument("--seed", type=int, default=20260902)
    args = ap.parse_args()
    cfg = load_config()
    tables = cfg.path("results", "tables", "x").parent
    ref_av = pd.read_csv(tables / "era5_added_value_current.csv")
    ref_pw = pd.read_csv(tables / "pairwise_tests_current.csv")
    ref_pw = ref_pw[ref_pw["height_m"] == 100]

    dec_rows, test_rows, problems = [], [], []
    for period in sorted(cfg.periods):
        site = cfg.periods[period]["validation_site"]
        frames = pairing.load_paired(cfg, EXPERIMENTS, period, common=True)
        era5 = pairing.add_era5(frames, cfg, period, height_for_era5=100)
        merged = None
        for exp, d in frames.items():
            d = d[d["model_height"] == 100][["time", "obs_speed", "mod_speed"]]
            d = d.rename(columns={"mod_speed": exp})
            merged = d if merged is None else merged.merge(
                d.drop(columns="obs_speed"), on="time")
        merged = merged.merge(era5, on="time", how="inner").sort_values("time")
        merged = merged.rename(columns={"era5_speed": "ERA5"}).reset_index(drop=True)
        t = pd.DatetimeIndex(merged["time"])
        o = merged["obs_speed"].to_numpy(float)
        sources = ["ERA5"] + [e for e in EXPERIMENTS if e in merged]

        # ---- reproduction + decomposition ------------------------------
        for src in sources:
            d = decompose(o, merged[src].to_numpy(float))
            ref = ref_av[(ref_av["source"] == src) & (ref_av["period"].astype(str) == period)]
            if ref.empty or int(ref["n"].iloc[0]) != d["n"] or \
                    abs(float(ref["rmse"].iloc[0]) - d["rmse"]) > TOL_RMSE:
                problems.append(f"{period} {src}: n={d['n']} rmse={d['rmse']:.12f} "
                                f"vs table {ref[['n', 'rmse']].values.tolist()}")
            mse = d["mse"]
            dec_rows.append({"period": period, "site": site, "height_m": 100,
                             "source": src, **d,
                             "frac_bias2": d["term_bias2"] / mse,
                             "frac_amplitude": d["term_amplitude"] / mse,
                             "frac_correlation": d["term_correlation"] / mse,
                             "rmse_table": float(ref["rmse"].iloc[0]) if len(ref) else np.nan})
        if problems:
            break
        mse_era5 = float(np.mean((merged["ERA5"].to_numpy(float) - o) ** 2))

        pairs = [("ERA5", e, False) for e in sources[1:]] + \
                [(a, b, True) for a, b in itertools.combinations(sources[1:], 2)]
        for a, b, gap in pairs:
            val, ci = paired_test(t, o, merged[a].to_numpy(float),
                                  merged[b].to_numpy(float), mse_era5,
                                  gap_aware=gap, block=args.block_hours,
                                  n_boot=args.n_boot, seed=args.seed)
            row = {"period": period, "site": site, "height_m": 100,
                   "comparison": "vs_ERA5" if a == "ERA5" else "pairwise",
                   "source_a": a, "source_b": b, "n": int(o.size),
                   "resampler": "gap_aware" if gap else "moving_block",
                   "block_hours": args.block_hours, "n_boot": args.n_boot,
                   "seed": args.seed}
            for j, k in enumerate(METRICS):
                lo, hi = ci[0, j], ci[1, j]
                sig = lo > 0 or hi < 0
                b_better = (val[j] > 0) == HIGHER_IS_BETTER[k]
                row.update({f"d_{k}": val[j], f"d_{k}_lo": lo, f"d_{k}_hi": hi,
                            f"better_{k}": (b if b_better else a) if sig else "no difference"})
            # cross-check against the published tables
            if a == "ERA5":
                ref = ref_av[(ref_av["source"] == b) & (ref_av["period"].astype(str) == period)]
                ref_sig, ref_skill = bool(ref["significant"].iloc[0]), float(ref["skill_vs_era5"].iloc[0])
                ref_better = (b if ref_skill > 0 else a) if ref_sig else "no difference"
                row["check_ref_skill_lo"] = float(ref["skill_lo"].iloc[0])
                row["check_ref_skill_hi"] = float(ref["skill_hi"].iloc[0])
            else:
                ref = ref_pw[(ref_pw["experiment_a"] == a) & (ref_pw["experiment_b"] == b) &
                             (ref_pw["period"].astype(str) == period)]
                ref_better = ref["better"].iloc[0]
                row["check_ref_skill_lo"] = float(ref["lo"].iloc[0]) / mse_era5
                row["check_ref_skill_hi"] = float(ref["hi"].iloc[0]) / mse_era5
            row["check_ref_better"] = ref_better
            row["check_rmse_agrees"] = row["better_rmse"] == ref_better
            row["check_skill_agrees"] = row["better_skill_vs_era5"] == ref_better
            test_rows.append(row)

    if problems:
        print("REPRODUCTION FAILED — stopping:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    dec = pd.DataFrame(dec_rows)
    tests = pd.DataFrame(test_rows)
    print(f"max |identity residual| = {dec['residual'].abs().max():.2e}")
    bad = tests[~(tests["check_rmse_agrees"] & tests["check_skill_agrees"])]
    print(f"verdict discrepancies vs published tables: {len(bad)}")
    if len(bad):
        print(bad[["period", "source_a", "source_b", "better_rmse",
                   "better_skill_vs_era5", "check_ref_better"]].to_string())
    out1 = tables / "meq04_3_error_decomposition.csv"
    out2 = tables / "meq04_3_paired_components.csv"
    for p in (out1, out2):
        if p.exists():
            print(f"{p} exists — refusing to overwrite", file=sys.stderr)
            return 3
    dec.to_csv(out1, index=False)
    tests.to_csv(out2, index=False)
    for p in (out1, out2):
        print(f"-> {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
