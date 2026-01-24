#!/usr/bin/env python3
"""
Download and tile OSM PBF data into overlapping extracts.

This script fetches a Geofabrik extract (or uses a local PBF) and produces
overlapping tiles with adaptive subdivision so no tile exceeds a target size.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.request import urlretrieve

import osmium

DEFAULT_TILE_SIZE_DEG = 0.5
DEFAULT_OVERLAP_KM = 2.0
DEFAULT_MAX_TILE_MB = 500
DEFAULT_MAX_DEPTH = 8
DEFAULT_MIN_TILE_DEG = 0.05


def _unique_path(parent: Path, suffix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return parent / f"{uuid.uuid4().hex}{suffix}"


def get_geofabrik_url(region: str) -> str:
    region_mappings = {
        "poland": "europe/poland",
        "london": "europe/united-kingdom/england/greater-london",
    }
    region_lower = region.lower().replace(" ", "-")
    full_region = region_mappings.get(region_lower, region_lower)
    return f"https://download.geofabrik.de/{full_region}-latest.osm.pbf"


def download_pbf(url: str, output_path: Path) -> None:
    print(f"Downloading from {url}...")

    def progress_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100, downloaded * 100 / total_size)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(
                f"\rProgress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)"
            )
            sys.stdout.flush()

    urlretrieve(url, output_path, reporthook=progress_hook)
    print("\nDownload complete!")


def parse_bbox(value: str) -> Tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be min_lat,min_lon,max_lat,max_lon")
    return parts[0], parts[1], parts[2], parts[3]


def get_pbf_bounds(pbf_path: Path) -> Optional[Tuple[float, float, float, float]]:
    try:
        reader = osmium.io.Reader(str(pbf_path))
        header = reader.header()
        box = header.box()
        reader.close()
        if box is None or not box.valid():
            return None
        return box.bottom_left.lat, box.bottom_left.lon, box.top_right.lat, box.top_right.lon
    except Exception:
        return None


def bbox_intervals(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, tile_size: float
) -> Iterable[Tuple[float, float, float, float]]:
    lat = min_lat
    while lat < max_lat:
        lat_next = min(lat + tile_size, max_lat)
        lon = min_lon
        while lon < max_lon:
            lon_next = min(lon + tile_size, max_lon)
            yield lat, lon, lat_next, lon_next
            lon = lon_next
        lat = lat_next


def expand_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, overlap_km: float
) -> Tuple[float, float, float, float]:
    lat_center = (min_lat + max_lat) / 2.0
    dlat = overlap_km / 111.32
    dlon = overlap_km / (111.32 * math.cos(math.radians(lat_center)))
    return min_lat - dlat, min_lon - dlon, max_lat + dlat, max_lon + dlon


def format_coord(value: float) -> str:
    return f"{value:.4f}".replace(".", "p")


def tile_name(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> str:
    return (
        f"tile_{format_coord(min_lat)}_{format_coord(min_lon)}"
        f"_{format_coord(max_lat)}_{format_coord(max_lon)}.osm.pbf"
    )


def _in_bbox(lat: float, lon: float, bbox: Tuple[float, float, float, float]) -> bool:
    min_lat, min_lon, max_lat, max_lon = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


class _BboxSizeWriter(osmium.SimpleHandler):
    def __init__(self, bbox: Tuple[float, float, float, float], writer: osmium.SimpleWriter):
        super().__init__()
        self.bbox = bbox
        self.writer = writer

    def node(self, n):
        if n.location and _in_bbox(n.location.lat, n.location.lon, self.bbox):
            self.writer.add_node(n)

    def way(self, w):
        for node in w.nodes:
            if node.location and _in_bbox(node.location.lat, node.location.lon, self.bbox):
                self.writer.add_way(w)
                return


def estimate_bbox_size_mb(
    pbf_path: Path, bbox: Tuple[float, float, float, float], work_dir: Path
) -> float:
    tmp_path = None
    try:
        tmp_path = _unique_path(work_dir / "size_estimates", suffix=".osm.pbf")
        writer = osmium.SimpleWriter(str(tmp_path))
        handler = _BboxSizeWriter(bbox, writer)
        handler.apply_file(str(pbf_path), locations=True)
        writer.close()
        size_mb = tmp_path.stat().st_size / (1024 * 1024)
        return size_mb
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


class _NodeInBboxCollector(osmium.SimpleHandler):
    def __init__(self, bbox: Tuple[float, float, float, float]):
        super().__init__()
        self.bbox = bbox
        self.node_ids: set[int] = set()

    def node(self, n):
        if n.location and _in_bbox(n.location.lat, n.location.lon, self.bbox):
            self.node_ids.add(int(n.id))


class _WayCollector(osmium.SimpleHandler):
    def __init__(self, nodes_in_bbox: set[int]):
        super().__init__()
        self.nodes_in_bbox = nodes_in_bbox
        self.required_node_ids: set[int] = set()
        self.way_ids: set[int] = set()

    def way(self, w):
        refs = [int(node.ref) for node in w.nodes]
        if any(ref in self.nodes_in_bbox for ref in refs):
            self.way_ids.add(int(w.id))
            self.required_node_ids.update(refs)


class _NodeWriter(osmium.SimpleHandler):
    def __init__(self, writer: osmium.SimpleWriter, required_node_ids: set[int]):
        super().__init__()
        self.writer = writer
        self.required_node_ids = required_node_ids

    def node(self, n):
        if int(n.id) in self.required_node_ids:
            self.writer.add_node(n)


class _WayWriter(osmium.SimpleHandler):
    def __init__(self, writer: osmium.SimpleWriter, way_ids: set[int]):
        super().__init__()
        self.writer = writer
        self.way_ids = way_ids

    def way(self, w):
        if int(w.id) in self.way_ids:
            self.writer.add_way(w)


def write_complete_tile(
    pbf_path: Path, output_path: Path, bbox: Tuple[float, float, float, float]
) -> None:
    node_collector = _NodeInBboxCollector(bbox)
    node_collector.apply_file(str(pbf_path), locations=True)

    way_collector = _WayCollector(node_collector.node_ids)
    way_collector.apply_file(str(pbf_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = osmium.SimpleWriter(str(output_path))
    _NodeWriter(writer, way_collector.required_node_ids).apply_file(str(pbf_path))
    _WayWriter(writer, way_collector.way_ids).apply_file(str(pbf_path))
    writer.close()


def subdivide_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> Iterable[Tuple[float, float, float, float]]:
    mid_lat = (min_lat + max_lat) / 2.0
    mid_lon = (min_lon + max_lon) / 2.0
    return [
        (min_lat, min_lon, mid_lat, mid_lon),
        (min_lat, mid_lon, mid_lat, max_lon),
        (mid_lat, min_lon, max_lat, mid_lon),
        (mid_lat, mid_lon, max_lat, max_lon),
    ]


def collect_leaf_tiles(
    pbf_path: Path,
    bbox: Tuple[float, float, float, float],
    max_tile_mb: float,
    max_depth: int,
    min_tile_deg: float,
    work_dir: Path,
    depth: int = 0,
) -> Iterable[Tuple[float, float, float, float]]:
    min_lat, min_lon, max_lat, max_lon = bbox
    tile_lat = max_lat - min_lat
    tile_lon = max_lon - min_lon
    if depth >= max_depth or (tile_lat <= min_tile_deg and tile_lon <= min_tile_deg):
        return [bbox]

    size_mb = estimate_bbox_size_mb(pbf_path, bbox, work_dir=work_dir)
    if size_mb <= max_tile_mb:
        return [bbox]

    leafs: list[Tuple[float, float, float, float]] = []
    for child in subdivide_bbox(min_lat, min_lon, max_lat, max_lon):
        leafs.extend(
            collect_leaf_tiles(
                pbf_path,
                child,
                max_tile_mb=max_tile_mb,
                max_depth=max_depth,
                min_tile_deg=min_tile_deg,
                work_dir=work_dir,
                depth=depth + 1,
            )
        )
    return leafs


def main():
    parser = argparse.ArgumentParser(
        description="Download and tile OSM PBF data into overlapping extracts."
    )
    parser.add_argument(
        "region",
        help="Geofabrik region (e.g., europe/poland) or local file path with --local",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Treat region argument as a local .osm.pbf path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./osm_tiles"),
        help="Output directory for tiles (default: ./osm_tiles)",
    )
    parser.add_argument(
        "--tile-size-deg",
        type=float,
        default=DEFAULT_TILE_SIZE_DEG,
        help="Base tile size in degrees (default: 0.5)",
    )
    parser.add_argument(
        "--overlap-km",
        type=float,
        default=DEFAULT_OVERLAP_KM,
        help="Overlap in kilometers (default: 2)",
    )
    parser.add_argument(
        "--max-tile-mb",
        type=float,
        default=DEFAULT_MAX_TILE_MB,
        help="Maximum tile size in MB before subdivision (default: 500)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help="Max subdivision depth (default: 8)",
    )
    parser.add_argument(
        "--min-tile-size-deg",
        type=float,
        default=DEFAULT_MIN_TILE_DEG,
        help="Minimum tile size in degrees (default: 0.05)",
    )
    parser.add_argument(
        "--keep-pbf",
        action="store_true",
        help="Keep the downloaded PBF file after processing",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="Directory to store downloaded PBF (default: <output-dir>/_downloads)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory for temporary files (default: <output-dir>/_work)",
    )
    parser.add_argument(
        "--bbox",
        type=str,
        default=None,
        help="Override bounds as min_lat,min_lon,max_lat,max_lon",
    )

    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    download_dir = args.download_dir or (args.output_dir / "_downloads")
    work_dir = args.work_dir or (args.output_dir / "_work")
    download_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = None
    if args.local:
        pbf_path = Path(args.region)
        if not pbf_path.exists():
            print(f"Error: File not found: {pbf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        url = get_geofabrik_url(args.region)
        if args.keep_pbf:
            pbf_path = download_dir / f"{args.region.replace('/', '-')}-latest.osm.pbf"
        else:
            # Keep downloads off /tmp by default; store in output_dir work area.
            temp_dir = tempfile.mkdtemp(dir=str(work_dir))
            pbf_path = Path(temp_dir) / "data.osm.pbf"
        try:
            pbf_path.parent.mkdir(parents=True, exist_ok=True)
            download_pbf(url, pbf_path)
        except Exception as exc:
            print(f"Error downloading data: {exc}", file=sys.stderr)
            print(f"URL attempted: {url}", file=sys.stderr)
            sys.exit(1)

    bounds = parse_bbox(args.bbox) if args.bbox else get_pbf_bounds(pbf_path)
    if not bounds:
        print(
            "Error: Unable to determine bounds from PBF header. "
            "Please provide --bbox=min_lat,min_lon,max_lat,max_lon.",
            file=sys.stderr,
        )
        sys.exit(1)

    min_lat, min_lon, max_lat, max_lon = bounds
    print(f"Bounds: {min_lat},{min_lon} -> {max_lat},{max_lon}")
    base_tiles = list(
        bbox_intervals(
            min_lat, min_lon, max_lat, max_lon, tile_size=args.tile_size_deg
        )
    )
    print(f"Base tiles: {len(base_tiles)}")

    leaf_tiles: list[Tuple[float, float, float, float]] = []
    for idx, tile in enumerate(base_tiles, start=1):
        print(f"[{idx}/{len(base_tiles)}] Checking tile {tile}...")
        leaf_tiles.extend(
            collect_leaf_tiles(
                pbf_path,
                tile,
                max_tile_mb=args.max_tile_mb,
                max_depth=args.max_depth,
                min_tile_deg=args.min_tile_size_deg,
                work_dir=work_dir,
            )
        )
    print(f"Leaf tiles after subdivision: {len(leaf_tiles)}")

    for idx, tile in enumerate(leaf_tiles, start=1):
        expanded = expand_bbox(*tile, overlap_km=args.overlap_km)
        output_path = args.output_dir / tile_name(*expanded)
        print(f"[{idx}/{len(leaf_tiles)}] Writing {output_path}...")
        write_complete_tile(pbf_path, output_path, expanded)

    if temp_dir and not args.keep_pbf:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
