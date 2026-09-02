# Scientific notes — MeqBr ~5 km MPAS experiment set

Living scientific record of the analysis. Written to be audited: every number
below is reproduced by a named script into a named table, and the reasoning
behind each methodological choice is stated rather than implied.

Status of the underlying simulations: `docs/run_status.md` (regenerated, not
edited by hand). Method detail: `docs/validation_protocol.md`.

---

## Research Questions

1. **Which of the three configurations (`CTL`, `EXP01`, `EXP02`) should carry the
   climatological runs?** Specifically: does the daily SST update (`EXP01`) or
   the buffered-mesh boundary treatment (`EXP02`) improve near-surface and
   hub-height wind (50-250 m) at the two offshore LiDAR sites, by enough to
   justify its cost, and consistently across two independent site-periods?

2. **Does the 5 km MPAS hindcast add skill over the ERA5 reanalysis that drives
   it?** ERA5 supplies the initial and lateral boundary conditions, so any skill
   beyond ERA5's is attributable to the regional integration. This is the
   precondition for proposing the runs as an ERA5 alternative for wind resource
   assessment on the Brazilian equatorial margin.

3. **Where, spatially, does the extra resolution matter?** Which features of the
   100 m wind field — coastal sea-breeze band, capes and headlands, terrain-
   driven jets — exist at 5 km and are absent at 31 km?

4. **How far can a one-month evaluation be extrapolated to a multi-year run?**
   How typical were November 2021 and October 2022 relative to the 1990-2020
   ERA5 distribution of the same calendar months?

---

## Physical / Statistical Framework

### The circulation being evaluated

The Brazilian equatorial margin is dominated by the southeast trade wind,
modulated by a strong diurnal sea-breeze/land-breeze cycle at the coast. For
offshore wind assessment, three properties matter and can fail independently:

- the **mean speed** at hub height, which sets the resource;
- the **distribution**, because energy is an integral of the speed histogram
  against a power curve, and wind power density goes as `U³` — a −10 % speed bias
  is roughly a −27 % energy bias;
- the **diurnal phase and amplitude**, which set when the resource is available,
  and which are governed by the land-sea thermal contrast and boundary-layer
  mixing.

### Verification statistics

Model-observation agreement is summarised with bias, MAE, RMSE, centred RMSE,
Pearson R, the standard-deviation ratio, Willmott's index of agreement, and the
Takacs (1985) decomposition

$$\mathrm{MSE} = \mathrm{bias}^2 + (\sigma_m - \sigma_o)^2 + 2\sigma_m\sigma_o(1-r)$$

whose three terms are the systematic offset, the **amplitude (dissipative)**
error, and the **phase (dispersive)** error. The identity is exact and is
checked numerically. The split is used because it says *how* a run is wrong:
here it turns out that essentially all the random error is dispersive.

### Wind-resource statistics

Weibull scale `A` and shape `k` by maximum likelihood with the location fixed at
zero (a free lower bound fits better numerically but implies a physically
meaningless minimum wind speed), and wind power density

$$\mathrm{WPD} = \tfrac{1}{2}\rho\,\overline{U^3}, \qquad \rho = 1.15\ \mathrm{kg\,m^{-3}}$$

with the cube accumulated **before** averaging.

### Inference

Hourly wind errors are strongly autocorrelated, so the effective sample is far
smaller than the number of hours. All intervals are **moving-block bootstraps**
with 24-hour blocks (2000 resamples). Experiments are compared through the
**paired difference of squared errors** on identical hours — a bootstrap
analogue of the Diebold-Mariano test — which cancels the shared synoptic
variability and is much more sensitive than comparing two RMSE values.

Added value over ERA5 is the Murphy skill score `SS = 1 − MSE_model/MSE_ERA5`,
read directly as the fraction of ERA5's mean-square error the downscaling
removes.

---

## Datasets and Variables

### Model

