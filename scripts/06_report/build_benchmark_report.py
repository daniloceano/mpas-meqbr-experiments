#!/usr/bin/env python3
"""MEQ-05.3 — self-contained HTML report of the MEQ-05.2 parallel benchmark.

Inputs (consolidated tables only; nothing else is read for results):
    results/tables/meq05_parallel_benchmark.csv   one row per trial (MEQ-05.2)
    results/tables/runtime_metrics.csv            production costs (EXP03 rows
                                                  for the cost correction; all
                                                  rows for the context table)

Output (one file; CSS, Plotly basic, data and JavaScript are inlined):
    results/report/meq05_parallel_benchmark.html

Style is reused from the technical report v2 without modifying it:
    docs/templates/report_v2/report.css       inlined verbatim at build time
    docs/templates/vendor/plotly-basic.min.js inlined verbatim at build time
    Plotly journal defaults (axis/layout/CONFIG/fmt) copied from
    docs/templates/report_v2/report.js; masthead, chapter navigation, captions
    with panel letters, tables and drawers use the existing CSS classes.

No result is typed by hand: every number in the page is computed below from
the two CSVs. The fixed constants in "Run metadata" are run settings
documented in docs/provenance/MEQ-05.2-benchmark-record.md, or the efficiency
criterion approved by the PI; they are not measurements.

The report presents options; it does not decide the MEQ-06 configuration.

Run:
    python scripts/06_report/build_benchmark_report.py [--output PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

BENCH_CSV = REPO_ROOT / "results/tables/meq05_parallel_benchmark.csv"
RUNTIME_CSV = REPO_ROOT / "results/tables/runtime_metrics.csv"
RECORD_MD = REPO_ROOT / "docs/provenance/MEQ-05.2-benchmark-record.md"
REPORT_CSS = REPO_ROOT / "docs/templates/report_v2/report.css"
PLOTLY_JS = REPO_ROOT / "docs/templates/vendor/plotly-basic.min.js"
DEFAULT_OUTPUT = REPO_ROOT / "results/report/meq05_parallel_benchmark.html"

# ---------------------------------------------------------------- run metadata
# Source: docs/provenance/MEQ-05.2-benchmark-record.md (namelist and hardware).
DT_S = 30                              # config_dt, unchanged from production
RESTART_LABEL = "2021-11-15 00 UTC"    # restart.2021-11-15_00.00.00.nc (EXP03)
CPU_MODEL = "2× Intel Xeon Gold 5420+"
SMT_THREADS = 2                        # threads per physical core (lscpu)
REP_RULE = 0.03                        # 3rd repetition only if |a-b|/mean > 3 %
# Approved by the PI (MEQ-05.3 brief): efficiency per physical core >= 70 %.
EFFICIENCY_CRITERION = 0.70
DAYS_PER_YEAR = 365                    # simulated days per simulated year
SECONDS_PER_DAY = 86400

BASE_CONFIG = "A_N008"                 # speed-up/efficiency reference (CSV)
EXP03_ID = "EXP03"
OPTIONS = ["A_N056", "B_N112", "C_N060", "D"]   # decision options, this order
PROPOSED = "B_N112"
PROPOSED_LABEL = "recomendação proposta — aguardando decisão do pesquisador"
D_CASES = ("D_N028x2_s0", "D_N028x2_s1")


# ---------------------------------------------------------------- helpers
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_value(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, check=False,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def br(value: float, decimals: int = 2) -> str:
    """pt-BR number: thousands '.', decimal ','."""
    if value is None or not np.isfinite(value):
        return "—"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def pct(value: float, decimals: int = 1) -> str:
    return br(100.0 * value, decimals) + " %"


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def throughput(s_per_step: float, steps_per_day: int) -> float:
    """Simulated days per wall day of the node for one run."""
    return SECONDS_PER_DAY / (s_per_step * steps_per_day)


# ---------------------------------------------------------------- computation
def compute() -> dict:
    bench = pd.read_csv(BENCH_CSV)
    runtime = pd.read_csv(RUNTIME_CSV)

    if not (bench["status"] == "ok").all() or not (bench["rc"] == 0).all():
        raise SystemExit("benchmark table has non-ok trials; stop")
    steps = bench["steps"].unique()
    if len(steps) != 1:
        raise SystemExit(f"trials with different step counts: {steps}")
    steps = int(steps[0])
    window_h = steps * DT_S / 3600.0
    steps_per_day = SECONDS_PER_DAY // DT_S
    if not np.isclose(steps_per_day, steps * 24.0 / window_h):
        raise SystemExit("steps per day inconsistent with the trial window")

    n_phys = int(bench["physical_cores"].max())
    n_logical = int(bench.loc[bench["series"] == "B", "ranks"].max())
    per_socket = int(bench.loc[bench["config"].isin(D_CASES), "ranks"].max())
    n_sockets = n_phys // per_socket
    if n_logical != n_phys * SMT_THREADS:
        raise SystemExit("logical CPU count inconsistent with SMT setting")

    # Per-configuration values, taken from the CSV's own cfg_* columns and
    # checked against the repetitions.
    cfg = {}
    for name, grp in bench.groupby("config", sort=False):
        row = grp.iloc[0]
        mean_sps = float(row["cfg_mean_s_per_step"])
        if not np.isclose(grp["s_per_step"].mean(), mean_sps, atol=1e-3):
            raise SystemExit(f"{name}: cfg_mean_s_per_step != mean of reps")
        cfg[name] = {
            "config": name, "series": row["series"], "ranks": int(row["ranks"]),
            "physical_cores": int(row["physical_cores"]),
            "pinning": row["pinning"], "n_reps": int(row["cfg_n_reps"]),
            "s_per_step": mean_sps,
            "reps_s_per_step": grp["s_per_step"].astype(float).tolist(),
            "spread_pct": float(row["cfg_rep_spread_pct"]),
            "speedup": float(row["speedup_vs_A8"]),
            "eff_phys": float(row["efficiency_vs_A8_physcores"]),
            "eff_ranks": float(row["efficiency_vs_A8_ranks"]),
            "throughput": throughput(mean_sps, steps_per_day),
            "reps_throughput": [throughput(s, steps_per_day)
                                for s in grp["s_per_step"].astype(float)],
        }

    base = cfg[BASE_CONFIG]
    base_cores = base["physical_cores"]
    s8 = base["s_per_step"]
    tp8 = base["throughput"]

    # Repetition-level speed-up/efficiency (points in the saturation figure).
    for c in cfg.values():
        c["reps_speedup"] = [s8 / s for s in c["reps_s_per_step"]]
        c["reps_eff_phys"] = [sp / (c["physical_cores"] / base_cores)
                              for sp in c["reps_speedup"]]
        chk_sp = s8 / c["s_per_step"]
        chk_eff = chk_sp / (c["physical_cores"] / base_cores)
        if not (np.isclose(chk_sp, c["speedup"], rtol=1e-3)
                and np.isclose(chk_eff, c["eff_phys"], rtol=1e-3)):
            raise SystemExit(f"{c['config']}: speed-up/efficiency mismatch")

    # Series D: two simultaneous 28-rank runs; node throughput = sum of both.
    d_rows = bench[bench["config"].isin(D_CASES)]
    d_reps = []
    for rep, grp in d_rows.groupby("repetition"):
        by_case = grp.set_index("config")
        tp_sum = sum(throughput(float(by_case.loc[k, "s_per_step"]),
                                steps_per_day) for k in D_CASES)
        csv_pair = float(by_case["pair_sim_days_per_node_day_integration"].iloc[0])
        if not np.isclose(tp_sum, csv_pair, atol=0.01):
            raise SystemExit("series D pair throughput differs from CSV")
        d_reps.append(tp_sum)
    s0, s1 = (cfg[k] for k in D_CASES)
    d_tp = s0["throughput"] + s1["throughput"]
    cfg["D"] = {
        "config": "D", "series": "D", "ranks": s0["ranks"] + s1["ranks"],
        "physical_cores": s0["physical_cores"] + s1["physical_cores"],
        "pinning": "2 × 28, um soquete cada", "throughput": d_tp,
        "reps_throughput": d_reps,
        "eff_phys": d_tp / (tp8 * (s0["physical_cores"] + s1["physical_cores"])
                            / base_cores),
        "n_reps": s0["n_reps"],
    }
    d_asym = s1["s_per_step"] / s0["s_per_step"] - 1.0

    # Production cost correction: EXP03 production s/step / series C s/step.
    exp03 = runtime[runtime["experiment"] == EXP03_ID].copy()
    if exp03.empty:
        raise SystemExit("no EXP03 rows in runtime_metrics.csv")
    prod_sps = float(exp03["wall_seconds_per_timestep"].mean())
    c_sps = cfg["C_N060"]["s_per_step"]
    corr = prod_sps / c_sps

    options = []
    for key in OPTIONS:
        c = cfg[key]
        cost_a = DAYS_PER_YEAR / c["throughput"]
        options.append({
            "key": key, "label": label_of(key), "ranks": c["ranks"],
            "physical_cores": c["physical_cores"], "throughput": c["throughput"],
            "reps_throughput": c["reps_throughput"], "eff_phys": c["eff_phys"],
            "meets": c["eff_phys"] >= EFFICIENCY_CRITERION,
            "cost_a": cost_a, "cost_b": cost_a * corr,
            "proposed": key == PROPOSED,
        })

    # Series E (I/O) against A56 (same ranks and pinning, no output).
    e_rows = bench[bench["series"] == "E"].sort_values("repetition")
    a56_compute_day = cfg["A_N056"]["s_per_step"] * steps_per_day
    io = []
    for _, r in e_rows.iterrows():
        io.append({
            "rep": int(r["repetition"]),
            "stream_output_s": float(r["stream_output_s"]),
            "d_total_s": float(r["delta_vs_A56_total_time_s"]),
            "d_ti_s": float(r["delta_vs_A56_time_integration_s"]),
            "d_wall_s": float(r["delta_vs_A56_wrapper_wall_s"]),
            "n_hist": int(r["n_history_written"]),
            "n_rst": int(r["n_restart_written"]),
            "hist_s": float(r["history_write_s_mean_filestat"]),
            "rst_s": float(r["restart_write_s_filestat"]),
            "extrap_s_day": float(r["io_extrap_s_per_sim_day"]),
            "method": str(r["io_extrap_method"]),
        })
    io_extrap_mean = float(np.mean([x["extrap_s_day"] for x in io]))

    # Historical production costs (context table).
    hist = runtime[["experiment", "period", "mpi_ranks", "n_cells",
                    "wall_seconds_per_timestep", "quality", "method"]].copy()

    spreads = {k: v["spread_pct"] for k, v in cfg.items() if "spread_pct" in v}
    max_spread_cfg = max(spreads, key=spreads.get)

    a_series = sorted((c for c in cfg.values() if c["series"] == "A"),
                      key=lambda c: c["physical_cores"])
    a_meeting = [c for c in a_series if c["eff_phys"] >= EFFICIENCY_CRITERION]

    exp03_cells = int(exp03["n_cells"].iloc[0])
    return {
        "bench": bench, "runtime": runtime, "cfg": cfg, "steps": steps,
        "window_h": window_h, "steps_per_day": steps_per_day,
        "n_phys": n_phys, "n_logical": n_logical, "per_socket": per_socket,
        "n_sockets": n_sockets, "base_cores": base_cores, "s8": s8, "tp8": tp8,
        "d_asym": d_asym, "prod_sps": prod_sps,
        "prod_rows": exp03[["period", "mpi_ranks", "wall_seconds_per_timestep",
                            "quality", "method"]].to_dict("records"),
        "c_sps": c_sps, "corr": corr, "options": options, "io": io,
        "io_extrap_mean": io_extrap_mean, "a56_compute_day": a56_compute_day,
        "hist": hist, "max_spread_cfg": max_spread_cfg,
        "max_spread": spreads[max_spread_cfg], "a_series": a_series,
        "a_meeting": a_meeting, "exp03_cells": exp03_cells,
        "trial_count": len(bench),
    }


def label_of(key: str) -> str:
    return {"A_N056": "A56", "B_N112": "B112", "C_N060": "C60",
            "D": "D (2 × 28)"}.get(key, key)


# ---------------------------------------------------------------- page text
def chart_payload(r: dict) -> dict:
    cfg = r["cfg"]
    a_pts = []
    for c in r["a_series"]:
        for k, (sp, ef) in enumerate(zip(c["reps_speedup"], c["reps_eff_phys"])):
            a_pts.append({"x": c["physical_cores"], "sp": sp, "eff": ef,
                          "rep": k + 1, "cfg": c["config"]})
    b = cfg["B_N112"]
    return {
        "criterion": EFFICIENCY_CRITERION,
        "base_cores": r["base_cores"], "n_phys": r["n_phys"],
        "a_mean": [{"x": c["physical_cores"], "sp": c["speedup"],
                    "eff": c["eff_phys"], "cfg": c["config"]}
                   for c in r["a_series"]],
        "a_pts": a_pts,
        "b_pts": [{"x": b["physical_cores"], "sp": sp, "eff": ef, "rep": k + 1}
                  for k, (sp, ef) in enumerate(zip(b["reps_speedup"],
                                                   b["reps_eff_phys"]))],
        "b_mean": {"x": b["physical_cores"], "sp": b["speedup"],
                   "eff": b["eff_phys"], "ranks": b["ranks"]},
        "options": [{"key": o["key"], "label": o["label"], "tp": o["throughput"],
                     "reps": o["reps_throughput"], "eff": o["eff_phys"],
                     "cost_a": o["cost_a"], "cost_b": o["cost_b"]}
                    for o in r["options"]],
    }


def build_html(r: dict, meta: dict) -> str:
    cfg = r["cfg"]
    o = {x["key"]: x for x in r["options"]}
    a56, b112, c60 = cfg["A_N056"], cfg["B_N112"], cfg["C_N060"]
    s0, s1 = cfg[D_CASES[0]], cfg[D_CASES[1]]
    hist = r["hist"]
    ranks_hist = sorted(hist["mpi_ranks"].unique())
    cells_hist = sorted(hist["n_cells"].unique())
    n_est = int((hist["quality"] != "measured").sum())
    multi_rank = [e for e, g in hist.groupby("experiment")
                  if g["mpi_ranks"].nunique() > 1]
    best_a = r["a_meeting"][-1] if r["a_meeting"] else None
    b_vs_a56 = b112["throughput"] / a56["throughput"] - 1.0
    a56_vs_c = a56["throughput"] / c60["throughput"] - 1.0
    io_share = r["io_extrap_mean"] / r["a56_compute_day"]

    # --- historical table (drawer)
    hist_rows = "".join(
        f"<tr><td>{esc(h.experiment)}</td><td>{esc(h.period)}</td>"
        f"<td>{int(h.mpi_ranks)}</td><td>{br(h.n_cells, 0)}</td>"
        f"<td>{br(h.wall_seconds_per_timestep, 3)}</td>"
        f"<td>{'medido' if h.quality == 'measured' else 'estimado'}</td></tr>"
        for h in hist.itertuples())

    # --- series table
    def cfg_list(series):
        names = [c["config"] for c in cfg.values()
                 if c["series"] == series and c["config"] != "D"]
        return ", ".join(f"<code>{esc(n)}</code>" for n in names)

    a_ns = "/".join(str(c["physical_cores"]) for c in reversed(r["a_series"]))
    series_rows = [
        ("A", f"Curva de saturação com núcleos físicos: N = {a_ns} ranks, "
              f"metade em cada soquete, uma rank por núcleo físico.",
         cfg_list("A"), "fixada, só núcleos físicos"),
        ("B", f"Efeito do SMT: {b112['ranks']} ranks, uma por CPU lógica, nos "
              f"mesmos {b112['physical_cores']} núcleos físicos.",
         cfg_list("B"), "fixada, uma rank por CPU lógica"),
        ("C", f"Referência de produção: {c60['ranks']} ranks sem fixação, como a "
              f"EXP03 foi rodada; liga o benchmark aos custos de produção.",
         cfg_list("C"), "sem fixação"),
        ("D", f"Vazão do nó com duas integrações independentes e simultâneas de "
              f"{s0['ranks']} ranks, uma em cada soquete.",
         cfg_list("D"), "fixada, um soquete por caso"),
        ("E", f"Custo de I/O: igual a A{a56['ranks']}, mas com a saída da produção "
              f"(<i>history</i> horário e um <i>restart</i> na janela).",
         cfg_list("E"), "fixada, como A56"),
    ]
    series_html = "".join(
        f"<tr><th>{s}</th><td style='text-align:left'>{t}</td>"
        f"<td style='text-align:left'>{c}</td><td>{p}</td></tr>"
        for s, t, c, p in series_rows)

    # --- measured table (all configurations)
    meas_rows = "".join(
        f"<tr><td>{esc(c['config'])}</td><td>{c['ranks']}</td>"
        f"<td>{c['physical_cores']}</td><td>{br(c['s_per_step'], 4)}</td>"
        f"<td>{br(c['spread_pct'], 2)}</td><td>{br(c['speedup'], 3)}</td>"
        f"<td>{pct(c['eff_phys'])}</td><td>{br(c['throughput'], 2)}</td></tr>"
        for c in cfg.values() if c["config"] != "D")

    # --- I/O table
    io_rows = "".join(
        f"<tr><td>r{x['rep']}</td><td>{br(x['stream_output_s'], 2)}</td>"
        f"<td>{br(x['d_ti_s'], 2)}</td><td>{br(x['d_wall_s'], 0)}</td>"
        f"<td>{x['n_hist']} × {br(x['hist_s'], 3)}</td>"
        f"<td>{x['n_rst']} × {br(x['rst_s'], 2)}</td>"
        f"<td><b>{br(x['extrap_s_day'], 2)}</b></td></tr>"
        for x in r["io"])

    # --- decision table
    def dec_row(x):
        mark = (f"<span class='pill gain'>{esc(PROPOSED_LABEL)}</span>"
                if x["proposed"] else "—")
        meets = ("sim" if x["meets"] else "não")
        return (f"<tr{' class=proposed' if x['proposed'] else ''}>"
                f"<th>{esc(x['label'])}</th>"
                f"<td>{x['ranks']} / {x['physical_cores']}</td>"
                f"<td>{br(x['throughput'], 2)}</td>"
                f"<td>{pct(x['eff_phys'])}</td><td>{meets}</td>"
                f"<td>{br(x['cost_a'], 1)}</td><td>{br(x['cost_b'], 1)}</td>"
                f"<td style='text-align:left'>{mark}</td></tr>")
    dec_rows = "".join(dec_row(x) for x in r["options"])

    prod_txt = "média das rodadas " + "; ".join(
        f"{p['period']}: {br(p['wall_seconds_per_timestep'], 4)} s/passo, "
        f"{p['mpi_ranks']} ranks, "
        f"{'medido' if p['quality'] == 'measured' else 'estimado'}"
        for p in r["prod_rows"])

    sha_rows = "".join(
        f"<tr><th><code>{esc(k)}</code></th><td><code>{esc(v)}</code></td></tr>"
        for k, v in meta["inputs"].items())

    a_eff_txt = "; ".join(f"A{c['physical_cores']}: {pct(c['eff_phys'])}"
                          for c in r["a_series"])

    body = f"""
