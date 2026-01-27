#!/usr/bin/env bash
# tile_osm_vm.sh - VM-optimized OSM PBF tiling (bounded RAM) using osmium-tool
#
# Key idea:
# - Filter once to highways-only (much smaller file)
# - Recursively split the PBF into variable-sized tiles based on file size
# - Each leaf tile is written/uploaded with bbox-based filenames
#
# Usage:
#   ./tile_osm_vm.sh <region|/path/to/input.osm.pbf> [gcs_path]
#
# Examples:
#   ./tile_osm_vm.sh europe
#   OUTPUT_DIR=/mnt/disks/ssd/osm_tiles SPLIT_GRID_N=auto TARGET_LEAF_BYTES=1073741824 ./tile_osm_vm.sh europe gs://rsp_graph_data_test/v2/osm_tiles
#   ./tile_osm_vm.sh /data/europe-latest.osm.pbf gs://rsp_graph_data_test/v2/osm_tiles
#
# Requirements:
#   osmium-tool, bc, curl, python3, (optional) gsutil
#
set -euo pipefail

# --- Tunables (safe defaults) ---
OVERLAP_KM="${OVERLAP_KM:-2.0}"
OUTPUT_DIR="${OUTPUT_DIR:-./osm_tiles}"

# Recursive split controls (recursive mode is the only mode).
SPLIT_GRID_N="${SPLIT_GRID_N:-auto}" # integer or "auto"
MIN_SPLIT_GRID_N="${MIN_SPLIT_GRID_N:-1}"
MAX_SPLIT_GRID_N="${MAX_SPLIT_GRID_N:-10}"
TARGET_LEAF_BYTES="${TARGET_LEAF_BYTES:-1073741824}" # 1 GiB
SUPERTILE_OVERLAP_KM="${SUPERTILE_OVERLAP_KM:-${OVERLAP_KM}}"

# Download caching (only applies when the first arg is a supported region name).
# Cached file path defaults to: "$OUTPUT_DIR/.cache/<region>-latest.osm.pbf"
CACHE_DIR="${CACHE_DIR:-}"
FORCE_DOWNLOAD="${FORCE_DOWNLOAD:-false}" # set to "true" to re-download even if cached

# When true, asks osmium to write bounds into output files (a bit slower).
SET_BOUNDS="${SET_BOUNDS:-false}"

# If non-empty, tries to raise open-file limit (useful for large extracts).
RAISE_NOFILE="${RAISE_NOFILE:-}"

HIGHWAY_TYPES="${HIGHWAY_TYPES:-motorway,trunk,primary,secondary,tertiary,unclassified,residential,motorway_link,trunk_link,primary_link,secondary_link,tertiary_link,living_street,service,road}"

log() { echo "[$(date '+%H:%M:%S')] $*" >&2; }
die() { echo "ERROR: $*" >&2; exit 1; }

get_geofabrik_url() {
  case "$1" in
    mazowieckie) echo "https://download.geofabrik.de/europe/poland/mazowieckie-latest.osm.pbf" ;;
    poland) echo "https://download.geofabrik.de/europe/poland-latest.osm.pbf" ;;
    europe) echo "https://download.geofabrik.de/europe-latest.osm.pbf" ;;
    *) die "Unknown region: $1. Supported: mazowieckie, poland, europe" ;;
  esac
}

# Approximate download sizes in GB for disk space checking
get_approx_size_gb() {
  case "$1" in
    mazowieckie) echo "0.2" ;;
    poland) echo "2" ;;
    europe) echo "30" ;;
    *) echo "1" ;;
  esac
}

fmt_coord() {
  # Matches the original script’s convention: '.' -> '_' and '-' -> 'm'
  echo "$1" | sed 's/\./_/g; s/-/m/g'
}

check_disk_space() {
  local dir="$1"
  local required_gb="$2"

  local available_gb
  available_gb=$(df -BG "$dir" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}' || echo "0")

  log "Disk space check: ${available_gb}GB available, ~${required_gb}GB required (download + working files)"
  if (( $(echo "$available_gb < $required_gb" | bc -l) )); then
    die "Not enough disk space in $dir. Need ~${required_gb}GB, have ${available_gb}GB"
  fi
}

maybe_raise_nofile() {
  [[ -z "${RAISE_NOFILE}" ]] && return 0
  # Best effort: if not permitted, keep going.
  ulimit -n "${RAISE_NOFILE}" 2>/dev/null || true
  log "ulimit -n is now: $(ulimit -n 2>/dev/null || echo '?')"
}