Three MPAS-Atmosphere regional experiments, hourly history output, over two
41-day integrations each (10-day spin-up discarded). Full configuration is in
the simulation repository (`runs/meqbr_05km/README.md` and `EXPERIMENTS.md`);
`config/experiments.yaml` mirrors what the analysis needs.

| | `CTL` | `EXP01` | `EXP02` |
|---|---|---|---|
| Mesh | `meqbr_05km`, 76 813 cells, ~4.6 km | same | `meqbr_05km_buf`, 95 138 cells, 5 → 32 km ramp |
| SST | ERA5 skin temperature of the initial instant, **frozen** for 41 days | NOAA OISST v2.1, **daily update** | daily update (inherited) |
| Lateral boundary | relaxation zone 189-227 km from the sites | same | 596-632 km from the sites; ERA5 re-downloaded over a wider box |
| Relative cost | 1.00 | 1.00 | 1.24 |
| Status | complete | complete | **2021 leg ~51 % of the analysis window; 2022 leg not started** |

The design is **cumulative, not factorial**: `EXP02 = EXP01 + boundary
treatment`. `EXP02 − EXP01` is therefore the *incremental* effect of the boundary
treatment given the SST update is already on, not the effect of the buffer alone.

Vertical: 55 layers, interfaces specified in height **above terrain**, so layer
centres sit at 12.5, 50, 100, 150, 200, 250 m AGL everywhere (verified: spread
across cells at the 100 m centre is 0.4 m).

Variables used: `uReconstructZonal/Meridional`, `theta`, `pressure`, `relhum`,
`w`, `u10/v10`, `t2m`, `hpbl`, `hfx`, `lh`, `ust`, `znt`, `zol`, `sst`,
`skintemp`, `landmask`, `zgrid`.

### In-situ observations (primary evidence)

| | **P0** | **LPI** |
|---|---|---|
| Instrument | floating LiDAR | fixed LiDAR (Porto-Ilha terminal) |
| Position | 2.694 °S, 42.555 °W | 4.879 °S, 37.148 °W |
| Coverage | 2021-11-09 → 2021-12-13 | 2022-06-23 → 2025-06-06 |
| Overlaps | `2021` window only | `2022` window only |
| Heights used | 50, 100, 150, 200, (240+260)/2 m | 50, 100, 150, 200 m |
| Native resolution | 10 min | 10 min |
| QC | per-height availability flag, ≥ 80 % | physical range only (no flag exists) |
| Distance to nearest model ocean cell | 2.5 km (`meqbr_05km`), 1.1 km (`_buf`) | 1.8 km |

### Public surface stations (secondary evidence)

Eight stations from the NOAA NCEI Integrated Surface Database, which is where the
Brazilian INMET automatic network and airport reports are internationally
archived — INMET's own API is unreachable from the analysis host. 10 m wind, land
sites, 7-24 reports per day depending on the station. Provenance and per-station
coverage: `data/metadata/isd_download.json`,
`results/tables/isd_station_coverage.csv`.

### ERA5

- **Simulation periods** (downloaded here): hourly 10 m and 100 m wind,
  0.25°, box 5/−52/−10/−32, covering both full integration windows. This is the
  reanalysis that forced the runs.
- **Climatology** (existing archive, `/p1-sto-swell/danilocs/ERA5_surface_wind_data_Brazil`):
  the same variables, 1990-2020, monthly files. It does **not** cover 2021 or
  2022, which is why the period files had to be downloaded.

---

## Methodology

Full detail and the reasoning behind each choice: `docs/validation_protocol.md`.
In brief:

1. **Extraction.** Model series at the five nearest **ocean** cells to each site
   (cell 0 used by default; the rest support the representativeness check), full
   vertical profiles plus surface/boundary-layer diagnostics. One pass over the
   history files, cached to NetCDF.
2. **Pairing.** The 10-minute LiDAR record is averaged into the hour centred on
   each model timestamp (≥ 4 of 6 samples). Layer centres are matched to LiDAR
   channels within 1 m, asserted rather than assumed.
