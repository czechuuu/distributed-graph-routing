import React, { useRef, useEffect, useState } from 'react';
import type { GraphData, NodeLocation } from '../domain/types';

interface GraphRendererProps {
    data: GraphData;
}

export interface GraphRendererHandle {
    resetView: () => void;
    focusNode: (nodeId: string) => void;
}

interface GraphRendererProps {
    data: GraphData;
    onNodeClick?: (node: NodeLocation | null) => void;
    selectedNodeId?: string | null;
}

export const GraphRenderer = React.forwardRef<GraphRendererHandle, GraphRendererProps>(({ data, onNodeClick, selectedNodeId }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
    const [isDragging, setIsDragging] = useState(false);
    const [lastPos, setLastPos] = useState({ x: 0, y: 0 });
    const dragStartPos = useRef({ x: 0, y: 0 });

    React.useImperativeHandle(ref, () => ({
        resetView: () => {
            setTransform({ x: 0, y: 0, k: 1 });
        },
        focusNode: (nodeId: string) => {
            const node = data.nodes.find(n => n.node_id === nodeId);
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
        }
    }));

    const draw = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        // Clear
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.save();
        // Apply transform
        ctx.translate(transform.x, transform.y);
        ctx.scale(transform.k, transform.k);

        // Draw Edges - Pass 1: Unselected
        ctx.lineWidth = 1;
        ctx.strokeStyle = '#999';
        ctx.beginPath();
        // Accelerate lookup? For now simple loop O(E*N) is bad if N large.
        // Build map
        const nodeMap = new Map<string, NodeLocation>();
        data.nodes.forEach(n => nodeMap.set(n.node_id, n));

        // Separate edges
        const normalEdges: typeof data.edges = [];
        const highlightedEdges: typeof data.edges = [];
        const neighborIds = new Set<string>();

        data.edges.forEach(edge => {
            if (selectedNodeId && (edge.from_node_id === selectedNodeId || edge.to_node_id === selectedNodeId)) {
                highlightedEdges.push(edge);
                neighborIds.add(edge.from_node_id === selectedNodeId ? edge.to_node_id : edge.from_node_id);
            } else {
                normalEdges.push(edge);
            }
        });

        // Draw normal
        normalEdges.forEach(edge => {
            const u = nodeMap.get(edge.from_node_id);
            const v = nodeMap.get(edge.to_node_id);
            if (u && v) {
                ctx.moveTo(u.x, u.y);
                ctx.lineTo(v.x, v.y);
            }
        });
        ctx.stroke();

        // Draw Edges - Pass 2: Highlighted
        if (highlightedEdges.length > 0) {
            ctx.beginPath();
            ctx.strokeStyle = '#F0E68C'; // Khaki (dusty pastel yellow)
            ctx.lineWidth = 1.5;
            highlightedEdges.forEach(edge => {
                const u = nodeMap.get(edge.from_node_id);
                const v = nodeMap.get(edge.to_node_id);
                if (u && v) {
                    ctx.moveTo(u.x, u.y);
                    ctx.lineTo(v.x, v.y);
                }
            });
            ctx.stroke();
        }

        // Draw Nodes
        data.nodes.forEach(node => {
            ctx.beginPath();
            const isSelected = node.node_id === selectedNodeId;
            const isNeighbor = neighborIds.has(node.node_id);

            ctx.fillStyle = isSelected ? '#ffff00' : '#ff4400';
            const radius = isSelected ? 6 : 3;

            ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
            ctx.fill();

            if (isSelected) {
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 1 / transform.k;
                ctx.stroke();
            } else if (isNeighbor) {
                ctx.strokeStyle = '#F0E68C'; // Matches highlighted edges
                ctx.lineWidth = 1.2 / transform.k;
                ctx.stroke();
            }
        });

        ctx.restore();
    };

    useEffect(() => {
        draw();
    }, [data, transform, selectedNodeId]);

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
        // e.preventDefault() is implicitly handled by React for wheel event in some cases, 
        // but explicit preventDefault on ref is safer for non-passive events. 
        // Here we just calculate state.

        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;

        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const scaleAmount = -e.deltaY * 0.001;
        const newScale = Math.max(0.1, Math.min(10, transform.k * (1 + scaleAmount)));

        // Calculate world coordinates of mouse before zoom
        const wx = (mx - transform.x) / transform.k;
        const wy = (my - transform.y) / transform.k;

        // Calculate new translation to keep world coordinates under mouse fixed
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

        // Transform to world space
        const wx = (mx - transform.x) / transform.k;
        const wy = (my - transform.y) / transform.k;

        let clickedNode: NodeLocation | null = null;
        for (const node of data.nodes) {
            // Hit radius 8
            if (Math.hypot(node.x - wx, node.y - wy) < 8) {
                clickedNode = node;
                break;
            }
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
