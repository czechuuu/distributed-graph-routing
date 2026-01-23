import type { OverlayGraph, ShardData, NodeLocation, Edge } from './types';
import { NodeType } from './types';
import { DEFAULT_REGION } from './MapMetadata';

export interface GraphProvider {
    getOverlayGraph(): Promise<OverlayGraph>;
    getShard(shardId: string): Promise<ShardData>;
    findPath(srcNodeId: string, dstNodeId: string): Promise<NodeLocation[]>;
    getNodeShard(nodeId: string): Promise<string | null>;
}

class LCG {
    private state: number;
    constructor(seed: number) { this.state = seed; }
    next(): number {
        this.state = (this.state * 1664525 + 1013904223) % 4294967296;
        return this.state / 4294967296;
    }
}

export class MockGraphProvider implements GraphProvider {
    private shardCount = 9; // 3x3 grid
    private cachedOverlay: OverlayGraph | null = null;

    async getOverlayGraph(): Promise<OverlayGraph> {
        if (this.cachedOverlay) return this.cachedOverlay;

        const allBridges: Edge[] = [];
        const allShortcuts: Edge[] = [];

        // Calculate Shard Grid based on Region Bounds
        const bounds = DEFAULT_REGION.bounds;
        const latStep = (bounds.maxLat - bounds.minLat) / 3;
        const lonStep = (bounds.maxLon - bounds.minLon) / 3;

        const shardCenters: { id: string, x: number, y: number }[] = [];

        for (let i = 0; i < this.shardCount; i++) {
            const row = Math.floor(i / 3);
            const col = i % 3;
            // Center of the grid cell
            // x = Lon (East-West), y = Lat (North-South)
            const cx = bounds.minLon + col * lonStep + lonStep / 2;
            const cy = bounds.minLat + row * latStep + latStep / 2;

            shardCenters.push({ id: i.toString(), x: cx, y: cy });
        }

        const boundaryNodesMap = new Map<string, NodeLocation[]>();

        for (let i = 0; i < this.shardCount; i++) {
            const shardId = i.toString();
            const center = shardCenters[i];
            const shardData = this.getShardDataSync(shardId, center.x, center.y); // x=Lon, y=Lat

            const bNodes = shardData.nodes.filter(n => n.type === NodeType.BOUNDARY);
            boundaryNodesMap.set(shardId, bNodes);

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

        const rngBridge = new LCG(999);
        for (let i = 0; i < this.shardCount; i++) {
            const r = Math.floor(i / 3);
            const c = i % 3;
            const neighbors: number[] = [];
            if (c < 2) neighbors.push(i + 1);
            if (r < 2) neighbors.push(i + 3);

            for (const neighborIdx of neighbors) {
                const idA = i.toString();
                const idB = neighborIdx.toString();
                const bA = boundaryNodesMap.get(idA) || [];
                const bB = boundaryNodesMap.get(idB) || [];

                if (bA.length && bB.length) {
                    const connections = 2;
                    for (let k = 0; k < connections; k++) {
                        const nodeA = bA[Math.floor(rngBridge.next() * bA.length)];
                        const nodeB = bB[Math.floor(rngBridge.next() * bB.length)];
                        allBridges.push({
                            from_node_id: nodeA.node_id,
                            to_node_id: nodeB.node_id,
                            weight: 10.0,
                            bidirectional: true
                        });
                    }
                }
            }
        }

        this.cachedOverlay = { bridges: allBridges, shortcuts: allShortcuts };
        return this.cachedOverlay;
    }

    async getShard(shardId: string): Promise<ShardData> {
        const id = parseInt(shardId);
        if (isNaN(id) || id < 0 || id >= this.shardCount) throw new Error("Invalid Shard ID");

        const bounds = DEFAULT_REGION.bounds;
        const latStep = (bounds.maxLat - bounds.minLat) / 3;
        const lonStep = (bounds.maxLon - bounds.minLon) / 3;

        const row = Math.floor(id / 3);
        const col = id % 3;

        const cx = bounds.minLon + col * lonStep + lonStep / 2;
        const cy = bounds.minLat + row * latStep + latStep / 2;

        await new Promise(r => setTimeout(r, 200 + Math.random() * 300));
        return this.getShardDataSync(shardId, cx, cy);
    }

    async findPath(srcNodeId: string, dstNodeId: string): Promise<NodeLocation[]> {
        // Need re-implementation of mock path to use real coords/logic? 
        // Or just map shard indices correctly.
        // We can reuse the BFS logic on shard indices (0-8) as the connectivity topology hasn't changed.
        // The coordinate shift is abstracted away in getShardDataSync.

        const parseId = (id: string) => {
            const parts = id.split('-');
            if (parts.length < 2) return { shard: '0' };
            return { shard: parts[0] };
        };

        const srcS = parseId(srcNodeId).shard;
        const dstS = parseId(dstNodeId).shard;

        const pathNodes: NodeLocation[] = [];

        // Helper to retrieve node pos
        const getShardNode = (shardId: string, nodeId: string): NodeLocation => {
            const id = parseInt(shardId);
            const bounds = DEFAULT_REGION.bounds;
            const latStep = (bounds.maxLat - bounds.minLat) / 3;
            const lonStep = (bounds.maxLon - bounds.minLon) / 3;
            const row = Math.floor(id / 3);
            const col = id % 3;
            const cx = bounds.minLon + col * lonStep + lonStep / 2;
            const cy = bounds.minLat + row * latStep + latStep / 2;

            const data = this.getShardDataSync(shardId, cx, cy);
            return data.nodes.find(n => n.node_id === nodeId) ||
                { node_id: nodeId, x: cx, y: cy, shard_id: shardId, type: NodeType.INTERNAL };
        };

        let curr = parseInt(srcS);
        const target = parseInt(dstS);
        const shardPath: string[] = [];

        if (isNaN(curr) || isNaN(target)) {
            pathNodes.push(getShardNode(srcS, srcNodeId));
            pathNodes.push(getShardNode(dstS, dstNodeId));
            return pathNodes;
        }

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

        pathNodes.push(getShardNode(shardPath[0], srcNodeId));

        const rngPath = new LCG(srcNodeId.length + dstNodeId.length);
        for (let i = 0; i < shardPath.length; i++) {
            const sId = shardPath[i];
            const id = parseInt(sId);
            const bounds = DEFAULT_REGION.bounds;
            const latStep = (bounds.maxLat - bounds.minLat) / 3;
            const lonStep = (bounds.maxLon - bounds.minLon) / 3;
            const row = Math.floor(id / 3);
            const col = id % 3;
            const cx = bounds.minLon + col * lonStep + lonStep / 2;
            const cy = bounds.minLat + row * latStep + latStep / 2;

            const sData = this.getShardDataSync(sId, cx, cy);
            // Walk through few random nodes
            const steps = 3 + Math.floor(rngPath.next() * 3);
            for (let k = 0; k < steps; k++) {
                const randomNode = sData.nodes[Math.floor(rngPath.next() * sData.nodes.length)];
                if (randomNode.node_id !== srcNodeId && randomNode.node_id !== dstNodeId) {
                    pathNodes.push(randomNode);
                }
            }
        }
        pathNodes.push(getShardNode(shardPath[shardPath.length - 1], dstNodeId));
        return pathNodes;
    }

    async getNodeShard(nodeId: string): Promise<string | null> {
        // Mock node IDs follow the pattern: {shardId}-{nodeIndex}
        const parts = nodeId.split('-');
        if (parts.length >= 2) {
            const shardId = parts[0];
            const id = parseInt(shardId);
            if (!isNaN(id) && id >= 0 && id < this.shardCount) {
                return shardId;
            }
        }
        return null;
    }

    private getShardDataSync(shardId: string, cx: number, cy: number): ShardData {
        const rng = new LCG(parseInt(shardId) * 1337 + 1);
        const nodes: NodeLocation[] = [];
        const edges: Edge[] = [];
        const numNodes = 20 + Math.floor(rng.next() * 30);

        for (let i = 0; i < numNodes; i++) {
            const angle = rng.next() * Math.PI * 2;
            // Radius in degrees. 0.02 deg ~ 2km?
            const dist = rng.next() * 0.02;
            const isBoundary = (dist > 0.015) && (rng.next() > 0.3);

            nodes.push({
                node_id: `${shardId}-${i}`,
                shard_id: shardId,
                x: cx + Math.cos(angle) * dist, // Lon
                y: cy + Math.sin(angle) * dist, // Lat
                type: isBoundary ? NodeType.BOUNDARY : NodeType.INTERNAL
            });
        }

        nodes.forEach(u => {
            const others = nodes.filter(v => v !== u).map(v => ({
                node: v,
                dist: Math.hypot(v.x - u.x, v.y - u.y)
            })).sort((a, b) => a.dist - b.dist);

            const numEdges = 2 + Math.floor(rng.next() * 2);
            for (let k = 0; k < Math.min(numEdges, others.length); k++) {
                const target = others[k].node;
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