3. **Common window.** Every inter-experiment comparison uses the hours all the
   compared experiments have. Because `EXP02` is still integrating, the pipeline
   also produces a `_fullwindow` set restricted to `CTL` and `EXP01`, which has
   far more statistical power.
4. **Scoring.** Point verification + wind-resource + diurnal groups, per
   experiment, site and height.
5. **Ranking.** Paired block-bootstrap tests between every experiment pair, at
   every site-period and height, plus a cost column.
6. **Mechanism checks.** The SST field each run actually saw, and the chain
   SST → surface heat fluxes → PBL depth → wind.
7. **ERA5 comparison.** Skill score at the sites; MPAS regridded down to ERA5's
   own 0.25° grid for the map comparison, so the difference is not a regridding
   artefact.

---

## Assumptions

- **A LiDAR point represents a ~20 km² model cell.** Irreducible. Quantified by
  recomputing every score on the five nearest ocean cells
  (`results/tables/cell_sensitivity.csv`) — see the caveat below, where it turns
  out to matter a great deal at LPI and hardly at all at P0.
- **The 250 m model level at P0 is represented by the mean of the 240 m and
  260 m LiDAR channels**, i.e. the profile is near-linear over that 20 m. Not
  separately validated; the channels bracket the target symmetrically.
- **Hourly averaging of the LiDAR is the right scale match.** An alternative
  (nearest 10-minute sample) was rejected because it compares a point
  measurement to a cell-average; the choice was not swept for sensitivity.
- **ρ = 1.15 kg m⁻³** for wind power density at both sites, rather than the
  model's own density. At these temperatures the error is ≲ 2 %, and using a
  fixed value keeps observed and modelled WPD comparable.
- **ERA5's site bias is stationary between 1990-2020 and 2021/2022.** Required
  for the representativeness percentiles, which are ERA5-against-ERA5. ERA5 is
  1.9 m/s slow at P0 relative to the LiDAR, most plausibly because the site falls
  within a coastal 0.25° cell; a land-fraction bias of that kind should not vary
  year to year, but this is an assumption, not a result.
- **The nearest ocean cell, not a spatial average, represents each site.**
- **24 hours is an adequate bootstrap block.** Long enough for the diurnal cycle
  and most synoptic persistence; not tuned.

---

## Results and Interpretation

### 2026-09-02 — First full pass over `CTL`, `EXP01` and the partial `EXP02`

#### 1. The SST forcing in `EXP01` and `EXP02` is contaminated at the coast — **[the decisive finding]**

`scripts/03_selection/check_sst_forcing.py`, `results/tables/sst_forcing_check.csv`,
`figures/selection/sst_forcing_2021.png`.

The `sfc_update.nc` produced by `init_atmosphere` case 8 from NOAA OISST carries
the OISST **land fill value, 273.15 K, into coastal ocean cells**:

| | `CTL` (ERA5 skin, frozen) | `EXP01` | `EXP02` |
|---|---|---|---|
| Ocean cells at exactly 273.15 K | 0 | **1 226** | **1 384** |
| Ocean cells below 296 K | 0 (2021) | 2 894 (2021), 2 965 (2022) | 3 120 (2021) |
| Median distance of those cells to land | — | 5 km | 5 km |
| Maximum distance | — | 26 km | 26 km |
| SST at **P0** | 300.2 K | **291.5 K** | **293.8 K** |
| SST at **LPI** | 300.5 K | **295.2-296.0 K** | **295.4 K** |

Far offshore (> 300 km from land) the OISST−ERA5skin difference is a sensible
+0.26 K, so the OISST field itself is fine; the failure is confined to the first
few cells from the coastline and has the geometry of an interpolation artefact,
not of upwelling — genuine coastal upwelling on this margin has a scale of tens
to hundreds of kilometres and does not reach 0 °C.

