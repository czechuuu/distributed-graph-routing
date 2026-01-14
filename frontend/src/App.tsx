import { useEffect, useState, useRef, useMemo } from 'react';
import './App.css';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { MockGraphProvider } from './domain/GraphProvider';
import { ShardManager } from './components/ShardManager';
import { PathControl } from './components/PathControl';
import type { ShardControlItem, ShardViewMode } from './components/ShardManager';
import type { NodeLocation, Edge, OverlayGraph, ShardData } from './domain/types';
import { NodeType } from './domain/types';
import { computeContraction } from './domain/pathLogic';

function App() {
  const [overlayGraph, setOverlayGraph] = useState<OverlayGraph>({ bridges: [], shortcuts: [] });
  const [selectedNode, setSelectedNode] = useState<NodeLocation | null>(null);
  const [searchId, setSearchId] = useState('');
  const [activePath, setActivePath] = useState<NodeLocation[] | null>(null);
  const [isPathLoading, setIsPathLoading] = useState(false);
  const graphRef = useRef<GraphRendererHandle>(null);

  // Shard State
  const [managedShards, setManagedShards] = useState<ShardControlItem[]>([]);
  const [shardCache, setShardCache] = useState<Map<string, ShardData>>(new Map());
  const providerRef = useRef(new MockGraphProvider());

  // Initial Load
  useEffect(() => {
    providerRef.current.getOverlayGraph().then(setOverlayGraph);
  }, []);

  // Compute display data & Contraction Logic
  const { displayNodes, displayEdges, displayOverlayEdges, pathEdges, pathNodesSet } = useMemo(() => {
    const nodes: NodeLocation[] = [];
    const intraEdges: Edge[] = [];

    // 0. Path Processing & Contraction
    const { pathEdges: activePathEdges, pathNodesSet } = computeContraction(activePath, managedShards);

    // 1. Shard Content (Nodes/Intra-Edges)
    managedShards.forEach(s => {
      const data = shardCache.get(s.id);
      if (!data) return;

      if (s.mode === 'ALL') {
        // Full Shard
        nodes.push(...data.nodes);
        intraEdges.push(...data.edges);
      } else if (s.mode === 'PATH') {
        // Path Mode: Show Boundary Nodes + ONLY Path Nodes in this shard
        const bNodes = data.nodes.filter(n => n.type === NodeType.BOUNDARY);
        // Add path nodes that are in this shard (avoid duplicates with boundary)
        const pNodes = data.nodes.filter(n => pathNodesSet.has(n.node_id) && n.type !== NodeType.BOUNDARY);

        nodes.push(...bNodes, ...pNodes);

        // Add intra-edges that are part of path? Already in activePathEdges.
        // What about intra-edges for context? Maybe not.
      } else {
        // NONE: Only Boundary Nodes
        nodes.push(...data.nodes.filter(n => n.type === NodeType.BOUNDARY));
      }
    });

    // 2. Overlay Edges
    const validNodeIds = new Set(nodes.map(n => n.node_id));
    const filterOverlay = (edges: Edge[]) => edges.filter(e =>
      validNodeIds.has(e.from_node_id) && validNodeIds.has(e.to_node_id)
    );

    const validBridges = filterOverlay(overlayGraph.bridges);
    const validShortcuts = filterOverlay(overlayGraph.shortcuts);

    return {
      displayNodes: nodes,
      displayEdges: intraEdges,
      displayOverlayEdges: { bridges: validBridges, shortcuts: validShortcuts },
      pathEdges: activePathEdges,
      pathNodesSet
    };
  }, [managedShards, shardCache, overlayGraph, activePath]);



  const handleAddShard = async (id: string, initialMode: ShardViewMode = 'ALL') => {
    setManagedShards(prev => [...prev, { id, mode: initialMode }]);
    if (!shardCache.has(id)) {
      try {
        const shardData = await providerRef.current.getShard(id);
        setShardCache(prev => {
          const next = new Map(prev);
          next.set(id, shardData);
          return next;
        });
        if (initialMode !== 'NONE') graphRef.current?.fitToNodes(shardData.nodes);
      } catch (e) {
        setManagedShards(prev => prev.filter(s => s.id !== id));
      }
    }
  };
  // overload/wrapper for ShardManager compat
  const handleAddShardUI = (id: string) => handleAddShard(id, 'ALL');

  const handleToggleShard = (id: string, mode: ShardViewMode) => {
    setManagedShards(prev => prev.map(s => s.id === id ? { ...s, mode } : s));
  };

  const handleToggleAll = (mode: ShardViewMode) => {
    setManagedShards(prev => prev.map(s => ({ ...s, mode })));
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

  const handleFindPath = async (src: string, dst: string) => {
    setIsPathLoading(true);
    try {
      const path = await providerRef.current.findPath(src, dst);
      setActivePath(path);

      // Auto-load & set mode for relevant shards
      const shardsInPath = new Set(path.map(n => n.shard_id));
      const needed = Array.from(shardsInPath);

      // We can't auto-fetch all inside 'setManagedShards' easily with async.
      // For now, let's just ensure they are managed.
      // Best effort: switch existing to PATH mode if NONE.
      setManagedShards(prev => {
        const next = [...prev];
        needed.forEach(sid => {
          const idx = next.findIndex(s => s.id === sid);
          if (idx >= 0) {
            // If hidden, switch to PATH
            if (next[idx].mode === 'NONE') next[idx] = { ...next[idx], mode: 'PATH' };
          } else {
            // Add new shard in ALL mode? Or PATH mode?
            // Let's add in PATH mode to not overwhelm.
            next.push({ id: sid, mode: 'PATH' });
            // IMPORTANT: We need to trigger fetch!
            // This simple set state won't fetch. 
            // We should call handleAddShard logic.
          }
        });
        return next;
      });

      // Trigger fetches for missing
      needed.forEach(sid => {
        if (!shardCache.has(sid)) handleAddShard(sid, 'PATH');
      });

    } catch (e) {
      alert('Path validation failed or error: ' + e);
      setActivePath(null);
    } finally {
      setIsPathLoading(false);
    }
  };

  return (
    <div className="App">
      <PathControl onFindPath={handleFindPath} isLoading={isPathLoading} />

      <GraphRenderer
        ref={graphRef}
        nodes={displayNodes}
        intraEdges={displayEdges}
        overlayEdges={displayOverlayEdges}
        onNodeClick={handleNodeClick}
        selectedNodeId={selectedNode?.node_id}
        pathEdges={pathEdges}
        pathNodes={pathNodesSet}
      />
      {/* ... (stats div) ... */}
      <div style={{
        /* ... existing style ... */
        display: 'none' // Optionally hide if reusing new PathControl? 
        // No, keep stats.
      }}
      >
        {/* ... (Searchbox etc) ... */}
      </div>

      {/* Re-using existing overlays logic implicitly by not deleting it */}

      <div style={{
        position: 'fixed',
        top: 10,
        left: 220, // Moved to allow PathControl
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
          Total Nodes: {displayNodes.length} &middot; Edges: {displayEdges.length + displayOverlayEdges.bridges.length + displayOverlayEdges.shortcuts.length} (Path: {activePath ? activePath.length : 0})
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
        onAddShard={handleAddShardUI}
        onToggleShard={handleToggleShard}
        onRemoveShard={handleRemoveShard}
        onHighlightShard={handleHighlightShard}
        onToggleAll={handleToggleAll}
      />
    </div>
  );
}


export default App;
