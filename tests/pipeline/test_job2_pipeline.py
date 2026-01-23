import sys
from pathlib import Path

import apache_beam as beam
from apache_beam.testing.util import assert_that, equal_to

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "preprocessing"))

from dataflow.job2_pipeline import EdgeBase, NodeLocationRow, ProcessShard
from dataflow.storage_types import bigtable_storage_pb2


def _parse_shortcuts(element):
    shard_id, payload = element
    shortcuts = bigtable_storage_pb2.Shortcuts()
    shortcuts.ParseFromString(payload)
    edges = [(e.from_node_id, e.to_node_id, e.weight) for e in shortcuts.edges]
    return (shard_id, edges)


def _parse_shard_graph(element):
    shard_id, payload = element
    shard = bigtable_storage_pb2.ShardGraph()
    shard.ParseFromString(payload)
    edges = [(e.from_node_id, e.to_node_id, e.weight) for e in shard.edges]
    locations = [(l.node_id, l.x, l.y) for l in shard.locations]
    return (shard_id, edges, locations)


def test_job2_shortcuts_smoke():
    shard_id = 42
    edges = [
        EdgeBase(u=1, v=2, weight=1.0),
        EdgeBase(u=2, v=3, weight=2.0),
        EdgeBase(u=1, v=3, weight=5.0),
    ]
    nodes = [
        NodeLocationRow(node_id=1, x=10.0, y=20.0),
        NodeLocationRow(node_id=2, x=11.0, y=21.0),
        NodeLocationRow(node_id=3, x=12.0, y=22.0),
    ]
    boundary_in = [1]
    boundary_out = [3]

    grouped = (
        shard_id,
        {"edges": edges, "nodes": nodes, "boundary_in": boundary_in, "boundary_out": boundary_out},
    )

    with beam.Pipeline() as p:
        results = (
            p
            | "CreateGrouped" >> beam.Create([grouped])
            | "ProcessShard" >> beam.ParDo(ProcessShard()).with_outputs(
                "shard_pb", "shortcuts_pb", "shortcuts_edge", "boundary_location"
            )
        )

        shortcuts_edges = results.shortcuts_edge
        shard_pbs = results.shard_pb | "ParseShardPb" >> beam.Map(_parse_shard_graph)
        shortcuts_pbs = results.shortcuts_pb | "ParseShortcutPb" >> beam.Map(_parse_shortcuts)
        boundary_locations = (
            results.boundary_location
            | "CollectBoundaryLocations" >> beam.combiners.ToList()
            | "SortBoundaryLocations" >> beam.Map(sorted)
        )

        assert_that(
            shortcuts_edges,
            equal_to([("shortcuts", 1, 3, 3)]),
            label="AssertShortcutEdges",
        )
        assert_that(
            shard_pbs,
            equal_to(
                [
                    (
                        shard_id,
                        [(1, 2, 1), (2, 3, 2), (1, 3, 5)],
                        [(1, 10.0, 20.0), (2, 11.0, 21.0), (3, 12.0, 22.0)],
                    )
                ]
            ),
            label="AssertShardGraph",
        )
        assert_that(
            shortcuts_pbs,
            equal_to([(shard_id, [(1, 3, 3)])]),
            label="AssertShortcutsPb",
        )
        assert_that(
            boundary_locations,
            equal_to(
                [
                    [
                        ("boundary_location", 1, 10.0, 20.0),
                        ("boundary_location", 3, 12.0, 22.0),
                    ]
                ]
            ),
            label="AssertBoundaryLocations",
        )
