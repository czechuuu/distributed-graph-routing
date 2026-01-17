import React, { useRef, useEffect } from 'react';
import { useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import type { NodeLocation, Edge, OverlayGraph } from '../domain/types';
import { NodeType } from '../domain/types';

interface GraphRendererProps {
    nodes: NodeLocation[];
    intraEdges: Edge[];
    overlayEdges: OverlayGraph;
    onNodeClick?: (node: NodeLocation | null) => void;
    selectedNodeId?: string | null;
    pathEdges?: Edge[];
    pathNodes?: Set<string>;
    onMapClick?: (latlng: L.LatLng) => void;
    isPointClickMode?: boolean;
}

export interface GraphRendererHandle {
    resetView: () => void;
    focusNode: (nodeId: string) => void;
    fitToNodes: (nodesToFit: NodeLocation[]) => void;
}

// Internal component to handle Map events and Drawing
export const GraphRenderer = React.forwardRef<GraphRendererHandle, GraphRendererProps>(({
    nodes, intraEdges, overlayEdges, onNodeClick, selectedNodeId, pathEdges, pathNodes,
    onMapClick, isPointClickMode
}, ref) => {
    const map = useMap();
    const canvasRef = useRef<HTMLCanvasElement>(null);

    // Map Interaction Handle
    React.useImperativeHandle(ref, () => ({
        resetView: () => {
            // In map context, maybe zoom out to bounds of all nodes?
            // Not strictly "reset" to 0,0 but fit content.
            fitToNodesInternal(nodes);
        },
        focusNode: (nodeId: string) => {
            const node = nodes.find(n => n.node_id === nodeId);
            if (node) {
                map.flyTo([node.y, node.x], 15); // y=Lat, x=Lon
            }
        },
        fitToNodes: (nodesToFit: NodeLocation[]) => fitToNodesInternal(nodesToFit)
    }));

    const fitToNodesInternal = (nodesToFit: NodeLocation[]) => {
        if (!nodesToFit.length) return;
        const bounds = L.latLngBounds(nodesToFit.map(n => [n.y, n.x]));
        map.fitBounds(bounds, { padding: [50, 50] });
    };

    // Resize canvas to match map size
    const resizeCanvas = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const size = map.getSize();
        canvas.width = size.x;
        canvas.height = size.y;
        canvas.style.width = `${size.x}px`;
        canvas.style.height = `${size.y}px`;
        draw();
    };

    const draw = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // No transforms on context! We project points directly.

        // Helper to project
        const project = (x: number, y: number) => {
            // x=Lon, y=Lat
            return map.latLngToContainerPoint([y, x]);
        };

        const nodeMap = new Map<string, NodeLocation>();
        const projectedNodes = new Map<string, L.Point>();

        // 1. Cache projected positions to avoid repeating projection logic
        // Only project nodes that are essentially visible or needed?
        // For now project all. Optim optimization: cull.
        nodes.forEach(n => {
            nodeMap.set(n.node_id, n);
            projectedNodes.set(n.node_id, project(n.x, n.y));
        });

        // 2. Draw Edges
        const drawEdge = (e: Edge, color: string, width: number, dashed: boolean = false) => {
            const p1 = projectedNodes.get(e.from_node_id);
            const p2 = projectedNodes.get(e.to_node_id);
            if (p1 && p2) {
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.strokeStyle = color;
                ctx.lineWidth = width;
                if (dashed) ctx.setLineDash([5, 5]); else ctx.setLineDash([]);
                ctx.stroke();
            }
        };

        // Shortcuts (Purple Dashed)
        overlayEdges.shortcuts.forEach(e => drawEdge(e, '#651FFF', 1.5, true));

        // Intra-Edges (Dark Grey)
        intraEdges.forEach(e => drawEdge(e, '#333', 1.2));

        // Bridges (Cyan/Blue)
        overlayEdges.bridges.forEach(e => drawEdge(e, 'rgba(0, 200, 255, 0.8)', 2.5));

        // Path Edges (Bright Yellow/Green)
        if (pathEdges) {
            ctx.shadowBlur = 10;
            ctx.shadowColor = 'rgba(255, 255, 0, 0.8)';
            pathEdges.forEach(e => {
                // Determine if it's a contraction shortcut (long) or detailed edge
                // Heuristic: If we don't have intermediate nodes in our list...
                // Actually, pathEdges passed here are whatever we decided to render.

                // If the edge connects two nodes that are far apart in the node list, etc.
                // Just draw it thick.
                drawEdge(e, '#FFEB3B', 4);
            });
            ctx.shadowBlur = 0;
        }

        // 3. Draw Nodes
        nodes.forEach(n => {
            const p = projectedNodes.get(n.node_id);
            if (!p) return;

            const isSelected = selectedNodeId === n.node_id;
            const isPathNode = pathNodes?.has(n.node_id);

            let radius = 4;
            let color = '#2979FF'; // Vibrant Blue

            if (n.type === NodeType.BOUNDARY) {
                radius = 5;
                color = '#ff5252'; // Red
            }

            if (isPathNode) {
                color = '#FFEB3B'; // Yellow
                radius = 6;
                if (n.type === NodeType.BOUNDARY) radius = 8;
            }

            if (isSelected) {
                color = '#fff';
                radius = 8;
                ctx.shadowBlur = 15;
                ctx.shadowColor = 'white';
            }

            ctx.beginPath();
            ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();

            if (isSelected) {
                ctx.shadowBlur = 0;
                ctx.strokeStyle = '#000';
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        });
    };

    // Events
    useMapEvents({
        move: draw,
        zoom: draw,
        resize: resizeCanvas
    });

    useEffect(() => {
        resizeCanvas();
    }, [nodes, intraEdges, overlayEdges, pathEdges, selectedNodeId, pathNodes]); // redraw on data change

    // Click Handling
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const handleClick = (e: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const clickY = e.clientY - rect.top;

            // Find closest node within tolerance
            let closest: NodeLocation | null = null;
            let minDist = 20; // 20px hit radius

            // Reverse iterate to hit top nodes first?
            for (const n of nodes) {
                const p = map.latLngToContainerPoint([n.y, n.x]);
                const dx = p.x - clickX;
                const dy = p.y - clickY;
                const dist = Math.hypot(dx, dy);
                if (dist < minDist) {
                    minDist = dist;
                    closest = n;
                }
            }

            // If a node was found, handle node click
            if (closest) {
                onNodeClick?.(closest);
            } else if (isPointClickMode && onMapClick) {
                // No node found and in point+click mode: trigger map click
                const latlng = map.containerPointToLatLng(L.point(clickX, clickY));
                onMapClick(latlng);
            } else {
                // Deselect (click empty space)
                onNodeClick?.(null);
            }
        };

        canvas.addEventListener('click', handleClick);
        return () => canvas.removeEventListener('click', handleClick);
    }, [nodes, onNodeClick, onMapClick, isPointClickMode, map]);

    return (
        <canvas
            ref={canvasRef}
            style={{
                position: 'absolute',
                top: 0,
                left: 0,
                zIndex: 500, // Above map tiles, below UI controls? Leaflet z-indexes: Pane 400.
                pointerEvents: 'auto',
                cursor: isPointClickMode ? 'crosshair' : 'default'
            }}
        />
    );
});
