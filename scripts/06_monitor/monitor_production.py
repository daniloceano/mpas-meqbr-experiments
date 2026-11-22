#!/usr/bin/env python3
"""MEQ-06.8 — automatic dashboard of the MEQ-06 production (EXP03) on Swell.

Runs ON Swell (cron, every 6 h). Reads the production directory WITHOUT writing
to it: simulated time (history names + tail of log.atmosphere.0000.out),
restarts, history mtimes (per-step timestamps), driver log
(logs/production.log: legs, failures, retries), LBC manifests (PRONTO), ERA5
intermediates, df, /proc/loadavg and per-core instantaneous CPU (two reads of /proc/<pid>/task/*/stat, 5 s apart).

Writes ONLY into --out (a separate git work clone): index.html, status.json and
status_history.csv (appended each run). With --publish, commits the outputs as
the single commit of the orphan branch "monitor" and force-pushes ONLY
refs/heads/monitor; it aborts if the checked-out branch is not "monitor".

Standard library only (Python >= 3.9).

    python3 monitor_production.py --out ~/meq06_monitor/site            # no push
    python3 monitor_production.py --out ~/meq06_monitor/site --publish  # cron
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------- config ---
P = Path("/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production")
RUN = P / "run"
DRIVER_LOG = P / "logs" / "production.log"
MODEL_LOG = RUN / "log.atmosphere.0000.out"
MANIFESTS = P / "manifests"
ERA5_DIR = P / "met_data" / "era5"
ERA5_LOG = P / "logs" / "era5_block1_monthly.log"

UTC = dt.timezone.utc
SP = ZoneInfo("America/Sao_Paulo")
SPINUP = dt.datetime(2021, 10, 21, tzinfo=UTC)
BLOCK1_END = dt.datetime(2023, 7, 1, tzinfo=UTC)          # ERA5/LBC/sfc_update block 1
AXIS_END = dt.datetime(2025, 2, 1, tzinfo=UTC)
# (label, simulated instant = end of day, authorized?)
DECISIONS = [("2023-06-30", dt.datetime(2023, 7, 1, tzinfo=UTC), True),
             ("2023-11-30", dt.datetime(2023, 12, 1, tzinfo=UTC), False),
             ("2025-01-31", dt.datetime(2025, 2, 1, tzinfo=UTC), False)]
REF_RATE = 21.9                       # simulated days per machine day (plan, MEQ-06.6)
PIN = ("0-22,56-78,28-49,84-105")     # P90C (production.sh)
PROD_CORES = {c for part in PIN.split(",") for c in range(int(part.split("-")[0]), int(part.split("-")[1]) + 1)}
# Disk growth per simulated day (plan, section c/g): 24 history + 4 LBC + ERA5.
HIST_B, LBC_B, ERA5_B_DAY = 192_475_360, 159_188_972, 0.097e9
GROWTH_B_DAY = 24 * HIST_B + 4 * LBC_B + ERA5_B_DAY

# Alert thresholds.
TH_CPU_OTHER = 20.0      # % CPU of a foreign thread on a production core
TH_LOAD = 95.0
TH_RATE6 = 0.90          # last 6 h < 90 % of median 6-h rate
TH_STALL_H = 36.0        # no new restart
TH_DISK_TB = 5.0
TH_SLACK_D = 2.0         # LBC slack (days)
DRIVER_RECENT_H = 48.0

HIST_RE = re.compile(r"^history\.(\d{4}-\d\d-\d\d)_(\d\d)\.00\.00\.nc$")
RST_RE = re.compile(r"^restart\.(\d{4}-\d\d-\d\d)_(\d\d)\.00\.00\.nc$")
DRV_RE = re.compile(r"^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\] (\w+) ?(.*)$")


# ---------------------------------------------------------------- helpers ---
def ts(x: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(x, UTC)


def iso(d: dt.datetime | None) -> str | None:
    return None if d is None else d.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def days(td: dt.timedelta) -> float:
    return td.total_seconds() / 86400.0


def tail(path: Path, nbytes: int = 400_000) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - nbytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def git_blob_sha(path: Path) -> str:
    b = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def dir_size(root: Path) -> int:
    tot = 0
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            try:
                st = os.lstat(os.path.join(dp, fn))
            except OSError:
                continue
            if not os.path.islink(os.path.join(dp, fn)):
                tot += st.st_size
    return tot


class Progress:
    """sim(t): largest simulated instant whose file was written at or before t."""

    def __init__(self, pairs):  # (mtime, sim datetime)
        pairs = sorted(pairs)
        self.t, self.s, best = [], [], None
        for m, s in pairs:
            best = s if best is None or s > best else best
            self.t.append(m)
            self.s.append(best)

    def at(self, t: float):
        i = bisect.bisect_right(self.t, t) - 1
        return self.s[i] if i >= 0 else None

    def rate(self, a: float, b: float, s0=None):
        """Simulated days per wall day over [a, b]."""
        sa, sb = self.at(a) or s0, self.at(b)
        if sa is None or sb is None or b <= a:
            return None
        return days(sb - sa) / ((b - a) / 86400.0)


CPU_SAMPLE_S = 5.0


def _read_tasks():
    """{(pid, tid): (utime+stime ticks, processor, uid, comm)} from /proc."""
    out = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            uid = os.stat(f"/proc/{pid}").st_uid
            tids = os.listdir(f"/proc/{pid}/task")
        except OSError:
            continue
        for tid in tids:
            try:
                with open(f"/proc/{pid}/task/{tid}/stat") as fh:
                    st = fh.read()
            except OSError:
                continue
            comm = st[st.index("(") + 1:st.rindex(")")]
            f = st[st.rindex(")") + 2:].split()  # f[0] = field 3 (state)
            out[(pid, tid)] = (int(f[11]) + int(f[12]), int(f[36]), uid, comm)
    return out


def cpu_sample(interval: float):
    """Instantaneous %CPU per thread over `interval` s: [(core, pct, user, comm)]."""
    import pwd
    hz = os.sysconf("SC_CLK_TCK")
    a = _read_tasks()
    t0 = time.monotonic()
    time.sleep(interval)
    b = _read_tasks()
    dtw = time.monotonic() - t0
    names, res = {}, []
    for k, (tk, cpu, uid, comm) in b.items():
        if k not in a:
            continue
        pct = 100.0 * (tk - a[k][0]) / hz / dtw
        if uid not in names:
            try:
                names[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                names[uid] = str(uid)
        res.append((cpu, pct, names[uid], comm))
    return res


# ------------------------------------------------------------- collectors ---
def collect(now: float) -> dict:
    got, missing = [], []
    R: dict = {"now": now}

    # History files (hourly output; mtime = time the hour was written).
    hist = []
    try:
        for e in os.scandir(RUN):
            m = HIST_RE.match(e.name)
            if m:
                hist.append((e.stat().st_mtime,
                             dt.datetime.strptime(m[1] + m[2], "%Y-%m-%d%H").replace(tzinfo=UTC)))
        got.append(f"history horários: {len(hist)} arquivos (nome e mtime)")
    except OSError as ex:
        missing.append(f"history: {ex}")
    R["hist"] = hist

    # Restarts.
    rst = []
    try:
        for e in os.scandir(RUN):
            m = RST_RE.match(e.name)
            if m:
                st = e.stat()
                rst.append((dt.datetime.strptime(m[1] + m[2], "%Y-%m-%d%H").replace(tzinfo=UTC),
                            st.st_mtime, st.st_size))
        rst.sort()
        got.append(f"restarts: {len(rst)}")
    except OSError as ex:
        missing.append(f"restarts: {ex}")
    R["rst"] = rst

    # Model log tail: last timestep and mean s/step.
    txt = tail(MODEL_LOG)
    steps = re.findall(r"Begin timestep (\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d)", txt)
    secs = [float(x) for x in re.findall(r"Timing for integration step:\s*([\d.]+)", txt)]
    R["log_step"] = (dt.datetime.strptime(steps[-1], "%Y-%m-%d_%H:%M:%S").replace(tzinfo=UTC)
                     if steps else None)
    R["s_per_step"] = statistics.median(secs[-200:]) if secs else None
    try:
        R["log_mtime"] = MODEL_LOG.stat().st_mtime
        got.append("log.atmosphere.0000.out (último passo, s/passo)")
    except OSError:
        R["log_mtime"] = None
        missing.append("log.atmosphere.0000.out")

    # Driver log.
    drv = []
    try:
        for line in DRIVER_LOG.read_text(errors="replace").splitlines():
            m = DRV_RE.match(line)
            if m:
                drv.append((dt.datetime.strptime(m[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC),
                            m[2], m[3].strip()))
        got.append(f"log do driver: {len(drv)} linhas com carimbo")
    except OSError as ex:
        missing.append(f"log do driver: {ex}")
    R["drv"] = drv

    # LBC manifests.
    man = {}
    try:
        for f in sorted(MANIFESTS.glob("lbc_manifest_*.txt")):
            t = f.read_text(errors="replace")
            st = re.search(r"^status:\s*(\S+)", t, re.M)
            gen = re.search(r"^generated_utc:\s*(\S+)", t, re.M)
            man[f.stem[-7:]] = (st[1] if st else "?", gen[1] if gen else None)
        got.append(f"manifestos LBC: {len(man)}")
    except OSError as ex:
        missing.append(f"manifestos: {ex}")
    R["man"] = man

    # ERA5 intermediates (ready = ERA5:<time> non-empty).
    era = []
    try:
        for e in os.scandir(ERA5_DIR):
            if e.is_dir() and len(e.name) == 10 and e.name.isdigit():
                t = dt.datetime.strptime(e.name, "%Y%m%d%H").replace(tzinfo=UTC)
                f = Path(e.path) / f"ERA5:{t:%Y-%m-%d_%H}"
                try:
                    st = f.stat()
                    if st.st_size > 0:
                        era.append((st.st_mtime, t))
                except OSError:
                    pass
        got.append(f"ERA5 intermediários prontos: {len(era)}")
    except OSError as ex:
        missing.append(f"ERA5: {ex}")
    R["era"] = era
    lines = [ln for ln in tail(ERA5_LOG, 20_000).splitlines() if ln.startswith("[")]
    R["era5_last"] = lines[-1][:160] if lines else None

    # Disk.
    try:
        sv = os.statvfs(P)
        R["disk_free"] = sv.f_bavail * sv.f_frsize
        R["disk_total"] = sv.f_blocks * sv.f_frsize
        R["used_prod"] = dir_size(P)
        got.append("df e tamanho do diretório da produção")
    except OSError as ex:
        R["disk_free"] = R["disk_total"] = R["used_prod"] = None
        missing.append(f"disco: {ex}")

    # Load and per-thread CPU.
    try:
        R["load"] = [float(x) for x in open("/proc/loadavg").read().split()[:3]]
    except OSError:
        R["load"] = None
        missing.append("/proc/loadavg")
    try:
        R["nproc"] = os.cpu_count()
        R["ps"] = cpu_sample(CPU_SAMPLE_S)
        R["n_model"] = sum(1 for p in R["ps"] if p[3].startswith("atmosphere_mod"))
        got.append(f"CPU instantânea por thread ({CPU_SAMPLE_S:.0f} s, /proc/*/task/*/stat): {len(R['ps'])} threads")
    except Exception as ex:  # noqa: BLE001
        R["ps"], R["n_model"] = [], None
        missing.append(f"ps: {ex}")
    try:
        R["owner"] = RUN.owner()
    except Exception:  # noqa: BLE001
        R["owner"] = os.environ.get("USER", "danilocs")
    R["got"], R["missing"] = got, missing
    return R


# --------------------------------------------------------------- analysis ---
def month_windows():
    out, y, m = [], 2021, 10
    while (y, m) <= (2023, 6):
        s = SPINUP if (y, m) == (2021, 10) else dt.datetime(y, m, 1, tzinfo=UTC)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"{y:04d}-{m:02d}", s, dt.datetime(ny, nm, 1, tzinfo=UTC)))
        y, m = ny, nm
    return out


def analyse(R: dict, history_rows: list[dict]) -> dict:
    now = R["now"]
    nowd = ts(now)
    S: dict = {"generated_utc": iso(nowd)}
    prog = Progress(R["hist"])

    sim_hist = max((s for _, s in R["hist"]), default=None)
    sim = max([x for x in (sim_hist, R["log_step"]) if x is not None], default=SPINUP)
    S["sim_now"] = iso(sim)
    S["sim_days"] = days(sim - SPINUP)

    # Production start = first START in the driver log.
    starts = [t for t, k, _ in R["drv"] if k == "START"]
    t0 = starts[0].timestamp() if starts else (min((m for m, _ in R["hist"]), default=now) - 3600)
    S["prod_start"] = iso(ts(t0))
    wall_d = (now - t0) / 86400.0
    S["rate_mean"] = S["sim_days"] / wall_d if wall_d > 0.02 else None
    # Use the log instant as "now" progress so rates are not quantised to 1 h.
    def rate_win(h):
        a = max(t0, now - h * 3600)
        if now - a < 1800:
            return None
        sa = prog.at(a) or SPINUP
        return days(sim - sa) / ((now - a) / 86400.0)
    S["rate_24h"], S["rate_6h"] = rate_win(24), rate_win(6)
    S["rate_step"] = (30.0 / R["s_per_step"]) if R["s_per_step"] else None  # dt = 30 s
    S["s_per_step"] = R["s_per_step"]

    # 6-hour bins for the chart and for the median.
    bins = []
    b = t0
    while b + 6 * 3600 <= now:
        r = prog.rate(b, b + 6 * 3600, SPINUP)
        bins.append({"t": iso(ts(b + 3 * 3600)), "rate": r})
        b += 6 * 3600
    S["bins6"] = bins
    full = [x["rate"] for x in bins if x["rate"] is not None]
    S["rate_median6"] = statistics.median(full) if full else None

    # Restarts.
    rst = R["rst"]
    S["n_restarts"] = len(rst)
    S["last_restart"] = iso(rst[-1][0]) if rst else None
    S["last_restart_written"] = iso(ts(rst[-1][1])) if rst else None

    # Data availability.
    mw = month_windows()
    lbc_ready = SPINUP
    for tag, s, e in mw:
        if R["man"].get(tag, ("", ""))[0] == "PRONTO":
            lbc_ready = e
        else:
            break
    S["lbc_ready_until"] = iso(lbc_ready)
    S["lbc_months_ready"] = sum(1 for v in R["man"].values() if v[0] == "PRONTO")
    S["lbc_months_total"] = len(mw)
    S["lbc_failed"] = [k for k, v in R["man"].items() if v[0] == "FALHA"]
    era_t = sorted(t for _, t in R["era"])
    era_until = SPINUP
    st = set(era_t)
    while era_until in st:
        era_until += dt.timedelta(hours=6)
    era_until = max(SPINUP, era_until - dt.timedelta(hours=6)) if era_t else None
    S["era5_until"] = iso(era_until)
    S["era5_n"] = len(era_t)
    S["era5_last_log"] = R["era5_last"]
    eprog = Progress(R["era"])
    era_rate = None
    for h in (72, 168):
        if R["era"]:
            r = eprog.rate(now - h * 3600, now, SPINUP)
            if r and r > 0:
                era_rate = r
                break
    S["era5_rate"] = era_rate  # simulated days of ERA5 per wall day
    S["lbc_slack_days"] = days(lbc_ready - sim)

    # ETA per decision point.
    rate = S["rate_24h"] or S["rate_mean"] or REF_RATE
    S["rate_used"] = rate
    S["rate_used_src"] = "24 h" if S["rate_24h"] else ("média" if S["rate_mean"] else "referência 21,9")
    used = R["used_prod"] or 0
    pts = []
    for lab, tgt, auth in DECISIONS:
        rem = max(0.0, days(tgt - sim))
        eta_rate = nowd + dt.timedelta(days=rem / rate)
        eta_data, data_note = None, ""
        if auth and lbc_ready < tgt:
            if era_until is not None and era_until >= tgt - dt.timedelta(hours=6):
                arrive = nowd + dt.timedelta(hours=1)
            elif era_rate:
                arrive = nowd + dt.timedelta(days=days(tgt - (era_until or SPINUP)) / era_rate)
            else:
                arrive = None
            if arrive:
                eta_data = arrive + dt.timedelta(days=30.4 / rate)
                data_note = f"dados até {iso(arrive)} + último trecho mensal"
            else:
                data_note = "chegada do ERA5 indeterminada (sem download nas últimas 168 h)"
        eta = max([x for x in (eta_rate, eta_data) if x is not None])
        proj_used = used + rem * GROWTH_B_DAY
        free_at = (R["disk_free"] - rem * GROWTH_B_DAY) if R["disk_free"] is not None else None
        pts.append({
            "label": lab, "target": iso(tgt), "authorized": auth,
            "status": "autorizado (MEQ-06.7)" if auth else "projeção; pressupõe ERA5 e autorização a tempo",
            "sim_days_total": days(tgt - SPINUP), "sim_days_left": rem,
            "pct": min(100.0, 100.0 * S["sim_days"] / days(tgt - SPINUP)),
            "machine_days_left": rem / rate,
            "eta_rate": iso(eta_rate), "eta_data": iso(eta_data), "eta": iso(eta),
            "eta_limited_by": "dados" if eta_data and eta_data > eta_rate else "vazão",
            "data_note": data_note,
            "disk_used_tb": proj_used / 1e12,
            "disk_free_tb_at": None if free_at is None else free_at / 1e12,
        })
    S["decisions"] = pts

    # Legs from the driver log.
    legs, order = {}, []
    for t, k, rest in R["drv"]:
        m = re.match(r"(\d{4}-\d\d)\b", rest)
        if k in ("START", "END", "DONE", "RETRY", "SKIP", "WAIT") and m:
            tag = m[1]
            if tag not in legs:
                legs[tag] = {"tag": tag, "start": None, "done": None, "attempts": 0, "rc": [], "wait": 0}
                order.append(tag)
            L = legs[tag]
            if k == "START":
                L["attempts"] += 1
                L["start"] = L["start"] or t
            elif k == "END":
                L["rc"].append(rest)
            elif k == "DONE":
                L["done"] = t
            elif k == "WAIT":
                L["wait"] += 1
    win = {tag: (s, e) for tag, s, e in mw}
    rows = []
    for tag in order:
        L = legs[tag]
        s, e = win.get(tag, (None, None))
        row = {"tag": tag, "sim_start": iso(s), "sim_end": iso(e), "start": iso(L["start"]),
               "done": iso(L["done"]), "attempts": L["attempts"], "waits": L["wait"],
               "dur_h": None, "rate": None, "state": "concluído" if L["done"] else
               ("em execução" if L["start"] else "aguardando contorno")}
        if L["start"]:
            end = L["done"] or nowd
            row["dur_h"] = (end - L["start"]).total_seconds() / 3600
            simd = days(e - s) if L["done"] else max(0.0, days(min(sim, e) - s))
            row["rate"] = simd / (row["dur_h"] / 24) if row["dur_h"] > 0.2 else None
        rows.append(row)
    S["legs"] = rows

    # ------------------------------------------------------------ alerts ---
    A = []

    def alert(code, msg, when, evid):
        A.append({"code": code, "msg": msg, "when": iso(when), "evidence": evid})

    owner = R["owner"]
    foreign = {}
    for psr, pc, user, comm in R["ps"]:
        if psr in PROD_CORES and user != owner and pc > TH_CPU_OTHER:
            foreign.setdefault((user, comm), []).append((psr, pc))
    for (user, comm), lst in foreign.items():
        ev = ", ".join(f"núcleo {p}: {c:.0f} %" for p, c in sorted(lst)[:8])
        alert("cpu_alheia", f"indício de disputa de núcleo: {user}/{comm} em {len(lst)} núcleo(s) da produção",
              nowd, ev + f" (%CPU instantâneo em {CPU_SAMPLE_S:.0f} s, /proc/*/task/*/stat; núcleo = último em que a thread rodou)")
    if R["load"] and R["load"][0] > TH_LOAD:
        alert("carga", f"carga {R['load'][0]:.1f} > {TH_LOAD:.0f}", nowd,
              f"/proc/loadavg = {' '.join(f'{x:.2f}' for x in R['load'])}; nproc = {R['nproc']}")
    if S["rate_6h"] is not None and S["rate_median6"] and len(full) >= 4 \
            and S["rate_6h"] < TH_RATE6 * S["rate_median6"]:
        alert("vazao", f"vazão 6 h = {S['rate_6h']:.1f} < 90 % da mediana ({S['rate_median6']:.1f})",
              nowd, "mtime dos history.*.nc nas últimas 6 h; indício, a causa não é inferida")
    reached = any(k == "REACHED" for _, k, _ in R["drv"])
    ref_t = rst[-1][1] if rst else t0
    if not reached and (now - ref_t) / 3600 > TH_STALL_H:
        alert("parada", f"sem restart novo há {(now - ref_t) / 3600:.0f} h", ts(ref_t),
              f"último restart: {S['last_restart'] or 'nenhum'}; processos atmosphere_model: {R['n_model']}")
    for t, k, rest in R["drv"]:
        bad = k in ("RETRY", "STOP") or (k == "END" and (not re.search(r"rc=0\b", rest)
                                                          or not re.search(r"errors=0\b", rest)))
        recent = (now - t.timestamp()) / 3600 < DRIVER_RECENT_H
        if bad and (recent or (k == "STOP" and not R["n_model"])):
            alert("driver", f"driver: {k}", t, f"[{iso(t)}] {k} {rest}"[:240])
    for tag in S["lbc_failed"]:
        alert("driver", f"manifesto {tag} FALHA", nowd, f"manifests/lbc_manifest_{tag}.txt")
    if R["disk_free"] is not None and R["disk_free"] / 1e12 < TH_DISK_TB:
        alert("disco", f"disco livre {R['disk_free'] / 1e12:.1f} TB < {TH_DISK_TB:.0f} TB", nowd,
              "statvfs de /p1-swell")
    if lbc_ready < BLOCK1_END and S["lbc_slack_days"] < TH_SLACK_D:
        alert("folga", f"folga de contorno {S['lbc_slack_days']:.1f} d < {TH_SLACK_D:.0f} d", nowd,
              f"LBC PRONTO até {iso(lbc_ready)}; simulado {iso(sim)}; ERA5 até {iso(era_until)}")
    sync_err = os.environ.get("MONITOR_SYNC_ERR", "").strip()
    if sync_err:
        alert("sync", "script não sincronizado com origin/main (rodou a cópia local)", nowd, sync_err[:240])
    S["alerts"] = A

    # Misc.
    S["load"] = R["load"]
    S["nproc"] = R["nproc"]
    S["n_model_threads"] = R["n_model"]
    S["disk_free_tb"] = None if R["disk_free"] is None else R["disk_free"] / 1e12
    S["disk_total_tb"] = None if R["disk_total"] is None else R["disk_total"] / 1e12
    S["used_prod_tb"] = None if R["used_prod"] is None else R["used_prod"] / 1e12
    S["reached_stop"] = reached
    S["last_driver"] = [f"[{iso(t)}] {k} {r}"[:200] for t, k, r in R["drv"][-8:]]
    others = {}
    for psr, pc, user, comm in R["ps"]:
        if user != owner and pc > 5:
            others.setdefault(user, [0.0, set()])
            others[user][0] += pc
            others[user][1].add(psr)
    S["cpu_other_users"] = {u: {"pcpu": round(v[0], 1),
                                "cores_in_prod": sorted(c for c in v[1] if c in PROD_CORES),
                                "cores_free": sorted(c for c in v[1] if c not in PROD_CORES)}
                            for u, v in others.items()}
    S["got"], S["missing"] = R["got"], R["missing"]
    return S


# ------------------------------------------------------------------- HTML ---
CSS = """
:root{--ink:#1a1a1a;--muted:#5c5c5c;--rule:#d4d4d4;--rule-strong:#1a1a1a;--bg:#fff;--bg-soft:#f6f6f6;
--accent:#1950a6;--loss:#883007;--nd:#8c8c8c;--font:Arial,"Helvetica Neue",Helvetica,"Liberation Sans",sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 var(--font)}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:32px 0 6px;padding-top:10px;border-top:1px solid var(--rule-strong)}
.lead{color:var(--muted);margin:0 0 12px;max-width:900px}.caption{font-size:12px;color:var(--muted);margin:6px 0 0;max-width:960px}
.caption b{color:var(--ink)}table{border-collapse:collapse;font-size:12px;width:100%}
th,td{padding:3px 6px;border-bottom:1px solid var(--rule);text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}thead th{border-bottom:1px solid var(--ink);font-weight:700}
.scroll{overflow-x:auto}.kpis{display:flex;flex-wrap:wrap;gap:28px;margin:8px 0}
.kpis div{font-size:12px;color:var(--muted);min-width:150px}.kpis b{display:block;font-size:22px;color:var(--ink)}
.kpis b.bad{color:var(--loss)}tr.proj td{color:var(--nd);font-style:italic}td.l{text-align:left;white-space:normal;min-width:160px}
.alerts li{margin:2px 0}.alerts .ev{color:var(--muted);font-size:12px}svg{display:block;width:100%;height:auto}
svg text{font-family:var(--font);font-size:11px;fill:var(--ink)}.legend{font-size:12px;color:var(--muted);margin-top:4px}
footer{margin-top:36px;border-top:1px solid var(--rule-strong);padding-top:8px;font-size:11.5px;color:var(--muted)}
code{font-size:11.5px;overflow-wrap:anywhere}
"""


def f(x, d=1, unit=""):
    if x is None:
        return "—"
    s = f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s + unit


def dshort(s):
    return "—" if not s else s.replace("T", " ").replace("Z", " UTC")


def tl_svg(S):
    W, H, L, Rr = 1100, 200, 150, 20
    a, b = dt.datetime(2021, 10, 1, tzinfo=UTC), AXIS_END
    def x(d):
        return L + (W - L - Rr) * days(d - a) / days(b - a)
    def p(s):
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Linha do tempo">',
         '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#8c8c8c" stroke-width="2"/>'
         '</pattern></defs>']
    # month ticks
    y, m = 2021, 10
    while dt.datetime(y, m, 1, tzinfo=UTC) <= b:
        d = dt.datetime(y, m, 1, tzinfo=UTC)
        xx = x(d)
        o.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="20" y2="140" stroke="#eee"/>')
        if m in (1, 4, 7, 10):
            o.append(f'<text x="{xx:.1f}" y="155" text-anchor="middle">{m:02d}/{y}</text>')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    rows = [("Simulado", S["sim_now"], "#1950a6"), ("Contorno pronto", S["lbc_ready_until"], "#5c5c5c"),
            ("ERA5 baixado", S["era5_until"], "#b0b0b0")]
    for i, (lab, end, col) in enumerate(rows):
        yy = 30 + i * 30
        o.append(f'<text x="{L - 8}" y="{yy + 13}" text-anchor="end">{lab}</text>')
        o.append(f'<rect x="{x(SPINUP):.1f}" y="{yy}" width="{x(BLOCK1_END) - x(SPINUP):.1f}" height="18" '
                 f'fill="none" stroke="#d4d4d4"/>')
        o.append(f'<rect x="{x(BLOCK1_END):.1f}" y="{yy}" width="{x(b) - x(BLOCK1_END):.1f}" height="18" '
                 f'fill="url(#hatch)" opacity=".25"/>')
        if end:
            e = p(end)
            o.append(f'<rect x="{x(SPINUP):.1f}" y="{yy}" width="{max(1, x(e) - x(SPINUP)):.1f}" height="18" '
                     f'fill="{col}"><title>{lab} até {dshort(end)}</title></rect>')
    for pt in S["decisions"]:
        e = p(pt["target"])
        xx = x(e)
        dash = "" if pt["authorized"] else ' stroke-dasharray="4 3"'
        col = "#1a1a1a" if pt["authorized"] else "#8c8c8c"
        o.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="18" y2="140" stroke="{col}" stroke-width="1.5"{dash}/>')
        anchor = "end" if xx > W - 60 else "middle"
        eta = dt.datetime.strptime(pt["eta"][:10], "%Y-%m-%d")
        star = "" if pt["authorized"] else "*"
        o.append(f'<g class="dp-lab" data-x="{xx:.1f}"><line class="dp-lead" x1="{xx:.1f}" x2="{xx:.1f}" y1="160" '
                 f'y2="160" stroke="{col}" stroke-width=".8"/>'
                 f'<text x="{xx:.1f}" y="172" text-anchor="{anchor}" fill="{col}">{pt["label"]}</text>'
                 f'<text x="{xx:.1f}" y="187" text-anchor="{anchor}" fill="{col}">ETA{star} {eta:%d/%m/%y}</text></g>')
    o.append(f'<text x="{x(SPINUP):.1f}" y="14" text-anchor="start" fill="#5c5c5c">spin-up 2021-10-21</text>')
    o.append("</svg>")
    return "".join(o)


def rate_svg(S, hist_rows):
    pts = [(x["t"], x["rate"]) for x in S["bins6"] if x["rate"] is not None]
    W, H, L, B = 1100, 260, 50, 40
    if not pts:
        return '<p class="caption">Ainda não há uma janela completa de 6 h de produção.</p>'
    def p(s):
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    t0 = p(S["prod_start"])
    t1 = p(S["generated_utc"])
    ymax = max([REF_RATE * 1.3] + [r for _, r in pts]) * 1.05
    def x(d):
        return L + (W - L - 20) * max(0.0, days(d - t0)) / max(days(t1 - t0), 1e-6)
    def y(v):
        return H - B - (H - B - 15) * v / ymax
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Vazão">']
    for k in range(0, int(ymax) + 1, 5):
        o.append(f'<line x1="{L}" x2="{W - 20}" y1="{y(k):.1f}" y2="{y(k):.1f}" stroke="#eee"/>'
                 f'<text x="{L - 6}" y="{y(k) + 4:.1f}" text-anchor="end">{k}</text>')
    o.append(f'<line x1="{L}" x2="{W - 20}" y1="{y(REF_RATE):.1f}" y2="{y(REF_RATE):.1f}" stroke="#883007" '
             f'stroke-dasharray="6 4"/><text x="{W - 22}" y="{y(REF_RATE) - 5:.1f}" text-anchor="end" '
             f'fill="#883007">referência 21,9</text>')
    nt = max(1, round(days(t1 - t0)))
    step = max(1, nt // 10)
    d = dt.datetime(t0.year, t0.month, t0.day, tzinfo=UTC) + dt.timedelta(days=1)
    i = 0
    while d <= t1:
        if i % step == 0:
            o.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="15" y2="{H - B}" stroke="#f0f0f0"/>'
                     f'<text x="{x(d):.1f}" y="{H - B + 15}" text-anchor="middle">{d:%d/%m}</text>')
        d += dt.timedelta(days=1)
        i += 1
    path = " ".join(f"{'M' if j == 0 else 'L'}{x(p(t)):.1f},{y(r):.1f}" for j, (t, r) in enumerate(pts))
    o.append(f'<path d="{path}" fill="none" stroke="#1950a6" stroke-width="1.6"/>')
    for t, r in pts:
        o.append(f'<circle cx="{x(p(t)):.1f}" cy="{y(r):.1f}" r="2.4" fill="#1950a6">'
                 f'<title>{dshort(t)}: {f(r)} dias/dia</title></circle>')
    for row in hist_rows:
        if row.get("alerts"):
            try:
                tt = p(row["generated_utc"])
            except (KeyError, ValueError):
                continue
            if tt >= t0:
                o.append(f'<path d="M{x(tt):.1f},{H - B - 2} l-5,-9 h10 z" fill="#883007">'
                         f'<title>{dshort(row["generated_utc"])}: {html.escape(row["alerts"])}</title></path>')
    o.append(f'<text x="{L}" y="{H - 6}" fill="#5c5c5c">hora de máquina (UTC) · eixo y: dias simulados por '
             f'dia de máquina, janelas de 6 h · triângulos: execuções do painel com alerta ativo</text>')
    o.append("</svg>")
    return "".join(o)


def render(S, hist_rows, sha, runtime_s):
    now = dt.datetime.strptime(S["generated_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    A = S["alerts"]
    d1 = S["decisions"][0]
    e = html.escape
    kp = [
        ("Data simulada", dshort(S["sim_now"]), f"{f(S['sim_days'])} dias desde 2021-10-21"),
        ("Até 2023-06-30", f"{f(d1['pct'])} %", f"ETA {d1['eta'][:10]} ({d1['eta_limited_by']})"),
        ("Vazão 24 h", f(S["rate_24h"]), f"média {f(S['rate_mean'])}; passo {f(S['rate_step'])} · ref. 21,9"),
        ("Último restart", dshort(S["last_restart"])[:16] if S["last_restart"] else "nenhum",
         f"escrito {dshort(S['last_restart_written'])}" if S["last_restart"] else "restart diário (00 UTC)"),
        ("Alertas ativos", str(len(A)), "ver lista abaixo" if A else "nenhum indício"),
        ("Folga de contorno", f"{f(S['lbc_slack_days'])} d", f"LBC até {dshort(S['lbc_ready_until'])[:10]}"),
        ("Disco livre", f"{f(S['disk_free_tb'])} TB", f"produção ocupa {f(S['used_prod_tb'], 2)} TB"),
    ]
    cards = "".join(f'<div>{e(a)}<b{" class=bad" if a == "Alertas ativos" and A else ""}>{e(b)}</b>{e(c)}</div>'
                    for a, b, c in kp)
    al = "".join(f'<li><b>{e(a["msg"])}</b> — {e(dshort(a["when"]))}<br><span class="ev">evidência: '
                 f'{e(a["evidence"])}</span></li>' for a in A) or "<li>Nenhum alerta ativo.</li>"
    dec = "".join(
        f'<tr{"" if p["authorized"] else " class=proj"}><td>{p["label"]}</td><td class="l">{e(p["status"])}</td>'
        f'<td>{f(p["sim_days_total"], 0)}</td><td>{f(p["sim_days_left"], 1)}</td><td>{f(p["pct"])} %</td>'
        f'<td>{f(p["machine_days_left"], 1)}</td><td>{p["eta_rate"][:16].replace("T", " ")}</td>'
        f'<td>{(p["eta_data"] or "—")[:16].replace("T", " ")}</td><td><b>{p["eta"][:10]}</b></td>'
        f'<td>{f(p["disk_used_tb"], 2)}</td><td>{f(p["disk_free_tb_at"])}</td></tr>' for p in S["decisions"])
    legs = "".join(
        f'<tr><td>{r["tag"]}</td><td>{(r["sim_start"] or "")[:10]} → {(r["sim_end"] or "")[:10]}</td>'
        f'<td>{dshort(r["start"])}</td><td>{dshort(r["done"])}</td><td>{f(r["dur_h"])}</td>'
        f'<td>{f(r["rate"])}</td><td>{r["attempts"]}</td><td class="l">{e(r["state"])}</td></tr>'
        for r in S["legs"]) or '<tr><td colspan="8">Sem trechos no log do driver.</td></tr>'
    others = "; ".join(f"{u}: {v['pcpu']} % CPU somado, núcleos da produção {v['cores_in_prod'] or 'nenhum'}"
                       for u, v in S["cpu_other_users"].items()) or "nenhum processo de outro usuário acima de 5 %"
    got = "".join(f"<li>{e(x)}</li>" for x in S["got"])
    miss = "".join(f"<li>{e(x)}</li>" for x in S["missing"]) or "<li>nada</li>"
    drv = "<br>".join(e(x) for x in S["last_driver"])
    spn = now.astimezone(SP)
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEQ-06.8 · Acompanhamento da produção</title><style>{CSS}</style></head><body><main>
<h1>Acompanhamento da produção — simulação climatológica (configuração EXP03)</h1>
<p class="lead">MEQ-06.8 · Painel automático gerado no Swell a cada 6 h, somente leitura sobre
<code>meq06_production/</code>. 90 processos com fixação P90C (núcleos 0–22, 28–49 e irmãos SMT); livres 23–27,
50–55 e SMT 79–83, 106–111. Plano: <code>research/MEQ-06-production-plan.md</code> (DEC-MEQ-006). Alertas são
<b>indícios</b>; a causa não é inferida.</p>
<div class="kpis">{cards}</div>
<h2>Alertas ativos</h2><ul class="alerts">{al}</ul>
<h2>a · Linha do tempo (out/2021 a jan/2025)</h2>{tl_svg(S)}
<p class="caption"><b>a</b> Barras: instante simulado atual, contorno lateral pronto (manifestos <code>PRONTO</code>
consecutivos) e ERA5 baixado (intermediários <code>ERA5:*</code> consecutivos). Retângulo vazado: bloco 1
(2021-10-21 → 2023-07-01); hachura: além do bloco 1, ainda sem ERA5 nem autorização. Linhas verticais: pontos de
decisão; contínua = autorizado; tracejada = projeção. Rótulos: ponto de decisão e ETA (dd/mm/aa).
<b>* projeção: pressupõe ERA5 e autorização a tempo.</b></p>
<h2>b · Vazão</h2>{rate_svg(S, hist_rows)}
<p class="caption"><b>b</b> Dias simulados por dia de máquina em janelas de 6 h, a partir do mtime dos
<code>history.*.nc</code> (inclui esperas por contorno e reinícios). Linha tracejada: referência de 21,9 dias/dia
(MEQ-06.6). Últimas 6 h: {f(S["rate_6h"])}; mediana das janelas de 6 h: {f(S["rate_median6"])}; s/passo (mediana
dos últimos 200 passos do log): {f(S["s_per_step"], 3)}.</p>
<h2>c · Pontos de decisão</h2><div class="scroll"><table><thead><tr><th>Ponto</th><th>Situação</th>
<th>Dias simulados (total)</th><th>Restantes</th><th>%</th><th>Dias de máquina restantes</th><th>ETA pela vazão (UTC)</th>
<th>ETA pelos dados (UTC)</th><th>ETA</th><th>Disco da produção (TB)</th><th>Livre no ponto (TB)</th></tr></thead>
<tbody>{dec}</tbody></table></div>
<p class="caption"><b>c</b> Vazão usada: {f(S["rate_used"])} dias/dia ({e(S["rate_used_src"])}). ETA = o maior entre
a conta pela vazão e a conta pela chegada dos dados (só para o ponto 1, o único com ERA5 previsto: chegada do ERA5
ao ponto pelo ritmo de download das últimas 72 h, mais um trecho mensal de integração). Disco projetado = ocupação
atual de <code>meq06_production/</code> + {f(GROWTH_B_DAY / 1e9, 2)} GB por dia simulado (24 history + 4 LBC +
ERA5), sem restarts adicionais. Linhas em itálico: projeção; pressupõe ERA5 e autorização a tempo.</p>
<h2>d · Trechos mensais</h2><div class="scroll"><table><thead><tr><th>Trecho</th><th>Período simulado</th>
<th>Início (UTC)</th><th>Fim (UTC)</th><th>Duração (h)</th><th>Vazão (d/d)</th><th>Tentativas</th><th>Estado</th></tr>
</thead><tbody>{legs}</tbody></table></div>
<p class="caption"><b>d</b> Do log do driver (<code>logs/production.log</code>): início = primeiro START do trecho;
fim = DONE; tentativas = número de START. Últimas linhas:<br><code>{drv}</code></p>
<h2>e · Máquina e dados</h2>
<p class="caption">Carga: {" ".join(f(x, 2) for x in (S["load"] or []))} (nproc {S["nproc"]}); threads
atmosphere_model: {S["n_model_threads"]}. Outros usuários: {e(others)}. ERA5: {S["era5_n"]} intermediários; até
{dshort(S["era5_until"])}; ritmo {f(S["era5_rate"])} dias/dia; último registro: <code>{e(S["era5_last_log"] or "—")}</code>.
LBC: {S["lbc_months_ready"]}/{S["lbc_months_total"]} meses PRONTO.</p>
<p class="caption"><b>Obtido nesta execução:</b></p><ul class="caption">{got}</ul>
<p class="caption"><b>Não obtido:</b></p><ul class="caption">{miss}</ul>
<footer>Gerado em {now:%Y-%m-%d %H:%M} UTC ({spn:%Y-%m-%d %H:%M} America/Sao_Paulo) em {runtime_s:.1f} s ·
<code>scripts/06_monitor/monitor_production.py</code> blob <code>{sha[:12]}</code>.<br>
<b>Limites:</b> limiares — CPU alheia &gt; {TH_CPU_OTHER:.0f} % por thread nos núcleos da produção (%CPU instantâneo
em {CPU_SAMPLE_S:.0f} s; o núcleo é o último em que a thread rodou); carga (1 min) &gt; {TH_LOAD:.0f}; vazão 6 h &lt; 90 % da mediana; sem
restart há &gt; {TH_STALL_H:.0f} h; falha/retomada do driver nas últimas {DRIVER_RECENT_H:.0f} h; disco &lt;
{TH_DISK_TB:.0f} TB; folga de contorno &lt; {TH_SLACK_D:.0f} d. Vazão medida pelo mtime dos history (resolução de 1 h
simulada). ETAs supõem vazão e ritmo de download constantes. Pontos 2 e 3 são projeções: pressupõem ERA5 e autorização
a tempo, que ainda não existem. Painel não substitui a verificação do log; nada é escrito na produção.</footer>
</main><script>
(function () {{
  // Stagger decision-point labels whose centres are < 110 screen px apart.
  var GAP = 110, DY = 34;
  function lay() {{
    var svg = document.querySelector('svg[aria-label="Linha do tempo"]');
    if (!svg) return;
    var k = svg.getBoundingClientRect().width / 1100, last = [], maxRow = 0;
    Array.prototype.forEach.call(svg.querySelectorAll('g.dp-lab'), function (g) {{
      var x = parseFloat(g.getAttribute('data-x')) * k, row = 0;
      while (last[row] !== undefined && x - last[row] < GAP) row++;
      last[row] = x;
      g.setAttribute('transform', 'translate(0,' + row * DY + ')');
      var ld = g.querySelector('.dp-lead');
      ld.setAttribute('y1', String(row ? 140 - row * DY : 160));
      maxRow = Math.max(maxRow, row);
    }});
    svg.setAttribute('viewBox', '0 0 1100 ' + (200 + maxRow * DY));
  }}
  lay(); window.addEventListener('resize', lay);
}})();
</script></body></html>"""


# ---------------------------------------------------------------- publish ---
def git(clone: Path, *args, check=True):
    return subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True, check=check).stdout.strip()


