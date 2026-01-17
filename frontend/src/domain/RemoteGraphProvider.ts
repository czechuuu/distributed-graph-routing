import type { GraphProvider } from './GraphProvider';
import type { OverlayGraph, ShardData, NodeLocation, Edge } from './types';
import { NodeType } from './types';
import { OverlayGraph as ProtoOverlay, ShardGraph as ProtoShard, ShortcutPath as ProtoShortcut } from './proto/bigtable_storage';

export class RemoteGraphProvider implements GraphProvider {
    private baseUrl: string;
    private overlayPromise: Promise<OverlayGraph> | null = null;

    constructor(baseUrl: string = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    async getOverlayGraph(): Promise<OverlayGraph> {
        if (this.overlayPromise) return this.overlayPromise;
        this.overlayPromise = this.fetchOverlay();
        return this.overlayPromise;
    }

    private async fetchOverlay(): Promise<OverlayGraph> {
        const res = await fetch(`${this.baseUrl}/overlay`);
        if (!res.ok) throw new Error(`Failed to fetch overlay: ${res.statusText}`);
        const data = await res.json() as ProtoOverlay;

        // Map Proto to Domain
        // Proto: bridges: Edge[], shortcuts: Edge[]
        // Domain: same structure
        // But formatting might differ (fixed64 string vs string)

        const mapEdge = (e: any): Edge => ({
            from_node_id: e.fromNodeId || e.from_node_id,
            to_node_id: e.toNodeId || e.to_node_id,
            weight: e.weight || 0,
            bidirectional: e.bidirectional || false
        });

        return {
            bridges: (data.bridges || []).map(mapEdge),
            shortcuts: (data.shortcuts || []).map(mapEdge)
        };
    }

    async getShard(shardId: string): Promise<ShardData> {
        // Ensure overlay is loading/loaded to identify boundary nodes
        let overlay: OverlayGraph | null = null;
        try {
            overlay = await this.getOverlayGraph();
        } catch (e) {
            console.warn("Could not load overlay for boundary identification", e);
        }

        const res = await fetch(`${this.baseUrl}/shard/${shardId}`);
        if (!res.ok) throw new Error(`Failed to fetch shard ${shardId}: ${res.statusText}`);
        const data = await res.json() as ProtoShard;

        const boundaryNodeIds = new Set<string>();
        if (overlay) {
            overlay.bridges.forEach(b => {
                boundaryNodeIds.add(b.from_node_id);
                boundaryNodeIds.add(b.to_node_id);
            });
        }

        const mapEdge = (e: any): Edge => ({
            from_node_id: e.fromNodeId || e.from_node_id,
            to_node_id: e.toNodeId || e.to_node_id,
            weight: e.weight || 0,
            bidirectional: e.bidirectional || false
        });

        const nodes: NodeLocation[] = (data.locations || []).map((l: any) => {
            const nid = String(l.nodeId || l.node_id);
            return {
                node_id: nid,
                shard_id: shardId,
                x: l.x,
                y: l.y,
                type: boundaryNodeIds.has(nid) ? NodeType.BOUNDARY : NodeType.INTERNAL
            };
        });

        const edges: Edge[] = (data.edges || []).map(mapEdge);

        return { nodes, edges };
    }

    async findPath(srcNodeId: string, dstNodeId: string): Promise<NodeLocation[]> {
        // 1. Get Path IDs
        const res = await fetch(`${this.baseUrl}/shortcut/${srcNodeId}/${dstNodeId}`);
        if (!res.ok) {
            console.warn("Shortcut not found");
            return [];
        }
        const pathData = await res.json() as ProtoShortcut;
        const nodeIds = pathData.nodes || [];

        if (nodeIds.length === 0) return [];

        // 2. Resolve Shards for these nodes
        const shardRes = await fetch(`${this.baseUrl}/node-shards/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_ids: nodeIds })
        });

        const shardMap: Record<string, string> = await shardRes.json(); // NodeID -> ShardID

        // 3. Fetch necessary shards to get locations
        // Optimization: Deduplicate shards
        const uniqueShards = new Set<string>(Object.values(shardMap));
        const fetchedShards = new Map<string, ShardData>();

        await Promise.all(Array.from(uniqueShards).map(async (sid) => {
            try {
                const sData = await this.getShard(sid);
                fetchedShards.set(sid, sData);
            } catch (e) {
                console.error(`Failed to fetch shard ${sid} for path resolution`);
            }
        }));

        // 4. Construct result
        const result: NodeLocation[] = [];
        for (const nidNum of nodeIds) {
            const nid = nidNum.toString();
            const sid = shardMap[nid];
            if (sid && fetchedShards.has(sid)) {
                const sData = fetchedShards.get(sid)!;
                const node = sData.nodes.find(n => n.node_id === nid);
                if (node) {
                    result.push(node);
                } else {
                    // Fallback if node not found in shard (should not happen)
                    result.push({
                        node_id: nid, shard_id: sid, x: 0, y: 0, type: NodeType.INTERNAL
                    });
                }
            }
        }
        return result;
    }

    async getNodeShard(nodeId: string): Promise<string | null> {
        try {
            const res = await fetch(`${this.baseUrl}/node-shard/${nodeId}`);
            if (!res.ok) return null;
            const data = await res.json();
            return data.shard_id || null;
        } catch {
            return null;
        }
    }
}
