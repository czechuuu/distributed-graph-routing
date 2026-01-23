import sys
from pathlib import Path

import apache_beam as beam
from apache_beam.testing.util import assert_that, equal_to

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "legacy"))

from legacy_pipeline import (
    EdgeBase,
    NodeLocationRow,
    ProcessShardLegacy,
    _make_direct_row,
)
from storage_types import bigtable_storage_pb2


def _parse_shard_graph(element):
    shard_id, payload = element
    shard = bigtable_storage_pb2.ShardGraph()
    shard.ParseFromString(payload)
    edges = [(e.from_node_id, e.to_node_id, e.weight) for e in shard.edges]
    locations = [(l.node_id, l.x, l.y) for l in shard.locations]
    return (shard_id, edges, locations)


def _parse_shortcut_path(element):
    src, dst, payload = element
    path = bigtable_storage_pb2.ShortcutPath()
    path.ParseFromString(payload)
    return (src, dst, list(path.nodes))


def test_legacy_process_shard_outputs():
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
        {
            "edges": edges,
            "nodes": nodes,
            "boundary_in": boundary_in,
            "boundary_out": boundary_out,
        },
    )

    with beam.Pipeline() as p:
        results = (
            p
            | "CreateGrouped" >> beam.Create([grouped])
            | "ProcessShardLegacy"
            >> beam.ParDo(ProcessShardLegacy()).with_outputs(
                "shard_pb", "shortcut_edge", "shortcut_path", "node_index"
            )
        )

        shard_pbs = results.shard_pb | "ParseShardPb" >> beam.Map(_parse_shard_graph)
        shortcut_edges = results.shortcut_edge
        shortcut_paths = results.shortcut_path | "ParseShortcutPath" >> beam.Map(
            _parse_shortcut_path
        )
        node_index = (
            results.node_index
            | "CollectNodeIndex" >> beam.combiners.ToList()
            | "SortNodeIndex" >> beam.Map(sorted)
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
            shortcut_edges,
            equal_to([("shortcuts", 1, 3, 3)]),
            label="AssertShortcutEdges",
        )
        assert_that(
            shortcut_paths,
            equal_to([(1, 3, [1, 2, 3])]),
            label="AssertShortcutPaths",
        )
        assert_that(
            node_index,
            equal_to([[(1, shard_id), (2, shard_id), (3, shard_id)]]),
            label="AssertNodeIndex",
        )


def test_legacy_bigtable_row_keys():
    keys = ["S#1", "N#99", "P#1#2", "O#"]
    with beam.Pipeline() as p:
        row_keys = (
            p
            | "CreateKeys" >> beam.Create(keys)
            | "MakeRows"
            >> beam.Map(lambda key: _make_direct_row(key, b"payload", "cf", "data").row_key)
        )
        assert_that(
            row_keys,
            equal_to([b"S#1", b"N#99", b"P#1#2", b"O#"]),
            label="AssertRowKeys",
        )