The diagnosis is tighter than "EXP01 has a bad SST field", and the table records
why: **`CTL` carries exactly the same contaminated `sfc_update.nc`** — 1226
ocean cells at the land fill, the same file, since the preprocessing is shared —
it simply never reads it, because `config_sst_update = false`. The three
experiments differ in whether the switch is on, not in the file. So the fix is
in the `init_atmosphere` case-8 interpolation, once, and it repairs every
experiment that uses it.

**Both LiDAR sites sit inside the contaminated strip.** The consequences at P0
are exactly what an 8.7 K cold sea would produce
(`results/tables/attribution_summary.csv`):

| At P0, 2021 | `CTL` | `EXP01` | `EXP02` |
|---|---|---|---|
| mean SST | 300.2 K | 291.6 K | 293.9 K |
| sensible heat flux | +1.1 W m⁻² | **−12.6** | **−10.5** |
| latent heat flux | +84.6 W m⁻² | **−24.3** | **−21.6** |
| PBL height | 488 m | **70 m** | **45 m** |
| friction velocity | 0.24 m s⁻¹ | 0.09 | 0.12 |

Negative sensible *and* latent heat flux over a tropical ocean is not a physical
state; it is the model responding correctly to an unphysical lower boundary. The
boundary layer collapses to 45-70 m — below the hub heights being evaluated.

**What this means for the ranking.** `EXP01 − CTL` and `EXP02 − EXP01` at these
two sites are not tests of the SST-update or boundary-treatment hypotheses. They
are dominated by an interpolation error in the surface forcing. The hypotheses
remain untested and the runs must be repeated with a corrected `sfc_update.nc`
before the experiment set can decide anything.

The check is a hard gate: `check_sst_forcing.py` exits non-zero when land-fill
cells are present, so this cannot be forgotten in a later re-run.

#### 2. Given that, `CTL` is the only defensible choice today

`results/tables/pairwise_tests_fullwindow.csv`,
`figures/selection/ranking_fullwindow.png`. Paired block bootstrap, both
experiments complete, over each site-period's full window (N = 507 h at P0,
740 h at LPI):

| Height | P0 / Nov 2021 | LPI / Oct 2022 |
|---|---|---|
| 50 m | **CTL better** (ΔMSE −2.15 [−3.06, −1.14]) | **CTL better** (−4.15 [−5.02, −3.17]) |
| 100 m | not distinguishable (−0.34 [−0.94, +0.35]) | **CTL better** (−1.23 [−1.83, −0.60]) |
| 150 m | not distinguishable (+0.48 [−0.06, +1.15]) | not distinguishable |
| 200 m | **EXP01 better** (+0.99 [+0.44, +1.67]) | not distinguishable |

The **height dependence is the mechanism showing through**: `EXP01`'s cold
coastal sea stabilises the surface layer, decoupling it and weakening the wind
at 50 m (bias −1.80 m/s at P0, −1.76 at LPI, against −1.17 and −1.16 in `CTL`),
while leaving the flow above the shallow inversion unaffected or slightly
improved. The same sign appears at both sites, in different months, with
different instruments — the pattern is consistent, which is what makes it
attributable rather than incidental.

`EXP02` over the 159 hours currently available is worse than `EXP01` at every
height (ΔMSE −1.0 to −1.2, all significant). This is a preliminary number over a
short window with a run that is still integrating and carries the same SST
contamination; it should not be treated as a verdict on the boundary treatment.

**Cost.** `EXP02` costs +24 % in cells and wall time. Nothing observed so far
earns that, but nothing observed so far tests it fairly either.

##### The one `EXP02` result that *is* informative

`scripts/03_selection/boundary_influence.py`,
`results/tables/boundary_influence.csv`,
`figures/selection/boundary_influence_2021.png`.

`EXP02`'s claim is spatial, not site-specific: moving the lateral relaxation zone
from ~190-230 km to ~600 km from the area of interest should produce a difference
that is **organised by distance from `EXP01`'s relaxation zone**. It is. Mean
|`EXP02` − `EXP01`| in the 100 m wind, binned by that distance over the whole
`meqbr_05km` footprint (379 common hours):

