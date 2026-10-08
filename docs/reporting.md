# Technical report

The report is a generated, portable summary of the experiment analysis. Its
source is version controlled; the rendered bundle is regenerable and must never
be edited by hand.

## Build

```bash
python scripts/03_selection/compute_runtime_metrics.py
python scripts/06_report/plot_report_context.py
python scripts/06_report/build_technical_report.py
```

Output:

```text
results/report/
  index.html
  report_manifest.json
  assets/
```

The context-figure stage reads mesh/static files and cached means. The builder
then reads only consolidated CSV tables and generated media. Neither stage opens
raw MPAS history, so rebuilding the HTML is safe while a simulation runs.

## Narrative order

The report is organized for a reader who did not work on the project:

1. purpose, common configuration and cumulative experimental design;
2. integration status and normalized computational cost;
3. spatial fields followed by local/point behavior;
4. observational network, data treatment and validation;
5. value added relative to ERA5;
6. physical attribution, limitations and next decisions.

Media are explicitly curated rather than copied by wildcard. Every displayed
table and figure has a plain-language caption, metric definitions and units.

## Evidence model

The report carries two primary validation axes:

1. offshore hub-height wind from P0/LPI LiDAR;
2. coastal surface wind from automatic INMET stations at 10 m.

These axes are not pooled. Airport/synoptic stations may be generated with
`validate_surface_stations.py --include-supplementary`, but they remain an
exposure-sensitivity appendix.

## Provisional snapshots

If any row in `experiment_inventory.csv` is below 100% completeness, the
report displays a prominent provisional banner. This allows layout and
interpretation to be reviewed while a run continues without making a final
selection claim.

## Portability and provenance

Figures and animations are copied into the bundle with relative links.
`report_manifest.json` records the analysis commit, dirty-worktree flag,
generation time, input tables, source media and byte sizes. Copy the whole
`results/report/` directory when sharing; `index.html` alone is not enough.
