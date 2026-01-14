import type { OverlayGraph, ShardData, NodeLocation, Edge } from './types';
import { NodeType } from './types';

export interface GraphProvider {
    getOverlayGraph(): Promise<OverlayGraph>;
    getShard(shardId: string): Promise<ShardData>;
    findPath(srcNodeId: string, dstNodeId: string): Promise<NodeLocation[]>;
}

// Simple seeded random to keep mocks deterministic per shard/run
class LCG {
    private state: number;
    constructor(seed: number) {
        this.state = seed;
    }
    next(): number {
        this.state = (this.state * 1664525 + 1013904223) % 4294967296;
        return this.state / 4294967296;
    }
    nextRange(min: number, max: number): number {
        return min + this.next() * (max - min);
    }
}

// Mock Generator that produces consistent, planar-ish graphs with boundary nodes
export class MockGraphProvider implements GraphProvider {
    private shardCount = 9; // 3x3 grid
    private cachedOverlay: OverlayGraph | null = null;

    // Generates the global overlay (bridges and shortcuts for ALL shards)
    async getOverlayGraph(): Promise<OverlayGraph> {
        if (this.cachedOverlay) return this.cachedOverlay;

        // Generate headers for all shards to build the overlay
        // We need to know boundary nodes for every shard to connect them
        const allBridges: Edge[] = [];
        const allShortcuts: Edge[] = [];

        // Pass 1: Generate Shard "Metadata" (Center X,Y)
        const shardCenters: { id: string, x: number, y: number }[] = [];

        for (let i = 0; i < this.shardCount; i++) {
            // Grid layout for shards
            const row = Math.floor(i / 3);
            const col = i % 3;
            shardCenters.push({
                id: i.toString(),
                x: col * 1000 + 500,
                y: row * 1000 + 500
            });
        }

        const boundaryNodesMap = new Map<string, NodeLocation[]>();

        // Generate local data just to extract boundary nodes/shortcuts
        // In a real app, this might come from a separate "Overlay Index"
        for (let i = 0; i < this.shardCount; i++) {
            const shardId = i.toString();
            const center = shardCenters[i];

            // We need deterministic generation for this shard
            // Use the getShardDataSync helper to avoid async mess in loop
            const shardData = this.getShardDataSync(shardId, center.x, center.y);

            const bNodes = shardData.nodes.filter(n => n.type === NodeType.BOUNDARY);
            boundaryNodesMap.set(shardId, bNodes);

            // In our mock, "Shortcuts" are just direct edges between some boundary nodes within the shard
            // Let's explicitly create them here or extract from shardData?
            // BigTable model says Shortcuts are in Overlay.
            // Let's create some random shortcuts between boundary nodes of this shard.
            const rng = new LCG(parseInt(shardId) * 777);
            if (bNodes.length > 1) {
                for (let k = 0; k < 3; k++) {
                    const idx1 = Math.floor(rng.next() * bNodes.length);
                    const idx2 = Math.floor(rng.next() * bNodes.length);
                    if (idx1 !== idx2) {
                        allShortcuts.push({
                            from_node_id: bNodes[idx1].node_id,
                            to_node_id: bNodes[idx2].node_id,
                            weight: 5.0,
                            bidirectional: true
                        });
                    }
                }
            }
        }

        // Generate Bridges (Edges between shards)
        // Connect nearby Shards (Grid neighbors)
        const rngBridge = new LCG(999);
        for (let i = 0; i < this.shardCount; i++) {
            const r = Math.floor(i / 3);
            const c = i % 3;

            const neighbors: number[] = [];
            if (c < 2) neighbors.push(i + 1); // Right
            if (r < 2) neighbors.push(i + 3); // Down

            for (const neighborIdx of neighbors) {
                const idA = i.toString();
                const idB = neighborIdx.toString();

                const bA = boundaryNodesMap.get(idA) || [];
                const bB = boundaryNodesMap.get(idB) || [];

                // Connect a few random boundary nodes
                if (bA.length && bB.length) {
                    const connections = 2; // num bridges
                    for (let k = 0; k < connections; k++) {
                        const nodeA = bA[Math.floor(rngBridge.next() * bA.length)];
                        const nodeB = bB[Math.floor(rngBridge.next() * bB.length)];

                        allBridges.push({
                            from_node_id: nodeA.node_id,
                            to_node_id: nodeB.node_id,
                            weight: 10.0, // Higher cost for jumping shards?
                            bidirectional: true
                        });
                    }
                }
            }
        }

        this.cachedOverlay = {
            bridges: allBridges,
            shortcuts: allShortcuts
        };
        return this.cachedOverlay;
    }

    async getShard(shardId: string): Promise<ShardData> {
        // Re-calculate center for determinism (or could cache)
        const id = parseInt(shardId);
        if (isNaN(id) || id < 0 || id >= this.shardCount) {
            throw new Error("Invalid Shard ID");
        }
        const row = Math.floor(id / 3);
        const col = id % 3;
        const x = col * 1000 + 500;
        const y = row * 1000 + 500;

        // Simulate network delay
        await new Promise(r => setTimeout(r, 200 + Math.random() * 300));

        return this.getShardDataSync(shardId, x, y);
    }

