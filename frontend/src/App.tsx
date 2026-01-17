import { useEffect, useState, useRef, useMemo } from 'react';
import './App.css';
import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer } from 'react-leaflet';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { MockGraphProvider } from './domain/GraphProvider';
import { RemoteGraphProvider } from './domain/RemoteGraphProvider';
import { ShardManager } from './components/ShardManager';
import { PathControl } from './components/PathControl';
import type { ShardControlItem, ShardViewMode } from './components/ShardManager';
import type { NodeLocation, Edge, OverlayGraph, ShardData } from './domain/types';
import { NodeType } from './domain/types';
import { computeContraction } from './domain/pathLogic';
import { StartupModal } from './components/StartupModal';
import { type Region } from './domain/MapMetadata';
import { getS2CellId } from './domain/s2utils';
import { DEFAULT_SETTINGS, type AppSettings } from './domain/AppSettings';
import type L from 'leaflet';
import type { GraphProvider } from './domain/GraphProvider';

function App() {
  const [activeRegion, setActiveRegion] = useState<Region | null>(null);
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_SETTINGS);

  const [overlayGraph, setOverlayGraph] = useState<OverlayGraph>({ bridges: [], shortcuts: [] });
  const [selectedNode, setSelectedNode] = useState<NodeLocation | null>(null);
  const [activePath, setActivePath] = useState<NodeLocation[] | null>(null);
  const [isPathLoading, setIsPathLoading] = useState(false);
  const [searchId, setSearchId] = useState('');

  // QOL State
  const [pathSourceId, setPathSourceId] = useState('');
  const [pathTargetId, setPathTargetId] = useState('');
  const [isStatsCollapsed, setIsStatsCollapsed] = useState(false);
  const graphRef = useRef<GraphRendererHandle>(null);

  // Shard State
  const [managedShards, setManagedShards] = useState<ShardControlItem[]>([]);
  const [shardCache, setShardCache] = useState<Map<string, ShardData>>(new Map());
  const [isPointClickMode, setIsPointClickMode] = useState(false);

  const providerRef = useRef<GraphProvider | null>(null);

  // Create provider when settings are set (after region selection)
  useEffect(() => {
    if (!activeRegion) return; // Don't create provider until region is selected

    if (appSettings.useRemote) {
      providerRef.current = new RemoteGraphProvider(appSettings.dataDomainUrl);
    } else {
      providerRef.current = new MockGraphProvider();
    }

    providerRef.current.getOverlayGraph().then(setOverlayGraph);
  }, [activeRegion, appSettings]);

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



  const handleAddShard = async (id: string, initialMode: ShardViewMode = 'ALL', options: { silentError?: boolean } = {}) => {
    if (!providerRef.current) return false;
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
        return true;
      } catch (e) {
        if (!options.silentError) alert('Shard not found: ' + id);
        setManagedShards(prev => prev.filter(s => s.id !== id));
        return false;
      }
    }
    return true;
  };
  // overload/wrapper for ShardManager compat
  // overload/wrapper for ShardManager compat
  const handleAddShardsUI = async (ids: string[]) => {
    const promises = ids.map(id => {
      if (!managedShards.find(s => s.id === id)) {
        return handleAddShard(id, 'ALL', { silentError: true });
      }
      return Promise.resolve(true);
    });

    const results = await Promise.all(promises);
    const missing: string[] = [];
    results.forEach((success, index) => {
      if (!success) missing.push(ids[index]);
    });

    if (missing.length > 0) {
      alert('Shards not found: ' + missing.join(', '));
    }
  };

  const handleToggleShard = (id: string, mode: ShardViewMode) => {
    setManagedShards(prev => prev.map(s => s.id === id ? { ...s, mode } : s));
  };

  const handleToggleAll = (mode: ShardViewMode) => {
    setManagedShards(prev => prev.map(s => ({ ...s, mode })));
  };

  const handleRemoveShard = (id: string) => {
    setManagedShards(prev => prev.filter(s => s.id !== id));
    // setShardCache(prev => { // Removed as per instructions
    //   const next = new Map(prev);
    //   next.delete(id);
    //   return next;
    // });
  };

  const handleHighlightShard = () => {
    // const el = document.getElementById(`shard-item-${id}`); // Removed as per instructions
    // if (el) {
    //   el.classList.add('highlight');
    //   setTimeout(() => el.classList.remove('highlight'), 500);
    // }
    // Optional: flash shard?
  };

  const handleNodeClick = (node: NodeLocation | null) => {
    if (node) {
      console.log('Clicked Node:', node);
      setSelectedNode(node);
      graphRef.current?.focusNode(node.node_id);
    } else {
      setSelectedNode(null);
    }
  };

  const handleSearch = async () => {
    // 1. Check loaded shards first (visible nodes)
    const node = displayNodes.find(n => n.node_id === searchId);
    if (node) {
      setSelectedNode(node);
      graphRef.current?.focusNode(node.node_id);
      return;
    }

    // 2. Node not in loaded shards - check if shard can be resolved
    if (!providerRef.current) {
      alert('Node not found (must be in a loaded/visible shard)');
      return;
    }

    try {
      const shardId = await providerRef.current.getNodeShard(searchId);
      if (shardId) {
        // 3. Check if shard is already loaded but collapsed
        const existingShard = managedShards.find(s => s.id === shardId);
        if (existingShard) {
          // Shard is loaded but collapsed (mode !== 'ALL') - uncollapse it
          if (existingShard.mode !== 'ALL') {
            handleToggleShard(shardId, 'ALL');
          }
          // Focus on the node from the cache
          setTimeout(() => {
            graphRef.current?.focusNode(searchId);
            const loadedNode = shardCache.get(shardId)?.nodes.find(n => n.node_id === searchId);
            if (loadedNode) setSelectedNode(loadedNode);
          }, 100);
          return;
        }

        // 4. Shard not loaded - ask user if they want to load it
        const shouldLoad = window.confirm(
          `Node ${searchId} belongs to shard ${shardId} which is not loaded.\n\nDo you want to load this shard?`
        );
        if (shouldLoad) {
          const success = await handleAddShard(shardId, 'ALL');
          if (success) {
            // Wait for state update, then focus
            setTimeout(() => {
              graphRef.current?.focusNode(searchId);
              // Find and select the node from the newly loaded shard
              const loadedNode = shardCache.get(shardId)?.nodes.find(n => n.node_id === searchId);
              if (loadedNode) setSelectedNode(loadedNode);
            }, 100);
          }
        }
      } else {
        alert('Node not found in any shard');
      }
    } catch (e) {
      alert('Node not found (must be in a loaded/visible shard)');
    }
  };

  const handleFindPath = async () => {
    if (!pathSourceId || !pathTargetId || !providerRef.current) return;
    setIsPathLoading(true);
    try {
      const path = await providerRef.current.findPath(pathSourceId, pathTargetId);
      setActivePath(path);

      // Auto-unhide shards involved in path
      const involvedShardIds = new Set(path.map(n => n.shard_id));

      // 1. Trigger add for missing shards
      involvedShardIds.forEach(sid => {
        const isManaged = managedShards.some(s => s.id === sid);
        if (!isManaged) {
          handleAddShard(sid, 'PATH');
        }
      });

      // 2. Switch hidden shards to PATH mode
      setManagedShards(prev => prev.map(s => {
        if (involvedShardIds.has(s.id) && s.mode === 'NONE') {
          return { ...s, mode: 'PATH' };
        }
        return s;
      }));

    } catch (e) {
      alert('Error finding path: ' + e);
      setActivePath(null);
    } finally {
      setIsPathLoading(false);
    }
  };

  const handleClearPath = () => {
    setActivePath(null);
  };

  const handleSelectRegion = (region: Region, settings: AppSettings) => {
    setAppSettings(settings);
    setActiveRegion(region);
  };

  // Point+Click map handler
  const handleMapClick = (latlng: L.LatLng) => {
    if (!isPointClickMode) return;

    // Calculate S2 cell ID using configured level
    const s2CellId = getS2CellId(latlng.lat, latlng.lng, appSettings.s2CellLevel);

    // Add the shard using existing logic
    handleAddShard(s2CellId, 'ALL');

    // Exit point+click mode after adding
    setIsPointClickMode(false);
  };

  if (!activeRegion) {
    return <StartupModal onSelectRegion={handleSelectRegion} />;
  }

  const centerLat = (activeRegion.bounds.minLat + activeRegion.bounds.maxLat) / 2;
  const centerLon = (activeRegion.bounds.minLon + activeRegion.bounds.maxLon) / 2;

  return (
    <div className="App" style={{ width: '100vw', height: '100vh', display: 'flex' }}>
      <MapContainer
        center={[centerLat, centerLon]}
        zoom={13}
        style={{ width: '100%', height: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <GraphRenderer
          ref={graphRef}
          nodes={displayNodes}
          intraEdges={displayEdges}
          overlayEdges={displayOverlayEdges}
          onNodeClick={handleNodeClick}
          selectedNodeId={selectedNode?.node_id}
          pathEdges={pathEdges}
          pathNodes={pathNodesSet}
          onMapClick={handleMapClick}
          isPointClickMode={isPointClickMode}
        />

        {/* UI Overlay Controls - We need them ON TOP of the map */}
        <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '0px', zIndex: 1000 }}>
          <PathControl
            sourceId={pathSourceId}
            targetId={pathTargetId}
            onSetSource={setPathSourceId}
            onSetTarget={setPathTargetId}
            onFindPath={handleFindPath}
            onClearPath={handleClearPath}
            isLoading={isPathLoading}
          />

          <div style={{ position: 'absolute', top: 10, left: 240, zIndex: 1001 }}>
            <ShardManager
              shards={managedShards}
              onAddShards={handleAddShardsUI}
              onToggleShard={handleToggleShard}
              onRemoveShard={handleRemoveShard}
              onHighlightShard={handleHighlightShard}
              onToggleAll={handleToggleAll}
              isPointClickMode={isPointClickMode}
              onTogglePointClickMode={() => setIsPointClickMode(prev => !prev)}
            />
          </div>

          {/* Stats Panel */}
          {isStatsCollapsed ? (
            <button
              onClick={() => setIsStatsCollapsed(false)}
              title="Open Stats & Search"
              style={{
                position: 'fixed', top: 10, left: 10,
                background: '#333', color: 'white',
                border: '1px solid #555', borderRadius: '50%',
                width: '40px', height: '40px', fontSize: '20px',
                cursor: 'pointer', zIndex: 9999,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 6px rgba(0,0,0,0.3)'
              }}
            >
              🔍
            </button>
          ) : (
            <div style={{
              position: 'fixed',
              top: 10,
              left: 10,
              width: '300px',
              color: 'white',
              background: 'rgba(30,30,30,0.95)',
              padding: '12px',
              borderRadius: '8px',
              zIndex: 9999,
              backdropFilter: 'blur(4px)',
              fontFamily: 'monospace',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
              border: '1px solid #444'
            }}>
              <div style={{
                fontWeight: 'bold', fontSize: '1rem', borderBottom: '1px solid rgba(255,255,255,0.2)', paddingBottom: '4px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center'
              }}>
                <span>Find node</span>
                <button onClick={() => setIsStatsCollapsed(true)} style={{ background: 'transparent', border: 'none', color: '#aaa', cursor: 'pointer' }}>✕</button>
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
                  style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.3)', color: 'white', borderRadius: '4px', padding: '4px', flex: 1 }}
                />
                <button
                  onClick={handleSearch}
                  style={{ background: '#444', color: 'white', border: '1px solid #666', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer' }}
                >
                  Search
                </button>
              </div>

              <button
                onClick={() => graphRef.current?.resetView()}
                style={{ background: '#444', color: 'white', border: '1px solid #666', borderRadius: '4px', padding: '4px 8px', fontSize: '0.8rem', cursor: 'pointer', alignSelf: 'flex-start' }}
              >
                Fit View
              </button>

              {selectedNode && (
                <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.2)', fontSize: '0.85rem' }}>
                  <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Selected Node</div>
                  <div>ID: {selectedNode.node_id}</div>
                  <div>Shard: {selectedNode.shard_id}</div>
                  <div>Type: {selectedNode.type}</div>
                  <div>Loc: ({selectedNode.y.toFixed(4)}, {selectedNode.x.toFixed(4)})</div>

                  <div style={{ display: 'flex', gap: '4px', marginTop: '6px' }}>
                    <button
                      onClick={() => setPathSourceId(selectedNode.node_id)}
                      style={{ flex: 1, background: '#2196F3', border: 'none', color: 'white', padding: '2px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}
                    >
                      Set Src
                    </button>
                    <button
                      onClick={() => setPathTargetId(selectedNode.node_id)}
                      style={{ flex: 1, background: '#4CAF50', border: 'none', color: 'white', padding: '2px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}
                    >
                      Set Dst
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </MapContainer>
    </div>
  );
}

export default App;
