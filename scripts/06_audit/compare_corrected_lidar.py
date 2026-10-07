#!/usr/bin/env python
"""Independent LiDAR-only audit of old versus corrected EXP01/EXP02 runs.

The script deliberately writes to a separate audit directory and never touches
the official report or the original MPAS outputs.  It reuses the repository's
observation QC, hourly pairing, vertical matching, metrics and moving-block
bootstrap so the only changed input is the MPAS history directory.

Run this on ``swell`` after staging the analysis code and linking the two LiDAR
files into ``data/obs``.  The expensive history traversal stays on the server.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import importlib.util
import json
import shutil
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from mpas_meqbr import metrics, pairing, plotting  # noqa: E402
from mpas_meqbr.config import load_config  # noqa: E402


RUNS = {
    "EXP01": {"old": "EXP01_BADSST", "corrected": "EXP01"},
    "EXP02": {"old": "EXP02_BADSST", "corrected": "EXP02"},
}
STATE_LABEL = {"old": "Antigo", "corrected": "Corrigido"}
STATE_COLOR = {"old": "#D97706", "corrected": "#146B8C"}
PERIOD_SITE = {"2021": "P0", "2022": "LPI"}


def import_extractor():
    path = REPO_ROOT / "scripts" / "01_extract" / "extract_site_timeseries.py"
    spec = importlib.util.spec_from_file_location("audit_extract_site_timeseries", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def alias(base: str, state: str) -> str:
    return f"{base}_{'OLD' if state == 'old' else 'CORRECTED'}"


def extract_task(task) -> str:
    """Extract one run/period in an isolated worker process."""
    runs_root, base, state, directory, period, force = task
    cfg = load_config(runs_root=runs_root)
    extractor = import_extractor()
    # The audit needs wind and SST only.  Reading no unused thermodynamic or
    # surface variables substantially reduces remote I/O while leaving the
    # cell selection, vertical coordinate and wind calculation unchanged.
    extractor.VARS_3D = ["uReconstructZonal", "uReconstructMeridional"]
    extractor.VARS_2D = ["sst", "skintemp"]
    label = alias(base, state)
    base_leg = cfg.leg(base, period)
    leg = replace(
        base_leg,
        experiment=label,
        history_dir=Path(runs_root) / directory / cfg.periods[period]["history_subdir"],
    )
    site = cfg.site(leg.validation_site)
    out = extractor.extract_leg(leg, site, cfg, n_cells=1, force=force)
    return str(out)


def extract_all(cfg, runs_root: Path, *, force: bool, workers: int) -> None:
    tasks = [
        (runs_root, base, state, directory, period, force)
        for base, versions in RUNS.items()
        for state, directory in versions.items()
        for period in sorted(cfg.periods)
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(extract_task, task) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            print(f"[complete] {future.result()}", flush=True)


def paired_versions(cfg, base: str, period: str) -> dict[str, pd.DataFrame]:
    labels = [alias(base, "old"), alias(base, "corrected")]
    frames = pairing.load_paired(
        cfg, labels, period, cell=0, common=True, repo_root=REPO_ROOT,
    )
    if set(frames) != set(labels):
        raise RuntimeError(f"missing paired data for {base} {period}: {sorted(frames)}")
    old = frames[labels[0]].sort_values(["model_height", "time"]).reset_index(drop=True)
    new = frames[labels[1]].sort_values(["model_height", "time"]).reset_index(drop=True)
    keys = ["time", "model_height"]
    check = old[keys + ["obs_speed"]].merge(
        new[keys + ["obs_speed"]], on=keys, suffixes=("_old", "_new"), validate="one_to_one",
    )
    if len(check) != len(old) or len(check) != len(new):
        raise RuntimeError(f"old/corrected pairing mismatch for {base} {period}")
    if not np.allclose(check["obs_speed_old"], check["obs_speed_new"], equal_nan=True):
        raise RuntimeError(f"observation vector differs for {base} {period}")
    return {"old": old, "corrected": new}


def score_all(cfg, *, n_boot: int, block_hours: int):
    rows, tests, paired = [], [], {}
    for base in RUNS:
        for period in sorted(cfg.periods):
            site = PERIOD_SITE[period]
            frames = paired_versions(cfg, base, period)
            paired[(base, period)] = frames
            heights = sorted(set(frames["old"]["model_height"]))
            for height in heights:
                subs = {
                    state: frame[frame["model_height"] == height].sort_values("time")
                    for state, frame in frames.items()
                }
                for state, sub in subs.items():
                    scores = metrics.all_scores(
                        sub["time"], sub["obs_speed"], sub["mod_speed"],
                        sub["obs_dir"], sub["mod_dir"],
                    )
                    rows.append({
                        "experiment": base,
                        "version": state,
                        "period": period,
                        "site": site,
                        "height_m": int(height),
                        "window_start": sub["time"].min(),
                        "window_end": sub["time"].max(),
                        **scores,
                    })

                merged = subs["old"].merge(
                    subs["corrected"][["time", "mod_speed"]],
                    on="time", suffixes=("_old", "_corrected"), validate="one_to_one",
                )
                test = metrics.paired_skill_test(
                    merged["obs_speed"], merged["mod_speed_old"],
                    merged["mod_speed_corrected"], block_hours=block_hours,
                    n_boot=n_boot,
                )
                if test["lo"] > 0:
                    verdict = "corrigido melhor"
                elif test["hi"] < 0:
                    verdict = "corrigido pior"
                else:
                    verdict = "sem diferença conclusiva"
                tests.append({
                    "experiment": base,
                    "period": period,
                    "site": site,
                    "height_m": int(height),
                    **test,
                    "verdict": verdict,
                })
    scores = pd.DataFrame(rows)
    test_df = pd.DataFrame(tests)
    return scores, test_df, paired


def comparison_table(scores: pd.DataFrame, tests: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "experiment", "period", "site", "height_m", "n", "bias", "rmse", "r",
        "wpd_rel_bias_pct", "diurnal_phase_error_h", "diurnal_amp_bias",
    ]
    old = scores[scores["version"] == "old"][keep].copy()
    new = scores[scores["version"] == "corrected"][keep].copy()
    keys = ["experiment", "period", "site", "height_m"]
    table = old.merge(new, on=keys, suffixes=("_old", "_corrected"), validate="one_to_one")
    table["rmse_improvement"] = table["rmse_old"] - table["rmse_corrected"]
    table["abs_bias_improvement"] = table["bias_old"].abs() - table["bias_corrected"].abs()
    table["r_change"] = table["r_corrected"] - table["r_old"]
    table["abs_wpd_bias_improvement"] = (
        table["wpd_rel_bias_pct_old"].abs() - table["wpd_rel_bias_pct_corrected"].abs()
    )
    table["abs_phase_error_improvement"] = (
        table["diurnal_phase_error_h_old"].abs()
        - table["diurnal_phase_error_h_corrected"].abs()
    )
    table = table.merge(
        tests[keys + ["delta_mse", "lo", "hi", "verdict"]], on=keys,
        validate="one_to_one",
    )
    return table


def sst_summary(cfg) -> pd.DataFrame:
    rows = []
    for base in RUNS:
        for period, site in PERIOD_SITE.items():
            values = {}
            for state in ("old", "corrected"):
                path = REPO_ROOT / "results" / "site_timeseries" / f"{alias(base, state)}_{period}_{site}.nc"
                with xr.open_dataset(path) as ds:
                    values[state] = ds["sst"].isel(cell=0).load().values.astype(float)
            n = min(len(values["old"]), len(values["corrected"]))
            old = values["old"][:n]
            new = values["corrected"][:n]
            rows.append({
                "experiment": base,
                "period": period,
                "site": site,
                "n_hours": n,
                "sst_old_mean_K": float(np.nanmean(old)),
                "sst_corrected_mean_K": float(np.nanmean(new)),
                "sst_change_K": float(np.nanmean(new - old)),
                "sst_old_min_K": float(np.nanmin(old)),
                "sst_corrected_min_K": float(np.nanmin(new)),
            })
    return pd.DataFrame(rows)


def make_metric_figure(table: pd.DataFrame, path: Path) -> None:
    plotting.use_style(1.05)
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 7.6), sharex="col")
    for col, (period, site) in enumerate(PERIOD_SITE.items()):
        sub = table[table["period"] == period]
        for base, marker in (("EXP01", "o"), ("EXP02", "s")):
            s = sub[sub["experiment"] == base].sort_values("height_m")
            axes[0, col].plot(s["height_m"], s["rmse_old"], marker=marker,
                              color=STATE_COLOR["old"], ls="--", label=f"{base} antigo")
            axes[0, col].plot(s["height_m"], s["rmse_corrected"], marker=marker,
                              color=STATE_COLOR["corrected"], label=f"{base} corrigido")
            axes[1, col].plot(s["height_m"], s["bias_old"], marker=marker,
                              color=STATE_COLOR["old"], ls="--", label=f"{base} antigo")
            axes[1, col].plot(s["height_m"], s["bias_corrected"], marker=marker,
                              color=STATE_COLOR["corrected"], label=f"{base} corrigido")
        axes[0, col].set_title(f"{site} — {period}")
        axes[0, col].set_ylabel("RMSE da velocidade (m s$^{-1}$)")
        axes[1, col].set_ylabel("Viés da velocidade (m s$^{-1}$)")
        axes[1, col].set_xlabel("Altura (m)")
        axes[1, col].axhline(0, color="0.35", lw=0.8)
        axes[0, col].legend(ncol=2, fontsize=7.5)
    fig.suptitle("LiDAR: execuções antigas versus corrigidas", fontsize=14, y=1.01)
    plotting.provenance_footer(
        fig,
        "scripts/06_audit/compare_corrected_lidar.py | mesmas horas, mesma observação, "
        "mesma célula oceânica e mesmo pareamento vertical; menor RMSE e viés mais perto de zero são melhores",
        fontsize=7,
    )
    fig.savefig(path, dpi=300)
    plt.close(fig)


def make_improvement_figure(table: pd.DataFrame, path: Path) -> None:
    plotting.use_style(1.0)
    panels = list(PERIOD_SITE.items())
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.5), sharey=True)
    for ax, (period, site) in zip(axes, panels):
        sub = table[table["period"] == period].copy()
        positions, labels, vals, colors = [], [], [], []
        k = 0
        for base in RUNS:
            for _, row in sub[sub["experiment"] == base].sort_values("height_m").iterrows():
                positions.append(k)
                labels.append(f"{base}\n{int(row['height_m'])} m")
                vals.append(row["rmse_improvement"])
                colors.append(
                    "#238B45" if row["verdict"] == "corrigido melhor"
                    else "#CB181D" if row["verdict"] == "corrigido pior"
                    else "#9E9E9E"
                )
                k += 1
            k += 0.6
        ax.bar(positions, vals, color=colors, width=0.75)
        ax.axhline(0, color="0.2", lw=0.9)
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7.5)
        ax.set_title(f"{site} — {period}")
        ax.set_ylabel("Redução do RMSE (m s$^{-1}$)\npositivo = corrigido melhor")
    fig.suptitle("Efeito da correção no erro horário contra o LiDAR", fontsize=13)
    fig.text(
        0.5, -0.05,
        "Verde/vermelho: intervalo de 95% do teste pareado (bootstrap em blocos de 24 h) "
        "exclui zero; cinza: diferença não conclusiva.",
        ha="center", fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def make_diurnal_figure(paired: dict, path: Path) -> None:
    plotting.use_style(1.0)
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 7.5), sharex=True)
    for row, base in enumerate(RUNS):
        for col, (period, site) in enumerate(PERIOD_SITE.items()):
            ax = axes[row, col]
            frames = paired[(base, period)]
            old = frames["old"][frames["old"]["model_height"] == 100]
            new = frames["corrected"][frames["corrected"]["model_height"] == 100]
            obs = metrics.diurnal_composite(old["time"], old["obs_speed"])
            co = metrics.diurnal_composite(old["time"], old["mod_speed"])
            cn = metrics.diurnal_composite(new["time"], new["mod_speed"])
            ax.plot(obs.index, obs["mean"], color="k", lw=2.2, label="LiDAR")
            ax.plot(co.index, co["mean"], color=STATE_COLOR["old"], ls="--", label="Antigo")
            ax.plot(cn.index, cn["mean"], color=STATE_COLOR["corrected"], label="Corrigido")
            ax.set_title(f"{base} — {site} / {period}")
            ax.set_ylabel("Velocidade a 100 m (m s$^{-1}$)")
            ax.set_xlabel("Hora local (UTC−3)")
            ax.set_xticks(range(0, 24, 3))
            ax.legend(fontsize=8)
    fig.suptitle("Ciclo diurno médio a 100 m", fontsize=14, y=1.01)
    plotting.provenance_footer(
        fig,
        "scripts/06_audit/compare_corrected_lidar.py | média por hora local sobre exatamente os mesmos pares horários",
        fontsize=7,
    )
    fig.savefig(path, dpi=300)
    plt.close(fig)


def make_sst_figure(cfg, path: Path) -> None:
    plotting.use_style(1.0)
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 7.5), sharex="col")
    for row, base in enumerate(RUNS):
        for col, (period, site) in enumerate(PERIOD_SITE.items()):
            ax = axes[row, col]
            for state in ("old", "corrected"):
                p = REPO_ROOT / "results" / "site_timeseries" / f"{alias(base, state)}_{period}_{site}.nc"
                with xr.open_dataset(p) as ds:
                    t = pd.DatetimeIndex(ds["time"].values)
                    sst = ds["sst"].isel(cell=0).values
                ax.plot(t, sst, color=STATE_COLOR[state],
                        ls="--" if state == "old" else "-", label=STATE_LABEL[state])
            ax.set_title(f"{base} — {site} / {period}")
            ax.set_ylabel("SST na célula do LiDAR (K)")
            ax.legend(fontsize=8)
    fig.suptitle("SST efetivamente vista pelo MPAS na célula oceânica de validação", fontsize=14, y=1.01)
    plotting.provenance_footer(
        fig,
        "scripts/06_audit/compare_corrected_lidar.py | célula oceânica mais próxima; janela científica",
        fontsize=7,
    )
    fig.savefig(path, dpi=300)
    plt.close(fig)


def fnum(value, digits=2, signed=False) -> str:
    if pd.isna(value):
        return "—"
    fmt = f"{{:{'+' if signed else ''}.{digits}f}}"
    return fmt.format(float(value))


def integrity_rows(integrity: dict) -> str:
    rows = []
    for leg in integrity["legs"]:
        recovered = leg["recovered_from_preserved_archive"]
        note = "—"
        if recovered:
            stamps = ", ".join(t.replace("T", " ") for t in recovered)
            note = f"{len(recovered)} arquivo preservado do reinício ({html.escape(stamps)})"
        rows.append(
            "<tr>"
            f"<td>{html.escape(leg['experiment'])}</td><td>{leg['period']}</td>"
            f"<td>{leg['active_history_count']}</td><td>{leg['logical_full_count']}/985</td>"
            f"<td>{leg['scientific_window_count']}/{leg['expected_scientific_count']}</td>"
            f"<td>{'sim' if leg['netcdf']['all_opened'] else 'não'}</td>"
            f"<td>{'limpos' if leg['logs']['all_clean'] else 'verificar'}</td>"
            f"<td>{note}</td><td class={'good' if leg['valid'] else 'bad'}>"
            f"{'VÁLIDO' if leg['valid'] else 'FALHOU'}</td></tr>"
        )
    return "\n".join(rows)


def metric_rows(table: pd.DataFrame) -> str:
    rows = []
    for _, r in table.sort_values(["site", "experiment", "height_m"]).iterrows():
        cls = "good" if r["verdict"] == "corrigido melhor" else (
            "bad" if r["verdict"] == "corrigido pior" else "neutral")
        rows.append(
            "<tr>"
            f"<td>{r['site']}</td><td>{r['experiment']}</td><td>{int(r['height_m'])}</td>"
            f"<td>{int(r['n_old'])}</td>"
            f"<td>{fnum(r['bias_old'], signed=True)}</td><td>{fnum(r['bias_corrected'], signed=True)}</td>"
            f"<td>{fnum(r['rmse_old'])}</td><td>{fnum(r['rmse_corrected'])}</td>"
            f"<td class={cls}>{fnum(r['rmse_improvement'], signed=True)}</td>"
            f"<td>{fnum(r['r_old'])}</td><td>{fnum(r['r_corrected'])}</td>"
            f"<td>{fnum(r['wpd_rel_bias_pct_old'], 1, True)}</td>"
            f"<td>{fnum(r['wpd_rel_bias_pct_corrected'], 1, True)}</td>"
            f"<td>{fnum(r['diurnal_phase_error_h_old'], 0, True)}</td>"
            f"<td>{fnum(r['diurnal_phase_error_h_corrected'], 0, True)}</td>"
            f"<td class={cls}>{html.escape(r['verdict'])}</td></tr>"
        )
    return "\n".join(rows)


def test_rows(tests: pd.DataFrame) -> str:
    rows = []
    for _, r in tests.sort_values(["site", "experiment", "height_m"]).iterrows():
        cls = "good" if r["verdict"] == "corrigido melhor" else (
            "bad" if r["verdict"] == "corrigido pior" else "neutral")
        rows.append(
            "<tr>"
            f"<td>{r['site']}</td><td>{r['experiment']}</td><td>{int(r['height_m'])}</td>"
            f"<td>{fnum(r['delta_mse'], 3, True)}</td>"
            f"<td>[{fnum(r['lo'], 3, True)}; {fnum(r['hi'], 3, True)}]</td>"
            f"<td>{fnum(r['rmse_a'])}</td><td>{fnum(r['rmse_b'])}</td>"
            f"<td class={cls}>{html.escape(r['verdict'])}</td></tr>"
        )
    return "\n".join(rows)


def sst_rows(sst: pd.DataFrame) -> str:
    rows = []
    for _, r in sst.sort_values(["site", "experiment"]).iterrows():
        rows.append(
            "<tr>"
            f"<td>{r['site']}</td><td>{r['experiment']}</td>"
            f"<td>{fnum(r['sst_old_mean_K'])}</td><td>{fnum(r['sst_corrected_mean_K'])}</td>"
            f"<td>{fnum(r['sst_change_K'], signed=True)}</td>"
            f"<td>{fnum(r['sst_old_min_K'])}</td><td>{fnum(r['sst_corrected_min_K'])}</td></tr>"
        )
    return "\n".join(rows)


def verdict_summary(tests: pd.DataFrame) -> dict:
    counts = tests["verdict"].value_counts().to_dict()
    by_exp = {}
    for exp, group in tests.groupby("experiment"):
        by_exp[exp] = group["verdict"].value_counts().to_dict()
    return {
        "better": int(counts.get("corrigido melhor", 0)),
        "worse": int(counts.get("corrigido pior", 0)),
        "neutral": int(counts.get("sem diferença conclusiva", 0)),
        "total": int(len(tests)),
        "by_experiment": by_exp,
    }


def build_html(out_dir: Path, integrity: dict, table: pd.DataFrame,
               tests: pd.DataFrame, sst: pd.DataFrame, summary: dict) -> None:
    exp_bits = []
    for exp in RUNS:
        c = summary["by_experiment"].get(exp, {})
        exp_bits.append(
            f"<strong>{exp}</strong>: {c.get('corrigido melhor', 0)} melhoras "
            f"significativas, {c.get('corrigido pior', 0)} pioras significativas e "
            f"{c.get('sem diferença conclusiva', 0)} diferenças inconclusivas."
        )
    overall_class = "goodbox" if summary["worse"] == 0 else "warnbox"
    overall = (
        f"Em {summary['total']} comparações independentes (altura × sítio × experimento), "
        f"a correção reduziu significativamente o MSE em {summary['better']}, piorou em "
        f"{summary['worse']} e não produziu diferença conclusiva em {summary['neutral']}. "
        + " ".join(exp_bits)
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditoria LiDAR — execuções corrigidas</title>
<style>
:root{{--ink:#17222b;--muted:#5b6870;--blue:#146b8c;--orange:#d97706;--green:#176b3a;--red:#a72b2b;--paper:#fff;--bg:#eef3f5;--line:#d6e0e4}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1220px;margin:auto;background:var(--paper);min-height:100vh;padding:36px 44px 72px}} h1{{font-size:2.05rem;margin:.1rem 0}} h2{{margin-top:2.6rem;border-bottom:2px solid var(--line);padding-bottom:.35rem}}
h3{{margin-top:1.8rem}} .lede{{color:var(--muted);max-width:920px}} .goodbox,.warnbox,.note{{padding:1rem 1.15rem;border-radius:8px;margin:1.1rem 0}}
.goodbox{{background:#eaf6ee;border-left:6px solid var(--green)}} .warnbox{{background:#fff3e2;border-left:6px solid var(--orange)}} .note{{background:#edf5f8;border-left:6px solid var(--blue)}}
nav{{display:flex;gap:.75rem;flex-wrap:wrap;margin:1.4rem 0}} nav a{{color:var(--blue);text-decoration:none;background:#eaf3f6;padding:.35rem .6rem;border-radius:5px}}
table{{border-collapse:collapse;width:100%;font-size:.86rem;margin:1rem 0 1.6rem}} caption{{text-align:left;font-weight:650;margin-bottom:.5rem}} th,td{{border:1px solid var(--line);padding:.42rem .5rem;text-align:right;vertical-align:top}} th{{background:#edf3f5;position:sticky;top:0}} td:first-child,th:first-child{{text-align:left}} .scroll{{overflow-x:auto}}
.good{{background:#dff2e5;color:#0d5b2d;font-weight:700}} .bad{{background:#fde3e3;color:#8d1d1d;font-weight:700}} .neutral{{background:#ededed;color:#4d4d4d}}
figure{{margin:1.6rem 0 2.2rem}} figure img{{width:100%;height:auto;border:1px solid var(--line);border-radius:6px}} figcaption{{color:var(--muted);font-size:.92rem;margin-top:.5rem}}
code{{background:#eef2f4;padding:.1rem .25rem;border-radius:3px}} ul{{max-width:980px}} footer{{margin-top:3rem;color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);padding-top:1rem}}
@media(max-width:700px){{main{{padding:22px 16px}} h1{{font-size:1.65rem}}}}
</style></head><body><main>
<header><p class="lede">RELATÓRIO DE AUDITORIA — NÃO SUBSTITUI O HTML TÉCNICO OFICIAL</p>
<h1>EXP01 e EXP02: antigo × corrigido, exclusivamente contra LiDAR</h1>
<p class="lede">Objetivo: verificar se a correção do preenchimento terrestre da OISST removeu a SST costeira artificial e se as novas integrações mudaram — e melhoraram — a comparação do vento com P0 e LPI. Gerado em {generated}.</p></header>
<nav><a href="#veredito">Veredito</a><a href="#integridade">Integridade</a><a href="#metodo">Método</a><a href="#sst">SST</a><a href="#resultados">LiDAR</a><a href="#incerteza">Incerteza</a></nav>

<section id="veredito"><h2>1. Veredito objetivo</h2><div class="{overall_class}">{overall}</div>
<p>A correção técnica é considerada comprovada somente se duas condições forem verdadeiras ao mesmo tempo: (1) a SST na célula oceânica deixa de carregar o valor terrestre interpolado; e (2) todos os pares antigos/corrigidos usam exatamente as mesmas observações, horas, célula e alturas. Melhorar o vento em cada métrica não é requisito lógico para provar a correção do dado de entrada: o modelo possui outros erros. Por isso o relatório separa <em>integridade da correção</em> de <em>efeito na habilidade</em>.</p></section>

<section id="integridade"><h2>2. Integridade das novas integrações</h2><div class="scroll"><table><caption>Sequência horária, janela científica, leitura NetCDF e encerramento do MPAS.</caption>
<thead><tr><th>Experimento</th><th>Período</th><th>Arquivos ativos</th><th>Sequência lógica</th><th>Janela científica</th><th>NetCDF</th><th>Logs</th><th>Observação</th><th>Status</th></tr></thead><tbody>{integrity_rows(integrity)}</tbody></table></div>
<p class="note">“Sequência lógica” conta um arquivo de checkpoint preservado quando ele completa uma lacuna causada pelo reinício. Nenhum arquivo foi movido, copiado ou sobrescrito. Todos os arquivos da sequência lógica foram abertos com <code>netCDF4</code> e tiveram um valor de SST realmente lido.</p></section>

<section id="metodo"><h2>3. Comparação controlada</h2>
<ol><li>O LiDAR de 10 minutos foi submetido ao mesmo controle de qualidade já documentado no projeto.</li><li>Os registros válidos foram agregados em médias horárias centradas no horário do MPAS, exigindo pelo menos 4 amostras de 10 minutos.</li><li>Antigo e corrigido foram comparados somente na interseção das mesmas horas.</li><li>Foi usada a mesma célula oceânica mais próxima e a mesma correspondência vertical entre centro da camada do MPAS e canal do LiDAR.</li><li>A significância da mudança do MSE foi testada com bootstrap móvel em blocos de 24 h, preservando autocorrelação e ciclo diurno.</li></ol>
<p><strong>P0/2021</strong> e <strong>LPI/2022</strong> são evidências independentes. ERA5 e INMET foram deliberadamente excluídos desta auditoria, conforme o escopo: aqui só o LiDAR decide.</p></section>

<section id="sst"><h2>4. O defeito de SST realmente desapareceu?</h2>
<figure><a href="figures/sst_old_corrected.png" target="_blank"><img src="figures/sst_old_corrected.png" alt="SST antiga e corrigida na célula dos LiDARes"></a><figcaption>Figura 1. SST registrada pelo próprio MPAS na célula oceânica mais próxima de cada LiDAR, durante a janela científica. A curva antiga mostra o efeito efetivo do preenchimento terrestre; a curva corrigida mostra o campo após a máscara ser convertida para o valor ausente aceito pelo interpolador. Clique para ampliar.</figcaption></figure>
<div class="scroll"><table><caption>Resumo da SST efetivamente vista pelo modelo (K). Mudança = corrigido − antigo.</caption><thead><tr><th>Sítio</th><th>Experimento</th><th>Média antiga</th><th>Média corrigida</th><th>Mudança</th><th>Mínimo antigo</th><th>Mínimo corrigido</th></tr></thead><tbody>{sst_rows(sst)}</tbody></table></div></section>

<section id="resultados"><h2>5. O vento ficou mais próximo do LiDAR?</h2>
<figure><a href="figures/metrics_old_corrected.png" target="_blank"><img src="figures/metrics_old_corrected.png" alt="RMSE e viés antigos e corrigidos por altura"></a><figcaption>Figura 2. RMSE e viés da velocidade por altura. Cada ponto antigo/corrigido usa a mesma observação e hora; portanto, a distância entre as curvas mede somente o efeito da nova integração. Menor RMSE e viés mais próximo de zero são melhores. Clique para ampliar.</figcaption></figure>
<figure><a href="figures/rmse_improvement.png" target="_blank"><img src="figures/rmse_improvement.png" alt="Redução do RMSE após correção"></a><figcaption>Figura 3. Redução do RMSE: positivo significa que o corrigido ficou mais próximo do LiDAR. A cor informa se o intervalo de 95% da diferença pareada do MSE exclui zero. Clique para ampliar.</figcaption></figure>
<div class="scroll"><table><caption>Todas as métricas por altura. “Redução RMSE” = RMSE antigo − RMSE corrigido. Viés e RMSE em m s⁻¹; WPD é o erro relativo da densidade de potência eólica; fase é o atraso (+) ou adiantamento (−), em horas, do máximo do ciclo diurno.</caption>
<thead><tr><th>Sítio</th><th>Exp.</th><th>Alt. (m)</th><th>N</th><th>Viés ant.</th><th>Viés corr.</th><th>RMSE ant.</th><th>RMSE corr.</th><th>Redução RMSE</th><th>r ant.</th><th>r corr.</th><th>Viés WPD ant. (%)</th><th>Viés WPD corr. (%)</th><th>Fase ant. (h)</th><th>Fase corr. (h)</th><th>Teste MSE</th></tr></thead><tbody>{metric_rows(table)}</tbody></table></div>
<figure><a href="figures/diurnal_100m.png" target="_blank"><img src="figures/diurnal_100m.png" alt="Ciclo diurno a 100 m antigo e corrigido"></a><figcaption>Figura 4. Ciclo diurno médio a 100 m em hora local (UTC−3). O LiDAR é idêntico nas duas comparações; diferenças entre as linhas antiga e corrigida resultam somente da correção aplicada à integração. Clique para ampliar.</figcaption></figure></section>

<section id="incerteza"><h2>6. A mudança é maior que a variabilidade amostral?</h2>
<p>Para cada altura foi calculada a diferença pareada <code>(erro_antigo² − erro_corrigido²)</code>. Valor positivo favorece o corrigido. O intervalo de 95% vem de 2.000 reamostragens em blocos móveis de 24 h.</p>
<div class="scroll"><table><caption>Teste pareado da mudança do MSE. RMSE em m s⁻¹; ΔMSE e intervalo em (m s⁻¹)².</caption><thead><tr><th>Sítio</th><th>Exp.</th><th>Alt. (m)</th><th>ΔMSE</th><th>IC 95%</th><th>RMSE ant.</th><th>RMSE corr.</th><th>Conclusão</th></tr></thead><tbody>{test_rows(tests)}</tbody></table></div></section>

<section><h2>7. Limites desta auditoria</h2><ul><li>Há somente um mês por sítio; o resultado não mede robustez sazonal ou interanual.</li><li>Os dois LiDARes amostram pontos costeiros específicos; a auditoria não substitui a avaliação espacial, ERA5 ou INMET do relatório oficial.</li><li>A correção pode remover um erro de SST e ainda assim expor outros erros do MPAS. Por isso “correção confirmada” e “vento melhor em toda métrica” são conclusões diferentes.</li><li>Nenhum resultado antigo foi sobrescrito. Esta página existe para revisão antes de qualquer substituição oficial.</li></ul></section>
<footer>Gerado por <code>scripts/06_audit/compare_corrected_lidar.py</code>. Tabelas-fonte em <code>tables/</code>; integridade em <code>run_integrity.json</code>; hashes em <code>sha256sums.txt</code>.</footer>
</main></body></html>"""
    (out_dir / "index.html").write_text(doc)