choose_split_grid_n() {
  # Args: size_bytes
  local size_bytes="$1"
  if [[ "$SPLIT_GRID_N" != "auto" ]]; then
    echo "$SPLIT_GRID_N"
    return 0
  fi
  python3 - "$size_bytes" "$TARGET_LEAF_BYTES" "$MIN_SPLIT_GRID_N" "$MAX_SPLIT_GRID_N" <<'PY'
import math, sys
size_bytes = max(1, int(sys.argv[1]))
target = max(1, int(sys.argv[2]))
min_n = max(1, int(sys.argv[3]))
max_n = max(min_n, int(sys.argv[4]))
raw = math.ceil(math.sqrt(size_bytes / target))
value = max(min_n, min(max_n, raw))
print(value)
PY
}

tile_filename() {
  # Args: min_lon min_lat max_lon max_lat
  local min_lon="$1"
  local min_lat="$2"
  local max_lon="$3"
  local max_lat="$4"
  local fn_min_lat fn_min_lon fn_max_lat fn_max_lon
  fn_min_lat=$(fmt_coord "$min_lat")
  fn_min_lon=$(fmt_coord "$min_lon")
  fn_max_lat=$(fmt_coord "$max_lat")
  fn_max_lon=$(fmt_coord "$max_lon")
  echo "tile_${fn_min_lat}_${fn_min_lon}_${fn_max_lat}_${fn_max_lon}.osm.pbf"
}

expanded_bbox() {
  # Args: core_min_lon core_min_lat core_max_lon core_max_lat
  local core_min_lon="$1"
  local core_min_lat="$2"
  local core_max_lon="$3"
  local core_max_lat="$4"
  local e_min_lon e_min_lat e_max_lon e_max_lat
  e_min_lon=$(python3 - "$core_min_lon" "$SUPERTILE_OVERLAP_DEG" "$ROOT_MIN_LON" "$ROOT_MAX_LON" <<'PY'
import sys
val = float(sys.argv[1]) - float(sys.argv[2])
lo = float(sys.argv[3]); hi = float(sys.argv[4])
print(f"{max(lo, min(hi, val)):.6f}")
PY
)
  e_max_lon=$(python3 - "$core_max_lon" "$SUPERTILE_OVERLAP_DEG" "$ROOT_MIN_LON" "$ROOT_MAX_LON" <<'PY'
import sys
val = float(sys.argv[1]) + float(sys.argv[2])
lo = float(sys.argv[3]); hi = float(sys.argv[4])
print(f"{max(lo, min(hi, val)):.6f}")
PY
)
  e_min_lat=$(python3 - "$core_min_lat" "$SUPERTILE_OVERLAP_DEG" "$ROOT_MIN_LAT" "$ROOT_MAX_LAT" <<'PY'
import sys
val = float(sys.argv[1]) - float(sys.argv[2])
lo = float(sys.argv[3]); hi = float(sys.argv[4])
print(f"{max(lo, min(hi, val)):.6f}")
PY
)
  e_max_lat=$(python3 - "$core_max_lat" "$SUPERTILE_OVERLAP_DEG" "$ROOT_MIN_LAT" "$ROOT_MAX_LAT" <<'PY'
import sys
val = float(sys.argv[1]) + float(sys.argv[2])
lo = float(sys.argv[3]); hi = float(sys.argv[4])
print(f"{max(lo, min(hi, val)):.6f}")
PY
)
  echo "$e_min_lon,$e_min_lat,$e_max_lon,$e_max_lat"
}

