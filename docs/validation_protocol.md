# Validation protocol

How the experiments are scored, and why each choice was made. The point of
writing this down is that a reader should be able to disagree with a specific
decision and see exactly which numbers it would change.

## 1. What counts as evidence

| Tier | Source | Height | What it can decide |
|---|---|---|---|
| **Primary** | P0 and LPI LiDAR profilers | 50-250 m | The experiment ranking. Offshore, at hub height, which is the quantity the project is about. |
| **Secondary** | 8 public surface stations (NOAA NCEI ISD, incl. the INMET automatic network) | 10 m | The coastal diurnal cycle and the along-coast structure — over ~700 km of coast rather than two points. |
| **Reference** | ERA5 | 10 m and 100 m | Not a competitor: it is the runs' own forcing, so "MPAS beats ERA5" is a statement about what the downscaling added. |

The tiers are kept apart on purpose. A 10 m land anemometer sits in a roughness
and stability regime a 5 km cell cannot represent, so a station bias must not be
carried across into a claim about offshore hub-height wind. What the stations
*can* do is test whether the sea breeze arrives at the right hour over a wide
area — which the two LiDARs cannot.

**Within the secondary tier, the two networks must be kept apart too.** The
INMET automatic masts record a mean wind about half that of the airport
synoptic stations in the same region and the same months (3.2 against
6.5 m s⁻¹). That is a siting and exposure difference — sheltered masts against
open airfields — and a ~5 km cell cannot see the shelter. Pooling them yields a
model bias with the *wrong sign*; the well-exposed airports are the meaningful
comparison. `validate_surface_stations.py` prints and writes a by-type table,
and the station map encodes the type in the marker shape.

INMET's own API and portal are unreachable from this host (the TCP connection is
reset, while other outbound HTTPS works), so the same stations are taken from
NOAA's Integrated Surface Database, where the Brazilian automatic network and
the airport reports are internationally archived.

## 2. Pairing model to observation

**Nearest ocean cell.** Each LiDAR is compared against the nearest MPAS cell of
the same surface type: 2.5 km away for P0 and 1.8 km for LPI on `meqbr_05km`,
1.1 km for P0 on `meqbr_05km_buf`. This is the conventional choice, and it is a
choice — `scripts/02_validation/check_cell_sensitivity.py` repeats every score
on the five nearest ocean cells so the spread across them can be read as a floor
that an experiment difference has to clear.

**Hourly averaging, not nearest sample.** The 10-minute record is averaged into
the hour centred on each model timestamp (`[t-30 min, t+30 min)`), requiring 4 of
the 6 possible samples. The alternative — taking the single 10-minute sample
closest to the model hour — needs no thresholds but compares a 10-minute point
measurement against an hourly value representing a ~20 km² cell. That mismatch
in averaging scale appears as scatter and is charged to the model. Hourly
averaging removes the part of it that can be removed; the spatial part is
irreducible and is stated as a caveat rather than hidden.

**Heights.** Model layer centres are matched to LiDAR channels within 1 m, and
the match is asserted, not assumed. The one exception is P0's 250 m model level,
which has no channel; it is compared against the mean of the 240 m and 260 m
channels, which bracket it symmetrically. LPI has no channel above 200 m, so its
250 m level is simply not scored.

**Quality control.** P0 carries a per-height availability flag; bins below 80 %
are dropped before pairing. LPI has no equivalent flag, so only a physical range
check is applied. That asymmetry is real and is not papered over by inventing a
threshold for LPI.

**Same hours for everyone.** Every comparison between experiments restricts to
the hours all of them have (`--common-period`, on by default). While EXP02 is
still integrating this shortens the window considerably, so the pipeline also
produces a `_fullwindow` set restricted to the completed experiments, where the
sample is much larger.

## 3. What is measured

Three groups, because they answer different questions and a model can pass one
and fail another.

**Point verification** — bias, MAE, RMSE, centred RMSE, correlation,
standard-deviation ratio, Willmott's index of agreement, and the Takacs (1985)
decomposition of MSE into an amplitude (dissipative) and a phase (dispersive)
part. The decomposition is exact: `MSE = bias² + MSE_diss + MSE_disp`. It
matters because it says *how* a run is wrong — damping the variability and
mistiming it call for different fixes.

**Wind resource** — mean speed, Weibull scale A and shape k (maximum likelihood,
location fixed at zero as resource practice requires), and wind power density.
WPD is the number that becomes energy and it goes as U³, so a −10 % speed bias
is roughly a −27 % energy bias. A model can have a respectable RMSE and still be
unusable for resource work; this group is what catches that.

**Diurnal cycle** — amplitude and phase of the mean daily cycle in local time.
On a sea-breeze coast this is where a 5 km mesh should beat a 31 km reanalysis,
and it is what determines *when* the resource is available.

Direction is scored with circular statistics, masked below 2 m/s.

## 4. Uncertainty, and why it is not optional here

Hourly wind errors are strongly autocorrelated: consecutive hours are not
independent samples. Treating N = 700 hours as 700 independent draws would
produce confidence intervals several times too narrow and would turn ordinary
noise into "significant" improvements — which, for a decision about which
configuration to spend months of compute on, is the expensive kind of mistake.

Two devices are used instead:

- **Moving-block bootstrap** with 24-hour blocks, long enough to span the diurnal
  cycle and most of the synoptic persistence. Used for confidence intervals on
  any single metric.
- **Paired difference of squared errors** for comparing two experiments. Because
  both saw the same weather at the same site, the shared variability cancels and
  only the difference in error is resampled — far more sensitive than comparing
  two RMSE values that each carry the full weather variance. This is a bootstrap
  analogue of the Diebold-Mariano test for equal predictive accuracy.

A verdict of "not distinguishable" means the interval spans zero. That is a
result, not a failure, and for a decision about spending compute it is a
consequential one: a configuration that costs 24 % more and is not
distinguishable does not earn the cost.

## 5. What this design cannot decide

- **One month per site.** The ranking is a ranking *for these conditions*.
  `scripts/04_era5/climatological_context.py` places each simulated month against
  the 1990-2020 ERA5 distribution of the same calendar month, so the size of
  that extrapolation is a number rather than a hope.
- **Two sites, one coast, both offshore.** Nothing here constrains behaviour
  inland or over complex terrain.
- **One cell per site.** Quantified, not eliminated — see the cell-sensitivity
  check.
- **Mechanism, not just score.** A configuration that wins without its designed
  mechanism being visible has not demonstrated anything that would transfer to
  another month. `scripts/03_selection/attribution_diagnostics.py` and
  `scripts/03_selection/check_sst_forcing.py` exist for that reason — and the
  second one found a problem that changes how the ranking must be read. See
  `SCIENTIFIC_NOTES.md`.
