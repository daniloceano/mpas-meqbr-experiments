#!/usr/bin/env python3
"""Read-only monitor of the MEQ-06 production run on Swell (MEQ-06.8).

Opens ONE ssh connection per refresh, runs a short read-only shell snippet
(ls, tail, grep, ps, df, uptime; no writes, no kill) and prints a one-screen
summary: progress bar to the next decision point (DEC-MEQ-006), simulated
date, monthly chunk, phase, throughput, ETAs, process/log/error/disk/load.

Standard library only (macOS system python3 is enough).

    python3 scripts/07_production/monitor_production.py
    python3 scripts/07_production/monitor_production.py --watch 10
    python3 scripts/07_production/monitor_production.py --run-dir <dir> --no-color
"""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CFG = HERE / "monitor_production.cfg"

# Remote snippet: read-only. Prints KEY<TAB>value lines between markers.
REMOTE = r"""
set +e
export PROC
echo "@@BEGIN"
printf 'NOW\t%s\n' "$(date -u +%s)"
printf 'ME\t%s\n' "$(id -un)"
printf 'NPROC\t%s\n' "$(nproc)"
printf 'LOAD\t%s\n' "$(cut -d' ' -f1-3 /proc/loadavg)"
if [ ! -d "$RUN_DIR" ]; then
  printf 'RUNDIR\tmissing\n'
else
  printf 'RUNDIR\tok\n'
  cd "$RUN_DIR"
  df -P -B1 . | awk 'NR==2{printf "DF\t%s %s\n",$4,$2}'
  LOG=$(ls -t $LOG_GLOB 2>/dev/null | head -1)
  if [ -n "$LOG" ]; then
    printf 'LOG\t%s %s\n' "$(stat -c %Y "$LOG")" "$LOG"
    printf 'LASTSTEP\t%s\n' "$(tail -n 400 "$LOG" | grep -o 'Begin timestep [0-9_:-]*' | tail -1 | awk '{print $3}')"
    printf 'NERR\t%s\n' "$(grep -c -E 'CRITICAL ERROR|ERROR' "$LOG")"
    grep -E 'CRITICAL ERROR|ERROR' "$LOG" | tail -2 | cut -c1-160 | sed 's/^/ERRLINE\t/'
  fi
  ls -l --time-style=+%s $HIST_GLOB 2>/dev/null | awk '{print "H\t"$6" "$7}' | tail -n 2000
  ls -l --time-style=+%s $RST_GLOB 2>/dev/null | awk '{print "R\t"$6" "$7}' | tail -n 1
fi
ps -eo user:20,pcpu,comm --no-headers | awk '$2>=1 || $3==ENVIRON["PROC"] {print "PS\t"$1" "$2" "$3}' | head -n 2000
echo "@@END"
"""


def load_cfg(path: Path) -> dict:
    cp = configparser.ConfigParser()
    if not cp.read(path):
        sys.exit(f"config not found: {path}")
    d = lambda s: dt.datetime.strptime(s.strip(), "%Y-%m-%d")  # noqa: E731
    return {
        "host": cp["ssh"]["host"],
        "run_dir": cp["run"]["run_dir"],
        "log_glob": cp["run"]["log_glob"],
        "hist_glob": cp["run"]["history_glob"],
        "rst_glob": cp["run"]["restart_glob"],
        "process": cp["run"]["process"],
        "spinup": d(cp["dates"]["spinup_start"]),
        "prod": d(cp["dates"]["production_start"]),
        # Decision point = end of day -> restart at next 00 UTC.
        "decisions": [d(x) + dt.timedelta(days=1)
                      for x in cp["dates"]["decision_points"].split(",")],
        "stale_min": cp.getfloat("thresholds", "stale_minutes"),
        "min_free_tb": cp.getfloat("thresholds", "min_free_tb"),
        "rate_h": cp.getfloat("thresholds", "rate_window_hours"),
        "foreign_pct": cp.getfloat("thresholds", "foreign_cpu_pct"),
    }


def fetch(cfg: dict) -> dict:
    env = (f"RUN_DIR={shlex.quote(cfg['run_dir'])} "
           f"LOG_GLOB={shlex.quote(cfg['log_glob'])} "
           f"HIST_GLOB={shlex.quote(cfg['hist_glob'])} "
           f"RST_GLOB={shlex.quote(cfg['rst_glob'])} "
           f"PROC={shlex.quote(cfg['process'])}")
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
           cfg["host"], f"{env} bash -s"]
    p = subprocess.run(cmd, input=REMOTE, capture_output=True, text=True,
                       timeout=120)
    out = p.stdout
    if "@@BEGIN" not in out or "@@END" not in out:
        raise RuntimeError(f"ssh failed (exit {p.returncode}): "
                           f"{p.stderr.strip()[-300:]}")
    body = out.split("@@BEGIN", 1)[1].split("@@END", 1)[0]
    r = {"H": [], "R": [], "PS": [], "ERRLINE": []}
    for line in body.splitlines():
        if "\t" not in line:
            continue
        k, v = line.split("\t", 1)
        if k in r and isinstance(r[k], list):
            r[k].append(v)
        else:
            r[k] = v
    return r


TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2})[.:](\d{2})[.:](\d{2})")


def ts(name: str) -> dt.datetime | None:
    m = TS_RE.search(name)
    if not m:
        return None
    return dt.datetime.strptime(f"{m[1]} {m[2]}:{m[3]}:{m[4]}", "%Y-%m-%d %H:%M:%S")


class Style:
    def __init__(self, on: bool):
        self.on = on

    def c(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    ok = lambda self, s: self.c("32", s)       # noqa: E731
    warn = lambda self, s: self.c("33;1", s)   # noqa: E731
    bad = lambda self, s: self.c("31;1", s)    # noqa: E731
    dim = lambda self, s: self.c("2", s)       # noqa: E731
    bold = lambda self, s: self.c("1", s)      # noqa: E731


def fmt_age(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 3600:
        return f"{sec // 60} min"
    if sec < 86400:
        return f"{sec / 3600:.1f} h"
    return f"{sec / 86400:.1f} d"


def bar(cfg, sim, target, st: Style, width=50) -> list[str]:
    t0 = cfg["spinup"]
    span = (target - t0).total_seconds()
    frac = 0.0 if sim is None else min(1.0, max(0.0, (sim - t0).total_seconds() / span))
    n = int(round(frac * width))
    cells = ["█"] * n + ["░"] * (width - n)
    marks = [(cfg["prod"], "P")] + [(d, "D") for d in cfg["decisions"] if d <= target]
    tick = [" "] * (width + 1)
    for d, ch in marks:
        i = int(round((d - t0).total_seconds() / span * width))
        if 0 <= i <= width:
            tick[i] = ch
    fill = "".join(cells)
    line = "[" + (st.ok(fill[:n]) + st.dim(fill[n:])) + f"] {frac * 100:5.1f} %"
    return [line, " " + "".join(tick),
            st.dim(f" {t0:%Y-%m-%d}  P=produção {cfg['prod']:%Y-%m-%d}  "
                   f"D=ponto de decisão  → {target - dt.timedelta(days=1):%Y-%m-%d}")]


def throughput(hist, window_h):
    """Simulated days per wall day over the last `window_h` h of output."""
    pts = []
    for v in hist:
        mt, name = v.split(" ", 1)
        t = ts(name)
        if t:
            pts.append((int(mt), t))
    pts.sort()
    if len(pts) < 2:
        return None, pts
    end_w, end_s = pts[-1]
    start = [p for p in pts if p[0] >= end_w - window_h * 3600]
    if len(start) < 2:
        start = pts[-2:]
    w0, s0 = start[0]
    dw = end_w - w0
    if dw <= 0:
        return None, pts
    return (end_s - s0).total_seconds() / dw, pts


def render(cfg: dict, r: dict, st: Style) -> str:
    now = int(r.get("NOW", time.time()))
    out = [st.bold(f"Simulação climatológica (configuração EXP03)   ({cfg['host']}:{cfg['run_dir']})"),
           st.dim(f"consulta {dt.datetime.fromtimestamp(now, dt.timezone.utc).replace(tzinfo=None):%Y-%m-%d %H:%M} UTC")]
    procs = [p.split() for p in r["PS"]]
    model = [p for p in procs if len(p) >= 3 and p[2] == cfg["process"]]
    nproc = int(r.get("NPROC", "0") or 0)
    load = r.get("LOAD", "?")

    sim = None
    hist_names = r["H"]
    rate, pts = throughput(hist_names, cfg["rate_h"])
    last_out_w = pts[-1][0] if pts else None
    if pts:
        sim = pts[-1][1]
    step = ts(r.get("LASTSTEP", "") or "")
    if step and (sim is None or step > sim):
        sim = step

    if r.get("RUNDIR") == "missing" or (sim is None and not model):
        out.append("")
        out.append(st.warn("Produção: NÃO INICIADA") +
                   st.dim(" (diretório ausente ou sem saída/log)"))
    else:
        target = next((d for d in cfg["decisions"] if sim < d), cfg["decisions"][-1])
        out.append("")
        out += bar(cfg, sim, target, st)
        phase = "spin-up" if sim < cfg["prod"] else "produção"
        cs = cfg["spinup"] if sim < dt.datetime(2021, 12, 1) else sim.replace(day=1, hour=0, minute=0, second=0)
        ce = (cs.replace(day=1) + dt.timedelta(days=32)).replace(day=1) if cs != cfg["spinup"] else dt.datetime(2021, 12, 1)
        out.append("")
        out.append(f"Data simulada : {st.bold(f'{sim:%Y-%m-%d %H:%M}')} UTC   fase: {st.bold(phase)}")
        out.append(f"Trecho mensal : {cs:%Y-%m-%d} → {ce:%Y-%m-%d}")
        if rate:
            out.append(f"Vazão         : {rate:.2f} dias simulados / dia real "
                       f"(últimas {cfg['rate_h']:.0f} h de saída)")
            for d in cfg["decisions"]:
                lab = f"{d - dt.timedelta(days=1):%Y-%m-%d}"
                if sim >= d:
                    out.append(f"  ETA {lab}  : {st.ok('atingido')}")
                else:
                    days = (d - sim).total_seconds() / 86400 / rate
                    eta = dt.datetime.fromtimestamp(now, dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(days=days)
                    out.append(f"  ETA {lab}  : {eta:%Y-%m-%d} ({days:.0f} dias reais)")
        else:
            out.append("Vazão         : " + st.dim("indisponível (menos de 2 arquivos de saída)"))
        if r["R"]:
            out.append(f"Último restart: {r['R'][-1].split(' ', 1)[1]}")

    # --- state
    out.append("")
    run_txt = st.ok(f"rodando ({len(model)} processos)") if model else st.dim("parado")
    out.append(f"Modelo        : {run_txt}")
    if "LOG" in r:
        lmt, lname = r["LOG"].split(" ", 1)
        age = now - int(lmt)
        txt = f"{fmt_age(age)} atrás ({lname})"
        if model and age > cfg["stale_min"] * 60:
            txt = st.bad(f"⚠ {txt} — possível travamento")
        out.append(f"Último log    : {txt}")
        nerr = int(r.get("NERR", "0") or 0)
        if nerr:
            out.append(st.bad(f"Erros no log  : {nerr}"))
            for e in r["ERRLINE"]:
                out.append(st.bad(f"   {e.strip()}"))
        else:
            out.append(f"Erros no log  : {st.ok('nenhum')}")
    if last_out_w:
        out.append(f"Última saída  : {fmt_age(now - last_out_w)} atrás")
    if "DF" in r:
        free, tot = (int(x) for x in r["DF"].split())
        ftb = free / 1e12
        txt = f"{ftb:.1f} TB livres de {tot / 1e12:.0f} TB"
        out.append("Disco         : " + (st.bad(f"⚠ {txt} (< {cfg['min_free_tb']} TB)")
                                         if ftb < cfg["min_free_tb"] else txt))
    l1 = float(load.split()[0]) if load != "?" else 0
    foreign = {}
    for p in procs:
        if len(p) >= 3 and p[0] != r.get("ME") and float(p[1]) >= cfg["foreign_pct"]:
            foreign[p[0]] = foreign.get(p[0], 0) + float(p[1])
    ltxt = f"carga {load} em {nproc} CPUs lógicas"
    out.append("Máquina       : " + (st.warn(ltxt) if nproc and l1 > nproc * 0.9 else ltxt))
    if foreign:
        lst = ", ".join(f"{u} {c / 100:.1f} núcleos" for u, c in sorted(foreign.items(), key=lambda x: -x[1]))
        out.append("Outros usuários: " + st.warn(lst))
    else:
        out.append("Outros usuários: " + st.ok("nenhum disputando núcleos"))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CFG)
    ap.add_argument("--run-dir", help="override run_dir (e.g. an existing run, to test)")
    ap.add_argument("--watch", type=float, metavar="N", help="refresh every N minutes")
    ap.add_argument("--no-color", action="store_true")
    a = ap.parse_args()
    cfg = load_cfg(a.config)
    if a.run_dir:
        cfg["run_dir"] = a.run_dir
    st = Style(not a.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    while True:
        try:
            txt = render(cfg, fetch(cfg), st)
        except Exception as e:  # noqa: BLE001
            txt = st.bad(f"erro ao consultar {cfg['host']}: {e}")
        if a.watch:
            print("\033[2J\033[H" if st.on else "\n" + "=" * 60, end="")
        print(txt, flush=True)
        if not a.watch:
            break
        try:
            time.sleep(a.watch * 60)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
