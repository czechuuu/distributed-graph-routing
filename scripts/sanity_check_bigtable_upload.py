import argparse
import math
import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from google.cloud import bigtable

from storage_types import bigtable_storage_pb2


def _get_cell_value(row, column_family: str, qualifier: str) -> Optional[bytes]:
    if row is None:
        return None
    family_cells = row.cells.get(column_family)
    if not family_cells:
        return None
    qualifier_key = qualifier.encode("utf-8")
    cells = family_cells.get(qualifier_key)
    if not cells:
        return None
    return cells[0].value


def _read_row_payload(
    table, row_key: bytes, column_family: str, qualifier: str
) -> Optional[bytes]:
    row = table.read_row(row_key)
    return _get_cell_value(row, column_family, qualifier)


def _list_row_keys(table, prefix: str, limit: int) -> List[bytes]:
    keys: List[bytes] = []
    rows = table.read_rows(row_key_prefix=prefix.encode("utf-8"), limit=limit)
    for row in rows:
        keys.append(row.row_key)
    return keys


def _reservoir_sample(keys: Iterable[bytes], sample_size: int, rng: random.Random) -> List[bytes]:
    sample: List[bytes] = []
    for i, key in enumerate(keys):
        if i < sample_size:
            sample.append(key)
        else:
            j = rng.randint(0, i)
            if j < sample_size:
                sample[j] = key
    return sample


def _parse_shard_id(row_key: bytes) -> Optional[int]:
    try:
        key_str = row_key.decode("utf-8")
        if not key_str.startswith("S#"):
            return None
        return int(key_str.split("#", 1)[1])
    except (UnicodeDecodeError, ValueError):
        return None


def _edge_stats(edges: Sequence[bigtable_storage_pb2.Edge]) -> Dict[str, int]:
    stats = {
        "count": len(edges),
        "self_loops": 0,
        "zero_weight": 0,
        "zero_node": 0,
    }
    for edge in edges:
        if edge.from_node_id == edge.to_node_id:
            stats["self_loops"] += 1
        if edge.weight == 0:
            stats["zero_weight"] += 1
        if edge.from_node_id == 0 or edge.to_node_id == 0:
            stats["zero_node"] += 1
    return stats


def _summarize_overlay(overlay: bigtable_storage_pb2.OverlayGraph) -> List[str]:
    issues: List[str] = []
    bridges_stats = _edge_stats(overlay.bridges)
    shortcuts_stats = _edge_stats(overlay.shortcuts)

    if bridges_stats["count"] == 0:
        issues.append("Overlay graph has 0 bridges.")
    if shortcuts_stats["count"] == 0:
        issues.append("Overlay graph has 0 shortcuts.")
    if bridges_stats["zero_weight"] > 0:
        issues.append(
            f"Overlay bridges contain {bridges_stats['zero_weight']} zero-weight edges."
        )
    if shortcuts_stats["zero_weight"] > 0:
        issues.append(
            f"Overlay shortcuts contain {shortcuts_stats['zero_weight']} zero-weight edges."
        )
    if bridges_stats["self_loops"] > 0:
        issues.append(
            f"Overlay bridges contain {bridges_stats['self_loops']} self-loops."
        )
    if shortcuts_stats["self_loops"] > 0:
        issues.append(
            f"Overlay shortcuts contain {shortcuts_stats['self_loops']} self-loops."
        )
    if bridges_stats["zero_node"] > 0:
        issues.append(
            f"Overlay bridges contain {bridges_stats['zero_node']} zero node IDs."
        )
    if shortcuts_stats["zero_node"] > 0:
        issues.append(
            f"Overlay shortcuts contain {shortcuts_stats['zero_node']} zero node IDs."
        )
    return issues


def _summarize_shard(
    shard: bigtable_storage_pb2.ShardGraph,
    shard_id: Optional[int],
) -> Tuple[List[str], Dict[str, int]]:
    issues: List[str] = []
    node_ids = [loc.node_id for loc in shard.locations]
    node_set = set(node_ids)
    duplicate_nodes = len(node_ids) - len(node_set)
    if duplicate_nodes > 0:
        issues.append(
            f"Shard {shard_id} has {duplicate_nodes} duplicate node IDs in locations."
        )
    if len(node_ids) == 0:
        issues.append(f"Shard {shard_id} has 0 node locations.")
    if len(shard.edges) == 0:
        issues.append(f"Shard {shard_id} has 0 edges.")

    invalid_coords = 0
    for loc in shard.locations:
        if not (math.isfinite(loc.x) and math.isfinite(loc.y)):
            invalid_coords += 1
    if invalid_coords > 0:
        issues.append(f"Shard {shard_id} has {invalid_coords} invalid coordinates.")

    missing_nodes = 0
    for edge in shard.edges:
        if edge.from_node_id not in node_set or edge.to_node_id not in node_set:
            missing_nodes += 1
    if missing_nodes > 0:
        issues.append(f"Shard {shard_id} has {missing_nodes} edges with missing nodes.")

    edge_stats = _edge_stats(shard.edges)
    if edge_stats["zero_weight"] > 0:
        issues.append(
            f"Shard {shard_id} has {edge_stats['zero_weight']} zero-weight edges."
        )
    if edge_stats["self_loops"] > 0:
        issues.append(f"Shard {shard_id} has {edge_stats['self_loops']} self-loops.")
    if edge_stats["zero_node"] > 0:
        issues.append(
            f"Shard {shard_id} has {edge_stats['zero_node']} edges with node_id=0."
        )
    return issues, edge_stats