split_node() {
  # Args: node_id input_pbf min_lon min_lat max_lon max_lat
  local node_id="$1"
  local input_pbf="$2"
  local min_lon="$3"
  local min_lat="$4"
  local max_lon="$5"
  local max_lat="$6"

  local size_bytes
  size_bytes=$(stat -c%s "$input_pbf" 2>/dev/null || wc -c < "$input_pbf")

  local grid_n
  grid_n="$(choose_split_grid_n "$size_bytes")"
  if (( grid_n < 2 )); then
    local out_name out_path expanded
    expanded="$(expanded_bbox "$min_lon" "$min_lat" "$max_lon" "$max_lat")"
    IFS=',' read -r e_min_lon e_min_lat e_max_lon e_max_lat <<< "$expanded"
    out_name="$(tile_filename "$e_min_lon" "$e_min_lat" "$e_max_lon" "$e_max_lat")"
    out_path="$OUTPUT_DIR/$out_name"
    if [[ -n "$gcs_path" ]]; then
      gsutil cp "$input_pbf" "$gcs_path/$out_name"
      rm -f "$input_pbf"
    else
      mv -f "$input_pbf" "$out_path"
    fi
    return 0
  fi

  local node_dir child_specs child_config
  node_dir="$work_dir/split_${node_id}"
  mkdir -p "$node_dir"
  child_specs="$node_dir/children.tsv"
  child_config="$node_dir/children.json"

  python3 - "$child_specs" "$child_config" "$node_dir" \
    "$min_lon" "$min_lat" "$max_lon" "$max_lat" "$grid_n" "$SUPERTILE_OVERLAP_DEG" \
    "$ROOT_MIN_LON" "$ROOT_MIN_LAT" "$ROOT_MAX_LON" "$ROOT_MAX_LAT" <<'PY'
import json
import math
import os
import sys

child_specs, child_config, node_dir = sys.argv[1:4]
min_lon, min_lat, max_lon, max_lat = map(float, sys.argv[4:8])
grid_n = int(sys.argv[8])
overlap = float(sys.argv[9])
root_min_lon, root_min_lat, root_max_lon, root_max_lat = map(float, sys.argv[10:14])

lon_step = (max_lon - min_lon) / grid_n
lat_step = (max_lat - min_lat) / grid_n

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def fmt_coord(value: float) -> str:
    return f"{value:.6f}".replace(".", "_").replace("-", "m")

extracts = []
with open(child_specs, "w", encoding="utf-8") as specs:
    for child_id in range(grid_n * grid_n):
        iy, ix = divmod(child_id, grid_n)
        c_min_lon = min_lon + ix * lon_step
        c_max_lon = min_lon + (ix + 1) * lon_step
        c_min_lat = min_lat + iy * lat_step
        c_max_lat = min_lat + (iy + 1) * lat_step

        e_min_lon = clamp(c_min_lon - overlap, root_min_lon, root_max_lon)
        e_max_lon = clamp(c_max_lon + overlap, root_min_lon, root_max_lon)
        e_min_lat = clamp(c_min_lat - overlap, root_min_lat, root_max_lat)
        e_max_lat = clamp(c_max_lat + overlap, root_min_lat, root_max_lat)

        out_name = (
            f"tile_{fmt_coord(e_min_lat)}_{fmt_coord(e_min_lon)}_"
            f"{fmt_coord(e_max_lat)}_{fmt_coord(e_max_lon)}.osm.pbf"
        )
        child_pbf = os.path.join(node_dir, out_name)

        specs.write(f"{child_id}\t{child_pbf}\t{c_min_lon},{c_min_lat},{c_max_lon},{c_max_lat}\n")
        extracts.append(
            {
                "output": child_pbf,
                "bbox": [e_min_lon, e_min_lat, e_max_lon, e_max_lat],
            }
        )

with open(child_config, "w", encoding="utf-8") as out:
    json.dump({"extracts": extracts}, out)
PY

  log "Splitting node $node_id into ${grid_n}x${grid_n} (size=$(du -h "$input_pbf" | cut -f1))"
  osmium extract -c "$child_config" "$input_pbf" --overwrite

  while IFS=$'\t' read -r child_id child_pbf child_bbox; do
    IFS=',' read -r c_min_lon c_min_lat c_max_lon c_max_lat <<< "$child_bbox"
    split_node "${node_id}_${child_id}" "$child_pbf" "$c_min_lon" "$c_min_lat" "$c_max_lon" "$c_max_lat"
  done < "$child_specs"
}

