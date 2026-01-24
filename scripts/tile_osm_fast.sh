#!/bin/bash
# tile_osm_fast.sh - Memory-efficient OSM PBF tiling using osmium-tool
#
# Usage:
#   ./tile_osm_fast.sh <region> [gcs_path]
#
# Examples:
#   ./tile_osm_fast.sh mazowieckie
#   ./tile_osm_fast.sh poland gs://rsp_graph_data/osm_tiles
#
# Supported regions: mazowieckie, poland, europe
#
# Requirements: osmium-tool, bc, curl

set -euo pipefail

TILE_SIZE_DEG=0.5
OVERLAP_KM=2.0
OUTPUT_DIR="./osm_tiles"

HIGHWAY_TYPES="motorway,trunk,primary,secondary,tertiary,unclassified,residential,motorway_link,trunk_link,primary_link,secondary_link,tertiary_link,living_street,service,road"

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
    echo "$1" | sed 's/\./_/g; s/-/m/g'
}

check_disk_space() {
    local dir="$1"
    local required_gb="$2"
    
    # Get available space in GB
    local available_gb
    available_gb=$(df -BG "$dir" 2>/dev/null | awk 'NR==2 {gsub("G",""); print $4}' || echo "0")
    
    log "Disk space check: ${available_gb}GB available, ~${required_gb}GB required (download + working files)"
    
    if (( $(echo "$available_gb < $required_gb" | bc -l) )); then
        die "Not enough disk space in $dir. Need ~${required_gb}GB, have ${available_gb}GB"
    fi
}

main() {
    command -v osmium >/dev/null 2>&1 || die "osmium-tool not found. Install with: apt install osmium-tool"
    command -v bc >/dev/null 2>&1 || die "bc not found. Install with: apt install bc"

    local region="${1:-}"
    local gcs_path="${2:-}"
    
    [[ -z "$region" ]] && die "Usage: $0 <region> [gcs_path]\n  Regions: mazowieckie, poland, europe"

    mkdir -p "$OUTPUT_DIR"
    
    # Use work directory inside OUTPUT_DIR to avoid /tmp space issues
    local work_dir="$OUTPUT_DIR/.work_$$"
    mkdir -p "$work_dir"
    trap "rm -rf '$work_dir'" EXIT
    log "Using work directory: $work_dir"

    # Check disk space (need ~2x download size for download + filtered file)
    local approx_size
    approx_size=$(get_approx_size_gb "$region")
    local required_space
    required_space=$(echo "$approx_size * 2.5" | bc)
    check_disk_space "$OUTPUT_DIR" "$required_space"

    # Download PBF
    local pbf_file="$work_dir/input.osm.pbf"
    local url
    url=$(get_geofabrik_url "$region")
    log "Downloading $region (~${approx_size}GB) from $url..."
    curl -# -L -f -o "$pbf_file" "$url" || die "Download failed. Check network connection and disk space."
    log "Download complete: $(du -h "$pbf_file" | cut -f1)"

    # Filter to highways only - this dramatically reduces file size
    local highways_file="$work_dir/highways.osm.pbf"
    log "Filtering to driveable highways..."
    local filter_expr=""
    IFS=',' read -ra types <<< "$HIGHWAY_TYPES"
    for type in "${types[@]}"; do
        filter_expr="${filter_expr}w/highway=${type} "
    done
    osmium tags-filter "$pbf_file" $filter_expr -o "$highways_file" --overwrite
    
    # Remove original to free disk space
    rm "$pbf_file"
    log "Filtered to highways: $(du -h "$highways_file" | cut -f1)"

    # Get bounds
    local box_str
    box_str=$(osmium fileinfo -g header.boxes "$highways_file" 2>/dev/null | head -1 || echo "")
    [[ -z "$box_str" ]] && die "Cannot determine bounds from PBF"
    local bbox
    bbox=$(echo "$box_str" | tr -d '()' | tr ',' ' ' | awk '{print $1","$2","$3","$4}')
    IFS=',' read -r min_lon min_lat max_lon max_lat <<< "$bbox"
    log "Bounds: ($min_lon, $min_lat) → ($max_lon, $max_lat)"

    # Calculate overlap in degrees
    local overlap_deg
    overlap_deg=$(echo "scale=6; $OVERLAP_KM / 111.32" | bc)

    # Generate tile list
    local tiles_file="$work_dir/tiles.txt"
    python3 - "$min_lon" "$min_lat" "$max_lon" "$max_lat" "$TILE_SIZE_DEG" "$overlap_deg" > "$tiles_file" << 'PYTHON'
import sys
min_lon, min_lat, max_lon, max_lat = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
tile_size, overlap = float(sys.argv[5]), float(sys.argv[6])
lat = min_lat
while lat < max_lat:
    lon = min_lon
    while lon < max_lon:
        t_min_lat, t_min_lon = lat - overlap, lon - overlap
        t_max_lat = min(lat + tile_size, max_lat) + overlap
        t_max_lon = min(lon + tile_size, max_lon) + overlap
        # Output: min_lon,min_lat,max_lon,max_lat
        print(f"{t_min_lon},{t_min_lat},{t_max_lon},{t_max_lat}")
        lon = min(lon + tile_size, max_lon) if lon + tile_size < max_lon else max_lon + 1
    lat = min(lat + tile_size, max_lat) if lat + tile_size < max_lat else max_lat + 1
PYTHON

    local tile_count
    tile_count=$(wc -l < "$tiles_file")
    log "Will create $tile_count tiles (one at a time for low memory usage)"

    # Extract tiles ONE AT A TIME to minimize memory usage
    local i=0
    while IFS=',' read -r t_min_lon t_min_lat t_max_lon t_max_lat; do
        i=$((i + 1))
        
        # Format coordinates for filename
        local fn_min_lat fn_min_lon fn_max_lat fn_max_lon
        fn_min_lat=$(fmt_coord "$t_min_lat")
        fn_min_lon=$(fmt_coord "$t_min_lon")
        fn_max_lat=$(fmt_coord "$t_max_lat")
        fn_max_lon=$(fmt_coord "$t_max_lon")
        
        local output_file="$OUTPUT_DIR/tile_${fn_min_lat}_${fn_min_lon}_${fn_max_lat}_${fn_max_lon}.osm.pbf"
        
        log "[$i/$tile_count] Extracting tile..."
        osmium extract -b "$t_min_lon,$t_min_lat,$t_max_lon,$t_max_lat" \
            "$highways_file" -o "$output_file" --overwrite --set-bounds
    done < "$tiles_file"

    log "✓ Created $tile_count tiles in $OUTPUT_DIR"

    # Upload to GCS if specified
    if [[ -n "$gcs_path" ]]; then
        log "Uploading to $gcs_path..."
        gsutil -m cp "$OUTPUT_DIR"/*.osm.pbf "$gcs_path/"
        log "✓ Upload complete"
    fi

    log "Done!"
}

main "$@"
