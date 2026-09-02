"""Configuration and path resolution — the single place that knows where
things live and what the experiments are.

Three files feed in:

``config/experiments.yaml``  what each experiment/period is (version controlled)
``config/sites.yaml``        validation sites and pairing rules (version controlled)
``config/paths.local.yaml``  where the data lives on this machine (gitignored)

Scripts should call :func:`load_config` and read from the returned object; no
script should build a path to the run directories by hand.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

# repo_root/src/mpas_meqbr/config.py -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
EXPERIMENTS_YAML = CONFIG_DIR / "experiments.yaml"
SITES_YAML = CONFIG_DIR / "sites.yaml"
PATHS_LOCAL_YAML = CONFIG_DIR / "paths.local.yaml"
PATHS_EXAMPLE_YAML = CONFIG_DIR / "paths.example.yaml"


def add_src_to_path() -> None:
    """Make ``import mpas_meqbr`` work from a plain ``python scripts/...`` call.

    Every script starts with this rather than requiring an installed package —
    the repo is an analysis workspace, not a distributable library.
    """
    src = str(REPO_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


@dataclass(frozen=True)
class Leg:
    """One (experiment, period) pair — a single MPAS integration."""

    experiment: str
    period: str
    history_dir: Path
    mesh: str
    analysis_start: pd.Timestamp
    analysis_end: pd.Timestamp
    integration_start: pd.Timestamp
    expected_history_records: int
    validation_site: str
    sst_update: bool

    @property
    def key(self) -> str:
        return f"{self.experiment}_{self.period}"

    @property
    def init_file(self) -> Path:
        """The ``<mesh>.init.nc`` in this leg's directory.

        It is the only place ``zgrid`` and the terrain are guaranteed to be
        available together, and it is per-leg because the mesh can differ.
        """
        return self.history_dir / f"{self.mesh}.init.nc"

    def exists(self) -> bool:
        return self.history_dir.is_dir()


@dataclass(frozen=True)
class Site:
    key: str
    label: str
    lat: float
    lon: float
    period: str
    heights_m: list
    height_map: dict          # model height (m) -> list of observed channel heights
    qc: dict
    source_file: str
    meta: dict = field(default_factory=dict)

    @property
    def model_heights(self) -> list:
        return sorted(self.height_map)


@dataclass(frozen=True)
class Config:
    runs_root: Path
    era5_periods_dir: Path
    era5_climatology_dir: Path
    obs_source_repo: Path | None
    ffmpeg: str | None
    experiments: dict
    periods: dict
    meshes: dict
    vertical: dict
    boundary_distance_km: dict
    sites: dict
    pairing: dict
    secondary: dict

    # -- experiment / leg access -------------------------------------------

    @property
    def experiment_keys(self) -> list:
        return list(self.experiments)

    def leg(self, experiment: str, period: str) -> Leg:
        if experiment not in self.experiments:
            raise KeyError(
                f"unknown experiment {experiment!r}; known: "
                f"{', '.join(self.experiments)}")
        if period not in self.periods:
            raise KeyError(
                f"unknown period {period!r}; known: {', '.join(self.periods)}")
        exp = self.experiments[experiment]
        per = self.periods[period]
        return Leg(
            experiment=experiment,
            period=period,
            history_dir=self.runs_root / experiment / per["history_subdir"],
            mesh=exp["mesh"],
            analysis_start=pd.Timestamp(per["analysis_start"]),
            analysis_end=pd.Timestamp(per["analysis_end"]),
            integration_start=pd.Timestamp(per["integration_start"]),
            expected_history_records=int(per["expected_history_records"]),
            validation_site=per["validation_site"],
            sst_update=bool(exp["sst_update"]),
        )

    def all_legs(self) -> list:
        return [self.leg(e, p)
                for e in self.experiments
                for p in self.experiments[e]["periods"]]

    # -- sites --------------------------------------------------------------

    def site(self, key: str) -> Site:
        if key not in self.sites:
            raise KeyError(
                f"unknown site {key!r}; known: {', '.join(self.sites)}")
        return self.sites[key]

    @property
    def comparison_heights(self) -> list:
        return list(self.vertical["comparison_heights_m"])

    @property
    def height_tolerance_m(self) -> float:
        return float(self.vertical["height_tolerance_m"])

    # -- output locations ---------------------------------------------------

    def path(self, *parts) -> Path:
        """A path inside the repo, creating the parent directory if needed."""
        p = REPO_ROOT.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


def _load_yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load_config(*, runs_root: str | Path | None = None) -> Config:
    """Build the :class:`Config`. ``runs_root`` overrides ``paths.local.yaml``."""
    exps = _load_yaml(EXPERIMENTS_YAML)
    sites_doc = _load_yaml(SITES_YAML)

    paths: dict = {}
    if runs_root is None:
        if not PATHS_LOCAL_YAML.exists():
            raise FileNotFoundError(
                f"missing {PATHS_LOCAL_YAML}. Copy the template and edit it:\n"
                f"  cp config/paths.example.yaml config/paths.local.yaml\n"
                "or pass --runs-root.")
        paths = _load_yaml(PATHS_LOCAL_YAML)
        runs_root = paths.get("runs_root")
        if not runs_root:
            raise ValueError(f"'runs_root' not set in {PATHS_LOCAL_YAML}")

    def _resolve(value, default) -> Path:
        p = Path(value or default).expanduser()
        return p if p.is_absolute() else (REPO_ROOT / p)

    sites = {}
    for key, meta in (sites_doc.get("primary") or {}).items():
        sites[key] = Site(
            key=key,
            label=meta["label"],
            lat=float(meta["lat"]),
            lon=float(meta["lon"]),
            period=str(meta["period"]),
            heights_m=list(meta["heights_m"]),
            height_map={int(k): list(v) for k, v in meta["height_map"].items()},
            qc=dict(meta.get("qc") or {}),
            source_file=meta["source_file"],
            meta=meta,
        )

    obs_repo = paths.get("obs_source_repo")
    return Config(
        runs_root=Path(runs_root).expanduser(),
        era5_periods_dir=_resolve(paths.get("era5_periods_dir"), "data/era5"),
        era5_climatology_dir=_resolve(paths.get("era5_climatology_dir"), "data/era5_clim"),
        obs_source_repo=Path(obs_repo).expanduser() if obs_repo else None,
        ffmpeg=paths.get("ffmpeg"),
        experiments=exps.get("experiments", {}),
        periods={str(k): v for k, v in (exps.get("periods") or {}).items()},
        meshes=exps.get("meshes", {}),
        vertical=exps.get("vertical", {}),
        boundary_distance_km=exps.get("boundary_distance_km", {}),
        sites=sites,
        pairing=sites_doc.get("pairing", {}),
        secondary=sites_doc.get("secondary", {}),
    )