<header class="masthead">
  <div class="masthead-inner">
    <p class="kicker">MPAS-Atmosphere · Margem Equatorial Brasileira · MEQ-05 · benchmark de paralelismo</p>
    <h1>Quantos processos usar no Swell para as integrações da MEQ-06?</h1>
    <p class="meta">Relatório gerado em {esc(meta['generated'])} · análise <code>{esc(meta['commit'])}</code>{' (árvore com alterações não versionadas)' if meta['dirty'] else ''} · dados do benchmark MEQ-05.2 ({r['trial_count']} ensaios)</p>
  </div>
</header>

<nav class="chapters" id="chapter-nav" aria-label="Capítulos">
  <div class="progress"><span id="progress-bar"></span></div>
  <ol>
    <li><a href="#contexto"><span>1</span>Contexto</a></li>
    <li><a href="#metodo"><span>2</span>Método</a></li>
    <li><a href="#saturacao"><span>3</span>Curva de saturação</a></li>
    <li><a href="#vazao"><span>4</span>Vazão do nó</a></li>
    <li><a href="#io"><span>5</span>I/O</a></li>
    <li><a href="#custo"><span>6</span>Custo da MEQ-06</a></li>
    <li><a href="#opcoes"><span>7</span>Opções</a></li>
    <li><a href="#limitacoes"><span>8</span>Limitações</a></li>
  </ol>