def _check_node_index(
    table,
    node_ids: Sequence[int],
    shard_id: Optional[int],
    column_family: str,
    qualifier: str,
    rng: random.Random,
    sample_limit: int,
) -> List[str]:
    if shard_id is None or not node_ids:
        return []
    issues: List[str] = []
    sample_size = min(sample_limit, len(node_ids))
    sampled_nodes = rng.sample(list(node_ids), k=sample_size)
    for node_id in sampled_nodes:
        row_key = f"N#{node_id}".encode("utf-8")
        payload = _read_row_payload(table, row_key, column_family, qualifier)
        if payload is None:
            issues.append(
                f"Node index missing row for node {node_id} (expected shard {shard_id})."
            )
            continue
        lookup = bigtable_storage_pb2.ShardLookup()
        lookup.ParseFromString(payload)
        if lookup.shard_id != shard_id:
            issues.append(
                f"Node {node_id} maps to shard {lookup.shard_id}, expected {shard_id}."
            )
    return issues


def _print_section(title: str) -> None:
    print("\n" + "=" * len(title))
    print(title)
    print("=" * len(title))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sanity checks for Bigtable overlay graph + shard data."
    )
    parser.add_argument("--project", default="repetitive-shortest-paths")
    parser.add_argument("--instance", default="routing-instance")
    parser.add_argument("--shards-table", default="shards")
    parser.add_argument("--overlay-table", default="overlay_graph")
    parser.add_argument("--node-index-table", default="node_index")
    parser.add_argument("--column-family", default="cf")
    parser.add_argument("--qualifier", default="data")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--scan-limit", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--node-index-sample", type=int, default=10)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    client = bigtable.Client(project=args.project, admin=False)
    instance = client.instance(args.instance)
    shards_table = instance.table(args.shards_table)
    overlay_table = instance.table(args.overlay_table)
    node_index_table = instance.table(args.node_index_table)

    _print_section("Overlay Graph Check")
    overlay_payload = _read_row_payload(
        overlay_table, b"O#", args.column_family, args.qualifier
    )
    if overlay_payload is None:
        print("Overlay graph row not found or empty at key 'O#'.")
    else:
        overlay = bigtable_storage_pb2.OverlayGraph()
        overlay.ParseFromString(overlay_payload)
        print(
            f"Overlay graph loaded: {len(overlay.bridges)} bridges, "
            f"{len(overlay.shortcuts)} shortcuts."
        )
        overlay_issues = _summarize_overlay(overlay)
        if overlay_issues:
            print("Potential issues:")
            for issue in overlay_issues:
                print(f"- {issue}")
        else:
            print("No obvious issues found in overlay graph.")

    _print_section("Shard Sampling Check")
    shard_keys = _list_row_keys(shards_table, "S#", args.scan_limit)
    if not shard_keys:
        print("No shard rows found with prefix 'S#'.")
        return

    if len(shard_keys) < args.sample_size:
        print(
            f"Only found {len(shard_keys)} shard rows, "
            f"sampling all instead of {args.sample_size}."
        )
    sample_keys = rng.sample(
        shard_keys, k=min(args.sample_size, len(shard_keys))
    )

    total_issues = 0
    for key in sample_keys:
        payload = _read_row_payload(
            shards_table, key, args.column_family, args.qualifier
        )
        shard_id = _parse_shard_id(key)
        if payload is None:
            print(f"- Shard row {key!r} missing data payload.")
            total_issues += 1
            continue
        shard = bigtable_storage_pb2.ShardGraph()
        shard.ParseFromString(payload)
        issues, edge_stats = _summarize_shard(shard, shard_id)
        node_index_issues = _check_node_index(
            node_index_table,
            [loc.node_id for loc in shard.locations],
            shard_id,
            args.column_family,
            args.qualifier,
            rng,
            args.node_index_sample,
        )
        issues.extend(node_index_issues)
        if issues:
            print(
                f"- Shard {shard_id} ({len(shard.locations)} nodes, "
                f"{edge_stats['count']} edges):"
            )
            for issue in issues:
                print(f"  - {issue}")
            total_issues += len(issues)
        else:
            print(
                f"- Shard {shard_id} looks OK "
                f"({len(shard.locations)} nodes, {edge_stats['count']} edges)."
            )

    _print_section("Summary")
    print(f"Sampled {len(sample_keys)} shard rows.")
    if total_issues == 0:
        print("No issues detected in sampled data.")
    else:
        print(f"Detected {total_issues} potential issues in sampled data.")


if __name__ == "__main__":
    main()
