#!/usr/bin/env bash
# MEQ-06.5 — OISST v2.1 download + coastal-safe conversion for block 1,
# written only under the production dir.
set -uo pipefail
set +u; source "$(conda info --base)/etc/profile.d/conda.sh"; conda activate cgfd-usp-mpas; set -u
P=/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production
U=/p1-swell/danilocs/MPAS-Research/usp-utils/pre_proc/real_data
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha256sum "$U/oisst_to_intermediate.py" "$U/oisst_land_fill.py" "$U/download_oisst.py" > "$P/records/oisst_converter_sha256.txt"
echo "[$(ts)] START download"; t0=$(date +%s)
python "$U/download_oisst.py" --start 2021-10-21 --end 2023-07-01 --outdir "$P/met_data/oisst"
echo "[$(ts)] END download rc=$? $(( $(date +%s)-t0 ))s"
echo "[$(ts)] START convert"; t0=$(date +%s)
python "$U/oisst_to_intermediate.py" --indir "$P/met_data/oisst" --start 2021-10-21 --end 2023-07-01 --outdir "$P/oisst_corrected"
echo "[$(ts)] END convert rc=$? $(( $(date +%s)-t0 ))s"