| Distance from `EXP01`'s relaxation cells | mean \|difference\| |
|---|---|
| 0-50 km | 0.28 m s⁻¹ |
| 50-100 km | 0.26 |
| 100-200 km | 0.22 |
| 200-300 km | 0.18 |
| 300-500 km | 0.16 |

A clean monotonic decay, with a sharp band along the southern and western
relaxation zones visible in the map. This is the predicted signature and it is
**not** contaminated by the SST problem: both runs carry the same corrupted
coastal SST, and the `EXP02` − `EXP01` SST difference is near zero offshore, so
this comparison does isolate the boundary treatment.

What it does *not* show is a benefit at the instruments. Both LiDAR sites sit
200-300 km from `EXP01`'s relaxation zone, where the difference has already
decayed to ~0.18 m s⁻¹ — real, but small compared with the model's ~1 m s⁻¹ bias
there, and in the direction that made the site scores slightly worse. **The
buffered mesh does what it was designed to do; the sites were not where it
mattered.** That is a useful negative result for the climatological runs: it
argues for keeping the cheaper mesh unless the near-boundary region itself is
part of the product.

#### 3. The runs add real skill over ERA5 at P0, and none that is detectable at LPI

`results/tables/era5_added_value_fullwindow.csv`, `figures/era5/added_value_fullwindow.png`.
Murphy skill score at 100 m, 95 % block-bootstrap interval:

| | ERA5 RMSE | `CTL` skill vs ERA5 | `EXP01` skill vs ERA5 |
|---|---|---|---|
| P0 / Nov 2021 | 2.49 m s⁻¹ | **+0.24 [+0.12, +0.39]** | **+0.18 [+0.06, +0.34]** |
| LPI / Oct 2022 | 2.47 m s⁻¹ | +0.12 [−0.02, +0.27] | −0.08 [−0.23, +0.08] |

The **trade** is consistent and worth stating plainly: MPAS roughly halves ERA5's
speed bias (P0: −1.24 vs −1.90 m s⁻¹; LPI: −0.96 vs −1.90) while **lowering the
correlation** (P0: 0.42 vs 0.53; LPI: 0.71 vs 0.85). The 5 km run is closer on
average and worse on timing. For resource assessment — an integral over the
distribution — the bias reduction is the more valuable half, which is why the
skill score comes out positive at P0 despite the correlation loss. For any
application that needs the right wind at the right hour, it is not.

The MSE decomposition says the same thing from the other side: at both sites the
dispersive (phase) term is 2.5-6.8 m² s⁻² while the dissipative (amplitude) term
is 0.0-0.5. **Essentially all the random error is timing, not variance.**

#### 4. A consistent low bias at every well-exposed site

At the LiDARs the model is slow at every height in every experiment: bias −0.4 to
−1.8 m s⁻¹, WPD −2 % to −48 %.

The 10 m land stations look at first as though they contradict this — pooled,
their mean bias is *positive*. Splitting them by station type shows that the
pooled number is an artefact of exposure, not a physical result
(`results/tables/station_metrics.csv`):

| Station type | n | observed mean | model mean | bias | RMSE | R |
|---|---|---|---|---|---|---|
| INMET automatic (`inmet_auto`) | 15 | 3.18 m s⁻¹ | 5.18 | **+2.00** | 2.32 | 0.72 |
| airport / synoptic (`synop_airport`) | 20 | 6.49 m s⁻¹ | 5.76 | **−0.74** | 1.59 | 0.67 |

(`CTL`; `EXP01` and `EXP02` differ by less than 0.15 m s⁻¹ in each row.)

The INMET automatic masts read 3.2 m s⁻¹ on average against 6.5 m s⁻¹ at the
airports in the same region and the same months. A factor-of-two difference
between two networks measuring the same wind is a siting and exposure
difference — sheltered masts against open airfields — and a ~5 km cell cannot
represent the shelter. Those stations therefore say very little about the model.