main() {
  command -v osmium >/dev/null 2>&1 || die "osmium-tool not found. Install with: apt install osmium-tool"
  command -v bc >/dev/null 2>&1 || die "bc not found. Install with: apt install bc"
  command -v curl >/dev/null 2>&1 || die "curl not found. Install with: apt install curl"
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install with: apt install python3"

  local region_or_file="${1:-}"
  local gcs_path="${2:-}"
  [[ -z "$region_or_file" ]] && die "Usage: $0 <region|/path/to/input.osm.pbf> [gcs_path]"

  mkdir -p "$OUTPUT_DIR"
  check_disk_space "$OUTPUT_DIR" "10"
  maybe_raise_nofile

  # Use work directory inside OUTPUT_DIR to avoid /tmp space issues
  local work_dir="$OUTPUT_DIR/.work_vm_$$"
  mkdir -p "$work_dir"
  trap "rm -rf '$work_dir'" EXIT
  log "Using work directory: $work_dir"

  # Determine input PBF (download if region)
  local input_pbf=""
  if [[ -f "$region_or_file" ]] && [[ "$region_or_file" == *.pbf ]]; then
    input_pbf="$region_or_file"
    log "Using local input PBF: $input_pbf"
  else
    local url approx_size required_space
    url=$(get_geofabrik_url "$region_or_file")
    approx_size=$(get_approx_size_gb "$region_or_file")
    required_space=$(echo "$approx_size * 2.5" | bc)
    check_disk_space "$OUTPUT_DIR" "$required_space"

    local cache_dir cache_pbf cache_part
    cache_dir="${CACHE_DIR:-$OUTPUT_DIR/.cache}"
    mkdir -p "$cache_dir"

    cache_pbf="$cache_dir/${region_or_file}-latest.osm.pbf"
    cache_part="$cache_pbf.part"

    if [[ "$FORCE_DOWNLOAD" == "true" ]]; then
      log "FORCE_DOWNLOAD=true: removing cached download (if any)."
      rm -f "$cache_pbf" "$cache_part"
    fi

    if [[ -s "$cache_pbf" ]]; then
      input_pbf="$cache_pbf"
      log "Using cached PBF: $input_pbf ($(du -h "$input_pbf" | cut -f1))"
    else
      input_pbf="$cache_pbf"
      log "Downloading $region_or_file (~${approx_size}GB) from $url..."
      log "Caching download at: $cache_pbf"
      # Resume if a partial download exists.
      curl -# -L -f -C - -o "$cache_part" "$url" || die "Download failed. Check network connection and disk space."
      mv -f "$cache_part" "$cache_pbf"
      log "Download complete: $(du -h "$cache_pbf" | cut -f1)"
    fi
  fi

  # Filter to highways only - reduces file size substantially
  local highways_file="$work_dir/highways.osm.pbf"
  log "Filtering to driveable highways..."
  local filter_expr=""
  IFS=',' read -ra types <<< "$HIGHWAY_TYPES"
  for type in "${types[@]}"; do
    filter_expr="${filter_expr}w/highway=${type} "
  done
  osmium tags-filter "$input_pbf" $filter_expr -o "$highways_file" --overwrite

  # If we downloaded the input, remove it to free disk
  if [[ "$input_pbf" == "$work_dir/"* ]]; then
    rm -f "$input_pbf"
  fi
  log "Filtered to highways: $(du -h "$highways_file" | cut -f1)"

  # Get bounds
  local box_str bbox min_lon min_lat max_lon max_lat
  box_str=$(osmium fileinfo -g header.boxes "$highways_file" 2>/dev/null | head -1 || echo "")
  [[ -z "$box_str" ]] && die "Cannot determine bounds from PBF"
  bbox=$(echo "$box_str" | tr -d '()' | tr ',' ' ' | awk '{print $1","$2","$3","$4}')
  IFS=',' read -r min_lon min_lat max_lon max_lat <<< "$bbox"
  log "Bounds: ($min_lon, $min_lat) → ($max_lon, $max_lat)"

  # Calculate overlap in degrees
  local supertile_overlap_deg
  supertile_overlap_deg=$(echo "scale=6; $SUPERTILE_OVERLAP_KM / 111.32" | bc)

  # If uploading, we upload+delete outputs to keep disk usage bounded.
  if [[ -n "$gcs_path" ]]; then
    command -v gsutil >/dev/null 2>&1 || die "gsutil not found. Install Google Cloud SDK or run without gcs_path."
    log "Will upload and delete outputs to: $gcs_path"
  fi

  ROOT_MIN_LON="$min_lon"
  ROOT_MIN_LAT="$min_lat"
  ROOT_MAX_LON="$max_lon"
  ROOT_MAX_LAT="$max_lat"
  SUPERTILE_OVERLAP_DEG="$supertile_overlap_deg"
  log "Recursive split enabled: grid=${SPLIT_GRID_N}, target_leaf_bytes=${TARGET_LEAF_BYTES}"
  split_node "root" "$highways_file" "$min_lon" "$min_lat" "$max_lon" "$max_lat"

  if [[ -n "$gcs_path" ]]; then
    log "✓ Finished tiling (uploaded to $gcs_path)"
  else
    log "✓ Finished tiling into $OUTPUT_DIR"
  fi
}

main "$@"
