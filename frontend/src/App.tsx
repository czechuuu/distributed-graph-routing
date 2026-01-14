import { useEffect, useState, useRef, useMemo } from 'react';
import './App.css';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { MockGraphProvider } from './domain/GraphProvider';
import { ShardManager } from './components/ShardManager';
import type { ShardControlItem } from './components/ShardManager';
import type { NodeLocation, Edge, OverlayGraph, ShardData } from './domain/types';
import { NodeType } from './domain/types';

function App() {
  const [overlayGraph, setOverlayGraph] = useState<OverlayGraph>({ bridges: [], shortcuts: [] });
  const [selectedNode, setSelectedNode] = useState<NodeLocation | null>(null);
  const [searchId, setSearchId] = useState('');
  const graphRef = useRef<GraphRendererHandle>(null);

  // Shard State
  const [managedShards, setManagedShards] = useState<ShardControlItem[]>([]);
  const [shardCache, setShardCache] = useState<Map<string, ShardData>>(new Map());
  const providerRef = useRef(new MockGraphProvider());

  // Initial Load
  useEffect(() => {
    providerRef.current.getOverlayGraph().then(setOverlayGraph);
  }, []);

  // Compute display data
  const { displayNodes, displayEdges, displayOverlayEdges } = useMemo(() => {
    const nodes: NodeLocation[] = [];
    const intraEdges: Edge[] = [];

    // 1. Nodes & Intra-Edges
    managedShards.forEach(s => {
      const data = shardCache.get(s.id);
      if (!data) return;

      if (s.visible) {
        // Visible: All nodes, All intra-edges
        nodes.push(...data.nodes);
        intraEdges.push(...data.edges);
      } else {
        // Hidden: Only Boundary nodes
        nodes.push(...data.nodes.filter(n => n.type === NodeType.BOUNDARY));
      }
    });

    // 2. Overlay Edges (Bridges & Shortcuts)
    // Filter: Draw only if known endpoints (both endpoints must be in loaded shards)
    const validNodeIds = new Set(nodes.map(n => n.node_id));

    const filterOverlay = (edges: Edge[]) => edges.filter(e =>
      validNodeIds.has(e.from_node_id) && validNodeIds.has(e.to_node_id)
    );

    const validBridges = filterOverlay(overlayGraph.bridges);
    const validShortcuts = filterOverlay(overlayGraph.shortcuts);

    return {
      displayNodes: nodes,
      displayEdges: intraEdges,
      displayOverlayEdges: { bridges: validBridges, shortcuts: validShortcuts }
    };
  }, [managedShards, shardCache, overlayGraph]);

  const handleAddShard = async (id: string) => {
    // Add to list first
    setManagedShards(prev => [...prev, { id, visible: true }]);

    // Fetch if not in cache
    if (!shardCache.has(id)) {
      console.log(`Fetching shard ${id}...`);
      try {
        const shardData = await providerRef.current.getShard(id);
        setShardCache(prev => {
          const next = new Map(prev);
          next.set(id, shardData);
          return next;
        });
        // Zoom to new shard
        graphRef.current?.fitToNodes(shardData.nodes);
      } catch (e) {
        console.error(`Failed to fetch shard ${id}`, e);
        alert(`Failed to fetch shard ${id}`);
        // Rollback mgmt
        setManagedShards(prev => prev.filter(s => s.id !== id));
      }
    } else {
      const shardData = shardCache.get(id);
      if (shardData) {
        graphRef.current?.fitToNodes(shardData.nodes);
      }
    }
  };

  const handleToggleShard = (id: string, visible: boolean) => {
    setManagedShards(prev => prev.map(s => s.id === id ? { ...s, visible } : s));
  };

  const handleToggleAll = (visible: boolean) => {
    setManagedShards(prev => prev.map(s => ({ ...s, visible })));
  };

  const handleRemoveShard = (id: string) => {
    setManagedShards(prev => prev.filter(s => s.id !== id));
    setShardCache(prev => {
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
  };

  const handleHighlightShard = (id: string) => {
    const el = document.getElementById(`shard-item-${id}`);
    if (el) {
      el.classList.add('highlight');
      setTimeout(() => el.classList.remove('highlight'), 500);
    }
  };

  const handleNodeClick = (node: NodeLocation | null) => {
    setSelectedNode(node);
  };

  const handleSearch = () => {
    const node = displayNodes.find(n => n.node_id === searchId);
    if (node) {
      setSelectedNode(node);
      graphRef.current?.focusNode(node.node_id);
    } else {
      alert('Node not found (must be in a loaded/visible shard)');
    }
  };

  return (
    <div className="App">
      <GraphRenderer
        ref={graphRef}
        nodes={displayNodes}
        intraEdges={displayEdges}
        overlayEdges={displayOverlayEdges}
        onNodeClick={handleNodeClick}
        selectedNodeId={selectedNode?.node_id}
      />
      <div style={{
        position: 'fixed',
        top: 10,
        left: 10,
        width: '300px',
        color: 'white',
        background: 'rgba(0,0,0,0.6)',
        padding: '12px',
        borderRadius: '8px',
        pointerEvents: 'none',
        userSelect: 'none',
        zIndex: 9999,
        backdropFilter: 'blur(4px)',
        fontFamily: 'monospace',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '1rem', borderBottom: '1px solid rgba(255,255,255,0.2)', paddingBottom: '4px' }}>
          Graph Routing Visualization
        </div>

        <div style={{ fontSize: '0.8rem', opacity: 0.9 }}>
          Total Nodes: {displayNodes.length} &middot; Edges: {displayEdges.length + displayOverlayEdges.bridges.length + displayOverlayEdges.shortcuts.length}
        </div>

        {/* Search Box */}
        <div style={{ display: 'flex', gap: '4px', pointerEvents: 'auto' }}>
          <input
            type="text"
            placeholder="Node ID"
            value={searchId}
            onChange={(e) => setSearchId(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            style={{
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.3)',
              color: 'white',
              borderRadius: '4px',
              padding: '4px',
              flex: 1
            }}
          />
          <button
            onClick={handleSearch}
            style={{
              background: '#444',
              color: 'white',
              border: '1px solid #666',
              borderRadius: '4px',
              padding: '4px 8px',
              cursor: 'pointer'
            }}
          >
            Search
          </button>
        </div>

        <button
          onClick={() => graphRef.current?.resetView()}
          style={{
            pointerEvents: 'auto',
            background: '#444',
            color: 'white',
            border: '1px solid #666',
            borderRadius: '4px',
            padding: '4px 8px',
            fontSize: '0.8rem',
            cursor: 'pointer',
            alignSelf: 'flex-start'
          }}
        >
          Fit View
        </button>

        {selectedNode && (
          <div style={{
            marginTop: '8px',
            paddingTop: '8px',
            borderTop: '1px solid rgba(255,255,255,0.2)',
            fontSize: '0.85rem'
          }}>
            <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Selected Node</div>
            <div>ID: {selectedNode.node_id}</div>
            <div>Shard: {selectedNode.shard_id}</div>
            <div>Type: {selectedNode.type}</div>
            <div>Loc: ({selectedNode.x.toFixed(1)}, {selectedNode.y.toFixed(1)})</div>
          </div>
        )}
      </div>

      <ShardManager
        shards={managedShards}
        onAddShard={handleAddShard}
        onToggleShard={handleToggleShard}
        onRemoveShard={handleRemoveShard}
        onHighlightShard={handleHighlightShard}
        onToggleAll={handleToggleAll}
      />
    </div>
  );
}

export default App;
