#!/usr/bin/env bash
# MEQ-05.4 — Etapa 1: partitions N = 45 and 90 inside the existing MEQ-05.2 benchmark directory.
# Writes ONLY new MEQ054_* entries inside $BENCH. Old trials, common/ and partitions/ are read-only.
set -euo pipefail

ROOT=/p1-swell/danilocs/MPAS-Research
BENCH=$ROOT/runs/meqbr_05km_oval_meq02a_bench_MEQ-05.2
GPMETIS=/home/danilocs/.conda/envs/cgfd-usp-mpas/bin/gpmetis
MESH=meqbr_05km_oval_meq02a
GRAPH_SRC=$ROOT/grids/$MESH/$MESH.graph.info
P=$BENCH/MEQ054_partitions
REC=$BENCH/MEQ054_records

[ -d "$BENCH" ] || { echo "BENCH missing: $BENCH" >&2; exit 1; }
[ -e "$P" ] && { echo "already exists: $P" >&2; exit 1; }
mkdir -p "$P" "$REC"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "setup_start_utc=$(ts)" > "$REC/setup.txt"
sha256sum "$GRAPH_SRC" >> "$REC/setup.txt"

ln -s "$GRAPH_SRC" "$P/$MESH.graph.info"
"$GPMETIS" -help 2>&1 | head -3 > "$P/gpmetis_version.txt" || true
# Same options as MEQ-05.2 and runs/meqbr_05km_oval_meq02a/provenance/gpmetis_part60.log
for N in 45 90; do
    ( cd "$P" && "$GPMETIS" -minconn -contig -niter=200 $MESH.graph.info $N > gpmetis_part$N.log 2>&1 )
done
sha256sum "$P"/$MESH.graph.info.part.* > "$P/partitions_sha256.txt"
{
  printf "N\tedgecut\tcomm_volume\tbalance\tcontiguous\n"
  for N in 45 90; do
    L=$P/gpmetis_part$N.log
    ec=$(sed -n 's/.*Edgecut: *\([0-9]*\),.*/\1/p' "$L")
    cv=$(sed -n 's/.*communication volume: *\([0-9]*\)\..*/\1/p' "$L")
    bal=$(sed -n 's/.*constraint #0: *\([0-9.]*\) .*/\1/p' "$L")
    ct=$(grep -q "Each partition is contiguous" "$L" && echo yes || echo no)
    printf "%s\t%s\t%s\t%s\t%s\n" "$N" "$ec" "$cv" "$bal" "$ct"
  done
} > "$P/partitions_summary.tsv"
# part ids per file: must be 0..N-1
for N in 45 90; do
    echo "part.$N lines=$(wc -l < "$P/$MESH.graph.info.part.$N") distinct=$(sort -u "$P/$MESH.graph.info.part.$N" | wc -l)"
done >> "$P/partitions_summary.tsv"

echo "setup_end_utc=$(ts)" >> "$REC/setup.txt"
cat "$P/partitions_summary.tsv"
echo OK
