import { useEffect, useState, useRef } from 'react';
import './App.css';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { generateMockOverlayGraph } from './domain/mockGraph';
import type { GraphData, NodeLocation } from './domain/types';

function App() {
  const [data, setData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeLocation | null>(null);
  const [searchId, setSearchId] = useState('');
  const graphRef = useRef<GraphRendererHandle>(null);

  useEffect(() => {
    // Simulate async fetch
    const graph = generateMockOverlayGraph(500, 10);
    setData(graph);
  }, []);

  const handleNodeClick = (node: NodeLocation | null) => {
    setSelectedNode(node);
  };

  const handleSearch = () => {
    if (!data) return;
    const node = data.nodes.find(n => n.node_id === searchId);
    if (node) {
      setSelectedNode(node);
      graphRef.current?.focusNode(node.node_id);
    } else {
      alert('Node not found');
    }
  };

  if (!data) return <div>Loading graph...</div>;

  return (
    <div className="App">
      <GraphRenderer
        ref={graphRef}
        data={data}
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
          Total Nodes: {data.nodes.length} &middot; Edges: {data.edges.length}
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
          Recenter Map
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
            <div>Loc: ({selectedNode.x.toFixed(1)}, {selectedNode.y.toFixed(1)})</div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
