import { computeContraction } from './pathLogic';
import { NodeType } from './types';
import type { NodeLocation } from './types';
import type { ShardControlItem } from '../components/ShardManager';
import { describe, test, expect } from 'vitest';

describe('computeContraction', () => {
    const makeNode = (id: string, shard: string): NodeLocation => ({
        node_id: id, shard_id: shard, x: 0, y: 0, type: NodeType.INTERNAL
    });

    const makeShard = (id: string, mode: 'ALL' | 'BOUNDARIES' | 'HIDDEN'): ShardControlItem => ({
        id, mode, lastAccessedAt: Date.now()
    });

    test('should return empty for null/empty path', () => {
        expect(computeContraction(null, []).pathEdges).toEqual([]);
        expect(computeContraction([], []).pathEdges).toEqual([]);
    });

    test('should contract hidden shard segment', () => {
        // Path: A(S1) -> B(S1) -> C(S1)
        // S1 is HIDDEN
        // Expected: Edge A->C only.
        const path = [makeNode('A', 'S1'), makeNode('B', 'S1'), makeNode('C', 'S1')];
        const shards: ShardControlItem[] = [makeShard('S1', 'HIDDEN')];

        const result = computeContraction(path, shards);
        expect(result.pathEdges).toHaveLength(1);
        expect(result.pathEdges[0]).toMatchObject({ from_node_id: 'A', to_node_id: 'C' });
        expect(result.pathNodesSet.has('A')).toBeTruthy();
        expect(result.pathNodesSet.has('C')).toBeTruthy();
        expect(result.pathNodesSet.has('B')).toBeFalsy();
    });

    test('should show full path for visible shard', () => {
        // Path: A(S1) -> B(S1) -> C(S1)
        // S1 is ALL
        // Expected: A->B, B->C
        const path = [makeNode('A', 'S1'), makeNode('B', 'S1'), makeNode('C', 'S1')];
        const shards: ShardControlItem[] = [makeShard('S1', 'ALL')];

        const result = computeContraction(path, shards);
        expect(result.pathEdges).toHaveLength(2);
        expect(result.pathNodesSet.size).toBe(3);
    });

    test('should handle cross-shard paths', () => {
        // Path: A(S1) -> B(S1) -> C(S2) -> D(S2)
        // S1 HIDDEN, S2 ALL
        // Expected: A->B (Contracted S1), B->C (Bridge), C->D (Full S2)
        const path = [
            makeNode('A', 'S1'), makeNode('B', 'S1'),
            makeNode('C', 'S2'), makeNode('D', 'S2')
        ];
        const shards: ShardControlItem[] = [
            makeShard('S1', 'HIDDEN'),
            makeShard('S2', 'ALL')
        ];

        const result = computeContraction(path, shards);

        // Edges: A->B (S1 contract), B->C (Bridge), C->D (S2 internal)
        expect(result.pathEdges).toHaveLength(3);

        const s1Edge = result.pathEdges.find(e => e.from_node_id === 'A' && e.to_node_id === 'B');
        expect(s1Edge).toBeDefined();

        const bridge = result.pathEdges.find(e => e.from_node_id === 'B' && e.to_node_id === 'C');
        expect(bridge).toBeDefined();

        const s2Edge = result.pathEdges.find(e => e.from_node_id === 'C' && e.to_node_id === 'D');
        expect(s2Edge).toBeDefined();
    });
});