    async findPath(srcNodeId: string, dstNodeId: string): Promise<NodeLocation[]> {
        // Mock Pathfinding:
        // Since we don't have the full graph in memory (it's sharded), we'll cheat for the mock.
        // We'll generate a "realistic" looking path that hops through shards.
        // If src/dst are in loaded shards, great. If not, we pretend.

        // 1. Determine Src/Dst Shards
        const parseId = (id: string) => {
            const parts = id.split('-');
            if (parts.length < 2) return { shard: '0', idx: 0 };
            return { shard: parts[0], idx: parseInt(parts[1]) };
        };

        const srcInfo = parseId(srcNodeId);
        const dstInfo = parseId(dstNodeId);

        // Simple case: Same shard -> Straight line simulation
        // Complex case: Cross shards -> BFS on Shard Grid (0-8)

        const pathNodes: NodeLocation[] = [];

        // Helper to get a random node in a shard
        const getShardNode = (shardId: string, nodeId: string): NodeLocation => {
            // Re-generate that specific node deterministically
            const id = parseInt(shardId);
            if (isNaN(id)) return { node_id: nodeId, x: 0, y: 0, shard_id: shardId, type: NodeType.INTERNAL }; // Fallback

            const row = Math.floor(id / 3);
            const col = id % 3;
            const x = col * 1000 + 500;
            const y = row * 1000 + 500;

            // We need to match the logic in getShardDataSync to find the EXACT node position
            // This is expensive to re-gen whole shard, but for mock it's fine.
            const data = this.getShardDataSync(shardId, x, y);
            return data.nodes.find(n => n.node_id === nodeId) ||
                // If not found (e.g. invalid ID), return center of shard
                { node_id: nodeId, x, y, shard_id: shardId, type: NodeType.INTERNAL };
        };

        // BFS on Grid to find sequence of shards
        const shardPath: string[] = [];
        let curr = parseInt(srcInfo.shard);
        const target = parseInt(dstInfo.shard);

        if (isNaN(curr) || isNaN(target)) {
            // Just return direct line
            pathNodes.push(getShardNode(srcInfo.shard, srcNodeId));
            pathNodes.push(getShardNode(dstInfo.shard, dstNodeId));
            return pathNodes;
        }

        // Greedy grid walk
        shardPath.push(curr.toString());
        while (curr !== target) {
            const Cr = Math.floor(curr / 3), Cc = curr % 3;
            const Tr = Math.floor(target / 3), Tc = target % 3;

            if (Cc < Tc) curr += 1;
            else if (Cc > Tc) curr -= 1;
            else if (Cr < Tr) curr += 3;
            else if (Cr > Tr) curr -= 3;

            shardPath.push(curr.toString());
        }

        // Now generate path nodes through these shards
        // Start
        pathNodes.push(getShardNode(shardPath[0], srcNodeId));

        // For each intermediate step, pick entry/exit boundary nodes
        // (For Mock, we'll just pick 2-3 random nodes in each shard to simulate traversal)
        const rngPath = new LCG(srcNodeId.length + dstNodeId.length);

        for (let i = 0; i < shardPath.length; i++) {
            const sId = shardPath[i];
            // const isLast = i === shardPath.length - 1;

            // If it's the start shard, we already added src. 
            // We need to add some internal nodes then exit.

            // If it's the end shard, we traverse then hit dst.

            const centerId = parseInt(sId);
            const r = Math.floor(centerId / 3);
            const c = centerId % 3;
            const cx = c * 1000 + 500;
            const cy = r * 1000 + 500;
            const sData = this.getShardDataSync(sId, cx, cy);

            // Pick a few random nodes in this shard to walk through
            const steps = 3 + Math.floor(rngPath.next() * 3);
            for (let k = 0; k < steps; k++) {
                const randomNode = sData.nodes[Math.floor(rngPath.next() * sData.nodes.length)];

                // Don't add duplicates of src/dst
                if (randomNode.node_id !== srcNodeId && randomNode.node_id !== dstNodeId) {
                    pathNodes.push(randomNode);
                }
            }
        }

        // End
        pathNodes.push(getShardNode(shardPath[shardPath.length - 1], dstNodeId));

        return pathNodes;
    }

    private getShardDataSync(shardId: string, cx: number, cy: number): ShardData {
        const rng = new LCG(parseInt(shardId) * 1337 + 1); // Deterministic seed
        const nodes: NodeLocation[] = [];
        const edges: Edge[] = [];

        const numNodes = 20 + Math.floor(rng.next() * 30);

        // 1. Generate Nodes
        for (let i = 0; i < numNodes; i++) {
            // Distribute in a cluster around cx, cy
            const angle = rng.next() * Math.PI * 2;
            const dist = rng.next() * 400; // Radius 400

            // Boundary nodes tend to be on the periphery? 
            // Or just randomly assigned for now.
            // Let's say top 20% by distance are boundary?
            const isBoundary = (dist > 300) && (rng.next() > 0.3);

            nodes.push({
                node_id: `${shardId}-${i}`,
                shard_id: shardId,
                x: cx + Math.cos(angle) * dist,
                y: cy + Math.sin(angle) * dist,
                type: isBoundary ? NodeType.BOUNDARY : NodeType.INTERNAL
            });
        }

        // 2. Generate Planar-ish Intra-Edges
        // Connect each node to k nearest neighbors to simulate road network
        nodes.forEach(u => {
            // Find distances
            const others = nodes
                .filter(v => v !== u)
                .map(v => ({
                    node: v,
                    dist: Math.hypot(v.x - u.x, v.y - u.y)
                }))
                .sort((a, b) => a.dist - b.dist);

            // Connect to closest 2-3
            const numEdges = 2 + Math.floor(rng.next() * 2);
            for (let k = 0; k < Math.min(numEdges, others.length); k++) {
                const target = others[k].node;
                // Avoid duplicates? The graph is undirected.
                // We'll just add simple directed edges for now, 
                // the renderer draws lines. Ideally we dedupe `u.id < v.id`
                if (u.node_id < target.node_id) {
                    edges.push({
                        from_node_id: u.node_id,
                        to_node_id: target.node_id,
                        weight: others[k].dist,
                        bidirectional: true
                    });
                }
            }
        });

        return { nodes, edges };
    }
}
