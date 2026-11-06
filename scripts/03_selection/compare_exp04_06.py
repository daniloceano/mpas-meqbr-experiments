#!/usr/bin/env python
"""Decision-support contrasts for the completed EXP04--EXP06 campaign.

Every contrast uses the same observed hours for all seven current MPAS
experiments.  Differences of squared errors are resampled in 24-hour moving
blocks that never cross an observational gap.  The outputs are exploratory
multiple comparisons; a confidence interval spanning zero is *not* evidence
of equivalence.

Outputs:
    results/tables/exp04_06_priority_tests.csv
    results/tables/exp04_06_contrast_summary.csv
    results/tables/exp04_06_contrast_summary.md
    figures/selection/exp04_06_priority_contrasts.png
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr import io, metrics, pairing, plotting  # noqa: E402
from mpas_meqbr.config import REPO_ROOT, load_config  # noqa: E402


CURRENT = ["CTL", "EXP01", "EXP02", "EXP03", "EXP04", "EXP05", "EXP06"]
CONTRASTS = [
    ("EXP01", "EXP04", "MYNN package conditional on EXP01"),
    ("EXP04", "EXP05", "Grell-Freitas conditional on MYNN"),
    ("EXP05", "EXP06", "diurnal SST conditional on MYNN + Grell-Freitas"),
    ("EXP01", "EXP05", "accumulated MYNN + Grell-Freitas"),
    ("EXP01", "EXP06", "accumulated MYNN + Grell-Freitas + diurnal SST"),
    ("EXP03", "EXP04", "physics branch versus Oval geometry branch"),
    ("EXP03", "EXP05", "physics branch versus Oval geometry branch"),
    ("EXP03", "EXP06", "physics branch versus Oval geometry branch"),
]


def time_hash(times) -> str:
    text = io.canonical_time_text(times)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--block-hours", type=int, default=24)
    parser.add_argument("--heights", nargs="*", type=int,
                        default=[50, 100, 150, 200])
    args = parser.parse_args()

    cfg = load_config()
    plotting.use_style()
    rows = []

    for period in sorted(cfg.periods):
        site = cfg.periods[period]["validation_site"]
        frames = pairing.load_paired(cfg, CURRENT, period, common=True)
        missing = sorted(set(CURRENT) - set(frames))
        if missing:
            raise RuntimeError(
                f"{period}/{site}: missing paired series for {', '.join(missing)}"
            )
        for height in args.heights:
            merged = None
            for experiment in CURRENT:
                part = frames[experiment][
                    frames[experiment]["model_height"] == height
                ][["time", "obs_speed", "mod_speed"]].rename(
                    columns={"mod_speed": experiment}
                )
                merged = part if merged is None else merged.merge(
                    part.drop(columns="obs_speed"), on="time", how="inner"
                )
            merged = merged.sort_values("time").dropna(
                subset=["obs_speed", *CURRENT]
            )
            if len(merged) < 3 * args.block_hours:
                continue
            paired_sha = time_hash(merged["time"])
            for index, (experiment_a, experiment_b, hypothesis) in enumerate(CONTRASTS):
                result = metrics.gap_aware_paired_skill_test(
                    merged["time"], merged["obs_speed"],
                    merged[experiment_a], merged[experiment_b],
                    block_hours=args.block_hours, n_boot=args.n_boot,
                    seed=20261106 + int(period) + height * 10 + index,
                )
                if result["significant"]:
                    better = experiment_b if result["delta_mse"] > 0 else experiment_a
                    verdict = f"{better} lower squared error"
                else:
                    better = "no detectable difference"
                    verdict = "difference not detected; equivalence not established"
                rows.append({
                    "period": period,
                    "site": site,
                    "height_m": height,
                    "experiment_a": experiment_a,
                    "experiment_b": experiment_b,
                    "hypothesis": hypothesis,
                    "n": result["n"],
                    "paired_hours_sha256": paired_sha,
                    "rmse_a": result["rmse_reference"],
                    "rmse_b": result["rmse_model"],
                    "delta_mse": result["delta_mse"],
                    "lo": result["lo"],
                    "hi": result["hi"],
                    "significant": result["significant"],
                    "better": better,
                    "verdict": verdict,
                    "block_hours": args.block_hours,
                    "n_boot": args.n_boot,
                })

    if not rows:
        print("no priority contrasts produced", file=sys.stderr)
        return 1

    table = pd.DataFrame(rows).sort_values(
        ["period", "height_m", "experiment_a", "experiment_b"], kind="stable"
    )
    table_out = cfg.path("results", "tables", "exp04_06_priority_tests.csv")
    table.to_csv(table_out, index=False)

    summary_rows = []
    for (experiment_a, experiment_b), group in table.groupby(
            ["experiment_a", "experiment_b"], sort=False):
        summary_rows.append({
            "experiment_a": experiment_a,
            "experiment_b": experiment_b,
            "comparisons": len(group),
            "b_better": int((group["better"] == experiment_b).sum()),
            "a_better": int((group["better"] == experiment_a).sum()),
            "not_detected": int((group["better"] == "no detectable difference").sum()),
            "mean_delta_mse": float(group["delta_mse"].mean()),
        })
    summary = pd.DataFrame(summary_rows)
    summary_out = cfg.path("results", "tables", "exp04_06_contrast_summary.csv")
    summary.to_csv(summary_out, index=False)

    labels = [f"{a}→{b}" for a, b, _ in CONTRASTS]
    periods = sorted(table["period"].unique())
    vmax = float(np.nanpercentile(np.abs(table["delta_mse"]), 95))
    vmax = vmax if vmax > 0 else 1.0
    fig, axes = plt.subplots(1, len(periods), figsize=(8.2 * len(periods), 4.6),
                             squeeze=False)
    for ax, period in zip(axes[0], periods):
        period_table = table[table["period"] == period]
        matrix = np.full((len(args.heights), len(CONTRASTS)), np.nan)
        annotations = np.full(matrix.shape, "", dtype=object)
        for i, height in enumerate(args.heights):
            for j, (a, b, _) in enumerate(CONTRASTS):
                row = period_table[
                    (period_table["height_m"] == height)
                    & (period_table["experiment_a"] == a)
                    & (period_table["experiment_b"] == b)
                ]
                if row.empty:
                    continue
                record = row.iloc[0]
                matrix[i, j] = record["delta_mse"]
                annotations[i, j] = (
                    "B" if record["better"] == b else
                    "A" if record["better"] == a else "ND"
                )
        image = ax.imshow(matrix, cmap=plotting.CMAP_DIFF, vmin=-vmax, vmax=vmax,
                          aspect="auto")
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                if annotations[i, j]:
                    ax.text(j, i, annotations[i, j], ha="center", va="center",
                            fontsize=7, fontweight="bold")
        ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
        ax.set_yticks(range(len(args.heights)), [f"{h} m" for h in args.heights])
        ax.set_title(f"{cfg.periods[period]['validation_site']} / {period}")
    colorbar = fig.colorbar(image, ax=axes[0].tolist(), fraction=0.025, pad=0.02)
    colorbar.set_label("MSE(A) − MSE(B) (m² s⁻²); positive favours B")
    fig.suptitle("EXP04–EXP06 priority contrasts (A/B significant; ND not detected)")
    plotting.provenance_footer(
        fig,
        "scripts/03_selection/compare_exp04_06.py | identical observed hours across "
        f"seven experiments | {args.block_hours} h gap-aware blocks | "
        f"{args.n_boot} resamples | exploratory multiple comparisons; ND is not equivalence",
        layout=False,
    )
    figure_out = cfg.path("figures", "selection", "exp04_06_priority_contrasts.png")
    fig.savefig(figure_out, dpi=300, bbox_inches="tight")
    plt.close(fig)

    lines = [
        "# EXP04–EXP06 priority contrasts",
        "",
        "Generated by `scripts/03_selection/compare_exp04_06.py`; do not edit.",
        "",
        "Positive MSE(A) − MSE(B) favours B. Intervals use 24-hour moving "
        "blocks, 2,000 resamples and identical observed hours. A non-detectable "
        "difference does not demonstrate equivalence. The family is exploratory "
        "and no multiplicity adjustment is used.",
        "",
        summary.round(4).to_markdown(index=False),
        "",
        "## Scientific scope",
        "",
        "- EXP04−EXP01 evaluates the coupled MYNN PBL/surface-layer package.",
        "- EXP05−EXP04 evaluates Grell–Freitas conditional on MYNN.",
        "- EXP06−EXP05 evaluates diurnal skin-temperature physics conditional "
        "on MYNN and Grell–Freitas.",
        "- EXP04–EXP06 versus EXP03 compares physics and geometry branches; the "
        "difference cannot be attributed to a single factor.",
    ]
    markdown_out = cfg.path("results", "tables", "exp04_06_contrast_summary.md")
    markdown_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for output in (table_out, summary_out, markdown_out, figure_out):
        print(f"-> {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