</nav>

<main>
  <div class="status"><strong>Status:</strong> tempos medidos no benchmark MEQ-05.2. Os custos da MEQ-06 são
    estimativas. A configuração para a MEQ-06 ainda não foi decidida: este relatório apresenta opções.</div>

  <section id="contexto" class="chapter">
    <p class="chapter-no">Capítulo 1</p>
    <h2>Contexto</h2>
    <p class="lead">A MEQ-06 vai integrar a EXP03 (malha Oval MEQ-02A, {br(r['exp03_cells'], 0)} células)
      por vários anos. Antes disso é preciso escolher quantos processos MPI usar e como distribuí-los
      no nó. A escolha é um compromisso entre prazo (dias simulados por dia) e uso do nó. Usar o
      maior número possível de núcleos não é, por si só, o objetivo.</p>
    <div class="questions">
      <div><b>O nó.</b> O Swell é um nó único com {r['n_sockets']} soquetes ({esc(CPU_MODEL)}),
        {r['per_socket']} núcleos físicos por soquete, {r['n_phys']} no total. Com SMT, cada núcleo
        executa {SMT_THREADS} threads, o que dá {r['n_logical']} CPUs lógicas. Todo o benchmark roda
        dentro desse nó, sem comunicação entre nós.</div>
      <div><b>A pergunta.</b> Até onde o tempo por passo cai quando se acrescentam núcleos? Vale usar o
        SMT? Rende mais uma integração grande ou duas menores lado a lado? Quanto pesa a escrita de saída?</div>
      <div><b>Por que medir de novo.</b> Os custos das rodadas de produção não formam uma curva de
        saturação. Mudam ao mesmo tempo o número de ranks, a malha e a física, e parte deles é estimada.</div>
    </div>
    <p>A tabela <code>runtime_metrics.csv</code> registra {len(hist)} rodadas de produção. Elas usaram
      de {ranks_hist[0]} a {ranks_hist[-1]} ranks, em {len(cells_hist)} malhas diferentes
      ({', '.join(br(c, 0) for c in cells_hist)} células). {n_est} desses tempos foram reconstruídos
      ou estimados, não medidos. Alguns experimentos ({', '.join(multi_rank)}) rodaram com números de
      ranks diferentes em cada período. Uma diferença de s/passo entre essas rodadas mistura, portanto,
      paralelismo, tamanho de malha, física e estado da máquina. Para isolar o efeito do paralelismo,
      a MEQ-05.2 repetiu o mesmo trecho da EXP03 variando apenas o número e a distribuição dos processos.</p>
    <details class="drawer">
      <summary>Custos históricos de produção (runtime_metrics.csv)</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Experimento</th><th>Período</th><th>Ranks</th><th>Células</th><th>s/passo (parede)</th><th>Qualidade</th></tr></thead>
        <tbody>{hist_rows}</tbody></table></div>
      <p class="caption">s/passo = tempo de parede da rodada inteira dividido pelo número de passos
        (inclui inicialização e I/O). As rodadas não são comparáveis entre si como medida de paralelismo.</p>
    </details>
    <nav class="pager"><span></span><a href="#metodo">Método →</a></nav>
  </section>

  <section id="metodo" class="chapter">
    <p class="chapter-no">Capítulo 2</p>
    <h2>Método</h2>
    <p class="lead">Cada ensaio integra {br(r['window_h'], 0)} h ({r['steps']} passos de {DT_S} s) a partir do
      <i>restart</i> de {RESTART_LABEL} da EXP03 de produção. Física, passo de tempo e malha são os da
      produção. Só mudam o número de processos e a forma de distribuí-los.</p>
    <ul>
      <li><b>Repetições.</b> {cfg[BASE_CONFIG]['n_reps']} por configuração. Uma terceira repetição seria
        feita se as duas diferissem em mais de {pct(REP_RULE, 0)}. Isso não ocorreu: a maior diferença foi
        {br(r['max_spread'], 2)}&nbsp;% (<code>{esc(r['max_spread_cfg'])}</code>).</li>
      <li><b>Fixação de processos.</b> Nas séries A, B, D e E, cada rank foi presa a uma CPU específica
        (<code>mpiexec -bind-to user:&lt;lista&gt;</code>). A fixação foi conferida três vezes durante cada
        ensaio. A série C roda sem fixação, como na produção, e o sistema operacional distribui as ranks.</li>
      <li><b>Tempo usado.</b> O timer <i>time integration</i> do MPAS, que exclui a inicialização.
        s/passo = <i>time integration</i> / {r['steps']}.</li>
      <li><b>Métricas.</b> Aceleração = s/passo de A{r['base_cores']} ÷ s/passo da configuração.
        Eficiência por núcleo físico = aceleração ÷ (núcleos físicos / {r['base_cores']}). Vazão =
        {br(SECONDS_PER_DAY, 0)} ÷ (s/passo × {br(r['steps_per_day'], 0)} passos por dia simulado), em dias
        simulados por dia de nó. A referência é A{r['base_cores']}, não um núcleo, porque um ensaio
        serial seria longo demais. A eficiência é, portanto, relativa a {r['base_cores']} núcleos.</li>
    </ul>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Série</th><th style="text-align:left">O que testa</th><th style="text-align:left">Configurações</th><th>Fixação</th></tr></thead>
      <tbody>{series_html}</tbody></table></div>
    <details class="drawer">
      <summary>Valores medidos por configuração (médias das repetições)</summary>
      <div class="scorecard-wrap"><table class="mini">
        <thead><tr><th>Configuração</th><th>Ranks</th><th>Núcleos físicos</th><th>s/passo</th><th>Diferença entre rep. (%)</th><th>Aceleração</th><th>Efic. por núcleo físico</th><th>Vazão (dias sim./dia)</th></tr></thead>
        <tbody>{meas_rows}</tbody></table></div>
      <p class="caption">Fonte: <code>results/tables/meq05_parallel_benchmark.csv</code>. Os casos D
        aparecem separados (cada um ocupa um soquete). A vazão de cada caso D isolado não é a vazão do nó.</p>
    </details>
    <nav class="pager"><a href="#contexto">← Contexto</a><a href="#saturacao">Curva de saturação →</a></nav>
  </section>

  <section id="saturacao" class="chapter">
    <p class="chapter-no">Capítulo 3</p>
    <h2>Curva de saturação</h2>
    <p class="lead">Na série A, o tempo por passo continua caindo até {r['n_phys']} núcleos, mas cada
      núcleo acrescentado rende menos. A eficiência fica em {a_eff_txt}.
      {f"A maior configuração da série A que cumpre o critério de {pct(EFFICIENCY_CRITERION, 0)} é A{best_a['physical_cores']}." if best_a else ""}
      A B{b112['ranks']}, com SMT, chega a uma aceleração de {br(b112['speedup'], 2)} nos mesmos
      {b112['physical_cores']} núcleos físicos ({pct(b112['eff_phys'])} por núcleo físico).</p>
    <div class="grid-2">
      <div>
        <div class="chart" id="chart-speedup" style="height:320px"></div>
        <p class="caption"><b>a</b> Aceleração em relação a A{r['base_cores']} em função dos núcleos
          físicos. Pontos: repetições. Linha cheia: média da série A. Tracejado: aceleração ideal
          (proporcional aos núcleos). Losango vazado: série B ({b112['ranks']} ranks com SMT), fora
          da curva A.</p>
      </div>
      <div>
        <div class="chart" id="chart-efficiency" style="height:320px"></div>
        <p class="caption"><b>b</b> Eficiência por núcleo físico (aceleração ÷ núcleos/{r['base_cores']}).
          Tracejado horizontal: critério de {pct(EFFICIENCY_CRITERION, 0)} aprovado pelo pesquisador.
          Pontos acima da linha cumprem o critério.</p>
      </div>
    </div>
    <nav class="pager"><a href="#metodo">← Método</a><a href="#vazao">Vazão do nó →</a></nav>
  </section>

  <section id="vazao" class="chapter">
    <p class="chapter-no">Capítulo 4</p>
    <h2>Vazão do nó</h2>
    <p class="lead">Para a MEQ-06, importa quantos dias simulados o nó inteiro produz por dia. A B112
      produz {br(b112['throughput'], 1)} dias simulados por dia de nó, {pct(b_vs_a56)} a mais que a A56
      ({br(a56['throughput'], 1)}). A C60, que reproduz a forma como a produção foi rodada, produz
      {br(c60['throughput'], 1)}, e a A56 rende {pct(a56_vs_c)} a mais que ela. As duas integrações
      simultâneas da série D somam {br(o['D']['throughput'], 1)}.</p>
    <div class="chart" id="chart-throughput" style="height:280px"></div>
    <p class="caption">Dias simulados por dia de nó = {br(SECONDS_PER_DAY, 0)} ÷ (s/passo × {br(r['steps_per_day'], 0)}).
      Barras cinza: valor calculado com o s/passo médio de cada configuração. Pontos pretos: repetições. Na série D,
      a vazão é a soma dos dois casos simultâneos ({br(s0['throughput'], 2)} no soquete 0 e
      {br(s1['throughput'], 2)} no soquete 1). O tempo de escrita de saída não está incluído (ver
      capítulo 5).</p>
    <nav class="pager"><a href="#saturacao">← Curva de saturação</a><a href="#io">I/O →</a></nav>
  </section>

  <section id="io" class="chapter">
    <p class="chapter-no">Capítulo 5</p>
    <h2>I/O</h2>
    <p class="lead">A série E repete a A56 com a saída da produção. Em cada repetição foram escritos
      {r['io'][0]['n_hist']} <i>history</i> e {r['io'][0]['n_rst']} <i>restart</i>. Extrapolado para um
      dia simulado, o custo de escrita fica em torno de {br(r['io_extrap_mean'], 1)} s, cerca de
      {pct(io_share, 2)} do tempo de cálculo de um dia simulado na A56
      ({br(r['a56_compute_day'], 0)} s). <b>Esse valor é uma extrapolação, não uma medida.</b></p>
    <div class="scorecard-wrap"><table class="mini">
      <thead><tr><th>Rep.</th><th>stream_output (s)</th><th>Δ time integration vs A56 (s)</th><th>Δ parede vs A56 (s)</th><th><i>history</i> (n × s)</th><th><i>restart</i> (n × s)</th><th>EXTRAPOLAÇÃO: s por dia simulado</th></tr></thead>
      <tbody>{io_rows}</tbody></table></div>
    <p class="caption">Medido: timer <code>stream_output</code> do MPAS e diferenças em relação à média
      da A56 (mesmas ranks e fixação, sem saída). Duração de escrita de cada arquivo = do nascimento à
      última modificação (ext4). Extrapolação = 24 × <i>history</i> médio + 1 × <i>restart</i>, supondo
      custo constante por arquivo. O timer e as durações por arquivo não foram reconciliados.</p>
    <nav class="pager"><a href="#vazao">← Vazão do nó</a><a href="#custo">Custo da MEQ-06 →</a></nav>
  </section>

  <section id="custo" class="chapter">
    <p class="chapter-no">Capítulo 6</p>
    <h2>Custo da MEQ-06</h2>
    <p class="lead">Custo em dias de nó por ano simulado ({DAYS_PER_YEAR} dias) = {DAYS_PER_YEAR} ÷ vazão.
      Há duas variantes, e as duas são <b>estimativas</b>.</p>
    <ol>
      <li><b>(a) Pelo trecho medido.</b> Usa a vazão das 3 h de benchmark, sem inicialização e sem I/O.</li>
      <li><b>(b) Corrigida pela produção.</b> A produção da EXP03 levou {br(r['prod_sps'], 4)} s/passo
        ({prod_txt}). O tempo de parede da produção inclui inicialização, leitura de fronteiras,
        escrita de saída e o mês inteiro de meteorologia. A série C reproduz a mesma configuração
        ({c60['ranks']} ranks, sem fixação) e mede {br(r['c_sps'], 4)} s/passo no trecho de 3 h. A razão
        {br(r['prod_sps'], 4)} ÷ {br(r['c_sps'], 4)} = <b>{br(r['corr'], 3)}</b> resume o que o trecho medido
        não captura. A variante (b) multiplica (a) por essa razão. A hipótese é que a razão vale para as
        demais configurações, e isso não foi verificado.</li>
    </ol>
    <div class="chart" id="chart-cost" style="height:280px"></div>
    <p class="caption">Estimativas de dias de nó por ano simulado. Barras cinza: variante (a), pelo
      trecho medido. Barras pretas: variante (b), corrigida pela razão produção/série C
      ({br(r['corr'], 3)}). Na série D, o custo supõe duas integrações independentes (por exemplo, dois anos)
      rodando ao mesmo tempo, uma em cada soquete.</p>
    <nav class="pager"><a href="#io">← I/O</a><a href="#opcoes">Opções →</a></nav>
  </section>

  <section id="opcoes" class="chapter">
    <p class="chapter-no">Capítulo 7</p>
    <h2>Opções para decisão</h2>
    <p class="lead">Quatro formas de ocupar o nó. A tabela reúne vazão, eficiência por núcleo físico,
      o critério de {pct(EFFICIENCY_CRITERION, 0)} e o custo estimado da MEQ-06. Não há pesos nem nota
      composta.</p>
    <div class="scorecard-wrap"><table class="decision">
      <thead><tr><th>Opção</th><th>Ranks / núcleos físicos</th><th>Vazão (dias sim. por dia de nó)</th><th>Efic. por núcleo físico</th><th>Cumpre {pct(EFFICIENCY_CRITERION, 0)}?</th><th>Custo MEQ-06 (a), dias de nó/ano</th><th>Custo MEQ-06 (b), dias de nó/ano</th><th style="text-align:left">Situação</th></tr></thead>
      <tbody>{dec_rows}</tbody></table></div>
    <p class="caption">Vazão e custos com o s/passo médio de cada configuração; custos são estimativas
      (capítulo 6). Eficiência relativa a A{r['base_cores']}. Na D, a eficiência é a do par:
      vazão somada ÷ (vazão de A{r['base_cores']} × {r['n_phys']}/{r['base_cores']}).</p>
    <div class="conclusion">
      <h3>Situação da decisão</h3>
      <p class="verdict">A B112 aparece como <b>{esc(PROPOSED_LABEL)}</b>. Nenhuma configuração foi
        decidida neste relatório. A escolha cabe ao pesquisador, considerando também as limitações
        abaixo, em especial a igualdade numérica entre números de processos, que não foi verificada.</p>
    </div>
    <nav class="pager"><a href="#custo">← Custo da MEQ-06</a><a href="#limitacoes">Limitações →</a></nav>
  </section>

  <section id="limitacoes" class="chapter">
    <p class="chapter-no">Capítulo 8</p>
    <h2>Limitações</h2>
    <p class="lead">Limitações registradas em <code>docs/provenance/MEQ-05.2-benchmark-record.md</code>
      ("O que não foi verificado"), mais as que decorrem das escolhas deste relatório.</p>
    <ul>
      <li><b>Igualdade numérica não verificada.</b> Não se verificou se o resultado numérico muda com o
        número de processos. Os campos de saída não foram comparados, e os ensaios sem saída não geram arquivos.</li>
      <li><b>Janela única de {br(r['window_h'], 0)} h</b> ({RESTART_LABEL}). Não se verificou se ela
        reproduz, na mesma proporção de um dia completo, a frequência de chamadas periódicas, como a radiação.</li>
      <li><b>Assimetria entre soquetes na série D.</b> Com os dois casos simultâneos, o soquete 1 levou
        {br(s1['s_per_step'], 4)} s/passo e o soquete 0, {br(s0['s_per_step'], 4)} s/passo
        ({pct(r['d_asym'])} mais lento). A causa não foi investigada. Numa produção em D, a metade mais lenta
        determina quando o nó fica livre, salvo se a carga for redistribuída.</li>
      <li><b>Frequência de CPU</b> (governor, turbo, temperatura) não foi registrada nem controlada.</li>
      <li><b>Uso e banda de memória</b> não foram medidos.</li>
      <li><b>Fixação amostrada</b> só três vezes por ensaio, até 330 s. Nos ensaios mais longos (A28, A14,
        A8, D), o restante da execução não foi amostrado.</li>
      <li><b>Cache de páginas</b> não foi controlado. O <i>restart</i> de entrada é relido a cada ensaio.</li>
      <li><b>Extrapolação de I/O</b> supõe custo constante por arquivo e não inclui operações anteriores à
        criação do arquivo. O timer <code>stream_output</code> e as durações por arquivo não foram reconciliados.
        O conteúdo dos arquivos escritos na série E não foi inspecionado.</li>
      <li><b>Correção de custo (variante b).</b> A razão produção/série C ({br(r['corr'], 3)}) foi obtida
        com {c60['ranks']} ranks sem fixação. Supõe-se que ela vale para as demais configurações, o que
        não foi verificado.</li>
      <li><b>Eficiência relativa a A{r['base_cores']}</b>, não a um núcleo. A perda de eficiência de 1 a
        {r['base_cores']} núcleos não está medida.</li>
    </ul>
    <nav class="pager"><a href="#opcoes">← Opções</a><a href="#contexto">Início ↑</a></nav>
  </section>

  <footer class="footer">
    <p>Gerado por <code>scripts/06_report/build_benchmark_report.py</code> (MEQ-05.3) a partir de tabelas
      consolidadas; não edite à mão. Estilo: <code>docs/templates/report_v2/report.css</code>, sem
      modificação; gráficos: Plotly basic {esc(meta['plotly_version'])}, embutido. Paleta: Crameri (2018),
      doi:10.5281/zenodo.1243862. Registro de proveniência:
      <code>docs/provenance/MEQ-05.2-benchmark-record.md</code>.</p>
    <table class="kv"><tbody>{sha_rows}</tbody></table>
  </footer>
