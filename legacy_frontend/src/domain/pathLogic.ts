import type { NodeLocation, Edge } from './types';
import type { ShardControlItem } from '../components/ShardManager';


interface PathContractionResult {
    pathEdges: Edge[];
    pathNodesSet: Set<string>;
}

export function computeContraction(
    activePath: NodeLocation[] | null,
    managedShards: ShardControlItem[]
): PathContractionResult {
    const pathEdges: Edge[] = [];
    const pathNodesSet = new Set<string>();

    if (!activePath || activePath.length <= 1) {
        return { pathEdges, pathNodesSet };
    }

    let currentSegment: NodeLocation[] = [activePath[0]];

    for (let i = 1; i < activePath.length; i++) {
        const prev = activePath[i - 1];
        const curr = activePath[i];

        if (prev.shard_id === curr.shard_id) {
            currentSegment.push(curr);
        } else {
            // Shard Boundary Crossed -> Process previous segment
            processSegment(currentSegment, pathEdges, pathNodesSet, managedShards);

            // Add Bridge Edge
            pathEdges.push({
                from_node_id: prev.node_id,
                to_node_id: curr.node_id,
                weight: 1,
                bidirectional: true
            });
            pathNodesSet.add(prev.node_id);
            pathNodesSet.add(curr.node_id);

            currentSegment = [curr];
        }
    }
    // Process last segment
    processSegment(currentSegment, pathEdges, pathNodesSet, managedShards);

    return { pathEdges, pathNodesSet };
}

function processSegment(
    segment: NodeLocation[],
    pathEdges: Edge[],
    pathNodes: Set<string>,
    shards: ShardControlItem[]
) {
    if (segment.length < 1) return;
    const shardId = segment[0].shard_id;
    const shardMode = shards.find(s => s.id === shardId)?.mode || 'HIDDEN';

    if (shardMode === 'HIDDEN') {
        // Contraction: Shortcut from First to Last (if different)
        const start = segment[0];
        const end = segment[segment.length - 1];

        pathNodes.add(start.node_id);
        pathNodes.add(end.node_id);

        if (start.node_id !== end.node_id) {
            pathEdges.push({
                from_node_id: start.node_id,
                to_node_id: end.node_id,
                weight: 1,
                bidirectional: true
            });
        }
    } else {
        // Visible (ALL or BOUNDARIES): Show full detail
        for (let i = 0; i < segment.length - 1; i++) {
            pathEdges.push({
                from_node_id: segment[i].node_id,
                to_node_id: segment[i + 1].node_id,
                weight: 1,
                bidirectional: true
            });
            pathNodes.add(segment[i].node_id);
            pathNodes.add(segment[i + 1].node_id);
        }
        if (segment.length === 1) pathNodes.add(segment[0].node_id);
    }
}
