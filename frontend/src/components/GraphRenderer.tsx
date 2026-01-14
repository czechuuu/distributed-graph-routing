import React, { useRef, useEffect, useState } from 'react';
import type { NodeLocation, Edge, OverlayGraph } from '../domain/types';
import { NodeType } from '../domain/types';

interface GraphRendererProps {
    nodes: NodeLocation[];
    intraEdges: Edge[];
    overlayEdges: OverlayGraph; // Contains bridges and shortcuts
    onNodeClick?: (node: NodeLocation | null) => void;
    selectedNodeId?: string | null;
    pathEdges?: Edge[];
    pathNodes?: Set<string>;
}

export interface GraphRendererHandle {
    resetView: () => void;
    focusNode: (nodeId: string) => void;
    fitToNodes: (nodes: NodeLocation[]) => void;
}

export const GraphRenderer = React.forwardRef<GraphRendererHandle, GraphRendererProps>(({
    nodes, intraEdges, overlayEdges, onNodeClick, selectedNodeId, pathEdges, pathNodes
}, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
    const [isDragging, setIsDragging] = useState(false);
    const [lastPos, setLastPos] = useState({ x: 0, y: 0 });
    const dragStartPos = useRef({ x: 0, y: 0 });

    React.useImperativeHandle(ref, () => ({
        resetView: () => {
            if (nodes.length === 0) {
                setTransform({ x: 0, y: 0, k: 1 });
            } else {
                fitToNodesInternal(nodes);
            }
        },
        focusNode: (nodeId: string) => {
            const node = nodes.find(n => n.node_id === nodeId);
            if (node && canvasRef.current) {
                const targetScale = 2.5;
                const cx = canvasRef.current.width / 2;
                const cy = canvasRef.current.height / 2;
                setTransform({
                    k: targetScale,
                    x: cx - node.x * targetScale,
                    y: cy - node.y * targetScale
                });
            }
        },
        fitToNodes: (nodesToFit: NodeLocation[]) => fitToNodesInternal(nodesToFit)
    }));

    const fitToNodesInternal = (nodesToFit: NodeLocation[]) => {
        if (!nodesToFit.length || !canvasRef.current) return;

        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        nodesToFit.forEach(n => {
            if (n.x < minX) minX = n.x;
            if (n.x > maxX) maxX = n.x;
            if (n.y < minY) minY = n.y;
            if (n.y > maxY) maxY = n.y;
        });

        const padding = 50;
        const width = maxX - minX + padding * 2;
        const height = maxY - minY + padding * 2;

        if (width <= 0 || height <= 0) return;

        const canvas = canvasRef.current;
        const scaleX = canvas.width / width;
        const scaleY = canvas.height / height;
        const scale = Math.min(scaleX, scaleY, 2);

        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;

        setTransform({
            k: scale,
            x: canvas.width / 2 - centerX * scale,
            y: canvas.height / 2 - centerY * scale
        });
    };

    const draw = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.save();
        ctx.translate(transform.x, transform.y);
        ctx.scale(transform.k, transform.k);

        // Prep Data
        const nodeMap = new Map<string, NodeLocation>();
        nodes.forEach(n => nodeMap.set(n.node_id, n));

        // Neighbor/Highlight tracking
        const neighborIds = new Set<string>();
        const allEdges = [...intraEdges, ...overlayEdges.bridges, ...overlayEdges.shortcuts];

        if (selectedNodeId) {
            allEdges.forEach(e => {
                if (e.from_node_id === selectedNodeId) neighborIds.add(e.to_node_id);
                if (e.to_node_id === selectedNodeId) neighborIds.add(e.from_node_id);
            });
        }

        const drawEdge = (edge: Edge, color: string, width: number, dashed: boolean) => {
            const u = nodeMap.get(edge.from_node_id);
            const v = nodeMap.get(edge.to_node_id);
            if (u && v) {
                ctx.beginPath();
                ctx.moveTo(u.x, u.y);
                ctx.lineTo(v.x, v.y);
                ctx.strokeStyle = color;
                ctx.lineWidth = width / transform.k;
                if (dashed) ctx.setLineDash([5 / transform.k, 5 / transform.k]);
                else ctx.setLineDash([]);
                ctx.stroke();
            }
        };

        // LAYER 1: Shortcuts (Translucent, Dashed)
        overlayEdges.shortcuts.forEach(e => {
            drawEdge(e, 'rgba(150, 150, 150, 0.5)', 1, true);
        });

        // LAYER 2: Intra-Edges (Thin, Solid)
        intraEdges.forEach(e => {
            drawEdge(e, '#888', 1, false);
        });

        // LAYER 3: Bridges (Thick, Distinct Shade - Blue/Purple)
        overlayEdges.bridges.forEach(e => {
            drawEdge(e, '#6A0DAD', 2.5, false); // Purple
        });

        // LAYER 4: Path Edges (Highest Priority, Cyan)
        if (pathEdges) {
            pathEdges.forEach(e => {
                drawEdge(e, '#00FFFF', 3, false);
            });
        }

        // HIGHLIGHT EDGES PASS (Overdraw)
        if (selectedNodeId) {
            allEdges.forEach(e => {
                if (e.from_node_id === selectedNodeId || e.to_node_id === selectedNodeId) {
                    drawEdge(e, '#F0E68C', 2.5, false);
                }
            });
        }

        // NODES
        const internalNodes = nodes.filter(n => n.type === NodeType.INTERNAL);
        const boundaryNodes = nodes.filter(n => n.type === NodeType.BOUNDARY);

        const drawNode = (node: NodeLocation) => {
            ctx.beginPath();
            const isSelected = node.node_id === selectedNodeId;
            const isNeighbor = neighborIds.has(node.node_id);
            const isBoundary = node.type === NodeType.BOUNDARY;
            const isPathNode = pathNodes?.has(node.node_id);

            // Path Halo
            if (isPathNode) {
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, (isBoundary ? 6 : 3) + 4, 0, 2 * Math.PI);
                ctx.fillStyle = 'rgba(0, 255, 255, 0.4)';
                ctx.fill();
                ctx.restore();
                ctx.beginPath(); // reset for main node
            }

            let radius = isBoundary ? 6 : 3;
            let fill = isBoundary ? '#FF3333' : '#AA4444';

            if (isSelected) {
                radius *= 1.5;
                fill = '#FFFF00';
            }

            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
            ctx.fillStyle = fill;
            ctx.fill();

            // Outline
            ctx.setLineDash([]);
            if (isSelected) {
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 1.5 / transform.k;
                ctx.stroke();
            } else if (isNeighbor) {
                ctx.strokeStyle = '#F0E68C';
                ctx.lineWidth = 1.2 / transform.k;
                ctx.stroke();
            }
        };

        internalNodes.forEach(drawNode);
        boundaryNodes.forEach(drawNode);

        ctx.restore();
    };

    useEffect(() => {
        draw();
    }, [nodes, intraEdges, overlayEdges, transform, selectedNodeId, pathEdges, pathNodes]);

    // Handle Resize
    useEffect(() => {
        const handleResize = () => {
            if (canvasRef.current && canvasRef.current.parentElement) {
                canvasRef.current.width = canvasRef.current.parentElement.clientWidth;
                canvasRef.current.height = canvasRef.current.parentElement.clientHeight;
                draw();
            }
        };
        window.addEventListener('resize', handleResize);
        handleResize(); // Init
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    const handleWheel = (e: React.WheelEvent) => {
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;

        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const scaleAmount = -e.deltaY * 0.001;
        const newScale = Math.max(0.1, Math.min(10, transform.k * (1 + scaleAmount)));

        const wx = (mx - transform.x) / transform.k;
        const wy = (my - transform.y) / transform.k;
        const newX = mx - wx * newScale;
        const newY = my - wy * newScale;

        setTransform({ x: newX, y: newY, k: newScale });
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        setIsDragging(true);
        setLastPos({ x: e.clientX, y: e.clientY });
        dragStartPos.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isDragging) {
            const dx = e.clientX - lastPos.x;
            const dy = e.clientY - lastPos.y;
            setTransform(t => ({ ...t, x: t.x + dx, y: t.y + dy }));
            setLastPos({ x: e.clientX, y: e.clientY });
        }
    };

    const handleMouseUp = (e: React.MouseEvent) => {
        setIsDragging(false);
        const dist = Math.hypot(e.clientX - dragStartPos.current.x, e.clientY - dragStartPos.current.y);
        if (dist < 5) {
            handleCanvasClick(e);
        }
    };

    const handleCanvasClick = (e: React.MouseEvent) => {
        if (!onNodeClick) return;
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const wx = (mx - transform.x) / transform.k;
        const wy = (my - transform.y) / transform.k;

        let clickedNode: NodeLocation | null = null;
        const checkHit = (n: NodeLocation) => Math.hypot(n.x - wx, n.y - wy) < 8;

        clickedNode = nodes.find(n => n.type === NodeType.BOUNDARY && checkHit(n)) || null;
        if (!clickedNode) {
            clickedNode = nodes.find(n => n.type === NodeType.INTERNAL && checkHit(n)) || null;
        }
        onNodeClick(clickedNode);
    };

    return (
        <div style={{ width: '100%', height: '100vh', overflow: 'hidden', background: '#111' }}>
            <canvas
                ref={canvasRef}
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                style={{ display: 'block' }}
            />
        </div>
    );
});
