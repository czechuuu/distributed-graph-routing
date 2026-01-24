#!/usr/bin/env python3
"""
Memory-efficient OSM processing script for large regions.

This script downloads OSM data from Geofabrik and processes it using pyosmium
for streaming (constant memory usage regardless of file size).

Usage:
    python process_osm.py <region> [--output-dir <dir>]

Examples:
    python process_osm.py poland
    python process_osm.py germany --output-dir ./data
    python process_osm.py europe/france
"""

import argparse
import math
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

import osmium
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import storage


# Highway types that are driveable (for road network)
DRIVEABLE_HIGHWAY_TYPES = {
    'motorway', 'trunk', 'primary', 'secondary', 'tertiary',
    'unclassified', 'residential', 'motorway_link', 'trunk_link',
    'primary_link', 'secondary_link', 'tertiary_link', 'living_street',
    'service', 'road'
}


def get_geofabrik_url(region: str) -> str:
    """
    Get the Geofabrik download URL for a region.
    
    Args:
        region: Region name (e.g., 'poland', 'germany', 'europe/france')
    
    Returns:
        URL to download the .osm.pbf file
    """
    # Common region mappings to full paths
    region_mappings = {
        'poland': 'europe/poland',
        'london': 'europe/united-kingdom/england/greater-london',
    }
    
    # Normalize region name
    region_lower = region.lower().replace(' ', '-')
    full_region = region_mappings.get(region_lower, region_lower)
    
    return f"https://download.geofabrik.de/{full_region}-latest.osm.pbf"


