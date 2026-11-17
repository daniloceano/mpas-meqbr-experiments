#!/usr/bin/env bash
# MEQ-05.4 — Etapa 4: READ-ONLY disk inventory of the EXP03 production legs (writes only to stdout).
# Run:  bash disk_inventory_meq054.sh > disk_inventory.txt   (on Swell)
set -uo pipefail

S=/p1-swell/danilocs/MPAS-Research/runs/meqbr_05km_oval_meq02a
MESH=meqbr_05km_oval_meq02a
LEGS="20211101_20211201 20221001_20221101"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

echo "# MEQ-05.4 disk inventory (read-only) — captured $(ts) on $(hostname)"
echo "# run root: $S"
echo "# tools: stat (GNU coreutils), du, find, ncdump ($(command -v ncdump); $(ncdump 2>&1 | grep -i 'netcdf library version' | head -1))"
echo "# sizes in bytes; 'apparent' = st_size; 'allocated' = du -B1 (blocks on disk); links followed with -L"
echo

first() { ls -1 "$1"/$2 2>/dev/null | head -1; }

for leg in $LEGS; do
    D=$S/$leg
    echo "================================================================ LEG $leg"
    echo "## directory: $D"
    echo "## file counts by prefix (entries in the leg directory; links counted as entries)"
    ls -1 "$D" | sed 's/\..*//' | sort | uniq -c
    echo
    echo "## representative files (stat -L: size, type of entry, link target)"
    H=$(first "$D" 'history.*.nc'); RS=$(first "$D" 'restart.*.nc'); L=$(first "$D" 'lbc.*.nc')
    for f in "$H" "$RS" "$D/$MESH.init.nc" "$D/$MESH.sfc_update.nc" "$L"; do
        [ -e "$f" ] || { echo "MISSING $f"; continue; }
        kind=file; [ -L "$f" ] && kind="symlink->$(readlink -f "$f")"
        printf "%s\tapparent=%s\tallocated=%s\t%s\n" "$(basename "$f")" "$(stat -L -c %s "$f")" "$(du -L -B1 "$f" | cut -f1)" "$kind"
        printf "    format(ncdump -k)=%s\n" "$(ncdump -k "$f" 2>&1)"
    done
    echo
    echo "## all history / restart files: size distribution (apparent bytes)"
    for p in history restart; do
        find -L "$D" -maxdepth 1 -name "$p.*.nc" -printf '%s\n' | sort -n | awk -v p=$p '
            {a[NR]=$1; s+=$1} END {printf "%s\tn=%d\tmin=%d\tmax=%d\tsum=%d\n", p, NR, a[1], a[NR], s}'
    done
    echo
    echo "## totals per category (apparent bytes, links followed; allocated via du -L)"
    tot() {  # $1 label, rest = find name patterns
        local lab=$1; shift
        local args=() first=1
        for pat in "$@"; do [ $first -eq 1 ] && first=0 || args+=(-o); args+=(-name "$pat"); done
        local app alloc n
        n=$(find -L "$D" -maxdepth 1 -type f \( "${args[@]}" \) | wc -l)
        app=$(find -L "$D" -maxdepth 1 -type f \( "${args[@]}" \) -printf '%s\n' | awk '{s+=$1} END{printf "%d", s}')
        alloc=$(find -L "$D" -maxdepth 1 -type f \( "${args[@]}" \) -print0 | du -L -B1 -c --files0-from=- 2>/dev/null | tail -1 | cut -f1)
        printf "%s\tn=%s\tapparent=%s\tallocated=%s\n" "$lab" "$n" "$app" "${alloc:-0}"
    }
    tot history 'history.*.nc'
    tot restart 'restart.*.nc'
    tot inputs_lbc 'lbc.*.nc'
    tot inputs_init_sfc "$MESH.init.nc" "$MESH.sfc_update.nc"
    tot other_nc 'diag.*.nc' 'diag_ugwp.*.nc' 'mpasout.*.nc'
    echo "## whole leg directory: du -s (not following links = real files physically in the leg dir) and du -sL"
    printf "du_B1_nolinks=%s\tdu_apparent_nolinks=%s\tdu_B1_follow_links=%s\n" \
        "$(du -s -B1 "$D" | cut -f1)" "$(du -s -B1 --apparent-size "$D" | cut -f1)" "$(du -sL -B1 "$D" | cut -f1)"
    echo "## entries that are symlinks (inputs live elsewhere): $(find "$D" -maxdepth 1 -type l | wc -l)"
    find "$D" -maxdepth 1 -type l -name '*.nc' -printf '%f -> %l\n' | sed 's|lbc\.[0-9_.:-]*\.nc|lbc.*.nc|' | sort | uniq -c | head -20
    echo
done

echo "================================================================ SHARED (run root)"
for f in "$S/$MESH.static.nc" "$S/$MESH.grid.nc"; do
    printf "%s\tapparent=%s\tallocated=%s\tformat=%s\n" "$(basename "$f")" "$(stat -L -c %s "$f")" "$(du -L -B1 "$f" | cut -f1)" "$(ncdump -k "$f" 2>&1)"
done
echo
echo "================================================================ COMPRESSION / STORAGE (ncdump -hs, special attributes)"
H=$(first "$S/20211101_20211201" 'history.*.nc')
for f in "$H" "$(first "$S/20211101_20211201" 'restart.*.nc')"; do
    echo "## $(basename "$f"): format=$(ncdump -k "$f")"
    ncdump -hs "$f" | grep -E '_Format|_Storage|_DeflateLevel|_Shuffle|_ChunkSizes|_Filter|_Endianness|_NoFill|_IsNetcdf4|_SuperblockVersion' | sort | uniq -c | head -20
    echo "   (no lines above = no per-variable storage/compression attributes reported)"
done
echo
echo "================================================================ HISTORY HEADER: ncdump -h $(basename "$H")"
ncdump -h "$H"
echo
echo "================================================================ stream_list.atmosphere.wind_energy (production leg 2021)"
echo "## target: $(readlink -f "$S/20211101_20211201/stream_list.atmosphere.wind_energy")"
echo "## lines (incl. last line without newline): $(awk 'END{print NR}' "$S/20211101_20211201/stream_list.atmosphere.wind_energy")"
cat "$S/20211101_20211201/stream_list.atmosphere.wind_energy"; echo
echo "## 2022 leg list identical to 2021: $(cmp -s "$S/20211101_20211201/stream_list.atmosphere.wind_energy" "$S/20221001_20221101/stream_list.atmosphere.wind_energy" && echo yes || echo NO)"
echo "## streams.atmosphere (output stream) in both legs:"
for leg in $LEGS; do printf "%s: %s\n" "$leg" "$(readlink -f "$S/$leg/streams.atmosphere")"; done
grep -A6 '<stream name="output"' "$S/streams.atmosphere"
echo "# end $(ts)"
