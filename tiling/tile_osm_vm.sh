#!/usr/bin/env bash
# tile_osm_vm.sh - VM-optimized OSM PBF tiling (bounded RAM) using osmium-tool
#
# Key idea:
# - Filter once to highways-only (much smaller file)
# - Extract tiles in BATCHES using `osmium extract -c <json>` (one pass per batch)
# - Optional bounded parallelism across batches
#
# Usage:
#   ./tile_osm_vm.sh <region|/path/to/input.osm.pbf> [gcs_path]
#
# Examples:
#   ./tile_osm_vm.sh europe
#   OUTPUT_DIR=/mnt/disks/ssd/osm_tiles BATCH_TILES=128 MAX_PROCS=2 ./tile_osm_vm.sh europe gs://rsp_graph_data_test/v2/osm_tiles
#   ./tile_osm_vm.sh /data/europe-latest.osm.pbf gs://rsp_graph_data_test/v2/osm_tiles
#
# Requirements:
#   osmium-tool, bc, curl, python3, coreutils (split), (optional) gsutil
#
set -euo pipefail

# --- Tunables (safe defaults) ---
TILE_SIZE_DEG="${TILE_SIZE_DEG:-0.5}"
OVERLAP_KM="${OVERLAP_KM:-2.0}"
OUTPUT_DIR="${OUTPUT_DIR:-./osm_tiles}"

# Hard bounds:
# - BATCH_TILES bounds the state osmium keeps for multi-extract.
# - MAX_PROCS bounds concurrent extract processes (CPU/IO/memory).
BATCH_TILES="${BATCH_TILES:-128}"
MAX_PROCS="${MAX_PROCS:-1}"

# Download caching (only applies when the first arg is a supported region name).
# Cached file path defaults to: "$OUTPUT_DIR/.cache/<region>-latest.osm.pbf"
CACHE_DIR="${CACHE_DIR:-}"
FORCE_DOWNLOAD="${FORCE_DOWNLOAD:-false}" # set to "true" to re-download even if cached

# When true, asks osmium to write bounds into output files (a bit slower).
SET_BOUNDS="${SET_BOUNDS:-false}"

# If non-empty, tries to raise open-file limit (useful for large BATCH_TILES).
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

write_extract_config_json() {
  # Args: tiles_csv output_json output_dir
  local tiles_csv="$1"
  local out_json="$2"
  local out_dir="$3"

  python3 - "$tiles_csv" "$out_json" "$out_dir" <<'PY'
import json, sys, os

tiles_csv, out_json, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]

def fmt_coord(s: str) -> str:
    return s.replace(".", "_").replace("-", "m")

extracts = []
with open(tiles_csv, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 4:
            raise ValueError(f"Bad tile line: {line!r}")
        min_lon_s, min_lat_s, max_lon_s, max_lat_s = (p.strip() for p in parts)
        out_name = (
            f"tile_{fmt_coord(min_lat_s)}_{fmt_coord(min_lon_s)}_"
            f"{fmt_coord(max_lat_s)}_{fmt_coord(max_lon_s)}.osm.pbf"
        )
        extracts.append(
            {
                "output": os.path.join(out_dir, out_name),
                "bbox": [float(min_lon_s), float(min_lat_s), float(max_lon_s), float(max_lat_s)],
            }
        )

cfg = {"extracts": extracts}
with open(out_json, "w", encoding="utf-8") as out:
    json.dump(cfg, out)
PY
}

wait_for_slot() {
  # Bounded parallelism without external deps; requires bash with wait -n.
  while (( $(jobs -pr | wc -l) >= MAX_PROCS )); do
    wait -n
  done
}