The **well-exposed** sites all agree, and they agree with the offshore
instruments: the airports are slow by 0.74-0.86 m s⁻¹, the LiDARs by 0.4-1.8
m s⁻¹. **The model has a low near-surface wind bias wherever it is compared
against a well-exposed measurement**, offshore and onshore alike. That points at
the surface-layer and roughness treatment, or at the ERA5 forcing (which carries
the same sign, −1.9 m s⁻¹ at both LiDARs), rather than at anything specific to
the marine boundary layer — and it is the single most consequential bias for
resource work, since −20 % in WPD is −20 % in energy.

This is also a caution about how the secondary tier is used: pooling stations of
different exposure gives a number with the wrong sign.

#### 5. The diurnal cycle: right phase inland, five hours late offshore

`figures/validation/diurnal_2021_P0.png`, `figures/validation/stations_diurnal.png`.

At the land stations the modelled diurnal **peak is within ±1 h** of observed in
every experiment — the sea-breeze timing over land is right. The **amplitude**
splits by exposure again: at the sheltered INMET masts the model overshoots
(3.6 against 3.2 m s⁻¹), at the exposed airports it badly undershoots (2.4
against 4.0 m s⁻¹). The airports are the more trustworthy comparison, so the
model is **damping the coastal diurnal swing** by roughly 40 %.

Offshore at P0 `CTL` peaks **5 hours late** and reproduces only 1.3 m s⁻¹ of the
observed 2.6-3.0 m s⁻¹ amplitude at 50-100 m. At LPI the phase is right (0-1 h)
and the amplitude slightly *too strong* (7.7 against 6.7 m s⁻¹ at 100 m).

`EXP01` improves P0's diurnal amplitude substantially (2.5 vs `CTL`'s 1.3, against
2.6 observed) and cuts the phase error from +5 h to +3 h — which is the **right
answer for the wrong reason**: a spuriously cold coastal sea strengthens the
land-sea thermal contrast and so strengthens the sea breeze. Any future
configuration that fixes the SST must be re-checked against this, because the
apparent improvement will disappear with the error that produced it.

#### 6. The sea-breeze circulation itself is well formed

`figures/exploration/xsection_P0_CTL_2021_composite_15local.png`. The
mid-afternoon composite shows a textbook sea-breeze cell: onshore flow in the
lowest ~1 km reaching ~110 km inland, a return flow offshore above 1.5-2.5 km,
ascent at the front and subsidence behind. The circulation exists and has the
right structure; the error is in its timing offshore and its strength, not in
its absence.

#### 7. November 2021 was the weakest November in 31 years — **[limits what the ranking can claim]**

`results/tables/era5_month_representativeness.csv`,
`figures/era5/climatological_context.png`.

| | Simulated month (ERA5) | 1990-2020 mean ± sd | Percentile | z |
|---|---|---|---|---|
| P0, Nov 2021 | 7.31 m s⁻¹ | 8.66 ± 0.55 | **0th of 31** | **−2.46** |
| LPI, Oct 2022 | 9.74 m s⁻¹ | 9.69 ± 0.43 | 47th of 30 | +0.13 |

Restricting to the LiDAR's own sub-window (9-30 Nov) gives the same answer:
6th percentile, z = −1.86. (The two rows rest on different sample sizes because
seven months are missing from the local ERA5 archive, one of them an October —
see `docs/data_sources.md`.) **The P0 evaluation therefore rests on an extreme
month**, and an experiment ranking derived from it is a ranking for anomalously
weak trade-wind conditions. The LPI evaluation, by contrast, is on an almost
exactly typical October — which is part of why the two site-periods agreeing
matters so much.

(The observed LiDAR mean at P0 over the same window was 9.45 m s⁻¹, well above
ERA5's 7.53. This is the ERA5 site bias discussed under Assumptions, not a
contradiction: the percentile is ERA5-against-ERA5 and is unaffected by a
stationary offset.)

#### 8. What the 5 km field adds over ERA5, spatially

