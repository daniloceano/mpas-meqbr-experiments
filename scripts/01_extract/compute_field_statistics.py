#!/usr/bin/env python
"""Accumulate domain-wide time-mean fields for each leg, once, and cache them.

Every map in the repo is drawn from these files. One pass over the history
output per leg; the alternative — re-reading ~700 files for each figure — makes
exploratory map work painfully slow and is the reason people stop exploring.

**The averaging window is the thing to get right.** By default each leg is
averaged over the hours it actually has, which is right for looking at one
experiment on its own but *wrong* for differencing two of them while EXP02 is
still integrating. Use ``--window common`` when the output will be differenced:
it intersects the available hours across the selected experiments and averages
everyone over the same weather.

    python scripts/01_extract/compute_field_statistics.py
    python scripts/01_extract/compute_field_statistics.py --window common --period 2021
    python scripts/01_extract/compute_field_statistics.py --start 2021-11-09 --end 2021-11-16

Output: results/fields/<EXP>_<period>_fields.nc
        (add --tag NAME to keep a second averaging window side by side)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import fields, io                         # noqa: E402
from mpas_meqbr.config import load_config, REPO_ROOT      # noqa: E402


def available_index(leg):
    idx = io.history_index(leg.history_dir, verify=1) if leg.exists() else pd.Series(dtype=object)
    if len(idx) == 0:
        return idx
    return io.select_window(idx, leg.analysis_start, leg.analysis_end)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiments", nargs="*", default=None)
    ap.add_argument("--period", nargs="*", default=None)
    ap.add_argument("--window", choices=["available", "common"], default="available",
                    help="'common' = intersect the hours across the selected "
                         "experiments (use whenever the fields will be differenced)")
    ap.add_argument("--start", default=None, help="explicit window start (overrides --window)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--height", type=float, default=100.0)
    ap.add_argument("--tag", default=None,
                    help="suffix for the output filename, to keep two windows side by side")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--runs-root", default=None)
    args = ap.parse_args()

    cfg = load_config(runs_root=args.runs_root)
    experiments = args.experiments or cfg.experiment_keys
    periods = args.period or sorted(cfg.periods)
    rc = 0

    for period in periods:
        legs = [cfg.leg(e, period) for e in experiments
                if period in cfg.experiments[e]["periods"]]
        indices = {leg.experiment: available_index(leg) for leg in legs}
        indices = {k: v for k, v in indices.items() if len(v) > 0}
        if not indices:
            print(f"[{period}] no history available for any experiment — skipping")
            continue

        if args.start or args.end:
            start = pd.Timestamp(args.start) if args.start else None
            end = pd.Timestamp(args.end) if args.end else None
        elif args.window == "common":
            common = None
            for idx in indices.values():
                common = idx.index if common is None else common.intersection(idx.index)
            if common is None or len(common) == 0:
                print(f"[{period}] no hours common to {list(indices)} — skipping")
                continue
            start, end = common.min(), common.max()
            print(f"[{period}] common window across {list(indices)}: {start} -> {end} "
                  f"({len(common)} hours)")
        else:
            start = end = None

        for leg in legs:
            if leg.experiment not in indices:
                print(f"[{leg.key}] nothing on disk yet — skipping")
                continue
            idx = indices[leg.experiment]
            if start is not None:
                idx = idx.loc[idx.index >= start]
            if end is not None:
                idx = idx.loc[idx.index <= end]
            if len(idx) < 24:
                print(f"[{leg.key}] only {len(idx)} hours in window — skipping")
                continue

            suffix = f"_{args.tag}" if args.tag else ""
            out = cfg.path("results", "fields",
                           f"{leg.experiment}_{leg.period}_fields{suffix}.nc")
            if out.exists() and not args.force:
                print(f"[{leg.key}] {out.name} exists — use --force to recompute")
                continue

            print(f"[{leg.key}] averaging {len(idx)} hours "
                  f"({idx.index[0]} -> {idx.index[-1]})", flush=True)
            try:
                ds = fields.compute_leg_fields(leg, idx, height_m=args.height)
            except Exception as exc:                       # noqa: BLE001
                print(f"[{leg.key}] FAILED: {exc}", file=sys.stderr)
                rc = 1
                continue
            ds.attrs["window_mode"] = args.window if not (args.start or args.end) else "explicit"
            ds.to_netcdf(out)
            print(f"[{leg.key}] -> {out.relative_to(REPO_ROOT)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