def download_pbf(url: str, output_path: Path) -> None:
    """
    Download PBF file from Geofabrik with progress reporting.
    """
    print(f"Downloading from {url}...")
    
    def progress_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100, downloaded * 100 / total_size)
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\rProgress: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
            sys.stdout.flush()
    
    urlretrieve(url, output_path, reporthook=progress_hook)
    print("\nDownload complete!")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points in meters.
    """
    R = 6371000  # Earth's radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


class NodeCollector(osmium.SimpleHandler):
    """
    First pass: Collect all node IDs that are part of highway ways.
    Uses minimal memory by only storing node IDs, not coordinates.
    """
    
    def __init__(self):
        super().__init__()
        self.highway_node_ids: set[int] = set()
        self.way_count = 0
    
    def way(self, w):
        highway_type = w.tags.get('highway')
        if highway_type in DRIVEABLE_HIGHWAY_TYPES:
            self.way_count += 1
            for node in w.nodes:
                self.highway_node_ids.add(node.ref)
            
            if self.way_count % 100000 == 0:
                print(f"  Processed {self.way_count:,} highway ways, "
                      f"collected {len(self.highway_node_ids):,} node IDs...")


class NodeExtractor(osmium.SimpleHandler):
    """
    Second pass: Extract coordinates for the collected node IDs.
    """
    
    def __init__(self, node_ids: set[int]):
        super().__init__()
        self.node_ids = node_ids
        self.node_coords: dict[int, tuple[float, float]] = {}
        self.processed = 0
    
    def node(self, n):
        if n.id in self.node_ids:
            self.node_coords[n.id] = (n.location.lat, n.location.lon)
            self.processed += 1
            
            if self.processed % 500000 == 0:
                print(f"  Extracted {self.processed:,} node coordinates...")


class EdgeBuilder(osmium.SimpleHandler):
    """
    Third pass: Build edges from highway ways using collected node coordinates.
    """
    
    def __init__(self, node_coords: dict[int, tuple[float, float]], edges_file: Path, batch_size: int = 200000):
        super().__init__()
        self.node_coords = node_coords
        self.edges_file = edges_file
        self.batch_size = batch_size
        self.schema = pa.schema([
            ('u', pa.int64()),
            ('v', pa.int64()),
            ('weight', pa.float64()),
        ])
        self.writer = pq.ParquetWriter(str(edges_file), self.schema)
        self.u_buffer: list[int] = []
        self.v_buffer: list[int] = []
        self.weight_buffer: list[float] = []
        self.edge_count = 0
        self.way_count = 0

    def _append_edge(self, u: int, v: int, weight: float) -> None:
        self.u_buffer.append(u)
        self.v_buffer.append(v)
        self.weight_buffer.append(weight)
        self.edge_count += 1
        if len(self.u_buffer) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self.u_buffer:
            return
        table = pa.Table.from_pydict(
            {
                'u': self.u_buffer,
                'v': self.v_buffer,
                'weight': self.weight_buffer,
            },
            schema=self.schema,
        )
        self.writer.write_table(table)
        self.u_buffer.clear()
        self.v_buffer.clear()
        self.weight_buffer.clear()
    
    def way(self, w):
        highway_type = w.tags.get('highway')
        if highway_type not in DRIVEABLE_HIGHWAY_TYPES:
            return
        
        self.way_count += 1
        
        # Get valid nodes (those with coordinates)
        valid_nodes = []
        for node in w.nodes:
            if node.ref in self.node_coords:
                valid_nodes.append(node.ref)
        
        if len(valid_nodes) < 2:
            return
        
        # Determine if road is one-way
        oneway = w.tags.get('oneway', 'no')
        is_oneway = oneway in ('yes', '1', 'true', '-1')
        is_reverse = oneway == '-1'
        
        # Create edges between consecutive nodes
        for i in range(len(valid_nodes) - 1):
            u = valid_nodes[i]
            v = valid_nodes[i + 1]
            
            lat1, lon1 = self.node_coords[u]
            lat2, lon2 = self.node_coords[v]
            
            weight = haversine_distance(lat1, lon1, lat2, lon2)
            
            if is_reverse:
                # Reverse direction
                self._append_edge(v, u, weight)
            elif is_oneway:
                # Forward direction only
                self._append_edge(u, v, weight)
            else:
                # Bidirectional - create edges in both directions
                self._append_edge(u, v, weight)
                self._append_edge(v, u, weight)
        
        if self.way_count % 100000 == 0:
            print(f"  Processed {self.way_count:,} ways, created {self.edge_count:,} edges...")
    
    def close(self):
        self._flush()
        self.writer.close()


def process_osm_file(pbf_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """
    Process an OSM PBF file and generate nodes and edges Parquet files.
    Uses multi-pass streaming to minimize memory usage.
    
    Args:
        pbf_path: Path to the .osm.pbf file
        output_dir: Directory to write output files
    
    Returns:
        Tuple of (nodes_file_path, edges_file_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_file = output_dir / 'nodes.parquet'
    edges_file = output_dir / 'edges.parquet'
    
    print("\n=== Pass 1/3: Collecting highway node IDs ===")
    node_collector = NodeCollector()
    node_collector.apply_file(str(pbf_path))
    print(f"Found {len(node_collector.highway_node_ids):,} nodes in "
          f"{node_collector.way_count:,} highway ways")
    
    print("\n=== Pass 2/3: Extracting node coordinates ===")
    node_extractor = NodeExtractor(node_collector.highway_node_ids)
    node_extractor.apply_file(str(pbf_path))
    print(f"Extracted coordinates for {len(node_extractor.node_coords):,} nodes")
    
    # Free memory from first pass
    del node_collector.highway_node_ids
    
    # Write nodes to Parquet as we have them in memory
    print("\nWriting nodes to Parquet...")
    node_ids = []
    lats = []
    lons = []
    for node_id, (lat, lon) in node_extractor.node_coords.items():
        node_ids.append(node_id)
        lats.append(lat)
        lons.append(lon)
    nodes_table = pa.Table.from_pydict(
        {'id': node_ids, 'y': lats, 'x': lons},
        schema=pa.schema([('id', pa.int64()), ('y', pa.float64()), ('x', pa.float64())]),
    )
    pq.write_table(nodes_table, nodes_file)
    print(f"Wrote {len(node_extractor.node_coords):,} nodes to {nodes_file}")
    
    print("\n=== Pass 3/3: Building edges ===")
    edge_builder = EdgeBuilder(node_extractor.node_coords, edges_file)
    edge_builder.apply_file(str(pbf_path))
    edge_builder.close()
    print(f"Created {edge_builder.edge_count:,} edges from "
          f"{edge_builder.way_count:,} ways")
    print(f"Wrote edges to {edges_file}")
    
    return nodes_file, edges_file


def upload_to_gcs(local_path: Path, bucket_name: str, destination_prefix: str) -> None:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    destination_path = f"{destination_prefix.rstrip('/')}/{local_path.name}"
    blob = bucket.blob(destination_path)
    print(f"Uploading {local_path} to gs://{bucket_name}/{destination_path}...")
    blob.upload_from_filename(local_path)
    print(f"Uploaded to gs://{bucket_name}/{destination_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Download and process OSM data for road network extraction.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s poland                    # Process Poland
    %(prog)s germany --output-dir data # Process Germany, output to ./data
    %(prog)s europe/france             # Process France using full path
    %(prog)s --local file.osm.pbf      # Process local PBF file
        """
    )
    parser.add_argument(
        'region',
        help='Region name (e.g., poland, germany, europe/france) or path to local .pbf file'
    )
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=Path('./osm_data'),
        help='Output directory for processed files (default: ./osm_data)'
    )
    parser.add_argument(
        '--local', '-l',
        action='store_true',
        help='Treat region argument as a local file path instead of downloading'
    )
    parser.add_argument(
        '--keep-pbf', '-k',
        action='store_true',
        help='Keep the downloaded PBF file after processing'
    )
    
    args = parser.parse_args()
    
    if args.local:
        # Use local file
        pbf_path = Path(args.region)
        if not pbf_path.exists():
            print(f"Error: File not found: {pbf_path}", file=sys.stderr)
            sys.exit(1)
        temp_dir = None
    else:
        # Download from Geofabrik
        url = get_geofabrik_url(args.region)
        
        if args.keep_pbf:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            pbf_path = args.output_dir / f"{args.region.replace('/', '-')}-latest.osm.pbf"
            temp_dir = None
        else:
            temp_dir = tempfile.mkdtemp()
            pbf_path = Path(temp_dir) / 'data.osm.pbf'
        
        try:
            download_pbf(url, pbf_path)
        except Exception as e:
            print(f"Error downloading data: {e}", file=sys.stderr)
            print(f"URL attempted: {url}", file=sys.stderr)
            sys.exit(1)
    
    try:
        nodes_file, edges_file = process_osm_file(pbf_path, args.output_dir)
        
        print("\n=== Processing Complete ===")
        print(f"Nodes file: {nodes_file}")
        print(f"Edges file: {edges_file}")
        
        # Print file sizes
        nodes_size = nodes_file.stat().st_size / (1024 * 1024)
        edges_size = edges_file.stat().st_size / (1024 * 1024)
        print(f"\nFile sizes:")
        print(f"  Nodes: {nodes_size:.1f} MB")
        print(f"  Edges: {edges_size:.1f} MB")

        upload_to_gcs(nodes_file, "rsp_graph_data_massive", "raw/nodes")
        upload_to_gcs(edges_file, "rsp_graph_data_massive", "raw/edges")
        
    finally:
        # Clean up temp directory if used
        if temp_dir and not args.keep_pbf:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