`figures/exploration/mean_fields_*.png`, `figures/era5/resource_comparison_*.png`,
`results/tables/resource_comparison.csv`.

Averaged over the domain and regridded to ERA5's own 0.25° grid, MPAS gives
**9-27 % more wind power density** than ERA5 for the same hours (`CTL`: +9.4 % in
Nov 2021, +23.2 % in Oct 2022). Note the sign: MPAS is *slower* than the LiDARs
offshore but *windier* than ERA5 over the domain as a whole, most of which is
land or open ocean far from the instruments.

The native-mesh fields show the structure ERA5 cannot carry: a coastal band of
large diurnal amplitude (4-7 m s⁻¹ peak-to-trough) that decays offshore within
~100 km, sharp WPD maxima at the capes near LPI, and terrain-driven jets inland.
The directional-constancy field separates the steady trade-wind regime offshore
(≈ 1.0) from the reversing coastal regime (0.5-0.8) — a distinction with direct
consequences for siting and one that a 31 km grid smooths away.

#### 9. Representativeness is a real constraint at LPI, not at P0

`results/tables/cell_sensitivity.csv`, `figures/validation/cell_sensitivity.png`.
RMSE spread across the five nearest ocean cells (all within 6.5 km):

| | P0 / 2021 | LPI / 2022 |
|---|---|---|
| `CTL` | 0.15 m s⁻¹ | **1.33 m s⁻¹** |
| `EXP01` | 0.11 m s⁻¹ | **1.00 m s⁻¹** |

At LPI, moving the comparison cell by a few kilometres changes RMSE by more than
the entire difference between experiments (~0.25 m s⁻¹ at 100 m). The site sits
in a strong horizontal gradient — it is an offshore terminal close to a cape.

This does **not** invalidate the paired ranking, which uses the same cell for
both experiments and therefore differences the gradient away: the sign of
`EXP01 − CTL` at 100 m is the same at 9 of the 10 site-cells tested (the sole
flip is the most distant LPI cell, 5.4 km away, which also has the worst absolute
RMSE). But it does mean the *absolute* skill numbers at LPI should be quoted as
a property of this comparison, not of the site.

---

## Caveats and Limitations

1. **The SST-update experiments are compromised at the sites** (Result 1). The
   `EXP01` and `EXP02` rankings do not test their stated hypotheses. Nothing in
   the ranking should be reported as evidence about SST updating or boundary
   treatment until the forcing is regenerated.
2. **`EXP02` is incomplete.** The 2021 leg reaches ~51 % of the analysis window
   (159 h overlap with P0); the 2022 leg has not started. Its numbers are
   preliminary and its intervals correspondingly wide.
3. **One month per site**, and one of them (P0, Nov 2021) sits at the 0th
   percentile of its 31-year distribution (Result 7).
4. **Two sites, one coast, both offshore.** Nothing constrains inland behaviour
   or complex terrain. The 10 m land stations are supporting evidence for the
   coastal circulation only.
5. **LPI's absolute scores are cell-sensitive** (Result 9).
6. **LPI has no QC flag** equivalent to P0's availability field, so its record
   receives only a physical-range check.
7. **The 2021 `CTL` leg was forced by a narrower ERA5 box** than the 2022 leg
   (clearing the mesh by 0.34° at the southern edge). This is a confounder
   between `CTL`'s two periods, documented in the run repository, and a candidate
   explanation for any 2021-only boundary artefact. It is not corrected here.
8. **ERA5's own site bias is large** (−1.9 m s⁻¹ at P0) and its stationarity is
   assumed, not shown (see Assumptions).
9. **Terrain and coastline are the model's own** ~5 km fields in every figure —
   no external DEM is used anywhere, so features finer than the mesh do not
   appear.

---

## Next Steps

**Blocking, before the experiment set can decide anything:**

1. **Regenerate `sfc_update.nc` with the OISST land mask honoured** — mask before
   interpolating, or fill land with a nearest-ocean-neighbour extrapolation, so
   coastal ocean cells receive an SST rather than a blend with 273.15 K. Verify
   with `scripts/03_selection/check_sst_forcing.py`, which must exit 0.
