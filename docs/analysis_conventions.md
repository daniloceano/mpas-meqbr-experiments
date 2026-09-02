# Analysis conventions

MPAS-specific behaviour that is easy to get wrong, and the decisions this repo
made once so that no script has to make them again. If you add a script, follow
these; if you disagree with one, change it here and in `src/mpas_meqbr/` rather
than locally.

## Time

- `xtime` (`YYYY-MM-DD_hh:mm:ss`) is the authoritative valid time. Filenames
  encode the same time and are chronological, so `io.history_index()` builds the
  time axis from the filenames — but it re-reads `xtime` from a few files and
  raises if they disagree, so a mislabelled file cannot pass silently.
- **Never assume the file list equals the analysis window.** EXP02's history is
  written from the integration start and has not been trimmed of spin-up. Always
  go through `io.select_window(index, leg.analysis_start, leg.analysis_end)`.
- All model times are UTC. Local solar time on this coast is **UTC-3**, and every
  diurnal composite in this repo is built in local time — a UTC composite would
  shift the sea breeze three hours away from the sun that drives it.

## Geography

- `latCell` / `lonCell` are in **radians**. `io.cell_lonlat_degrees()` converts
  and wraps longitude to (-180, 180].
- Distances use a tangent-plane approximation (degrees scaled by `cos(lat)`).
  Near the equator, over the few hundred kilometres these lookups span, the error
  against a great circle is well under a percent — far below the ~5 km cell size
  the answer is quantised to.
- **Nearest-cell lookups are per leg.** `meqbr_05km` and `meqbr_05km_buf` do not
  share cell indices. A cell index cached from one experiment and used in another
  points somewhere else entirely.
- Both LiDAR sites are over water, so site lookups are restricted to **ocean
  cells** (`landmask == 0`); surface stations are matched to **land** cells. A
  land cell standing in for an offshore instrument would be a different physical
  regime, not a small error.

## Vertical grid

- MPAS is staggered: `zgrid` and `w` are on layer **interfaces**
  (`nVertLevelsP1` = 56); winds, `theta`, `rho`, `pressure`, `relhum` are at
  layer **centres** (`nVertLevels` = 55).
- Layer centres are the midpoint of adjacent interfaces
  (`vertical.layer_center_heights`), and AGL heights subtract `zgrid[..., 0]`
  (the terrain).
- The interface set (`zeta_wind.txt`) is specified in height **above terrain**,
  so the centres are the same AGL everywhere: 12.5, 50, 100, 150, 200, 250 m ...
  This has been verified on these meshes (the spread across cells at the 100 m
  centre is 0.4 m), which is what lets the field scripts read one level index for
  the whole mesh.
- Even so, **never hardcode the index**. `vertical.match_heights()` derives it and
  raises if no centre is within tolerance. A silent 30 m mismatch would bias every
  metric computed from it, and nothing downstream would show that it had happened.
- MPAS/Fortran is 1-based: the run documentation's "level 2" is index **1** in
  numpy.

## Wind conventions

- Speed from `uReconstructZonal` / `uReconstructMeridional`, which are already
  earth-relative at cell centres.
- Direction is meteorological — the direction the wind blows **from**:
  `(270 - atan2(v, u) in degrees) mod 360`. This matches the LiDAR and ISD
  conventions, so no conversion happens at comparison time.
- Direction statistics are circular (`metrics.circular_mean`,
  `metrics.angular_difference`). A scalar mean of 350° and 10° is 180°, which is
  the opposite of the answer.
- Directions are masked below 2 m/s, where the measurement carries no
  information about the model.

## Averaging

- Wind speed is **scalar**-averaged; direction is **vector**-averaged. Scalar
  mean speed is the resource-relevant quantity; the ratio of the two is the
  directional constancy, which the field scripts keep as a diagnostic.
- Wind power density accumulates `U**3` hour by hour and averages afterwards.
  `0.5*rho*mean(U)**3` understates WPD by 15-30 % for realistic distributions,
  silently.
- The 10-minute LiDAR record is averaged into the hour **centred** on each model
  timestamp, requiring 4 of 6 samples. See `docs/validation_protocol.md` for why
  this rather than nearest-sample matching.

## Masks

- `landmask` (static, 1 = land, 0 = ocean) and `xland` (time-varying, 1 = land
  including sea ice, 2 = ocean) use **different encodings**. Do not mix them.

## Memory and I/O

- Two access patterns cover everything and both are cheap: a *column at one cell*
  (`io.read_cell_columns`) and a *map at one level* (`io.read_level_map`). Anything
  that needs a whole run in memory is doing something wrong.
- The heavy passes (`extract_site_timeseries.py`, `compute_field_statistics.py`)
  write small cached NetCDF files; every figure reads those, not the raw history.

## Comparability

- When two experiments are compared — in a metric, a test or a difference map —
  they must be evaluated over the **same hours**. `pairing.load_paired(...,
  common=True)` and `fields.assert_same_window()` enforce it. A difference
  between different windows is a difference in weather.
