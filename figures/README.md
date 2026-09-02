# figures/

All figures are **regenerated, never edited** — nothing here is version
controlled except this file. Every figure carries a footer naming the script
that produced it, the averaging window, and the processing choices that matter,
so one found loose in a slide deck can still be traced back.

Naming is `<what>_<period>_<site or experiment>[_<height>].png`.

## validation/ — how good is each run at the LiDAR sites

| File | Shows |
|---|---|
| `timeseries_<period>_<site>_<h>m.png` | model, ERA5 and LiDAR through the window |
| `scatter_<period>_<site>_<h>m.png` | joint distribution, density-coloured, with scores |
| `diurnal_<period>_<site>.png` | mean daily cycle in local time, three heights |
| `profile_<period>_<site>.png` | mean profile, bias by height, shear exponent |
| `taylor_<period>_<site>.png` | correlation / variance / centred RMSE together |
| `distribution_<period>_<site>_<h>m.png` | histogram + fitted Weibull |
| `windrose_<period>_<site>_<h>m.png` | 16-sector rose, observed vs each experiment |
| `cell_sensitivity.png` | the same scores on the five nearest cells — the representativeness floor |
| `stations_diurnal.png` | coastal diurnal cycle at the public 10 m stations |
| `stations_map.png` | station bias in space; marker shape = station type |

## selection/ — the decision, and whether it is trustworthy

| File | Shows |
|---|---|
| `sst_forcing_*.png` | **look here first** — the SST each run actually saw, and the OISST land-fill contamination in `EXP01`/`EXP02` |
| `ranking*.png` | RMSE per experiment and height, with bootstrap intervals |
| `attribution_*.png` | SST → surface fluxes → PBL depth → wind at the site |
| `boundary_influence_*.png` | is `EXP02 − EXP01` organised by distance from the relaxation zone |

## era5/ — is this better than the reanalysis it came from

| File | Shows |
|---|---|
| `added_value*.png` | Murphy skill score vs ERA5 at 100 m, with intervals |
| `climatological_context.png` | how typical the simulated months were, 1990-2020 |
| `resource_comparison_*.png` | ERA5, MPAS at ERA5's grid, their difference, and the month's anomaly |

## exploration/ — what the model is actually doing

| File | Shows |
|---|---|
| `mean_fields_<exp>_<period>.png` | mean speed, wind power density, directional constancy, diurnal amplitude, on the native mesh |
| `diff_<B>_vs_<A>_<period>[_common].png` | experiment differences on a common lattice; `_common` = averaged over the window all experiments share |
| `xsection_<site>_<exp>_<period>_composite_<HH>local.png` | coast-normal vertical section at a fixed local hour — the sea-breeze cell |

## animations/

`wind<height>_<exp>_<period>_<start>_<n>d.mp4` — the 100 m wind field with
vectors, one frame per hour. Falls back to GIF if no ffmpeg is found; set
`ffmpeg:` in `config/paths.local.yaml` to choose one.
