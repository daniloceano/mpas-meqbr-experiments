#!/usr/bin/env python
"""Populate data/obs/ with the two LiDAR files from the sibling poster repo.

The P0 and LPI records were received from their operators and prepared in
``mpas-earthsyms2026-analysis``; there is no download script for them and there
is no second copy anywhere. Rather than duplicate ~90 MB, this creates symlinks
and verifies that each target reads back with the expected shape and period.

Run once, after cloning:

    python scripts/00_setup/link_observations.py [--copy]

``--copy`` makes real copies instead of symlinks — use it if this repo will be
moved to a machine where the sibling repo is not present.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from mpas_meqbr.config import load_config, REPO_ROOT  # noqa: E402

# repo-relative destination -> path inside the source repo
WANTED = {
    "data/obs/P0_LIDAR_matrix.mat": "data/P0_LIDAR_matrix.mat",
    "data/obs/LPI_processed.csv.gz": "data/LPI_processed.csv.gz",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--copy", action="store_true", help="copy instead of symlink")
    ap.add_argument("--source", default=None,
                    help="override obs_source_repo from paths.local.yaml")
    args = ap.parse_args()

    cfg = load_config()
    source = Path(args.source) if args.source else cfg.obs_source_repo
    if source is None or not source.is_dir():
        print(f"source repo not found: {source}", file=sys.stderr)
        print("set obs_source_repo in config/paths.local.yaml, or pass --source",
              file=sys.stderr)
        return 2

    records = []
    for dest_rel, src_rel in WANTED.items():
        src = source / src_rel
        dest = REPO_ROOT / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            print(f"MISSING in source: {src}", file=sys.stderr)
            return 1
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        if args.copy:
            shutil.copy2(src, dest)
            how = "copied"
        else:
            dest.symlink_to(src.resolve())
            how = "symlinked"
        size = dest.stat().st_size
        print(f"{how:9s} {dest_rel}  ({size/1e6:.1f} MB)  <- {src}")
        records.append({"dest": dest_rel, "source": str(src.resolve()),
                        "mode": how, "size_bytes": size})

    # Read both back so a broken link or a truncated copy fails here, loudly,
    # rather than three scripts later inside a metric.
    from mpas_meqbr import obs

    print("\nverifying...")
    for key in ("P0", "LPI"):
        site = cfg.site(key)
        df = obs.read_lidar(site, REPO_ROOT)
        print(f"  {key:4s} {len(df):>8,d} QC-passed 10-min records, "
              f"{df['time'].min()} -> {df['time'].max()}, "
              f"heights {sorted(df['height'].unique())}")
        records.append({"site": key, "records": int(len(df)),
                        "start": str(df["time"].min()), "end": str(df["time"].max()),
                        "heights_m": sorted(map(float, df["height"].unique()))})

    meta = REPO_ROOT / "data" / "metadata" / "observations_provenance.json"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({
        "created": datetime.now(timezone.utc).isoformat(),
        "source_repo": str(source.resolve()),
        "note": ("LiDAR records received from their operators; no download "
                 "script exists. The sibling repo's data/README.md is the "
                 "authoritative description of how LPI_processed.csv.gz was "
                 "derived from the raw spreadsheet."),
        "entries": records,
    }, indent=2))
    print(f"\nprovenance -> {meta.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
