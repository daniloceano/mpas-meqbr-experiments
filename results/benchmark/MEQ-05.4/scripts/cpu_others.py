#!/usr/bin/env python3
"""MEQ-05.5 (dirs MEQ054_*) — instantaneous CPU of other users' processes and mean CPU frequency.

Samples /proc/<pid>/stat (utime+stime, all threads of the process) twice, INTERVAL s apart, and
prints ONE line:
  utc=... interval_s=... max_other_pct=X other=user:pid:comm:pct;... (only > REPORT_PCT)
  mhz_all=<mean of 'cpu MHz' over all CPUs> mhz_list=<mean over CPU_LIST, or NA>
pct is % of ONE CPU (a process using 2 full CPUs = 200).  Read-only.
Usage: python3 -I cpu_others.py INTERVAL [CPU_LIST] [REPORT_PCT]
"""
import os
import pwd
import sys
import time
from datetime import datetime, timezone

interval = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
cpu_list = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else ""
report = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
me = os.getuid()
hz = os.sysconf("SC_CLK_TCK")


def snap():
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            uid = os.stat(f"/proc/{d}").st_uid
            if uid == me:
                continue
            s = open(f"/proc/{d}/stat").read()
            comm = s[s.index("(") + 1:s.rindex(")")]
            f = s[s.rindex(")") + 2:].split()
            out[int(d)] = (uid, comm, int(f[11]) + int(f[12]))
        except (OSError, ValueError, IndexError):
            continue
    return out


def mhz():
    vals = {}
    cpu = None
    for line in open("/proc/cpuinfo"):
        if line.startswith("processor"):
            cpu = int(line.split(":")[1])
        elif line.startswith("cpu MHz"):
            vals[cpu] = float(line.split(":")[1])
    allm = sum(vals.values()) / len(vals) if vals else float("nan")
    lm = "NA"
    if cpu_list:
        ids = [int(x) for x in cpu_list.split(",")]
        lm = "%.0f" % (sum(vals[i] for i in ids) / len(ids))
    return "%.0f" % allm, lm


a = snap()
t0 = time.time()
time.sleep(interval)
b = snap()
dt = time.time() - t0
rows = []
for pid, (uid, comm, t) in b.items():
    if pid in a and a[pid][0] == uid:
        pct = 100.0 * (t - a[pid][2]) / hz / dt
        if pct > 0:
            try:
                user = pwd.getpwuid(uid).pw_name
            except KeyError:
                user = str(uid)
            rows.append((pct, user, pid, comm))
rows.sort(reverse=True)
mx = rows[0][0] if rows else 0.0
m_all, m_list = mhz()
other = ";".join(f"{u}:{p}:{c.replace(' ', '_')}:{x:.0f}" for x, u, p, c in rows if x > report)
print(f"utc={datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} interval_s={dt:.1f} max_other_pct={mx:.1f} "
      f"other={other} mhz_all={m_all} mhz_list={m_list}")