main() {
  command -v osmium >/dev/null 2>&1 || die "osmium-tool not found. Install with: apt install osmium-tool"
  command -v bc >/dev/null 2>&1 || die "bc not found. Install with: apt install bc"
  command -v curl >/dev/null 2>&1 || die "curl not found. Install with: apt install curl"
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install with: apt install python3"
  command -v split >/dev/null 2>&1 || die "split not found. Install with: apt install coreutils"

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
  local overlap_deg
  overlap_deg=$(echo "scale=6; $OVERLAP_KM / 111.32" | bc)

  # Generate tile list
  local tiles_file="$work_dir/tiles.csv"
  python3 - "$min_lon" "$min_lat" "$max_lon" "$max_lat" "$TILE_SIZE_DEG" "$overlap_deg" > "$tiles_file" << 'PYTHON'
import sys
min_lon, min_lat, max_lon, max_lat = map(float, sys.argv[1:5])
tile_size, overlap = float(sys.argv[5]), float(sys.argv[6])
lat = min_lat
while lat < max_lat:
    lon = min_lon
    while lon < max_lon:
        t_min_lat, t_min_lon = lat - overlap, lon - overlap
        t_max_lat = min(lat + tile_size, max_lat) + overlap
        t_max_lon = min(lon + tile_size, max_lon) + overlap
        print(f"{t_min_lon},{t_min_lat},{t_max_lon},{t_max_lat}")
        lon = min(lon + tile_size, max_lon) if lon + tile_size < max_lon else max_lon + 1
    lat = min(lat + tile_size, max_lat) if lat + tile_size < max_lat else max_lat + 1
PYTHON

  local tile_count
  tile_count=$(wc -l < "$tiles_file")
  log "Prepared $tile_count tiles. Extracting in batches of $BATCH_TILES with MAX_PROCS=$MAX_PROCS."

  # Split tiles into batches
  local batches_dir="$work_dir/batches"
  mkdir -p "$batches_dir"
  split -l "$BATCH_TILES" -d --additional-suffix=.csv "$tiles_file" "$batches_dir/batch_"

  # If uploading, we upload+delete each batch to keep disk usage bounded.
  if [[ -n "$gcs_path" ]]; then
    command -v gsutil >/dev/null 2>&1 || die "gsutil not found. Install Google Cloud SDK or run without gcs_path."
    log "Will upload and delete each batch to: $gcs_path"
  fi

  # Extract each batch in one pass over highways_file
  shopt -s nullglob
  local batch_tiles
  for batch_tiles in "$batches_dir"/batch_*.csv; do
    wait_for_slot
    (
      # Important: prevent subshells from running the parent's EXIT trap.
      # Otherwise, when a background batch exits (or gets OOM-killed), it could delete
      # the shared work_dir (including highways.osm.pbf) while other batches are running.
      trap - EXIT

      local batch_name config_json batch_out_dir
      batch_name="$(basename "$batch_tiles" .csv)"
      config_json="$batches_dir/${batch_name}.json"

      # If uploading, extract into a batch-specific temp dir; upload it; then delete it.
      # Otherwise, write outputs directly to OUTPUT_DIR.
      if [[ -n "$gcs_path" ]]; then
        batch_out_dir="$work_dir/out/$batch_name"
        mkdir -p "$batch_out_dir"
      else
        batch_out_dir="$OUTPUT_DIR"
      fi

      write_extract_config_json "$batch_tiles" "$config_json" "$batch_out_dir"
      log "Extracting $batch_name ($(wc -l < "$batch_tiles") tiles)..."
      if [[ "$SET_BOUNDS" == "true" ]]; then
        osmium extract -c "$config_json" "$highways_file" --overwrite --set-bounds
      else
        osmium extract -c "$config_json" "$highways_file" --overwrite
      fi
      log "Finished $batch_name"

      if [[ -n "$gcs_path" ]]; then
        if compgen -G "$batch_out_dir"/*.osm.pbf >/dev/null; then
          log "Uploading $batch_name..."
          gsutil -m cp "$batch_out_dir"/*.osm.pbf "$gcs_path/"
          rm -f "$batch_out_dir"/*.osm.pbf
        else
          log "No outputs found for $batch_name (skipping upload)."
        fi
        rm -rf "$batch_out_dir"
        log "Uploaded+deleted $batch_name"
      fi
    ) &
  done
  wait
  shopt -u nullglob

  if [[ -n "$gcs_path" ]]; then
    log "✓ Finished tiling (uploaded per batch to $gcs_path)"
  else
    log "✓ Finished tiling into $OUTPUT_DIR"
  fi
}

main "$@"
