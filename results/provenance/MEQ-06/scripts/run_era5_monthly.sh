#!/usr/bin/env bash
# CDS key: line 16 of /p1-swell/danilocs/cds-keys (instructed 2026-11-21); env only, ~/.cdsapirc untouched.
set +u; source $(conda info --base)/etc/profile.d/conda.sh; conda activate cgfd-usp-mpas
export CDSAPI_URL=$(sed -n 's/^url: *//p' ~/.cdsapirc)
export CDSAPI_KEY=$(sed -n 16p /p1-swell/danilocs/cds-keys | awk -F' - ' '{gsub(/[[:space:]]/,"",$1); print $1}')
cd /p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a/meq06_production
exec python era5_block1_monthly.py
