// Derived type for visualization
export type NodeType = 'INTERNAL' | 'BOUNDARY';
export const NodeType = {
    INTERNAL: 'INTERNAL' as NodeType,
    BOUNDARY: 'BOUNDARY' as NodeType
};

export interface NodeLocation {
    node_id: string; // strict proto says fixed64 (string in JS)
    shard_id: string;
    x: number;
    y: number;
    type: NodeType;
}

export interface Edge {
    from_node_id: string;
    to_node_id: string;
    weight: number;
    bidirectional: boolean;
}

// Full Topology (Global)
export interface OverlayGraph {
    bridges: Edge[];
    shortcuts: Edge[];
}

// Local Details (Per Shard)
export interface ShardData {
    nodes: NodeLocation[];
    edges: Edge[]; // Intra-shard edges
}