def publish(clone: Path, msg: str) -> str:
    branch = git(clone, "symbolic-ref", "--short", "HEAD", check=False)
    if branch != "monitor":
        sys.exit(f"ABORT: branch is '{branch}', expected 'monitor'; nothing pushed")
    git(clone, "add", "-A")
    tree = git(clone, "write-tree")
    commit = subprocess.run(["git", "-C", str(clone), "commit-tree", tree, "-m", msg],
                            capture_output=True, text=True, check=True).stdout.strip()
    git(clone, "update-ref", "refs/heads/monitor", commit)
    git(clone, "reset", "-q", "--soft", "refs/heads/monitor")
    if git(clone, "symbolic-ref", "--short", "HEAD") != "monitor":
        sys.exit("ABORT: HEAD moved away from 'monitor'; nothing pushed")
    subprocess.run(["git", "-C", str(clone), "push", "-q", "--force", "origin",
                    "refs/heads/monitor:refs/heads/monitor"], check=True, timeout=120)
    git(clone, "reflog", "expire", "--expire=now", "--all", check=False)
    git(clone, "gc", "-q", "--prune=now", check=False)
    return commit


# ------------------------------------------------------------------- main ---
HIST_COLS = ["generated_utc", "sim_now", "sim_days", "pct_p1", "rate_24h", "rate_6h", "rate_mean",
             "last_restart", "load1", "disk_free_tb", "used_prod_tb", "lbc_ready_until", "era5_until",
             "eta_p1", "eta_p2", "eta_p3", "n_alerts", "alerts", "runtime_s"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path, help="output dir (separate work clone)")
    ap.add_argument("--publish", action="store_true", help="commit + force-push ONLY branch monitor")
    a = ap.parse_args()
    out = a.out.resolve()
    if str(out).startswith(str(P)):
        sys.exit("ABORT: --out inside the production directory")
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    R = collect(t_start)
    hpath = out / "status_history.csv"
    hist_rows = []
    if hpath.exists():
        with open(hpath, newline="") as fh:
            hist_rows = list(csv.DictReader(fh))
    S = analyse(R, hist_rows)
    sha = git_blob_sha(Path(__file__).resolve())
    S["script_blob_sha"] = sha
    runtime = time.time() - t_start
    S["runtime_s"] = round(runtime, 2)
    row = {"generated_utc": S["generated_utc"], "sim_now": S["sim_now"], "sim_days": round(S["sim_days"], 3),
           "pct_p1": round(S["decisions"][0]["pct"], 2),
           "rate_24h": None if S["rate_24h"] is None else round(S["rate_24h"], 2),
           "rate_6h": None if S["rate_6h"] is None else round(S["rate_6h"], 2),
           "rate_mean": None if S["rate_mean"] is None else round(S["rate_mean"], 2),
           "last_restart": S["last_restart"], "load1": S["load"][0] if S["load"] else None,
           "disk_free_tb": None if S["disk_free_tb"] is None else round(S["disk_free_tb"], 2),
           "used_prod_tb": None if S["used_prod_tb"] is None else round(S["used_prod_tb"], 3),
           "lbc_ready_until": S["lbc_ready_until"], "era5_until": S["era5_until"],
           "eta_p1": S["decisions"][0]["eta"], "eta_p2": S["decisions"][1]["eta"],
           "eta_p3": S["decisions"][2]["eta"], "n_alerts": len(S["alerts"]),
           "alerts": "; ".join(x["code"] for x in S["alerts"]), "runtime_s": round(runtime, 2)}
    hist_rows.append({k: ("" if v is None else str(v)) for k, v in row.items()})
    (out / "index.html").write_text(render(S, hist_rows, sha, runtime), encoding="utf-8")
    (out / "status.json").write_text(json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
    new = not hpath.exists()
    with open(hpath, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HIST_COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"{S['generated_utc']} sim={S['sim_now']} rate24={row['rate_24h']} alerts={len(S['alerts'])} "
          f"runtime={runtime:.1f}s")
    if a.publish:
        c = publish(out, f"monitor {S['generated_utc']} sim={S['sim_now']} alerts={len(S['alerts'])}")
        print(f"published monitor {c}")


if __name__ == "__main__":
    main()
