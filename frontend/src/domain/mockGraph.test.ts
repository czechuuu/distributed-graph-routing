import { describe, it, expect } from 'vitest';
import { generateMockOverlayGraph } from './mockGraph';

describe('generateMockOverlayGraph', () => {
    it('should generate requested number of nodes', () => {
        const data = generateMockOverlayGraph(100, 5);
        expect(data.nodes.length).toBe(100);
        expect(data.edges.length).toBeGreaterThan(0);
    });

    it('should generate edges with valid node IDs', () => {
        const data = generateMockOverlayGraph(50, 2);
        const nodeIds = new Set(data.nodes.map(n => n.node_id));

        data.edges.forEach(edge => {
            expect(nodeIds.has(edge.from_node_id)).toBe(true);
            expect(nodeIds.has(edge.to_node_id)).toBe(true);
        });
    });

    it('should assign shard IDs', () => {
        const data = generateMockOverlayGraph(10, 2);
        data.nodes.forEach(n => {
            expect(n.shard_id).toBeDefined();
            expect(typeof n.shard_id).toBe('string');
        });
    });

    it('should produce reproducible results', () => {
        const run1 = generateMockOverlayGraph(20, 2);
        const run2 = generateMockOverlayGraph(20, 2);
        expect(run1).toEqual(run2);
    });
});