def sha256_manifest(out_dir: Path) -> None:
    rows = []
    for path in sorted(p for p in out_dir.rglob("*") if p.is_file()
                       and p.name != "sha256sums.txt"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(out_dir)}")
    (out_dir / "sha256sums.txt").write_text("\n".join(rows) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--integrity-json", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--block-hours", type=int, default=24)
    parser.add_argument("--extract-workers", type=int, default=4)
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args()

    cfg = load_config(runs_root=args.runs_root)
    out_dir = args.out_dir.resolve()
    figures = out_dir / "figures"
    tables = out_dir / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    obs_dir = REPO_ROOT / "data" / "obs"
    missing = [str(obs_dir / name) for name in ("P0_LIDAR_matrix.mat", "LPI_processed.csv.gz")
               if not (obs_dir / name).exists()]
    if missing:
        raise FileNotFoundError("missing LiDAR inputs: " + ", ".join(missing))

    integrity = json.loads(args.integrity_json.read_text())
    if not integrity.get("all_valid"):
        raise RuntimeError("corrected integrations failed integrity audit; comparison aborted")

    extract_all(
        cfg, args.runs_root, force=args.force_extract,
        workers=max(1, args.extract_workers),
    )
    scores, tests, paired = score_all(
        cfg, n_boot=args.n_boot, block_hours=args.block_hours,
    )
    table = comparison_table(scores, tests)
    sst = sst_summary(cfg)
    summary = verdict_summary(tests)

    scores.to_csv(tables / "all_scores.csv", index=False)
    tests.to_csv(tables / "paired_mse_tests.csv", index=False)
    table.to_csv(tables / "old_vs_corrected_metrics.csv", index=False)
    sst.to_csv(tables / "sst_at_lidar_cells.csv", index=False)
    (tables / "verdict.json").write_text(json.dumps(summary, indent=2) + "\n")
    integrity_target = out_dir / "run_integrity.json"
    if args.integrity_json.resolve() != integrity_target.resolve():
        shutil.copy2(args.integrity_json, integrity_target)

    make_metric_figure(table, figures / "metrics_old_corrected.png")
    make_improvement_figure(table, figures / "rmse_improvement.png")
    make_diurnal_figure(paired, figures / "diurnal_100m.png")
    make_sst_figure(cfg, figures / "sst_old_corrected.png")
    build_html(out_dir, integrity, table, tests, sst, summary)
    shutil.copy2(Path(__file__), out_dir / "compare_corrected_lidar.py")
    sha256_manifest(out_dir)

    print(json.dumps({
        "out_dir": str(out_dir),
        "summary": summary,
        "rows": len(table),
        "figures": sorted(p.name for p in figures.glob("*.png")),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
