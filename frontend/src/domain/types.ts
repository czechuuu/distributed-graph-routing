export interface NodeLocation {
    node_id: string; // strict proto says fixed64 (string in JS)
    x: number;
    y: number;
}

export interface Edge {
    from_node_id: string;
    to_node_id: string;
    weight: number;
    bidirectional: boolean;
}

// Derived type for visualization which combines location and connectivity
export interface GraphData {
    nodes: NodeLocation[];
    edges: Edge[];
}

export interface OverlayGraph {
    bridges: Edge[];
    shortcuts: Edge[];
}
