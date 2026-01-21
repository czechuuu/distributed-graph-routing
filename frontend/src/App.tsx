import { useEffect, useState, useRef, useMemo } from 'react';
import './App.css';
import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer } from 'react-leaflet';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { MockGraphProvider } from './domain/GraphProvider';
import { RemoteGraphProvider } from './domain/RemoteGraphProvider';
import { ServingLayerClient } from './domain/ServingLayerClient';
import { ShardManager } from './components/ShardManager';
import { PathControl } from './components/PathControl';
import type { ShardControlItem, ShardViewMode } from './components/ShardManager';
import type { NodeLocation, Edge, OverlayGraph, ShardData } from './domain/types';
import { NodeType } from './domain/types';
import { StartupModal } from './components/StartupModal';
import { type Region } from './domain/MapMetadata';
import { getS2CellId } from './domain/s2utils';
import { DEFAULT_SETTINGS, type AppSettings } from './domain/AppSettings';
import L from 'leaflet';
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
  const findNodePanelRef = useRef<HTMLDivElement>(null);
  const shardManagerPanelRef = useRef<HTMLDivElement>(null);

  // Shard State
  const [managedShards, setManagedShards] = useState<ShardControlItem[]>([]);
  const [shardCache, setShardCache] = useState<Map<string, ShardData>>(new Map());
  const [isPointClickMode, setIsPointClickMode] = useState(false);
  const [isFindNodeMode, setIsFindNodeMode] = useState(false);

  const providerRef = useRef<GraphProvider | null>(null);
  const servingLayerClientRef = useRef<ServingLayerClient | null>(null);

  // Disable Leaflet event propagation on UI panels so text is selectable
  useEffect(() => {
    const panels = [findNodePanelRef.current, shardManagerPanelRef.current];
    panels.forEach(panel => {
      if (panel) {
        L.DomEvent.disableClickPropagation(panel);
        L.DomEvent.disableScrollPropagation(panel);
      }
    });
  });

  // Create provider when settings are set (after region selection)
  useEffect(() => {
    if (!activeRegion) return; // Don't create provider until region is selected

    if (appSettings.useRemote) {
      providerRef.current = new RemoteGraphProvider(appSettings.dataDomainUrl);
    } else {
      providerRef.current = new MockGraphProvider();
    }

    // Create serving layer client
    servingLayerClientRef.current = new ServingLayerClient(appSettings.servingLayerUrl);

    providerRef.current.getOverlayGraph().then(setOverlayGraph);
  }, [activeRegion, appSettings]);

  // Helper to update LRU timestamp
  const touchShard = (id: string) => {
    setManagedShards(prev => prev.map(s =>
      s.id === id ? { ...s, lastAccessedAt: Date.now() } : s
    ));
  };

  // Compute display data - simplified with paths always drawn separately
  const { displayNodes, displayEdges, displayOverlayEdges, pathEdges, pathNodesSet } = useMemo(() => {
    const nodes: NodeLocation[] = [];
    const intraEdges: Edge[] = [];

    // Compute path edges from activePath (always visible)
    const pathNodeIds = new Set(activePath?.map(n => n.node_id) ?? []);
    const pathEdgesList: Edge[] = [];
    if (activePath && activePath.length > 1) {
      for (let i = 0; i < activePath.length - 1; i++) {
        pathEdgesList.push({
          from_node_id: activePath[i].node_id,
          to_node_id: activePath[i + 1].node_id,
          weight: 0,
          bidirectional: false
        });
      }
    }

    // Collect nodes based on shard visibility mode
    managedShards.forEach(s => {
      const data = shardCache.get(s.id);
      if (!data) return;

      if (s.mode === 'ALL') {
        nodes.push(...data.nodes);
        intraEdges.push(...data.edges);
      } else if (s.mode === 'BOUNDARIES') {
        // Only boundary nodes, no intra-edges
        nodes.push(...data.nodes.filter(n => n.type === NodeType.BOUNDARY));
      }
      // HIDDEN: add nothing by default
    });

    // Add selected node + neighbors (even from HIDDEN shards)
    if (selectedNode) {
      for (const [_shardId, data] of shardCache.entries()) {
        const nodeInShard = data.nodes.find(n => n.node_id === selectedNode.node_id);
        if (nodeInShard) {
          // Add selected node if not already present
          if (!nodes.find(n => n.node_id === selectedNode.node_id)) {
            nodes.push(selectedNode);
          }

          // Find and add neighbors
          const neighborIds = new Set<string>();
          data.edges.forEach(e => {
            if (e.from_node_id === selectedNode.node_id) neighborIds.add(e.to_node_id);
            if (e.to_node_id === selectedNode.node_id) neighborIds.add(e.from_node_id);
          });

          const neighbors = data.nodes.filter(n =>
            neighborIds.has(n.node_id) && !nodes.find(existing => existing.node_id === n.node_id)
          );
          nodes.push(...neighbors);

          // Add connecting edges
          const connectingEdges = data.edges.filter(e =>
            e.from_node_id === selectedNode.node_id || e.to_node_id === selectedNode.node_id
          );
          intraEdges.push(...connectingEdges.filter(e => !intraEdges.find(
            existing => existing.from_node_id === e.from_node_id && existing.to_node_id === e.to_node_id
          )));

          break;
        }
      }
    }

    // ALWAYS add path nodes (including phantom nodes from activePath)
    if (activePath) {
      activePath.forEach(pathNode => {
        if (!nodes.find(n => n.node_id === pathNode.node_id)) {
          nodes.push(pathNode);
        }
      });
    }

    // Overlay edges filtering
    const validNodeIds = new Set(nodes.map(n => n.node_id));
    const filterOverlay = (edges: Edge[]) => edges.filter(e =>
      validNodeIds.has(e.from_node_id) && validNodeIds.has(e.to_node_id)
    );

    return {
      displayNodes: nodes,
      displayEdges: intraEdges,
      displayOverlayEdges: { bridges: filterOverlay(overlayGraph.bridges), shortcuts: filterOverlay(overlayGraph.shortcuts) },
      pathEdges: pathEdgesList,
      pathNodesSet: pathNodeIds
    };
  }, [managedShards, shardCache, overlayGraph, activePath, selectedNode]);



  const handleAddShard = async (id: string, initialMode: ShardViewMode = 'HIDDEN', options: { silentError?: boolean } = {}) => {
    if (!providerRef.current) return false;

    // Already loaded?
    const existingShard = managedShards.find(s => s.id === id);
    if (existingShard) {
      touchShard(id);
      return true;
    }

    // LRU eviction if at capacity
    if (managedShards.length >= appSettings.maxShards) {
      const sorted = [...managedShards].sort((a, b) => a.lastAccessedAt - b.lastAccessedAt);

      // Find first evictable shard (not containing src or dst)
      for (const candidate of sorted) {
        const shardData = shardCache.get(candidate.id);
        const containsSrc = shardData?.nodes.some(n => n.node_id === pathSourceId);
        const containsDst = shardData?.nodes.some(n => n.node_id === pathTargetId);

        if (containsSrc || containsDst) {
          continue; // Skip - protected shard
        }

        // Check if shard contains path nodes and convert to phantom
        if (activePath && shardData) {
          const pathNodeIds = new Set(activePath.map(n => n.node_id));
          const pathNodesInShard = shardData.nodes.filter(n => pathNodeIds.has(n.node_id));

          if (pathNodesInShard.length > 0) {
            // Convert path nodes to phantom before evicting
            setActivePath(prev => {
              if (!prev) return prev;
              return prev.map(n => {
                if (pathNodesInShard.some(pn => pn.node_id === n.node_id)) {
                  return { ...n, isPhantom: true, shard_id: 'evicted' };
                }
                return n;
              });
            });
          }
        }

        // Evict this shard
        setManagedShards(prev => prev.filter(s => s.id !== candidate.id));
        setShardCache(prev => {
          const next = new Map(prev);
          next.delete(candidate.id);
          return next;
        });
        break;
      }
    }

    const now = Date.now();
    setManagedShards(prev => [...prev, { id, mode: initialMode, lastAccessedAt: now }]);

    if (!shardCache.has(id)) {
      try {
        const shardData = await providerRef.current.getShard(id);
        setShardCache(prev => {
          const next = new Map(prev);
          next.set(id, shardData);
          return next;
        });
        // Don't auto-fit when adding as HIDDEN
        if (initialMode !== 'HIDDEN') graphRef.current?.fitToNodes(shardData.nodes);
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
  const handleAddShardsUI = async (ids: string[]) => {
    const promises = ids.map(id => {
      if (!managedShards.find(s => s.id === id)) {
        return handleAddShard(id, 'HIDDEN', { silentError: true });
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
    setManagedShards(prev => prev.map(s => s.id === id ? { ...s, mode, lastAccessedAt: Date.now() } : s));
  };

  const handleToggleAll = (mode: ShardViewMode) => {
    setManagedShards(prev => prev.map(s => ({ ...s, mode })));
  };

  const handleRemoveShard = (id: string) => {
    const shardData = shardCache.get(id);

    // Block removal of shards containing source or destination nodes
    const containsSrc = shardData?.nodes.some(n => n.node_id === pathSourceId);
    const containsDst = shardData?.nodes.some(n => n.node_id === pathTargetId);

    if (containsSrc || containsDst) {
      alert('Cannot remove shard that contains source or destination node. Clear the path first.');
      return;
    }

    // Convert path nodes to phantom before removing
    if (activePath && shardData) {
      const pathNodeIds = new Set(activePath.map(n => n.node_id));
      const pathNodesInShard = shardData.nodes.filter(n => pathNodeIds.has(n.node_id));

      if (pathNodesInShard.length > 0) {
        setActivePath(prev => {
          if (!prev) return prev;
          return prev.map(n => {
            if (pathNodesInShard.some(pn => pn.node_id === n.node_id)) {
              return { ...n, isPhantom: true, shard_id: 'removed' };
            }
            return n;
          });
        });
      }
    }

    setManagedShards(prev => prev.filter(s => s.id !== id));
    setShardCache(prev => {
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
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
      // Update LRU for the shard containing this node
      const shardId = node.shard_id;
      if (shardId && shardId !== 'unknown' && shardId !== 'evicted') {
        touchShard(shardId);
      }
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
            touchShard(shardId);
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
    if (!pathSourceId || !pathTargetId || !providerRef.current || !servingLayerClientRef.current) return;
    setIsPathLoading(true);
    try {
      console.log('Finding path from', pathSourceId, 'to', pathTargetId);

      // 1. Resolve shard IDs for source and target
      console.log('Resolving shard IDs...');
      const srcShard = await providerRef.current.getNodeShard(pathSourceId);
      const dstShard = await providerRef.current.getNodeShard(pathTargetId);
      console.log('Resolved shards:', srcShard, dstShard);

      if (!srcShard || !dstShard) {
        alert('Could not resolve shard for source or target node');
        setIsPathLoading(false);
        return;
      }

      // 2. Call serving layer routing
      console.log('Calling serving layer:', appSettings.servingLayerUrl);
      const response = await servingLayerClientRef.current.findRoute(
        pathSourceId,
        srcShard,
        pathTargetId,
        dstShard
      );
      console.log('Serving layer response:', response);

      if (response.status !== 'success' || response.path.length === 0) {
        alert('No path found');
        setActivePath(null);
        return;
      }

      // 3. Build path with phantom nodes for nodes not in loaded shards
      const path: NodeLocation[] = response.path.map((nodeId, idx) => {
        const nodeIdStr = nodeId.toString();
        // Check if node exists in any loaded shard
        for (const [_shardId, shardData] of shardCache.entries()) {
          const known = shardData.nodes.find(n => n.node_id === nodeIdStr);
          if (known) return known;
        }
        // Node not in loaded shards - create phantom node
        const coord = response.coordinates[idx];
        return {
          node_id: nodeIdStr,
          shard_id: 'unknown',
          x: coord?.lng ?? 0,  // x = longitude
          y: coord?.lat ?? 0,  // y = latitude
          type: NodeType.INTERNAL,
          isPhantom: true
        };
      });

      setActivePath(path);

      // Path no longer auto-unhides shards - paths are always drawn via activePath
      // Users can manually toggle shard visibility if they want to see non-path nodes

    } catch (e) {
      console.error('Path finding error:', e);
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

  // Point+Click map handler (for both add shard and find node modes)
  const handleMapClick = async (latlng: L.LatLng) => {
    if (isPointClickMode) {
      // Add shard at click location
      const s2CellId = getS2CellId(latlng.lat, latlng.lng, appSettings.s2CellLevel);
      handleAddShard(s2CellId, 'HIDDEN');
      setIsPointClickMode(false);
      return;
    }

    if (isFindNodeMode) {
      // Find nearest node at click location
      const s2CellId = getS2CellId(latlng.lat, latlng.lng, appSettings.s2CellLevel);

      // Ensure shard is loaded
      let shardData = shardCache.get(s2CellId);
      if (!shardData) {
        const success = await handleAddShard(s2CellId, 'HIDDEN');
        if (!success) {
          alert('Could not load shard for this location');
          setIsFindNodeMode(false);
          return;
        }
        // Wait for cache update
        await new Promise(resolve => setTimeout(resolve, 300));
        shardData = shardCache.get(s2CellId);
      }

      // Find nearest node
      if (shardData) {
        let nearestNode: NodeLocation | null = null;
        let minDist = Infinity;
        shardData.nodes.forEach(n => {
          const dist = Math.hypot(n.y - latlng.lat, n.x - latlng.lng);
          if (dist < minDist) {
            minDist = dist;
            nearestNode = n;
          }
        });

        if (nearestNode !== null) {
          setSelectedNode(nearestNode);
          graphRef.current?.focusNode((nearestNode as NodeLocation).node_id);
          touchShard(s2CellId);
        }
      }

      setIsFindNodeMode(false);
    }
  };

  if (!activeRegion) {
    return <StartupModal onSelectRegion={handleSelectRegion} />;
  }

  const regionBounds = L.latLngBounds(
    [activeRegion.bounds.minLat, activeRegion.bounds.minLon],
    [activeRegion.bounds.maxLat, activeRegion.bounds.maxLon]
  );

  return (
    <div className="App" style={{ width: '100vw', height: '100vh', display: 'flex' }}>
      <MapContainer
        bounds={regionBounds}
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
          pathSourceId={pathSourceId}
          pathTargetId={pathTargetId}
          onMapClick={handleMapClick}
          isPointClickMode={isPointClickMode}
          isFindNodeMode={isFindNodeMode}
          activePath={activePath ?? undefined}
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

          <div ref={shardManagerPanelRef} style={{ position: 'absolute', top: 10, left: 240, zIndex: 1001 }}>
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
            <div
              ref={findNodePanelRef}
              style={{
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
                <button
                  onClick={() => setIsFindNodeMode(prev => !prev)}
                  title={isFindNodeMode ? "Cancel point+find" : "Click on map to find nearest node"}
                  style={{
                    background: isFindNodeMode ? '#ff9800' : '#444',
                    border: isFindNodeMode ? '2px solid #ffb74d' : '1px solid #666',
                    color: 'white', borderRadius: '4px', padding: '4px 8px', cursor: 'pointer'
                  }}
                >
                  📍
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
