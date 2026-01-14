import type { GraphData, NodeLocation, Edge } from './types';

// Simple Linear Congruential Generator for reproducible random numbers
class LCG {
    private seed: number;
    constructor(seed: number) {
        this.seed = seed;
    }
    next() {
        this.seed = (this.seed * 1664525 + 1013904223) % 4294967296;
        return this.seed / 4294967296;
    }
}

export function generateMockOverlayGraph(nodeCount: number = 100, shardCount: number = 5): GraphData {
    const rng = new LCG(12345);
    const nodes: NodeLocation[] = [];
    const edges: Edge[] = [];

    // Generate nodes in clusters (shards)
    for (let s = 0; s < shardCount; s++) {
        // Shard center
        const cx = rng.next() * 800;
        const cy = rng.next() * 600;

        for (let i = 0; i < nodeCount / shardCount; i++) {
            const id = (s * (nodeCount / shardCount) + i).toString();
            nodes.push({
                node_id: id,
                x: cx + (rng.next() - 0.5) * 150,
                y: cy + (rng.next() - 0.5) * 150
            });
        }
    }

    // Generate edges
    // 1. Shortcuts (dense intra-shard connections) - Mocking them as random connections within shard for now
    // Real shortcuts are boundary-to-boundary, but for vis we might want to see them.
    // Actually, for Overlay Graph, we mainly care about Bridges (Shard-to-Shard) and Shortcuts (Boundary-to-Boundary).
    // I will interpret "Mock Overlay" as: Nodes are boundary nodes.

    // Let's make "bridges" connect different shards
    for (let i = 0; i < nodes.length; i++) {
        const u = nodes[i];
        // Connect to 2 nearest neighbors to ensure some structure? 
        // Or just random for Mock.

        // Random connection to another node (Bridge if different shard, Shortcut if same?)
        // For simplicity, just edges.
        if (rng.next() > 0.7) {
            const targetIdx = Math.floor(rng.next() * nodes.length);
            if (targetIdx !== i) {
                edges.push({
                    from_node_id: u.node_id,
                    to_node_id: nodes[targetIdx].node_id,
                    weight: Math.floor(rng.next() * 100),
                    bidirectional: true
                });
            }
        }
    }

    return { nodes, edges };
}
