# Technical report

The report is a generated, portable summary of the experiment analysis. Its
source is version controlled; the rendered bundle is regenerable and must never
be edited by hand.

## Build

```bash
python scripts/03_selection/compute_runtime_metrics.py
python scripts/02_validation/export_point_series.py   # on Swell: needs results/site_timeseries
python scripts/06_report/plot_report_context.py
python scripts/06_report/export_report_geography.py   # Natural Earth via the cartopy cache
python scripts/06_report/build_technical_report.py    # --layout v1 for the legacy panels
python scripts/06_report/validate_technical_report.py
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

## Narrative order (layout v2)

A linear sequence of seven chapters with a fixed chapter rail and
previous/next links. Each chapter answers one question with one primary
interactive view; detail is one click away.

1. **Experiments and meshes** — clickable cumulative-design tree, the three
   distinct meshes (not one per experiment), integration windows and cost.
2. **Simulated fields** — separate tabs for static mean fields (Leaflet map,
   EPSG:4326, coastline and state boundaries, A|B swipe comparison on a shared
   colour scale with ERA5 selectable, and an in-browser A − B difference mode),
   vertical cross-sections (15 h local composites), and synchronised side-by-side
   animations.
3. **Observation network** — map of LiDARs and INMET stations; clicking a point
   loads its paired hourly series (observation, ERA5, seven experiments), the
   mean diurnal cycle, the speed distribution and its metrics.
4. **Validation** — scorecard (unit × source, colour relative to the row,
   metric switch), confidence-interval chart and pairwise-test matrix for the
   selected unit, LiDAR vertical profiles, and per-network summary.
5. **Added value vs ERA5** — Murphy skill with CIs (LiDAR and INMET), month
   representativeness and domain resource difference (MPAS × ERA5 maps live in
   chapter 2's field viewer).
6. **Physical coherence** — hypothesis → evidence → verdict blocks (SST chain,
   boundary influence, EXP04–06 contrast matrix, EXP06 skin SST, cell sensitivity).
7. **Synthesis** — criteria × experiment matrix without weights, pairwise
   win/loss balance, error × cost, conclusion and open limitations.

Charts are drawn in the browser from embedded JSON (Plotly basic bundle);
only maps of fields and meshes remain pre-rendered PNG. Styling follows a
journal-figure convention (white, Arial, hairline axes). Colour maps are
Crameri's scientific colour maps (batlow, lipari, devon, lajolla, roma, vik),
embedded in `src/mpas_meqbr/sci_colormaps.py`; experiments keep one fixed
colour everywhere (`plotting.EXPERIMENT_COLORS`).

### Offline runtime

`index.html` inlines `docs/templates/report_v2/report.{css,js}`. Plotly and
Leaflet are vendored in `docs/templates/vendor/` and copied to
`assets/vendor/`. Point series are small `.js` files under `assets/series/`,
loaded on demand with `<script>` so the page works from `file://`.

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