</main>
"""
    return body


EXTRA_CSS = """
/* MEQ-05.3 benchmark report: additions only (report.css is inlined above unchanged). */
.chapter ul { max-width: 880px; }
.chapter ul li { margin: 4px 0; }
table.decision tr.proposed th { font-weight: 700; }
table.decision td, table.decision th { border-bottom: 1px solid var(--rule); }
.pager span { flex: 1; }
.footer table.kv { margin-top: 8px; }
.footer table.kv th { width: auto; }
.footer table.kv code { overflow-wrap: anywhere; word-break: break-all; }
"""

# Plotly journal defaults copied from docs/templates/report_v2/report.js
# (fmt, axis, layout, CONFIG, plot, navigation), then the three charts.
REPORT_JS = r"""
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('bench-data').textContent);
  var $ = function (id) { return document.getElementById(id); };
  function fmt(v, d) {
    if (d === undefined) d = 2;
    if (v === null || v === undefined || !isFinite(v)) return '—';
    return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  var FONT = { family: 'Arial, Helvetica, sans-serif', size: 11, color: '#1a1a1a' };
  function axis(o) {
    return Object.assign({
      showline: true, linecolor: '#1a1a1a', linewidth: 0.8, ticks: 'outside', ticklen: 3,
      tickwidth: 0.8, tickcolor: '#1a1a1a', showgrid: false, zeroline: false, automargin: true,
      title: { font: { size: 11 } }
    }, o || {});
  }
  function layout(extra) {
    var base = {
      font: FONT, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      margin: { l: 56, r: 12, t: 12, b: 42 }, showlegend: false, hovermode: 'closest',
      hoverlabel: { font: { family: FONT.family, size: 11 }, bgcolor: '#fff', bordercolor: '#1a1a1a' },
      legend: { orientation: 'h', y: -0.22, x: 0, font: { size: 10 } },
      xaxis: axis(), yaxis: axis()
    };
    extra = extra || {};
    Object.keys(extra).forEach(function (k) {
      if (/^[xy]axis\d*$/.test(k)) base[k] = axis(extra[k]); else base[k] = extra[k];
    });
    return base;
  }
  var CONFIG = {
    displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines', 'hoverCompareCartesian', 'hoverClosestCartesian'],
    toImageButtonOptions: { format: 'svg', filename: 'meq05_parallel_benchmark' }
  };
  function plot(id, traces, lay) {
    var node = $(id); if (!node) return;
    if (!window.Plotly) { node.innerHTML = '<div class="empty">Biblioteca de gráficos indisponível.</div>'; return; }
    Plotly.react(node, traces, layout(lay), CONFIG);
  }
  function pick(a, k) { return a.map(function (p) { return p[k]; }); }

  function initNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll('#chapter-nav a'));
    var sections = links.map(function (a) { return document.querySelector(a.getAttribute('href')); });
    function onScroll() {
      var y = window.scrollY + window.innerHeight * 0.3, current = 0;
      sections.forEach(function (s, i) { if (s && s.offsetTop <= y) current = i; });
      links.forEach(function (a, i) { a.classList.toggle('active', i === current); });
      var h = document.documentElement.scrollHeight - window.innerHeight;
      $('progress-bar').style.width = (h > 0 ? 100 * window.scrollY / h : 0) + '%';
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  function initSaturation() {
    var b0 = D.base_cores, xmax = D.n_phys;
    var xs = [b0, xmax];
    var ticks = pick(D.a_mean, 'x');
    var common = { xaxis: { title: { text: 'núcleos físicos' }, range: [0, xmax + 4], tickvals: ticks },
                   showlegend: true, legend: { orientation: 'h', yanchor: 'bottom', y: 1.04, x: 0, font: { size: 10 } },
                   margin: { l: 56, r: 12, t: 58, b: 42 } };
    var spTr = [
      { type: 'scatter', mode: 'lines', x: xs, y: xs.map(function (x) { return x / b0; }), name: 'ideal',
        line: { color: '#8c8c8c', width: 1, dash: 'dash' }, hoverinfo: 'skip' },
      { type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, 'sp'), name: 'série A (média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: aceleração %{y:.3f}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, 'sp'), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:.3f}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.b_pts, 'x'), y: pick(D.b_pts, 'sp'),
        name: 'série B (' + D.b_mean.ranks + ' ranks, SMT)',
        marker: { symbol: 'diamond-open', color: '#1a1a1a', size: 9, line: { width: 1.4 } },
        customdata: pick(D.b_pts, 'rep'), hovertemplate: 'B r%{customdata}: %{y:.3f}<extra></extra>' }
    ];
    plot('chart-speedup', spTr, Object.assign({}, common, {
      yaxis: { title: { text: 'aceleração em relação a ' + b0 + ' núcleos' }, rangemode: 'tozero' } }));

    var efTr = [
      { type: 'scatter', mode: 'lines', x: [0, xmax + 4], y: [D.criterion, D.criterion],
        name: 'critério ' + fmt(100 * D.criterion, 0) + ' %', line: { color: '#883007', width: 1, dash: 'dash' }, hoverinfo: 'skip' },
      { type: 'scatter', mode: 'lines', x: pick(D.a_mean, 'x'), y: pick(D.a_mean, 'eff'), name: 'série A (média)',
        line: { color: '#1a1a1a', width: 1.4 }, customdata: pick(D.a_mean, 'cfg'),
        hovertemplate: '%{customdata}: %{y:.1%}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.a_pts, 'x'), y: pick(D.a_pts, 'eff'), name: 'série A (repetições)',
        marker: { color: '#1a1a1a', size: 6 }, customdata: D.a_pts.map(function (p) { return [p.cfg, p.rep]; }),
        hovertemplate: '%{customdata[0]} r%{customdata[1]}: %{y:.1%}<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: pick(D.b_pts, 'x'), y: pick(D.b_pts, 'eff'),
        name: 'série B (' + D.b_mean.ranks + ' ranks, SMT)',
        marker: { symbol: 'diamond-open', color: '#1a1a1a', size: 9, line: { width: 1.4 } },
        customdata: pick(D.b_pts, 'rep'), hovertemplate: 'B r%{customdata}: %{y:.1%}<extra></extra>' }
    ];
    plot('chart-efficiency', efTr, Object.assign({}, common, {
      yaxis: { title: { text: 'eficiência por núcleo físico' }, tickformat: '.0%', range: [0, 1.08] } }));
  }

  function initThroughput() {
    var O = D.options, labels = pick(O, 'label');
    var tr = [
      { type: 'bar', x: labels, y: pick(O, 'tp'), marker: { color: '#8c8c8c' }, width: 0.55,
        name: 'média', hovertemplate: '%{x}: %{y:.2f} dias simulados por dia de nó<extra></extra>' }
    ];
    var px = [], py = [];
    O.forEach(function (o) { o.reps.forEach(function (v) { px.push(o.label); py.push(v); }); });
    tr.push({ type: 'scatter', mode: 'markers', x: px, y: py, name: 'repetições',
      marker: { color: '#1a1a1a', size: 6 },
      hovertemplate: '%{x} (repetição): %{y:.2f}<extra></extra>' });
    plot('chart-throughput', tr, { yaxis: { title: { text: 'dias simulados por dia de nó' }, rangemode: 'tozero' },
      xaxis: { type: 'category' } });
  }

  function initCost() {
    var O = D.options, labels = pick(O, 'label');
    var tr = [
      { type: 'bar', orientation: 'h', y: labels, x: pick(O, 'cost_a'), name: '(a) pelo trecho medido — estimativa',
        marker: { color: '#b8b8b8' },
        hovertemplate: '%{y} (a): %{x:.1f} dias de nó por ano simulado<extra></extra>' },
      { type: 'bar', orientation: 'h', y: labels, x: pick(O, 'cost_b'), name: '(b) corrigida pela produção — estimativa',
        marker: { color: '#1a1a1a' },
        hovertemplate: '%{y} (b): %{x:.1f} dias de nó por ano simulado<extra></extra>' }
    ];
    plot('chart-cost', tr, { barmode: 'group', showlegend: true, legend: { orientation: 'h', y: 1.16, x: 0 },
      xaxis: { title: { text: 'dias de nó por ano simulado (estimativa)' }, rangemode: 'tozero' },
      yaxis: { type: 'category', autorange: 'reversed' }, margin: { l: 80, r: 12, t: 34, b: 42 } });
  }

  function safe(fn, name) {
    try { fn(); } catch (err) { if (window.console) console.error('[benchmark report] ' + name, err); }
  }
  function boot() {
    safe(initNav, 'nav');
    safe(initSaturation, 'saturation');
    safe(initThroughput, 'throughput');
    safe(initCost, 'cost');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
"""


def assemble(body: str, payload: dict) -> str:
    css = REPORT_CSS.read_text(encoding="utf-8")
    plotly = PLOTLY_JS.read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    for chunk in (plotly, REPORT_JS):
        if "</script" in chunk.lower():
            raise SystemExit("inline script contains '</script'")
    return (
        "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<link rel=\"icon\" href=\"data:,\">\n"
        "<title>MPAS MEQ-Br — Benchmark de paralelismo (MEQ-05)</title>\n"
        f"<style>\n{css}\n{EXTRA_CSS}\n</style>\n</head>\n<body>\n{body}\n"
        f"<script>\n{plotly}\n</script>\n"
        f"<script type=\"application/json\" id=\"bench-data\">{data}</script>\n"
        f"<script>\n{REPORT_JS}\n</script>\n</body>\n</html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    results = compute()
    plotly_head = PLOTLY_JS.read_text(encoding="utf-8")[:200]
    plotly_version = next((tok for tok in plotly_head.split() if tok.startswith("v2.")),
                          "unknown")
    meta = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git_value("rev-parse", "--short", "HEAD"),
        "dirty": bool(git_value("status", "--porcelain")),
        "plotly_version": plotly_version,
        "inputs": {str(p.relative_to(REPO_ROOT)) + " (sha256)": sha256(p)
                   for p in (BENCH_CSV, RUNTIME_CSV, RECORD_MD)},
    }
    page = assemble(build_html(results, meta), chart_payload(results))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size / 1e6:.2f} MB)")
    for o in results["options"]:
        print(f"  {o['label']:<11} tp={o['throughput']:.3f} eff={o['eff_phys']:.4f} "
              f"meets={o['meets']} cost_a={o['cost_a']:.2f} cost_b={o['cost_b']:.2f}")
    print(f"  correction ratio = {results['corr']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
