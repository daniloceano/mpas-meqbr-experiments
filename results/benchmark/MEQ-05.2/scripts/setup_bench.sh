#!/usr/bin/env bash
# MEQ-05.2 — Etapa 1: prepare the benchmark directory (partitions, namelist, streams).
# Writes ONLY inside $BENCH. Production run directories are read-only sources.
set -euo pipefail

ROOT=/p1-swell/danilocs/MPAS-Research
SRC_RUN=$ROOT/runs/meqbr_05km_oval_meq02a
SRC=$SRC_RUN/20211101_20211201
BENCH=$ROOT/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2
GPMETIS=/home/danilocs/.conda/envs/cgfd-usp-mpas/bin/gpmetis
MESH=meqbr_05km_oval_meq02a
GRAPH_SRC=$ROOT/grids/$MESH/$MESH.graph.info

[ -e "$BENCH" ] && { echo "BENCH already exists: $BENCH" >&2; exit 1; }
mkdir -p "$BENCH"/{common,partitions,partitions/check60,records,scripts}
cd "$BENCH"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "setup_start_utc=$(ts)" > records/setup.txt

# ---------------- partitions ----------------
ln -s "$GRAPH_SRC" partitions/$MESH.graph.info
ln -s "$GRAPH_SRC" partitions/check60/$MESH.graph.info
sha256sum "$GRAPH_SRC" >> records/setup.txt
"$GPMETIS" -help 2>&1 | head -3 > partitions/gpmetis_version.txt || true
# Same options as provenance/gpmetis_part60.log: ptype=kway, minconn=YES, contig=YES, niter=200, ufactor default (1.030)
for N in 8 14 28 42 56 112; do
    ( cd partitions && "$GPMETIS" -minconn -contig -niter=200 $MESH.graph.info $N > gpmetis_part$N.log 2>&1 )
done
# Reproducibility check of the parameter set against the production partition (not used in runs)
( cd partitions/check60 && "$GPMETIS" -minconn -contig -niter=200 $MESH.graph.info 60 > gpmetis_part60_check.log 2>&1 )
{
  echo "# sha256 of production part.60 vs regenerated (check only; runs use the production file)"
  sha256sum "$SRC_RUN/$MESH.graph.info.part.60" partitions/check60/$MESH.graph.info.part.60
} > partitions/check60/compare.txt
ln -s "$SRC_RUN/$MESH.graph.info.part.60" partitions/$MESH.graph.info.part.60
sha256sum partitions/$MESH.graph.info.part.* > partitions/partitions_sha256.txt

# ---------------- namelist ----------------
cp "$SRC/namelist.atmosphere" common/namelist.atmosphere.orig
sed -e "s/^\(\s*config_start_time\s*=\s*\).*/\1'2021-11-15_00:00:00'/" \
    -e "s/^\(\s*config_run_duration\s*=\s*\).*/\1'0_03:00:00'/" \
    -e "s/^\(\s*config_do_restart\s*=\s*\).*/\1true/" \
    common/namelist.atmosphere.orig > common/namelist.atmosphere
diff common/namelist.atmosphere.orig common/namelist.atmosphere > common/namelist.diff || true

# ---------------- streams ----------------
cp "$SRC_RUN/streams.atmosphere" common/streams.atmosphere.orig
python3 - "$BENCH/common" <<'PY'
import re, sys, pathlib
d = pathlib.Path(sys.argv[1])
s = (d / "streams.atmosphere.orig").read_text()

def set_interval(text, name, value):
    # replace output_interval inside the <stream>/<immutable_stream> block with the given name
    pat = re.compile(r'(<(?:immutable_)?stream name="%s".*?output_interval=")[^"]*(")' % re.escape(name), re.S)
    new, n = pat.subn(r'\g<1>%s\g<2>' % value, text, count=1)
    assert n == 1, name
    return new

noout = set_interval(set_interval(s, "output", "none"), "restart", "none")
prod = set_interval(s, "restart", "03:00:00")
(d / "streams.atmosphere.nooutput").write_text(noout)
(d / "streams.atmosphere.production").write_text(prod)
PY
diff common/streams.atmosphere.orig common/streams.atmosphere.nooutput > common/streams.nooutput.diff || true
diff common/streams.atmosphere.orig common/streams.atmosphere.production > common/streams.production.diff || true

echo "setup_end_utc=$(ts)" >> records/setup.txt
echo OK
