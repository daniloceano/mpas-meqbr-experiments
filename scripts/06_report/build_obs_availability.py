"""MEQ-06.2 / MEQ-06.4 — observation availability panel for choosing the simulation period.

Reads every observed-wind record the project holds, applies the SAME quality
control used by the MEQ-04 validations, reduces each record to valid hours at
the reference height, and writes:

* ``results/obs_availability/instruments.csv`` — metadata, coordinates, first
  and last valid hour, mean availability, longest gap, hour-of-day coverage;
* ``results/obs_availability/availability_daily.csv`` — % of valid hours per day;
* ``results/obs_availability/availability_monthly.csv`` — % of valid hours per month;
* ``results/obs_availability/gaps.csv`` — gaps >= 3 h (profilers) / >= 24 h (stations);
* ``results/obs_availability/candidate_windows_12_24_36.csv`` — every window starting on the
  1st of a month (2021-10 onwards) of 12, 24 and 36 months, one column per criterion (MEQ-06.4);
* ``results/obs_availability/preoptions.csv`` — the 3 windows with most valid hours per
  duration and criterion ("Total" / "Só perfiladores"), shown as buttons in the panel;
* ``results/obs_availability/index.html`` — self-contained interactive panel
  (layout-v2 aesthetic; Leaflet inlined from ``docs/templates/vendor``).

QC and hourly reduction (identical to MEQ-04, see ``src/mpas_meqbr/obs.py``):

* P0 and P1 LiDAR (struct ``L``): ``obs.read_p0_lidar`` — ``avail >= 80`` %
  and 0-40 m/s, per height; 100 m channel.
* LPI LiDAR: ``obs.read_lpi_lidar`` — 0-40 m/s; ``spd_100``.
* SODAR P1 (struct ``SD``): not used in the MEQ-03 selection (DEC-MEQ-003); included in
  the final validation (researcher, 2026-11-19) and in every total; QC of
  ``scripts/06_audit/verify_sodar_p0_overlap.py:read_sodar`` (finite values,
  duplicated stamps dropped) plus the same 0-40 m/s range; reference height 100 m
  (an exact SODAR level: 30-280 m every 10 m).
* Profilers -> hourly with ``obs.to_hourly`` (hour centred, >= 4 of 6 10-min samples).
* ANM-1/PPE1A (platform PPE-1A, Bacia Potiguar; hourly YOUNG anemometer, height and
  time zone not given in the file): group "Plataforma offshore (anemômetro)", qualified by
  an independent assessment (researcher, 2026-11-19); counts in the totals.
  Already hourly, so the >= 4/6 rule cannot apply; equivalent criterion: a valid hour
  has FLG_BRT_WSPD == 1 (pass), FLG_OP_WSPD == 0 (operational) and 0-40 m/s. The
  4-digit FLG_CONSIST_WSPD code is undocumented and not used. Time stamps taken as UTC.
* ISD stations: ``obs.parse_isd_wind`` — quality codes 2/3/6/7 dropped,
  0-40 m/s, hourly mean of the reports in each hour; 10 m anemometer.

An hour is valid when it survives that chain. Periods without a source file
(ISD years without a file; outside an instrument's record) are reported
as "no data", never as 0 %.

Run (paths are arguments; nothing is downloaded or modified)::

    python scripts/06_report/build_obs_availability.py \\
        --p0 data/obs/P0_LIDAR_matrix.mat --lpi data/obs/LPI_processed.csv.gz \\
        --p1-lidar /path/P1_LIDAR_matrix.mat --p1-sodar /path/P1_SODAR.mat \\
        --anm /path/WIND_DATA_ANM_1_PPE1A_20250819100158.csv --isd-dir data/stations
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from mpas_meqbr import obs, sci_colormaps  # noqa: E402

OUT = REPO / "results" / "obs_availability"
T0 = pd.Timestamp("2021-10-01 00:00")
T1 = pd.Timestamp("2025-08-31 23:00")
HOURS = pd.date_range(T0, T1, freq="h")
DAYS = pd.date_range(T0.normalize(), T1.normalize(), freq="D")
REF_HEIGHT = 100.0
GAP_MIN_H = {"profiler": 3, "station": 24, "platform": 24}
VALID_DAY_H = 12                 # a "valid day" in the window panel: >= 12 of 24 h
STATION_OK_PCT = 80.0
DURATIONS = (12, 24, 36)              # months; candidate windows start on the 1st of each month
WIN_FIRST = pd.Timestamp("2021-10-01")
SPINUP_DAYS = 11
SODAR_NOTE = "SODAR P1 — não usado na seleção MEQ-03; incluído na validação final"
ANM_NOTE = "altura e fuso não informados no arquivo; horário tratado como UTC"
CRITERIA = [("total_hours", "Total"), ("prof_hours", "Só perfiladores")]
PROFILER_GROUPS = ("LIDAR", "SODAR")
TOTAL_GROUPS = ("LIDAR", "SODAR", "PLAT", "INMET", "AERO")
SITE_OF = {"P0_LIDAR": "P0", "P1_LIDAR": "P1", "P1_SODAR": "P1", "LPI_LIDAR": "LPI"}
GROUPS = [("LIDAR", "LiDAR"), ("SODAR", SODAR_NOTE),
          ("PLAT", "Plataforma offshore (anemômetro)"),
          ("INMET", "INMET"), ("AERO", "Aeroportos (ISD)")]

def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------
# readers -> set of valid hourly stamps
# ----------------------------------------------------------------------------
def hourly_profiler(tidy: pd.DataFrame, height_map: dict) -> dict:
    """Valid hours at 100 m, valid native 10-min records at 100 m, and valid
    hour x height pairs at the MEQ-04 comparison heights (``obs.observed_at_model_heights``)."""
    sub = tidy[tidy["height"] == REF_HEIGHT]
    hr = obs.to_hourly(sub, min_samples=4)
    used = sorted({h for chans in height_map.values() for h in chans})
    pairs = obs.observed_at_model_heights(
        obs.to_hourly(tidy[tidy["height"].isin(used)], min_samples=4), height_map)
    return {"hours": pd.DatetimeIndex(hr["time"]).unique().sort_values(),
            "native": pd.DatetimeIndex(sub["time"]),
            "pairs": pd.DatetimeIndex(pairs["time"])}


def read_sodar_tidy(path: Path) -> pd.DataFrame:
    from scipy.io import loadmat
    sd = loadmat(str(path), simplify_cells=True)["SD"]
    levels = np.asarray(sd["levels"]).astype(float)
    frames = []
    for i, lev in enumerate(levels):
        t = (pd.Timestamp("1970-01-01") + pd.to_timedelta(
            np.asarray(sd["mtime"], float)[i] - obs.MATLAB_EPOCH_OFFSET, unit="D"))
        t = pd.DatetimeIndex(t).round("min")
        s = pd.Series(np.asarray(sd["speed"], float)[i], index=t)
        s = s[~s.index.duplicated(keep="first")]
        s = s[np.isfinite(s) & (s >= 0) & (s <= 40)]
        frames.append(pd.DataFrame({"time": s.index, "height": float(lev), "speed": s.values,
                                    "direction": np.nan}))
    return pd.concat(frames, ignore_index=True)


def lidar_coords(path: Path):
    from scipy.io import loadmat
    L = loadmat(str(path), simplify_cells=True)["L"]
    if "lat" in L:
        return float(np.nanmedian(L["lat"])), float(np.nanmedian(L["lon"]))
    return None, None


def read_anm(path: Path) -> dict:
    """ANM-1/PPE1A hourly CSV (';' separated, decimal comma) -> valid hours.

    The file is treated as untrusted data: read with pandas only. Valid hour:
    FLG_BRT_WSPD == 1, FLG_OP_WSPD == 0 and 0 <= speed <= 40 m/s.
    """
    df = pd.read_csv(path, sep=";", dtype=str)
    t = pd.to_datetime(df["DT_ACQUISITION"], format="%d/%m/%Y %H:%M")
    spd = pd.to_numeric(df["METE_VL_WSPD"].str.replace(",", "."), errors="coerce")
    ok = (df["FLG_BRT_WSPD"] == "1") & (df["FLG_OP_WSPD"] == "0") & spd.between(0, 40)
    hrs = pd.DatetimeIndex(t[ok.values]).unique().sort_values()
    return {"hours": hrs, "native": pd.DatetimeIndex(t[ok.values]), "pairs": None,
            "n_rows": len(df)}


def isd_hours(isd_dir: Path, sid: str):
    files = sorted(isd_dir.glob(f"isd_{sid}_*.csv"))
    years = sorted(int(re.search(r"_(\d{4})\.csv$", f.name).group(1)) for f in files)
    if not files:
        return pd.DatetimeIndex([]), years, files
    df = pd.concat([pd.read_csv(f, dtype=str, usecols=["DATE", "WND"]) for f in files])
    w = obs.parse_isd_wind(df)
    # Native valid reports: the same masks as obs.parse_isd_wind, before the hourly mean.
    wnd = df["WND"].astype(str).str.split(",", expand=True)
    spd = pd.to_numeric(wnd[3], errors="coerce") / 10.0
    ok = (spd < 999.0) & ~wnd[4].astype(str).isin(["2", "3", "6", "7"]) & (spd >= 0) & (spd <= 40)
    native = pd.DatetimeIndex(pd.to_datetime(df["DATE"][ok.fillna(False).values]))
    return {"hours": pd.DatetimeIndex(w["time"]).unique().sort_values(), "native": native,
            "pairs": None}, years, files


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def coverage_mask(inst) -> np.ndarray:
    """True where a source exists for the hour (inside record / downloaded year)."""
    m = np.zeros(len(HOURS), bool)
    if inst["kind"] == "station":
        for y in inst["years"]:
            m |= HOURS.year == y
    if inst["first"] is not None:
        rec = (HOURS >= inst["first"]) & (HOURS <= inst["last"])
        m = m & rec if inst["kind"] == "station" else rec
    return m


def per_day(times) -> np.ndarray:
    """Count timestamps per day of the analysis span."""
    t = pd.DatetimeIndex(times)
    t = t[(t >= T0) & (t < T1 + pd.Timedelta(hours=1))]
    idx = ((t.normalize() - DAYS[0]) // pd.Timedelta(days=1)).astype(int)
    return np.bincount(idx, minlength=len(DAYS))


def gaps(valid: np.ndarray, first, last, min_h: int):
    out = []
    if first is None:
        return out
    i0, i1 = HOURS.get_loc(first), HOURS.get_loc(last)
    v = valid[i0:i1 + 1]
    run = None
    for k, ok in enumerate(v):
        if not ok and run is None:
            run = k
        if ok and run is not None:
            if k - run >= min_h:
                out.append((HOURS[i0 + run], HOURS[i0 + k - 1], k - run))
            run = None
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--p0", type=Path, default=REPO / "data/obs/P0_LIDAR_matrix.mat")
    ap.add_argument("--lpi", type=Path, default=REPO / "data/obs/LPI_processed.csv.gz")
    ap.add_argument("--p1-lidar", type=Path, required=True)
    ap.add_argument("--p1-sodar", type=Path, required=True)
    ap.add_argument("--anm", type=Path, required=True)
    ap.add_argument("--isd-dir", type=Path, default=REPO / "data/stations")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    sites = yaml.safe_load(open(REPO / "config/sites.yaml"))
    qc_p0 = sites["primary"]["P0"]["qc"]
    insts = []
    HMAP_P0 = {int(k): v for k, v in sites["primary"]["P0"]["height_map"].items()}
    HMAP_LPI = {int(k): v for k, v in sites["primary"]["LPI"]["height_map"].items()}
    HMAP_SODAR = {h: [h] for h in HMAP_P0}          # SODAR has exact 50..250 m levels

    def add(**kw):
        kw.setdefault("years", [])
        pack = kw.pop("hours")
        hrs = pack["hours"]
        kw["nat_d"] = per_day(pack["native"])
        kw["pair_d"] = per_day(pack["pairs"]) if pack["pairs"] is not None else None
        kw["rec_first"] = hrs.min().isoformat() if len(hrs) else ""
        kw["rec_last"] = hrs.max().isoformat() if len(hrs) else ""
        hrs = hrs[(hrs >= T0) & (hrs <= T1)]
        kw["valid"] = np.isin(HOURS.values, hrs.values)
        kw["first"] = hrs.min() if len(hrs) else None
        kw["last"] = hrs.max() if len(hrs) else None
        insts.append(kw)

    print("P0 ...")
    add(key="P0_LIDAR", label="P0 · LiDAR flutuante", kind="profiler", sym="P0",
        lat=sites["primary"]["P0"]["lat"], lon=sites["primary"]["P0"]["lon"],
        source=str(a.p0.name), md5=md5(a.p0), native="10 min", heights="40–260 m (20 níveis)",
        ref="100 m", qc="obs.read_p0_lidar: avail ≥ 80 %, 0–40 m/s; obs.to_hourly ≥ 4/6",
        status="validação MEQ-04 (2021)", group="LIDAR",
        hours=hourly_profiler(obs.read_p0_lidar(a.p0, avail_min_percent=qc_p0["avail_min_percent"]), HMAP_P0))
    print("P1 LiDAR ...")
    la, lo = lidar_coords(a.p1_lidar)
    add(key="P1_LIDAR", label="P1 · LiDAR (EOSOLAR)", kind="profiler", sym="P1L", lat=la, lon=lo,
        source=a.p1_lidar.name, md5=md5(a.p1_lidar), native="10 min", heights="40–260 m (20 níveis)",
        ref="100 m", qc="obs.read_p0_lidar (mesma estrutura L): avail ≥ 80 %, 0–40 m/s; obs.to_hourly ≥ 4/6",
        status="não usado na MEQ-04", group="LIDAR",
        hours=hourly_profiler(obs.read_p0_lidar(a.p1_lidar, avail_min_percent=qc_p0["avail_min_percent"]), HMAP_P0))
    print("P1 SODAR ...")
    add(key="P1_SODAR", label="P1 · SODAR (EOSOLAR)", kind="profiler", sym="SODAR",
        lat=-2.724877, lon=-42.575182, source=a.p1_sodar.name, md5=md5(a.p1_sodar),
        native="10 min", heights="30–280 m (26 níveis)", ref="100 m",
        qc="verify_sodar_p0_overlap.read_sodar (finito, sem duplicatas) + 0–40 m/s; obs.to_hourly ≥ 4/6",
        status=SODAR_NOTE, group="SODAR",
        hours=hourly_profiler(read_sodar_tidy(a.p1_sodar), HMAP_SODAR))
    print("LPI ...")
    add(key="LPI_LIDAR", label="LPI · LiDAR fixo (Porto-Ilha)", kind="profiler", sym="LPI",
        lat=sites["primary"]["LPI"]["lat"], lon=sites["primary"]["LPI"]["lon"],
        source=a.lpi.name, md5=md5(a.lpi), native="10 min", heights="10, 26, 50, 100, 150, 200 m",
        ref="100 m", qc="obs.read_lpi_lidar: 0–40 m/s; obs.to_hourly ≥ 4/6",
        status="validação MEQ-04 (2022)", group="LIDAR",
        hours=hourly_profiler(obs.read_lpi_lidar(a.lpi), HMAP_LPI))
    print("ANM-1/PPE1A ...")
    anm = read_anm(a.anm)
    anm.pop("n_rows")
    add(key="ANM_PPE1A", label="ANM-1/PPE1A · anemômetro (plataforma)", kind="platform",
        sym="ANM", lat=-4.70467, lon=-36.82571, source=a.anm.name, md5=md5(a.anm),
        native="horária", heights="não informada no arquivo", ref="altura desconhecida",
        qc="FLG_BRT_WSPD = 1, FLG_OP_WSPD = 0, 0–40 m/s (já horário; ≥ 4/6 não se aplica)",
        status="plataforma offshore, qualificada por avaliação independente (19/11/2026); " + ANM_NOTE,
        group="PLAT", hours=anm)
    for st in sites["surface"]["stations"]:
        print(st["id"], "...")
        hrs, years, files = isd_hours(a.isd_dir, st["id"])
        auto = st["kind"] == "inmet_auto"
        add(key="ISD_" + st["id"], label=st["name"], kind="station", sym="INMET" if auto else "SYNOP",
            lat=st["lat"], lon=st["lon"], years=years,
            source=f"NOAA ISD {st['id']} ({', '.join(map(str, years))})",
            md5=";".join(md5(f)[:8] for f in files), native="horária" if auto else "sinótica/METAR",
            heights="10 m", ref="10 m",
            qc="obs.parse_isd_wind: códigos 2/3/6/7 excluídos, 0–40 m/s, média horária",
            status="validação MEQ-04 (superfície, primária)" if auto else "suplementar (aeroporto/sinótica)",
            hours=hrs, group="INMET" if auto else "AERO")

    # ---------------------------------------------------------------- tables
    daily_rows, monthly_rows, gap_rows, inst_rows = [], [], [], []
    hdf = pd.DataFrame({"t": HOURS})
    for it in insts:
        cov = coverage_mask(it)
        it["cov"] = cov
        v = it["valid"]
        d = pd.DataFrame({"day": HOURS.normalize(), "v": v, "c": cov}).groupby("day").sum()
        for day, r in d.iterrows():
            daily_rows.append({"instrument": it["key"], "date": day.date().isoformat(),
                               "valid_hours": int(r.v),
                               "pct_valid": round(100 * r.v / 24, 1) if r.c > 0 else np.nan,
                               "source_coverage_hours": int(r.c)})
        m = pd.DataFrame({"m": HOURS.to_period("M"), "v": v, "c": cov}).groupby("m").agg(
            v=("v", "sum"), c=("c", "sum"), n=("v", "size"))
        for per, r in m.iterrows():
            monthly_rows.append({"instrument": it["key"], "month": str(per),
                                 "valid_hours": int(r.v), "hours_in_month": int(r.n),
                                 "pct_valid": round(100 * r.v / r.n, 1) if r.c > 0 else np.nan,
                                 "source_coverage_hours": int(r.c)})
        g = gaps(v, it["first"], it["last"], GAP_MIN_H[it["kind"]])
        it["gaps"] = g
        for s, e, n in g:
            gap_rows.append({"instrument": it["key"], "start": s.isoformat(), "end": e.isoformat(),
                             "hours": n, "threshold_h": GAP_MIN_H[it["kind"]]})
        rec = cov.sum()
        hod = ""
        if it["kind"] == "station" and it["first"] is not None:
            sub = pd.DataFrame({"h": HOURS.hour, "v": v, "c": cov})[cov]
            frac = sub.groupby("h")["v"].mean()
            it["hod"] = [round(100 * x, 1) for x in frac.reindex(range(24), fill_value=0)]
            hod = int((frac >= 0.5).sum())
        longest = max(g, key=lambda x: x[2]) if g else None
        inst_rows.append({
            "instrument": it["key"], "label": it["label"], "kind": it["kind"], "symbol": it["sym"],
            "lat": it["lat"], "lon": it["lon"], "source": it["source"], "md5": it["md5"],
            "native_resolution": it["native"], "heights": it["heights"], "reference_height": it["ref"],
            "qc": it["qc"], "status": it["status"],
            "first_valid": it["first"].isoformat() if it["first"] is not None else "",
            "last_valid": it["last"].isoformat() if it["last"] is not None else "",
            "record_first_valid_any_date": it["rec_first"], "record_last_valid_any_date": it["rec_last"],
            "valid_hours": int(v.sum()), "record_hours": int(rec),
            "pct_valid_in_record": round(100 * v.sum() / rec, 1) if rec else np.nan,
            "n_gaps": len(g), "longest_gap_h": longest[2] if longest else 0,
            "longest_gap_start": longest[0].isoformat() if longest else "",
            "utc_hours_covered_ge50pct": hod,
            "isd_years_available": ",".join(map(str, it["years"])),
        })
    pd.DataFrame(inst_rows).to_csv(a.out / "instruments.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(a.out / "availability_daily.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(a.out / "availability_monthly.csv", index=False)
    pd.DataFrame(gap_rows, columns=["instrument", "start", "end", "hours", "threshold_h"]).to_csv(
        a.out / "gaps.csv", index=False)

    # ------------------------------ grouped window totals + candidate windows
    for it in insts:
        it["h_d"] = it["valid"].reshape(-1, 24).sum(1)
        if it["kind"] == "station":   # "sem fonte" = no ISD file for that year
            it["src_d"] = np.isin(DAYS.year, it["years"])
        else:
            it["src_d"] = np.ones(len(DAYS), bool)
    exps = yaml.safe_load(open(REPO / "config/experiments.yaml"))
    periods = [{"label": v["label"], "site": v["validation_site"],
                "start": pd.Timestamp(v["analysis_start"]).date().isoformat(),
                "end": pd.Timestamp(v["analysis_end"]).date().isoformat()}
               for v in exps["periods"].values()]
    prof_union = np.any([it["valid"] for it in insts if it["group"] in PROFILER_GROUPS], axis=0)
    wins = []
    for dur in DURATIONS:
        s0 = WIN_FIRST
        while s0 + pd.DateOffset(months=dur) - pd.Timedelta(days=1) <= T1.normalize():
            wins.append(window_metrics(insts, prof_union, periods, s0, dur))
            s0 += pd.DateOffset(months=1)
    mark_best(wins)
    pd.DataFrame([{"months": w["months"], "start": w["start"], "end": w["end"], **w["v"],
                   "best_cols": ";".join(w["best"]), "best_row": w["best_row"]} for w in wins]
                 ).to_csv(a.out / "candidate_windows_12_24_36.csv", index=False)
    preopts = preoptions(wins)
    pd.DataFrame([{**p, **{k: p["v"][k] for k in ("prof_hours", "total_hours", "longest_gap_h", "meq04_months")}}
                  for p in preopts]).drop(columns="v").to_csv(a.out / "preoptions.csv", index=False)

    # ---------------------------------------------------------------- HTML
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    payload = {
        "t0": T0.date().isoformat(), "ndays": len(DAYS),
        "valid_day_h": VALID_DAY_H, "station_ok": STATION_OK_PCT,
        "preoptions": [{k: p[k] for k in ("months", "criterion", "rank", "start", "end", "value")} for p in preopts],
        "criteria": CRITERIA, "durations": list(DURATIONS), "sodar_note": SODAR_NOTE, "anm_note": ANM_NOTE,
        "groups": [{"key": k, "label": v} for k, v in GROUPS],
        "windows": wins, "win_cols": WIN_COLS, "periods": periods,
        "prof_union": "".join("1" if x else "0" for x in prof_union),
        "site_of": SITE_OF, "total_groups": TOTAL_GROUPS, "profiler_groups": PROFILER_GROUPS,
        "months": [str(p) for p in pd.period_range(T0, T1, freq="M")],
        "instruments": [],
        "geography": json.load(open(REPO / "results/interactive/geo/geography.json")),
        "mesh": mesh_extent(),
        "cmap": sci_colormaps.stops("devon_r", 32)[5:],
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sha": sha,
    }
    mon = pd.DataFrame(monthly_rows)
    for it, row in zip(insts, inst_rows):
        hv = it["valid"].reshape(-1, 24).sum(1)
        hc = it["cov"].reshape(-1, 24).sum(1)
        payload["instruments"].append({
            **{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()},
            "h": [int(x) if c else -1 for x, c in zip(hv, hc)],
            "group": it["group"],
            "r": [int(x) for x in it["nat_d"]],
            "p": [int(x) for x in it["pair_d"]] if it["pair_d"] is not None else None,
            "src": [1 if x else 0 for x in it["src_d"]],
            "monthly": [None if np.isnan(x) else x for x in
                        mon[mon.instrument == it["key"]]["pct_valid"].tolist()],
            "gaps": [[s.isoformat(), e.isoformat(), n] for s, e, n in it["gaps"]],
            "hod": it.get("hod"),
        })
    vendor = REPO / "docs/templates/vendor"
    css = (REPO / "docs/templates/report_v2/report.css").read_text().split("\n")[3:21]
    html = (TEMPLATE
            .replace("/*LEAFLET_CSS*/", (vendor / "leaflet.css").read_text())
            .replace("/*ROOT_VARS*/", "\n".join(css))
            .replace("/*LEAFLET_JS*/", (vendor / "leaflet.js").read_text())
            .replace("/*DATA*/", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                     .replace("</", "<\\/")))
    (a.out / "index.html").write_text(html, encoding="utf-8")
    print("wrote", a.out)


# (key, header, better) — better: "max", "min" or None (no highlight).
WIN_COLS = [
    ["total_hours", "Total de horas válidas", "max"],
    ["prof_hours", "Horas de perfiladores (LiDAR + SODAR)", "max"],
    ["lidar_days", "Dias com LiDAR (≥ 12 h)", "max"],
    ["lidar_hours", "Horas de LiDAR a 100 m", "max"],
    ["lidar_pairs", "Pares hora×altura (LiDAR)", "max"],
    ["prof_sites", "Sítios de perfilador", "max"],
    ["simul_days", "Dias com ≥ 2 sítios de perfilador", "max"],
    ["meq04_months", "Meses validados na MEQ-04", "max"],
    ["inmet_hours", "Horas INMET", "max"],
    ["aero_hours", "Horas em aeroportos", "max"],
    ["stations_ge80", "Estações ≥ 80 %", "max"],
    ["longest_gap_h", "Maior lacuna de perfilador (h)", "min"],
    ["spinup_start", "Início do spin-up (11 d)", None],
    ["sodar_hours", "Horas SODAR P1 (100 m)", None],
    ["plat_hours", "Horas plataforma (ANM-1/PPE1A)", None],
]


def window_metrics(insts, prof_union, periods, s, months):
    """Criteria of one candidate window [s, s + months). Mirrors computeWin() in JS.

    Hours: each instrument counts at most 1 per hour (valid-hour flags), only where a
    source exists (ISD years without a file). "Só perfiladores" = LiDAR (P0, P1, LPI)
    + SODAR P1 at 100 m; "Total" = perfiladores + plataforma + INMET + aeroportos.
    Profiler sites: P0, P1 (LiDAR or SODAR) and LPI; a site-day is valid when any of
    its profilers has >= 12 valid hours. Longest profiler gap: longest run of
    consecutive hours with no valid 100 m hour at any LiDAR or the SODAR.
    """
    e = s + pd.DateOffset(months=months) - pd.Timedelta(days=1)
    m = (DAYS >= s) & (DAYS <= e)
    hm = (HOURS >= s) & (HOURS < e + pd.Timedelta(days=1))
    by = lambda *g: [it for it in insts if it["group"] in g]
    lid = by("LIDAR")
    vd = np.array([it["h_d"][m] >= VALID_DAY_H for it in lid])
    site = {}
    for it in by(*PROFILER_GROUPS):
        k = SITE_OF[it["key"]]
        site[k] = site.get(k, np.zeros(int(m.sum()), bool)) | (it["h_d"][m] >= VALID_DAY_H)
    sd = np.array(list(site.values()))
    hsum = lambda its: int(sum(it["h_d"][m][it["src_d"][m]].sum() for it in its))
    run = best = 0
    for ok in prof_union[hm]:
        run = 0 if ok else run + 1
        best = max(best, run)
    st = [it for it in insts if it["kind"] == "station"]
    v = {
        "total_hours": hsum(by(*TOTAL_GROUPS)),
        "prof_hours": hsum(by(*PROFILER_GROUPS)),
        "lidar_days": int(vd.any(0).sum()),
        "lidar_hours": hsum(lid),
        "lidar_pairs": int(sum(it["pair_d"][m].sum() for it in lid)),
        "prof_sites": int(sd.any(1).sum()),
        "simul_days": int((sd.sum(0) >= 2).sum()),
        "meq04_months": sum(1 for p in periods if pd.Timestamp(p["start"]) >= s
                            and pd.Timestamp(p["end"]) <= e + pd.Timedelta(days=1)),
        "inmet_hours": hsum(by("INMET")),
        "aero_hours": hsum(by("AERO")),
        "stations_ge80": sum(1 for it in st if 100 * it["valid"][hm].mean() >= STATION_OK_PCT),
        "longest_gap_h": int(best),
        "spinup_start": (s - pd.Timedelta(days=SPINUP_DAYS)).date().isoformat(),
        "sodar_hours": hsum(by("SODAR")),
        "plat_hours": hsum(by("PLAT")),
    }
    return {"months": months, "start": s.date().isoformat(), "end": e.date().isoformat(), "v": v}


def preoptions(wins):
    """Top 3 windows per duration and criterion (value desc, then earliest start). Mirrors JS."""
    out = []
    for dur in DURATIONS:
        for key, _ in CRITERIA:
            ws = sorted((w for w in wins if w["months"] == dur), key=lambda w: (-w["v"][key], w["start"]))
            for r, w in enumerate(ws[:3], 1):
                out.append({"months": dur, "criterion": key, "rank": r, "start": w["start"],
                            "end": w["end"], "value": w["v"][key], "v": w["v"]})
    return out


def mark_best(wins):
    """Per duration: best cell(s) of each column (ties all) and the best row by LiDAR hours."""
    for dur in DURATIONS:
        ws = [w for w in wins if w["months"] == dur]
        for w in ws:
            w["best"] = []
        for key, _, better in WIN_COLS:
            if better is None:
                continue
            vals = [w["v"][key] for w in ws]
            t = max(vals) if better == "max" else min(vals)
            for w in ws:
                if w["v"][key] == t:
                    w["best"].append(key)
        top = max(w["v"]["lidar_hours"] for w in ws)
        for w in ws:
            w["best_row"] = w["v"]["lidar_hours"] == top


def mesh_extent():
    """EXP03 mesh extent, read from the consolidated payload of the main report."""
    h = (REPO / "results/report/index.html").read_text()
    m = re.search(r'id="report-data">(.*?)</script>', h, re.S)
    for x in json.loads(m.group(1)).get("meshes", []):
        if "EXP03" in x.get("experiments", []):
            return {"name": x["name"], "extent": x["extent"]}
    return None


TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEQ-06.4 · Disponibilidade das observações</title>
<style>/*LEAFLET_CSS*/</style>
<style>
/*ROOT_VARS*/
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--font); }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; font-weight: 700; }
h2 { font-size: 16px; margin: 32px 0 6px; padding-top: 10px; border-top: 1px solid var(--rule-strong); }
.lead { color: var(--muted); margin: 0 0 12px; max-width: 900px; }
.caption { font-size: 12px; color: var(--muted); margin: 6px 0 0; max-width: 960px; }
.caption b { color: var(--ink); }
.panel { border-top: 1px solid var(--rule); padding-top: 8px; }
#tl-wrap { position: relative; width: 100%; overflow: hidden; }
#tl { display: block; width: 100%; }
#tip { position: fixed; pointer-events: none; background: #fff; border: 1px solid var(--ink); padding: 4px 7px; font-size: 12px; display: none; z-index: 2000; max-width: 280px; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; font-size: 12px; color: var(--muted); margin-top: 6px; }
.cbar { width: 160px; height: 10px; border: 1px solid var(--rule); }
.sw { display: inline-block; width: 14px; height: 10px; border: 1px solid var(--rule); vertical-align: middle; margin-right: 4px; }
.ctrl { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0; font-size: 13px; }
.ctrl button { font: inherit; font-size: 12px; background: #fff; border: 1px solid var(--rule); padding: 3px 9px; cursor: pointer; }
.ctrl button.active { border-color: var(--ink); background: var(--ink); color: #fff; }
.ctrl select { font: inherit; font-size: 12px; padding: 2px 4px; border: 1px solid var(--rule); background: #fff; }
.ctrl input { font: inherit; padding: 2px 4px; border: 1px solid var(--rule); }
table { border-collapse: collapse; font-size: 12px; width: 100%; }
th, td { padding: 3px 6px; border-bottom: 1px solid var(--rule); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
thead th { border-bottom: 1px solid var(--ink); font-weight: 700; }
.scroll { overflow-x: auto; }
.kpis { display: flex; flex-wrap: wrap; gap: 28px; margin: 8px 0; }
.kpis div { font-size: 12px; color: var(--muted); }
.kpis b { display: block; font-size: 22px; color: var(--ink); font-weight: 700; }
.hm td { padding: 0; width: 18px; min-width: 18px; height: 16px; border: 1px solid #fff; text-align: center; font-size: 9px; }
.hm th { font-weight: 400; font-size: 10px; color: var(--muted); padding: 0 2px; border: 0; }
.hm td.lbl { width: auto; text-align: left; padding: 0 8px 0 0; font-size: 12px; white-space: nowrap; border: 0; }
.excl { color: var(--loss); font-size: 11px; }
h3.sub { font-size: 13px; margin: 14px 0 4px; }
tr.grp td { font-weight: 700; border-bottom: 1px solid var(--ink); }
tr.sod td { color: #8c8c8c; }
tr.tot td { font-weight: 700; border-top: 1px solid var(--ink); }
td.na { color: #8c8c8c; font-style: italic; }
.cand th { cursor: pointer; white-space: normal; vertical-align: bottom; min-width: 64px; }
.cand th.sorted::after { content: ' ▾'; } .cand th.sorted.asc::after { content: ' ▴'; }
.cand tbody tr { cursor: pointer; }
.cand tbody tr:hover td { background: #f3f3f3; }
.cand td.best { background: #d9ead3; font-weight: 700; }
.cand tr.bestrow td { background: #eef6eb; }
.cand tr.bestrow td.best { background: #d9ead3; }
.cand tr.sel td { box-shadow: inset 0 1px 0 var(--ink), inset 0 -1px 0 var(--ink); }
.cand th.g, .cand td.g { color: #8c8c8c; }
.cand td.g { background: #fafafa; }
.sw.best { background: #d9ead3; } .sw.bestrow { background: #eef6eb; }
#hm-wrap { position: relative; display: inline-block; min-width: 100%; }
#hm-win { position: absolute; border: 1.6px solid #1a1a1a; pointer-events: none; display: none; }
#map { height: 520px; border: 1px solid var(--rule); background: #fff; }
.leaflet-popup-content { font: 12px/1.4 var(--font); }
footer { margin-top: 36px; border-top: 1px solid var(--rule-strong); padding-top: 8px; font-size: 11.5px; color: var(--muted); }
footer code { font-size: 11px; }
@media (max-width: 700px) { #map { height: 380px; } h1 { font-size: 19px; } }
</style>
</head>
<body>
<main>
<h1>Disponibilidade das observações de vento — 2021-10 a 2025-08</h1>
<p class="lead">MEQ-06.4 · Painel de apoio à escolha do período da integração longa da EXP03 (12, 24 ou 36 meses). Mostra apenas os dados: horas válidas por instrumento após o mesmo controle de qualidade das validações da MEQ-04.</p>

<h2>a · Linha do tempo</h2>
<div class="ctrl" id="win-ctrl">
  <span>Janela de</span>
  <span id="win-dur"><button type="button" data-m="12" class="active">12 meses</button><button type="button" data-m="24">24 meses</button><button type="button" data-m="36">36 meses</button></span>
  <span>a partir de</span>
  <input type="date" id="win-start" min="2021-10-01">
</div>
<div class="ctrl" id="pre-ctrl">
  <label for="crit">Critério:</label>
  <select id="crit"><option value="total_hours">Total</option><option value="prof_hours">Só perfiladores</option></select>
  <span>3 janelas com mais horas válidas:</span>
  <span id="win-pre"></span>
</div>
<div id="tl-wrap"><canvas id="tl"></canvas></div>
<div class="legend" id="tl-legend"></div>
<p class="caption"><b>a</b> Uma faixa por instrumento (perfiladores LiDAR e SODAR no topo, depois a plataforma offshore e as estações). Os botões de pré-opção mostram, para a duração escolhida, as 3 janelas (início no dia 1) com mais horas válidas no critério escolhido: <b>Total</b> = perfiladores + plataforma + INMET + aeroportos; <b>Só perfiladores</b> = LiDAR (P0, P1, LPI) + SODAR P1, a 100 m. Cada instrumento conta no máximo 1 por hora. A cor é a disponibilidade diária (% das 24 h com dado válido na altura de referência: 100 m nos perfiladores, inclusive o SODAR; 10 m nas estações; altura não informada na plataforma). Branco: dia sem nenhuma hora válida dentro do registro do instrumento (lacuna). Cinza-claro: sem fonte (fora do registro do instrumento ou ano ISD sem arquivo). O retângulo preto marca a janela selecionada (12, 24 ou 36 meses). ANM-1/PPE1A (plataforma offshore): altura e fuso não informados no arquivo; horário tratado como UTC. Passe o cursor para ver a data, o % e a lacuna que contém o dia.</p>

<h2>b · Disponibilidade mensal</h2>
<div class="scroll"><div id="hm-wrap"><table class="hm" id="hm"></table><div id="hm-win"></div></div></div>
<p class="caption"><b>b</b> % das horas do mês com dado válido, por instrumento. Célula em branco com borda: 0 %; cinza-claro: sem fonte no mês. O retângulo preto é a mesma janela selecionada em (a). Mapa de cor Crameri <i>devon</i>.</p>

<h2>c · Janelas candidatas</h2>
<div class="ctrl" id="cand-dur"><span>Duração:</span><button type="button" data-m="12" class="active">12 meses</button><button type="button" data-m="24">24 meses</button><button type="button" data-m="36">36 meses</button><span id="cand-n"></span></div>
<div class="legend"><span><span class="sw best"></span>melhor valor da coluna (empates: todas as células)</span><span><span class="sw bestrow"></span>janela com mais horas de LiDAR a 100 m (linha inteira)</span><span>sem destaque: início do spin-up e as colunas de horas por instrumento (SODAR, plataforma)</span></div>
<div class="scroll"><table id="cand" class="cand"></table></div>
<p class="caption"><b>c</b> Todas as janelas que começam no dia 1 de cada mês, de 2021-10 até a última que cabe nos dados (fim ≤ 31/08/2025). Clique no cabeçalho para ordenar e numa linha para aplicar a janela ao seletor. <b>Total</b>: horas válidas de perfiladores + plataforma + INMET + aeroportos (cada instrumento conta no máximo 1 por hora). <b>Horas de perfiladores</b>: LiDAR (P0, P1, LPI) + SODAR P1, a 100 m (≥ 4 de 6 amostras). <b>Dias com LiDAR</b>: dias com ≥ <span class="vdh"></span> válidas em pelo menos um LiDAR. <b>Horas de LiDAR</b>: só os três LiDARs. <b>Pares hora×altura</b>: horas válidas dos LiDARs em cada altura da validação da MEQ-04. <b>Sítios de perfilador</b>: P0, P1 (LiDAR ou SODAR) e LPI com ≥ 1 dia válido. <b>Dias com ≥ 2 sítios</b>: dias válidos em pelo menos dois desses sítios. <b>Meses MEQ-04</b>: meses já validados (Nov 2021 em P0; Oct 2022 em LPI) inteiramente contidos. <b>Horas INMET / aeroportos</b>: horas com dado válido, só onde há arquivo ISD. <b>Estações ≥ 80 %</b>: das 11 estações. <b>Maior lacuna de perfilador</b>: maior sequência de horas sem nenhuma hora válida em nenhum LiDAR nem no SODAR; quanto menor, melhor. <b>Spin-up</b>: início da integração, 11 dias antes da janela.</p>

<h3 class="sub">Janela selecionada</h3>
<div class="kpis" id="win-kpis"></div>
<div class="scroll"><table id="win-table"></table></div>
<p class="caption">Contagens na janela selecionada, por grupo, com subtotal. <b>Registros nativos</b>: amostras de 10 min válidas a 100 m (LiDAR/SODAR), relatos ISD válidos (estações) ou registros horários válidos (plataforma). <b>Horas válidas</b>: média horária com ≥ 4 de 6 amostras a 100 m (perfiladores) ou hora com relato válido (estações, plataforma). <b>Pares hora×altura</b>: horas válidas em cada altura da validação da MEQ-04 (50, 100, 150, 200 e 250 m; LPI sem 250 m). "sem fonte": nenhum arquivo ISD no período; "parcial": parte da janela sem arquivo. Todos os grupos entram no total. <b>Dia válido</b>: ≥ <span class="vdh"></span> das 24 h válidas. <b>Dias com ≥ 2 sítios de perfilador</b>: P0, P1 (LiDAR ou SODAR) e LPI. <b>Estações ≥ 80 %</b>: estações com ≥ 80 % das horas da janela válidas.</p>

<h2>d · Mapa da rede</h2>
<div id="map"></div>
<div class="legend" id="map-legend"></div>
<p class="caption"><b>d</b> Sítios e estações; clique para ver o período válido e a disponibilidade na janela selecionada em (a). A ANM-1/PPE1A (plataforma offshore) está na célula 35433 da malha da EXP03, a 40,6 km do LPI. Tracejado: extensão da malha da EXP03 (<span id="mesh-name"></span>), como no relatório principal.</p>

<footer id="foot"></footer>
</main>
<div id="tip"></div>
<script>/*LEAFLET_JS*/</script>
<script type="application/json" id="obs-data">/*DATA*/</script>
<script>
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('obs-data').textContent);
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmt(x, d) { return x == null ? '—' : Number(x).toLocaleString('pt-BR', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); }
  var DAY = 86400000, T0 = Date.parse(D.t0 + 'T00:00:00Z'), N = D.ndays;
  function dayIdx(iso) { return Math.round((Date.parse(iso + 'T00:00:00Z') - T0) / DAY); }
  function isoDay(i) { return new Date(T0 + i * DAY).toISOString().slice(0, 10); }
  function br(iso) { var p = iso.slice(0, 10).split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
  function hex2rgb(h) { return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)]; }
  var CM = D.cmap.map(function (s) { return hex2rgb(s.colour); });
  function col(p) {
    var x = Math.max(0, Math.min(1, p / 100)) * (CM.length - 1), i = Math.floor(x), f = x - i, a = CM[i], b = CM[Math.min(i + 1, CM.length - 1)];
    return 'rgb(' + [0, 1, 2].map(function (k) { return Math.round(a[k] + f * (b[k] - a[k])); }).join(',') + ')';
  }
  var NOSRC = '#ececec';
  var I = D.instruments;
  I.forEach(function (it) {
    it.gapDay = {};
    (it.gaps || []).forEach(function (g) {
      var a = Math.max(0, dayIdx(g[0].slice(0, 10))), b = Math.min(N - 1, dayIdx(g[1].slice(0, 10)));
      for (var d = a; d <= b; d++) it.gapDay[d] = g;
    });
  });
  $('tl-legend').innerHTML = '<span>0 %</span><span class="cbar" style="background:linear-gradient(90deg,' + D.cmap.map(function (s, i) { return s.colour + ' ' + (100 * i / (D.cmap.length - 1)).toFixed(1) + '%'; }).join(',') + ')"></span><span>100 %</span>' +
    '<span><span class="sw" style="background:#fff;border-color:#9a9a9a"></span>lacuna (0 h válidas)</span><span><span class="sw" style="background:' + NOSRC + '"></span>sem fonte</span>';
  Array.prototype.forEach.call(document.querySelectorAll('.vdh'), function (e) { e.textContent = D.valid_day_h + ' h'; });

  // ---------------- window state
  function addMonths(s, m) { var d = new Date(T0 + s * DAY); d.setUTCMonth(d.getUTCMonth() + m); return Math.round((d - T0) / DAY); }
  function winEnd(s, m) { return addMonths(s, m || win.m) - 1; }
  var crit = 'total_hours';
  function topWins(m, key) { return D.preoptions.filter(function (p) { return p.months === m && p.criterion === key; }); }
  var win = { m: 12, s: dayIdx(topWins(12, crit)[0].start) }; win.e = winEnd(win.s);
  function drawPre() {
    var unit = crit === 'total_hours' ? 'h no total' : 'h de perfiladores';
    $('win-pre').innerHTML = topWins(win.m, crit).map(function (p) { return '<button type="button" data-s="' + p.start + '" data-v="' + p.value + '">' + br(p.start) + ' → ' + br(p.end) + ' · ' + fmt(p.value) + ' ' + unit + '</button>'; }).join('');
    Array.prototype.forEach.call($('win-pre').querySelectorAll('button'), function (b) { b.classList.toggle('active', dayIdx(b.dataset.s) === win.s); });
  }
  $('crit').addEventListener('change', function () { crit = this.value; drawPre(); });
  $('win-dur').addEventListener('click', function (ev) { var b = ev.target.closest('button'); if (!b) return; win.m = +b.dataset.m; setWin(win.s); });
  $('win-pre').addEventListener('click', function (ev) { var b = ev.target.closest('button'); if (!b) return; setWin(dayIdx(b.dataset.s)); });
  $('win-start').addEventListener('change', function () { if (this.value) setWin(dayIdx(this.value)); });
  function setWin(s, m) {
    if (m) win.m = m;
    s = Math.max(0, s); while (s > 0 && winEnd(s) > N - 1) s--;
    win.s = s; win.e = winEnd(win.s);
    $('win-start').value = isoDay(win.s);
    var mx = 0; while (winEnd(mx + 1) <= N - 1) mx++; $('win-start').max = isoDay(mx);
    Array.prototype.forEach.call($('win-dur').querySelectorAll('button'), function (b) { b.classList.toggle('active', +b.dataset.m === win.m); });
    drawPre();
    drawTL(); drawWin(); drawHmWin(); markCand(); updatePopups();
  }

  // ---------------- a · timeline (canvas)
  var cv = $('tl'), ctx = cv.getContext('2d'), LBLW = 230, ROWH = 15, TOP = 22, SEP = 10, geo = {};
  function rows() { var r = [], y = TOP; I.forEach(function (it, k) { if (k > 0 && it.kind !== I[k - 1].kind) y += SEP; r.push(y); y += ROWH; }); return { y: r, h: y + 6 }; }
  function drawTL() {
    var W = cv.parentNode.clientWidth, R = rows(), dpr = window.devicePixelRatio || 1;
    var lw = W < 600 ? 120 : LBLW;
    cv.width = W * dpr; cv.height = R.h * dpr; cv.style.height = R.h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, R.h);
    var x0 = lw, pw = (W - lw - 4) / N; geo = { x0: x0, pw: pw, y: R.y, lw: lw };
    ctx.font = '10px Arial'; ctx.fillStyle = '#5c5c5c'; ctx.textBaseline = 'alphabetic';
    for (var i = 0; i < N; i++) {
      var d = new Date(T0 + i * DAY);
      if (d.getUTCDate() === 1) {
        var m = d.getUTCMonth(), x = x0 + i * pw;
        ctx.fillStyle = m === 0 ? '#1a1a1a' : '#d4d4d4'; ctx.fillRect(x, TOP - 4, m === 0 ? 1 : 0.5, R.h - TOP);
        if (m === 0 || (m % 3 === 0 && W > 700)) { ctx.fillStyle = '#5c5c5c'; ctx.fillText(m === 0 ? String(d.getUTCFullYear()) : ('0' + (m + 1)).slice(-2), x + 2, 12); }
      }
    }
    I.forEach(function (it, k) {
      var y = R.y[k];
      ctx.fillStyle = '#1a1a1a'; ctx.font = (it.kind === 'profiler' ? 'bold ' : '') + '11px Arial'; ctx.textBaseline = 'middle';
      var lab = it.label.length > (lw < 200 ? 18 : 34) ? it.label.slice(0, lw < 200 ? 17 : 33) + '…' : it.label;
      ctx.fillText(lab, 2, y + ROWH / 2);
      for (var i = 0; i < N; i++) {
        var h = it.h[i];
        ctx.fillStyle = h < 0 ? NOSRC : (h === 0 ? '#ffffff' : col(100 * h / 24));
        ctx.fillRect(x0 + i * pw, y + 1, Math.max(pw, 0.6) + 0.3, ROWH - 3);
      }
      ctx.strokeStyle = '#d4d4d4'; ctx.lineWidth = 0.5; ctx.strokeRect(x0, y + 1, N * pw, ROWH - 3);
      if (it.instrument === 'P1_SODAR' || it.kind === 'platform') {
        var note = it.kind === 'platform' ? 'altura e fuso não informados; UTC' : 'não usado na seleção MEQ-03; incluído na validação final';
        ctx.font = 'italic 10px Arial'; var tw = ctx.measureText(note).width;
        ctx.fillStyle = 'rgba(255,255,255,0.92)'; ctx.fillRect(W - 10 - tw, y + 1, tw + 8, ROWH - 3);
        ctx.fillStyle = '#883007'; ctx.textAlign = 'right';
        ctx.fillText(note, W - 6, y + ROWH / 2); ctx.textAlign = 'left';
      }
    });
    if (win.e != null) {
      ctx.strokeStyle = '#1a1a1a'; ctx.lineWidth = 1.6;
      ctx.strokeRect(x0 + win.s * pw, TOP - 6, (win.e - win.s + 1) * pw, R.h - TOP + 2);
    }
  }
  var tip = $('tip');
  cv.addEventListener('mousemove', function (ev) {
    var r = cv.getBoundingClientRect(), x = ev.clientX - r.left, y = ev.clientY - r.top;
    var i = Math.floor((x - geo.x0) / geo.pw), k = -1;
    geo.y.forEach(function (yy, j) { if (y >= yy && y < yy + ROWH) k = j; });
    if (i < 0 || i >= N || k < 0) { tip.style.display = 'none'; return; }
    var it = I[k], h = it.h[i], g = it.gapDay[i];
    var html = '<b>' + esc(it.label) + '</b><br>' + br(isoDay(i)) + ' · ' + (h < 0 ? 'sem fonte' : fmt(100 * h / 24, 0) + ' % (' + h + ' de 24 h)');
    if (g) html += '<br>lacuna de ' + fmt(g[2]) + ' h (' + (g[2] >= 48 ? fmt(g[2] / 24, 1) + ' d, ' : '') + br(g[0]) + ' ' + g[0].slice(11, 16) + ' → ' + br(g[1]) + ' ' + g[1].slice(11, 16) + ' UTC)';
    if (it.instrument === 'P1_SODAR') html += '<br>' + esc(D.sodar_note);
    if (it.kind === 'platform') html += '<br>Plataforma offshore: ' + esc(D.anm_note);
    tip.innerHTML = html; tip.style.display = 'block';
    tip.style.left = Math.min(ev.clientX + 12, window.innerWidth - 290) + 'px'; tip.style.top = (ev.clientY + 12) + 'px';
  });
  cv.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
  cv.addEventListener('click', function (ev) { var r = cv.getBoundingClientRect(), i = Math.floor((ev.clientX - r.left - geo.x0) / geo.pw); if (i >= 0 && i < N) setWin(i); });
  window.addEventListener('resize', drawTL);

  // ---------------- b · window panel
  function stats(it) {
    var vd = 0, vh = 0, n = 0;
    for (var i = win.s; i <= win.e; i++) { var h = Math.max(it.h[i], 0); vh += h; n += 24; if (h >= D.valid_day_h) vd++; }
    return { vd: vd, pct: 100 * vh / n };
  }
  function drawWin() {
    var nd = win.e - win.s + 1, both = 0, prof = I.filter(function (it) { return it.kind === 'profiler'; });
    for (var i = win.s; i <= win.e; i++) { var st = {}; prof.forEach(function (it) { if (it.h[i] >= D.valid_day_h) st[D.site_of[it.instrument]] = 1; }); if (Object.keys(st).length >= 2) both++; }
    var okSt = 0, nSt = 0, body = '', totals = {}, grand = { nat: 0, hrs: 0, pairs: 0 };
    D.groups.forEach(function (g) {
      var mem = I.filter(function (it) { return it.group === g.key; }), anyv = {}, G = { nat: 0, hrs: 0, pairs: (g.key === 'LIDAR' || g.key === 'SODAR') ? 0 : null, vd: 0, src: 'completo' }, rowsH = '';
      mem.forEach(function (it) {
        var nat = 0, hrs = 0, pairs = it.p ? 0 : null, vd = 0, nsrc = 0;
        for (var i = win.s; i <= win.e; i++) {
          if (!it.src[i]) continue; nsrc++;
          nat += it.r[i]; hrs += Math.max(it.h[i], 0); if (it.p) pairs += it.p[i];
          if (it.h[i] >= D.valid_day_h) { vd++; anyv[i] = 1; }
        }
        var src = nsrc === 0 ? 'sem fonte' : (nsrc < nd ? 'parcial' : 'completo');
        var s = stats(it); it._win = s;
        if (it.kind === 'station') { nSt++; if (s.pct >= D.station_ok) okSt++; }
        if (src !== 'completo') G.src = 'parcial';
        if (src !== 'sem fonte') { G.nat += nat; G.hrs += hrs; if (pairs != null) G.pairs += pairs; }
        var na = '<td class="na">sem fonte</td>';
        rowsH += '<tr' + '' + '><td>' + esc(it.label) + (src === 'parcial' ? ' <span class="na">(parcial)</span>' : '') + '</td>' +
          (src === 'sem fonte' ? na + na + '<td>—</td>' + na + na :
          '<td>' + fmt(nat) + '</td><td>' + fmt(hrs) + '</td><td>' + (pairs == null ? '—' : fmt(pairs)) + '</td><td>' + fmt(vd) + '</td><td>' + fmt(100 * vd / nd, 1) + '</td>') + '</tr>';
      });
      for (var k in anyv) G.vd++;
      totals[g.key] = G;
      { grand.nat += G.nat; grand.hrs += G.hrs; grand.pairs += G.pairs || 0; }
      body += '<tr class="grp' + '' + '"><td>' + esc(g.label) + (G.src !== 'completo' ? ' — <span class="na">parcial</span>' : '') + '</td><td>' + fmt(G.nat) + '</td><td>' + fmt(G.hrs) + '</td><td>' + (G.pairs == null ? '—' : fmt(G.pairs)) + '</td><td>' + fmt(G.vd) + '</td><td>' + fmt(100 * G.vd / nd, 1) + '</td></tr>' + rowsH;
    });
    body += '<tr class="tot"><td>Total (LiDAR + SODAR + plataforma + INMET + aeroportos)</td><td>' + fmt(grand.nat) + '</td><td>' + fmt(grand.hrs) + '</td><td>' + fmt(grand.pairs) + '</td><td></td><td></td></tr>';
    window.__groupTotals = totals;
    $('win-table').innerHTML = '<thead><tr><th>Grupo / instrumento</th><th>Registros nativos válidos</th><th>Horas válidas</th><th>Pares hora×altura</th><th>Dias válidos (de ' + nd + ')</th><th>% do período</th></tr></thead><tbody>' + body + '</tbody>';
    $('win-kpis').innerHTML = '<div><b>' + br(isoDay(win.s)) + ' – ' + br(isoDay(win.e)) + '</b>janela (' + nd + ' dias)</div>' +
      '<div><b>' + fmt(both) + '</b>dias com ≥ 2 sítios de perfilador válidos (P0, P1 LiDAR/SODAR, LPI)</div><div><b>' + okSt + ' de ' + nSt + '</b>estações com ≥ 80 %</div>';
  }
  // ---------------- independent JS recomputation of a candidate window (parity check with Python)
  var PU = D.prof_union;
  function computeWin(startIso, months) {
    var s = dayIdx(startIso), e = addMonths(s, months) - 1;
    var lid = I.filter(function (it) { return it.group === 'LIDAR'; }), prof = I.filter(function (it) { return D.profiler_groups.indexOf(it.group) >= 0; });
    function hsum(gs) { var t = 0; I.forEach(function (it) { if (gs.indexOf(it.group) < 0) return; for (var i = s; i <= e; i++) if (it.src[i]) t += Math.max(it.h[i], 0); }); return t; }
    var days = 0, simul = 0, pairs = 0, sites = {};
    for (var i = s; i <= e; i++) {
      var c = 0, st = {};
      lid.forEach(function (it) { if (it.h[i] >= D.valid_day_h) c++; });
      prof.forEach(function (it) { if (it.h[i] >= D.valid_day_h) { st[D.site_of[it.instrument]] = 1; sites[D.site_of[it.instrument]] = 1; } });
      if (c >= 1) days++; if (Object.keys(st).length >= 2) simul++;
    }
    lid.forEach(function (it) { for (var i = s; i <= e; i++) pairs += it.p[i]; });
    var run = 0, gap = 0; for (var h = s * 24; h < (e + 1) * 24; h++) { run = PU.charAt(h) === '1' ? 0 : run + 1; if (run > gap) gap = run; }
    var ok = 0; I.forEach(function (it) { if (it.kind !== 'station') return; var v = 0; for (var i = s; i <= e; i++) v += Math.max(it.h[i], 0); if (100 * v / (24 * (e - s + 1)) >= D.station_ok) ok++; });
    var months04 = D.periods.filter(function (p) { return dayIdx(p.start) >= s && dayIdx(p.end) <= e + 1; }).length;
    return { total_hours: hsum(D.total_groups), prof_hours: hsum(D.profiler_groups), lidar_days: days, lidar_hours: hsum(['LIDAR']), lidar_pairs: pairs,
      prof_sites: Object.keys(sites).length, simul_days: simul, meq04_months: months04,
      inmet_hours: hsum(['INMET']), aero_hours: hsum(['AERO']), stations_ge80: ok, longest_gap_h: gap, spinup_start: isoDay(s - 11),
      sodar_hours: hsum(['SODAR']), plat_hours: hsum(['PLAT']) };
  }
  window.__topWins = function (m, key) {
    var out = [];
    for (var s = dayIdx('2021-10-01'); addMonths(s, m) - 1 <= N - 1; s = addMonths(s, 1)) out.push({ start: isoDay(s), value: computeWin(isoDay(s), m)[key] });
    out.sort(function (a, b) { return b.value - a.value || (a.start < b.start ? -1 : 1); });
    return out.slice(0, 3);
  };
  window.__shownPre = function () { return Array.prototype.map.call($('win-pre').querySelectorAll('button'), function (b) { return { start: b.dataset.s, value: +b.dataset.v }; }); };
  window.__computeWin = computeWin;

  // ---------------- c · candidate windows (sortable; click a row -> selector)
  var cand = { m: 12, key: 'start', asc: true };
  function drawCand() {
    var W = D.windows.filter(function (w) { return w.months === cand.m; }), C = D.win_cols;
    W.sort(function (a, b) {
      var x = cand.key === 'start' ? a.start : a.v[cand.key], y = cand.key === 'start' ? b.start : b.v[cand.key];
      return (x < y ? -1 : x > y ? 1 : 0) * (cand.asc ? 1 : -1) || (a.start < b.start ? -1 : 1);
    });
    function th(k, lbl, g) { return '<th data-k="' + k + '" class="' + (g ? 'g ' : '') + (cand.key === k ? 'sorted' + (cand.asc ? ' asc' : '') : '') + '">' + esc(lbl) + '</th>'; }
    var h = '<thead><tr>' + th('start', 'Janela') + C.map(function (c) { return th(c[0], c[1]); }).join('') + '</tr></thead><tbody>';
    W.forEach(function (w) {
      h += '<tr data-s="' + w.start + '" class="' + (w.best_row ? 'bestrow' : '') + '"><td>' + br(w.start) + ' → ' + br(w.end) + '</td>' + C.map(function (c) {
        var v = w.v[c[0]], cls = w.best.indexOf(c[0]) >= 0 ? 'best' : '';
        return '<td class="' + cls + '">' + (c[0] === 'spinup_start' ? br(v) : fmt(v)) + '</td>';
      }).join('') + '</tr>';
    });
    $('cand').innerHTML = h + '</tbody>';
    $('cand-n').textContent = W.length + ' janelas';
    Array.prototype.forEach.call($('cand-dur').querySelectorAll('button'), function (b) { b.classList.toggle('active', +b.dataset.m === cand.m); });
    markCand();
  }
  function markCand() {
    Array.prototype.forEach.call(document.querySelectorAll('#cand tbody tr'), function (tr) { tr.classList.toggle('sel', cand.m === win.m && dayIdx(tr.dataset.s) === win.s); });
  }
  $('cand').addEventListener('click', function (ev) {
    var t = ev.target.closest('th');
    if (t) { var k = t.dataset.k; if (cand.key === k) cand.asc = !cand.asc; else { cand.key = k; cand.asc = k === 'start' || k === 'longest_gap_h'; } drawCand(); return; }
    var tr = ev.target.closest('tbody tr'); if (tr) setWin(dayIdx(tr.dataset.s), cand.m);
  });
  $('cand-dur').addEventListener('click', function (ev) { var b = ev.target.closest('button'); if (!b) return; cand.m = +b.dataset.m; drawCand(); });
  drawCand();

  // ---------------- b · rectangle of the selected window on the monthly table
  function drawHmWin() {
    var box = $('hm-win'), tb = $('hm'); if (!tb.tBodies.length) return;
    var m0 = isoDay(win.s).slice(0, 7), m1 = isoDay(win.e).slice(0, 7), j0 = D.months.indexOf(m0), j1 = D.months.indexOf(m1);
    if (j0 < 0 || j1 < 0) { box.style.display = 'none'; return; }
    var hr = tb.tHead.rows[0], c0 = hr.cells[j0 + 1], c1 = hr.cells[j1 + 1], last = tb.tBodies[0].rows[tb.tBodies[0].rows.length - 1];
    var wr = $('hm-wrap').getBoundingClientRect(), a = c0.getBoundingClientRect(), b = c1.getBoundingClientRect(), z = last.getBoundingClientRect();
    box.style.display = 'block'; box.style.left = (a.left - wr.left - 1) + 'px'; box.style.top = (a.top - wr.top) + 'px';
    box.style.width = (b.right - a.left + 2) + 'px'; box.style.height = (z.bottom - a.top + 1) + 'px';
    box.title = 'Janela ' + br(isoDay(win.s)) + ' – ' + br(isoDay(win.e));
  }
  window.addEventListener('resize', drawHmWin);

  // ---------------- b · monthly heatmap table
  (function () {
    var head = '<thead><tr><th></th>' + D.months.map(function (m, j) { var mm = m.slice(5); return '<th>' + (mm === '01' || j === 0 ? m.slice(2, 4) + '<br>' : '<br>') + mm + '</th>'; }).join('') + '</tr></thead>';
    var body = I.map(function (it) {
      return '<tr><td class="lbl">' + esc(it.label) + '</td>' + it.monthly.map(function (p, j) {
        var t = esc(it.label) + ' · ' + D.months[j] + ': ' + (p == null ? 'sem fonte' : fmt(p, 1) + ' %');
        if (p == null) return '<td title="' + t + '" style="background:' + NOSRC + '"></td>';
        if (p === 0) return '<td title="' + t + '" style="background:#fff;border:1px solid #c9c9c9"></td>';
        return '<td title="' + t + '" style="background:' + col(p) + ';color:' + (p > 55 ? '#fff' : '#1a1a1a') + '">' + (p >= 99.5 ? '' : Math.round(p)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    $('hm').innerHTML = head + '<tbody>' + body + '</tbody>';
  })();

  // ---------------- d · map
  var markers = [];
  function icon(sym) {
    var s;
    if (sym === 'P0') s = '<circle cx="9" cy="9" r="6.5" fill="#fff" stroke="#1a1a1a" stroke-width="2"/>';
    else if (sym === 'LPI') s = '<rect x="2.5" y="2.5" width="13" height="13" fill="#fff" stroke="#1a1a1a" stroke-width="2"/>';
    else if (sym === 'P1L') s = '<polygon points="9,1.5 16.5,9 9,16.5 1.5,9" fill="#fff" stroke="#1a1a1a" stroke-width="2"/>';
    else if (sym === 'SODAR') s = '<path d="M3 3 L15 15 M15 3 L3 15" stroke="#883007" stroke-width="2.4"/>';
    else if (sym === 'ANM') s = '<polygon points="9,1.5 11,7 16.5,7 12,10.5 13.8,16 9,12.7 4.2,16 6,10.5 1.5,7 7,7" fill="#fff" stroke="#883007" stroke-width="1.5"/>';
    else if (sym === 'INMET') s = '<polygon points="9,2 16,15.5 2,15.5" fill="#fff" stroke="#1a1a1a" stroke-width="1.6"/>';
    else s = '<polygon points="9,16 16,2.5 2,2.5" fill="#fff" stroke="#5c5c5c" stroke-width="1.4" stroke-dasharray="2 1.5"/>';
    return L.divIcon({ className: '', html: '<svg width="18" height="18" viewBox="0 0 18 18">' + s + '</svg>', iconSize: [18, 18], iconAnchor: [9, 9] });
  }
  function popup(it) {
    var s = it._win || stats(it);
    return '<b>' + esc(it.label) + '</b><br>' + esc(it.status) + '<br>Período válido: ' + (it.first_valid ? br(it.first_valid) + ' → ' + br(it.last_valid) : 'sem dados') +
      (it.record_first_valid_any_date && it.record_first_valid_any_date < '2021-10-01' ? '<br>Registro completo desde ' + br(it.record_first_valid_any_date) : '') + '<br>Altura: ' + esc(it.reference_height) + '<br>Janela ' + br(isoDay(win.s)) + '–' + br(isoDay(win.e)) + ': <b>' + fmt(s.pct, 1) + ' %</b> das horas, ' + fmt(s.vd) + ' dias válidos';
  }
  function updatePopups() { markers.forEach(function (m) { m.mk.setPopupContent(popup(m.it)); }); }
  (function () {
    if (!window.L) { $('map').innerHTML = 'Biblioteca de mapas indisponível.'; return; }
    var map = L.map('map', { crs: L.CRS.EPSG4326, zoomSnap: 0.25, zoomAnimation: false, attributionControl: false, minZoom: 2, maxZoom: 11 });
    map.fitBounds([[-9.5, -50], [3.5, -33]]);
    map.createPane('land'); map.getPane('land').style.zIndex = 250;
    map.createPane('lines'); map.getPane('lines').style.zIndex = 450; map.getPane('lines').style.pointerEvents = 'none';
    var g = D.geography && D.geography.layers;
    if (g) {
      if (g.land) L.geoJSON(g.land, { pane: 'land', interactive: false, style: { stroke: false, fillColor: '#ececec', fillOpacity: 1 } }).addTo(map);
      if (g.states) L.geoJSON(g.states, { pane: 'lines', interactive: false, style: { color: '#7a7a7a', weight: 0.6, dashArray: '3 2' } }).addTo(map);
      if (g.countries) L.geoJSON(g.countries, { pane: 'lines', interactive: false, style: { color: '#4a4a4a', weight: 0.9 } }).addTo(map);
      if (g.coastline) L.geoJSON(g.coastline, { pane: 'lines', interactive: false, style: { color: '#1a1a1a', weight: 0.9 } }).addTo(map);
    }
    for (var lon = -64; lon <= -24; lon += 2) L.polyline([[-16, lon], [16, lon]], { pane: 'lines', color: '#b5b5b5', weight: 0.4, interactive: false }).addTo(map);
    for (var lat = -16; lat <= 16; lat += 2) L.polyline([[lat, -64], [lat, -24]], { pane: 'lines', color: '#b5b5b5', weight: 0.4, interactive: false }).addTo(map);
    L.control.scale({ imperial: false, position: 'bottomright' }).addTo(map);
    if (D.mesh) {
      var e = D.mesh.extent; $('mesh-name').textContent = D.mesh.name;
      L.rectangle([[e[1], e[0]], [e[3], e[2]]], { color: '#1a1a1a', weight: 1, dashArray: '5 4', fill: false }).bindTooltip('Malha da EXP03: ' + D.mesh.name, { sticky: true }).addTo(map);
    }
    I.forEach(function (it) {
      if (it.lat == null) return;
      var mk = L.marker([it.lat, it.lon], { icon: icon(it.symbol), title: it.label }).bindTooltip(it.label, { direction: 'top', offset: [0, -8] }).bindPopup(popup(it));
      mk.addTo(map); markers.push({ mk: mk, it: it });
    });
    $('map-legend').innerHTML = [['P0', 'P0 — LiDAR flutuante'], ['P1L', 'P1 — LiDAR (EOSOLAR)'], ['SODAR', 'P1 — SODAR (não usado na seleção MEQ-03; incluído na validação final)'], ['LPI', 'LPI — LiDAR fixo'], ['ANM', 'ANM-1/PPE1A — plataforma offshore (anemômetro)'], ['INMET', 'Estação automática INMET (10 m)'], ['SYNOP', 'Aeroporto/sinótica (suplementar)']]
      .map(function (p) { return '<span>' + icon(p[0]).options.html + ' ' + p[1] + '</span>'; }).join('') + '<span><svg width="22" height="10"><line x1="0" y1="5" x2="22" y2="5" stroke="#1a1a1a" stroke-dasharray="5 4"/></svg> malha EXP03</span>';
  })();

  // ---------------- e · footer
  $('foot').innerHTML = '<p><b>Critério de QC</b> (o mesmo das validações da MEQ-04, <code>src/mpas_meqbr/obs.py</code>): ' +
    I.filter(function (it, k) { return k <= 5; }).map(function (it) { return esc(it.label) + ' — ' + esc(it.qc); }).join('; ') +
    '. Hora válida: média horária centrada com ≥ 4 de 6 amostras de 10 min (perfiladores); média dos relatos na hora (estações); registro horário (plataforma). Lacunas: ≥ 3 h (perfiladores) e ≥ 24 h (estações), contadas entre o primeiro e o último dado válido.</p>' +
    '<p><b>Fontes</b>: ' + I.map(function (it) { return esc(it.label) + ': <code>' + esc(it.source) + '</code>'; }).join(' · ') +
    '. As estações ISD têm arquivos de 2021 a 2025 (2023 baixado em 18/11/2026 e 2024–2025 em 19/11/2026, com autorização do responsável; proveniência em <code>results/obs_availability/isd_*_download.json</code>). Em 2025 não há arquivo para FORTALEZA, APODI e SOBRAL (INMET), que aparecem como "sem fonte". SODAR P1: não usado na seleção MEQ-03 (DEC-MEQ-003); incluído na validação final (decisão do responsável, 19/11/2026); altura de referência 100 m (nível exato do SODAR). ANM-1/PPE1A (plataforma offshore, qualificada por avaliação independente segundo o responsável, 19/11/2026): registro horário, sem ≥ 4/6; vale hora com FLG_BRT_WSPD = 1, FLG_OP_WSPD = 0 e 0–40 m/s; o código FLG_CONSIST (4 dígitos, sem documentação) não é usado; altura e fuso não informados no arquivo; horário tratado como UTC.</p>' +
    '<p>Gerado por <code>scripts/06_report/build_obs_availability.py</code> · commit <code>' + esc(D.sha) + '</code> · ' + esc(D.generated) + ' · MEQ-06.2 / MEQ-06.4. Tabelas: <code>results/obs_availability/*.csv</code>.</p>';

  setWin(win.s);
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
