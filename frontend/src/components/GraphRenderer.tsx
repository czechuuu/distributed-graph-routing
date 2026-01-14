import React, { useRef, useEffect, useState } from 'react';
import type { GraphData, NodeLocation } from '../domain/types';

interface GraphRendererProps {
    data: GraphData;
}

export interface GraphRendererHandle {
    resetView: () => void;
}

export const GraphRenderer = React.forwardRef<GraphRendererHandle, GraphRendererProps>(({ data }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
    const [isDragging, setIsDragging] = useState(false);
    const [lastPos, setLastPos] = useState({ x: 0, y: 0 });

    React.useImperativeHandle(ref, () => ({
        resetView: () => {
            setTransform({ x: 0, y: 0, k: 1 });
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

        // Draw Edges
        ctx.strokeStyle = '#999';
        ctx.lineWidth = 1;
        ctx.beginPath();
        // Accelerate lookup? For now simple loop O(E*N) is bad if N large.
        // Build map
        const nodeMap = new Map<string, NodeLocation>();
        data.nodes.forEach(n => nodeMap.set(n.node_id, n));

        data.edges.forEach(edge => {
            const u = nodeMap.get(edge.from_node_id);
            const v = nodeMap.get(edge.to_node_id);
            if (u && v) {
                ctx.moveTo(u.x, u.y);
                ctx.lineTo(v.x, v.y);
            }
        });
        ctx.stroke();

        // Draw Nodes
        ctx.fillStyle = '#ff4400';
        data.nodes.forEach(node => {
            ctx.beginPath();
            // Draw small circle
            ctx.arc(node.x, node.y, 3, 0, 2 * Math.PI);
            ctx.fill();
        });

        ctx.restore();
    };

    useEffect(() => {
        draw();
    }, [data, transform]);

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
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isDragging) {
            const dx = e.clientX - lastPos.x;
            const dy = e.clientY - lastPos.y;
            setTransform(t => ({ ...t, x: t.x + dx, y: t.y + dy }));
            setLastPos({ x: e.clientX, y: e.clientY });
        }
    };

    const handleMouseUp = () => {
        setIsDragging(false);
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
