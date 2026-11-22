# MEQ-06.5 / MEQ-06.6 — provenance records

Small text records copied from Swell (`runs/meqbr_05km_oval_meq02a/meq06_production/` and
`meq06_restart_test/`). No NetCDF is versioned; large files stay on Swell.

## MEQ-06.5 — block 1 preprocessing (2021-10-21 → 2023-07-01)
- Model: MPAS-Research `6754c6f4`; executable SHA256 `ab5e4113…`; init_atmosphere configuration of EXP03 (`run_preproc_2022.sh`, 60 ranks, `part.60`), via `scripts/preproc_prod.sh` (namelist/streams emitters copied verbatim).
- Partition for production: `graph.info.part.90`, MD5 `c7f544ee01f011b95927463c1ac9359c` (`partition_md5.txt`).
- OISST v2.1 + coastal land fill: `oisst_converter_sha256.txt`; 619 daily SST intermediates (7.2 GB, not in the 455 GB estimate).
- `sfc_update` block 1: 619 records, 510 070 700 B, MD5 `c65e410fdb20846307e1037f0f403a62`, case 8 in 150 s (`preproc_sfc_block1.log`).
- SST gate (`sst_gate_block1.log`): **PASS** — 0 ocean cells at 273.15 K in all 619 records (ocean 298.00–304.09 K) and in `init.nc` (297.72–304.98 K).
- `init.nc` 2021-10-21: MD5 `f0270edd…`; differs from the EXP03 file (`5654ac21…`) only in global attributes `config_stop_time`, `file_id`, `parent_id` (132/132 variables bit-identical); the new file is used. Same for the first LBC.
- ERA5: month-batched sequential CDS requests (`scripts/era5_block1_monthly.py`, `era5_monthly_requests.json`), split per time with `grib_copy`, unchanged `era5_to_intermediate.py`; intermediates verified MD5-identical to the shared EXP03 ones at 2021-10-21_00, 10-25_12, 10-31_18. CDS key was switched to another account key from the project key list (key value never recorded).
- LBC: monthly, incremental, `manifests/lbc_manifest_AAAA-MM.txt` (window up to 00 UTC of day 1 of next month, inclusive; status PRONTO/FALHA). All months use the 2021-10-21 `init.nc`.

## MEQ-06.6 — restart test (90 processes, P90C)
- `restart_test/`: C = 2 days continuous; R1 = day 1; R2 = restart from `restart.2021-10-22_00` + day 2. Namelist diffs only in start/duration/do_restart.
- Result (`restart_comparison.txt`): **IDENTICAL bit for bit** — 49 hourly histories × 34 variables, restart at 2021-10-23 00 × 296 variables. (R2 writes no history at the restart instant; hour 10-22 00 is compared via R1.)
- Wall: C 7874 s (48 h → ~21.9 simulated days per machine-day); R1 3806 s + R2 4115 s.

## Limits
- SST gate used `sst_gate_files.py`, a wrapper applying the `check_sst_forcing.py` criterion to all records of the raw forcing files (the stock script expects experiment legs).
- ERA5 batched by month (not per time as in EXP03); identity verified on 3 sampled timestamps.