2. **Re-run `EXP01` (both periods) with the corrected forcing.** The SST-update
   hypothesis is currently untested. Until then `EXP01 − CTL` measures an
   interpolation error.
3. **Decide `EXP02`'s fate after that.** The boundary treatment demonstrably
   works — the difference decays with distance from the relaxation zone, exactly
   as designed (Result 2) — but it is worth ~0.18 m s⁻¹ at the sites, against a
   ~1 m s⁻¹ model bias there, for +24 % compute. Unless the near-boundary region
   is itself part of the product, the cheaper mesh is the better buy for
   climatological runs. Completing `EXP02` as currently configured adds only
   another contaminated-SST comparison; restarting it on corrected forcing is
   the only version worth the machine time.

**Scientifically valuable next:**

4. **Explain the low offshore / high onshore bias** (Result 4). Candidates worth
   separating: the sea-surface roughness formulation (`znt` over water), the YSU
   mixing depth, and the ERA5 lateral forcing itself, which carries the same sign.
   `ust`, `znt` and `zol` are already extracted at the sites for exactly this.
5. **Explain the 5-hour offshore diurnal phase error at P0**, which does not
   appear at LPI or at the land stations. A site-specific error of that size in a
   sea-breeze regime is a strong lead.
6. **Add a second, typical month at P0** — the current evaluation there is on the
   weakest November in three decades.
7. **Check the pairing-tolerance and bootstrap-block assumptions** with a short
   sensitivity sweep, now that the machinery exists.
8. **Consider `config_sstdiurn_update`.** For the offshore diurnal wind cycle a
   diurnal SST cycle may matter more than the daily update does — and it should
   be tested only after the daily-update forcing is fixed.

---

## References

- Takacs, L. L. (1985). A two-step scheme for the advection equation with
  minimized dissipation and dispersion errors. *Monthly Weather Review*, 113(6),
  1050-1065. https://doi.org/10.1175/1520-0493(1985)113<1050:ATSSFT>2.0.CO;2
- Willmott, C. J. (1981). On the validation of models. *Physical Geography*,
  2(2), 184-194. https://doi.org/10.1080/02723646.1981.10642213
- Diebold, F. X., & Mariano, R. S. (1995). Comparing predictive accuracy.
  *Journal of Business & Economic Statistics*, 13(3), 253-263.
  https://doi.org/10.1080/07350015.1995.10524599
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary
  observations. *The Annals of Statistics*, 17(3), 1217-1241.
  https://doi.org/10.1214/aos/1176347265
- Murphy, A. H. (1988). Skill scores based on the mean square error and their
  relationships to the correlation coefficient. *Monthly Weather Review*, 116(12),
  2417-2424. https://doi.org/10.1175/1520-0493(1988)116<2417:SSBOTM>2.0.CO;2
- Hersbach, H. et al. (2020). The ERA5 global reanalysis. *Quarterly Journal of
  the Royal Meteorological Society*, 146(730), 1999-2049.
  https://doi.org/10.1002/qj.3803
- Huang, B. et al. (2021). Improvements of the Daily Optimum Interpolation Sea
  Surface Temperature (DOISST) version 2.1. *Journal of Climate*, 34(8),
  2923-2939. https://doi.org/10.1175/JCLI-D-20-0166.1
- Skamarock, W. C. et al. (2012). A multiscale nonhydrostatic atmospheric model
  using centroidal Voronoi tesselations and C-grid staggering. *Monthly Weather
  Review*, 140(9), 3090-3105. https://doi.org/10.1175/MWR-D-11-00215.1
- Smith, A., Lott, N., & Vose, R. (2011). The Integrated Surface Database:
  Recent developments and partnerships. *Bulletin of the American Meteorological
  Society*, 92(6), 704-708. https://doi.org/10.1175/2011BAMS3015.1
