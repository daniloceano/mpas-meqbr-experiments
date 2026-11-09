---
name: technical-report-dashboard
description: How to modify, extend or rebuild the MPAS MEQ-Br technical report (results/report/index.html, layout v2). Use whenever a task touches the HTML report, its charts, maps, colours, chapters, the builder scripts/06_report/build_technical_report.py, or docs/templates/technical_report_v2.html.j2 / report_v2/*. Keeps the approved aesthetic and narrative logic identical.
---

# Technical report dashboard (layout v2)

The report layout, aesthetic and logic were approved by the PI (2026-11-09).
Any change must preserve them. Read this whole file before editing.

## Files

| Role | Path |
|---|---|
| Page skeleton + narrative text (Jinja) | `docs/templates/technical_report_v2.html.j2` |
| Styles (inlined at build) | `docs/templates/report_v2/report.css` |
| All client rendering (inlined at build) | `docs/templates/report_v2/report.js` |
| Vendored libs (copied to `assets/vendor/`) | `docs/templates/vendor/` — Plotly **basic** 2.35.2, Leaflet 1.9.4 |
| Payload builder | `build_v2_payload()` in `scripts/06_report/build_technical_report.py` |
| Colour maps (Crameri, embedded LUTs) | `src/mpas_meqbr/sci_colormaps.py` |
| Experiment colours, cmap constants, mpl style | `src/mpas_meqbr/plotting.py` |
| Point series export (run on Swell) | `scripts/02_validation/export_point_series.py` → `results/interactive/series/*.js` |
| Coastline/states/land | `scripts/06_report/export_report_geography.py` → `results/interactive/geo/geography.json` |
| Checks | `scripts/06_report/validate_technical_report.py` |
| Legacy layout (do not extend) | `technical_report.html.j2`, `--layout v1` |

## Narrative logic (fixed order, section ids are validated)

Linear story, one question per chapter, one primary interactive view per
chapter, detail one click away (drawer, row click, point click). Section ids
must stay: `introducao, resultados-modelo, rede-observacional, validacao,
valor-adicionado, mecanismos, sintese`.

1. Experiments & meshes — clickable cumulative-design tree; show **distinct
   meshes only** (3), never one figure per experiment; windows + cost charts.
2. Simulated fields — tabs separate **static** fields (Leaflet, EPSG:4326,
   A|B swipe on a shared scale), derived diagnostics, and **animations**
   (two synchronised videos).
3. Observation network — map (land, coastline, state lines, graticule,
   optional mesh domains); click point → paired hourly series, diurnal cycle
   (local = UTC−3, paired hours only), distribution, metrics table.
4. Validation — scorecard (unit × source, colour **relative to the row**,
   best value outlined, non-significant skill hatched), CI chart + pairwise
   ΔMSE matrix for the selected row, LiDAR profiles, per-network summary.
   LiDAR and INMET are never pooled. P0/250 m is descriptive only. ERA5 only
   at 100 m (LiDAR) / 10 m (INMET); elsewhere "Não avaliado nesta altura".
5. Added value — Murphy skill with CIs (filled = detectable, open = not).
6. Physics — blocks *hypothesis → evidence chart → verdict*.
7. Synthesis — criteria × experiment matrix, **no weights or composite
   score**; every criterion traceable to one CSV (`_decision_matrix`).
   Conclusion never ratifies a configuration beyond what the tests support.

## Aesthetic (journal figure, Scientific Reports-like)

- White page, Arial/Helvetica, ink `#1a1a1a`, hairline rules `#d4d4d4`;
  no shadows, no rounded corners, no coloured cards. Colour is for data only.
- Plotly: use the `layout()`/`axis()`/`plot()` helpers in `report.js`
  (outside ticks, 0.8 px axis lines, no grid, no zero line unless meaningful,
  horizontal legend, SVG export). Panel letters **a, b, c** in captions.
- Every chart has a caption stating what, units, and how to read it.
- Colour maps: Crameri only — `batlow` speed, `lipari` WPD, `devon_r`
  constancy, `lajolla` amplitude, `roma_r` temperature, `vik` differences /
  skill / relative-to-row scales (blue = better). Reference:
  https://dominicroye.github.io/color-for-geoscience/ .
- Experiment identity is fixed everywhere (`plotting.EXPERIMENT_COLORS`):
  CTL grey, EXP01–03 cool (roma blues, batlow green), EXP04–06 warm (roma
  reds/ochres), ERA5 grey dashed, observation black and thickest.

## Rules

- **All non-map charts are interactive** (Plotly from embedded JSON). Only
  field/mesh maps stay PNG. If a chart needs data, export a table upstream;
  never add a static PNG chart.
- Plotly basic has no heatmap/polar: tables with coloured cells are the
  heatmap idiom; skip Taylor/polar charts.
- Offline/portable: no CDN or http references (validator fails). Data loaded
  lazily must be `.js` files registering on `window.*` (works on `file://`).
- The builder reads only consolidated tables/media; never raw MPAS history.
  Superseded `_BADSST` runs are filtered with `drop_superseded`.
- New data → add to `V2_TABLES` (or payload) → render in `report.js` inside
  the chapter's `init*` function, wrapped by `safe()`.
- Keep JS ES5-compatible style already used (no build step); `node --check`.
- Keep text in Portuguese; numbers formatted pt-BR via `fmt()`.

## Build and verify

```bash
# on Swell (holds figures/ and site_timeseries caches)
python scripts/02_validation/export_point_series.py      # if series changed
python scripts/05_exploration/export_interactive_layers.py  # if palettes/fields changed
python scripts/06_report/plot_report_context.py
python scripts/06_report/build_technical_report.py
python scripts/06_report/validate_technical_report.py --report-dir results/report
```

Then sync per `docs/sync_workflow.md`. Visual check: headless Chrome
screenshot of `results/report/index.html`; confirm no console errors and
phone width (≤390 px) without horizontal scroll. Update `docs/reporting.md`
and this skill when chapters or conventions change.
