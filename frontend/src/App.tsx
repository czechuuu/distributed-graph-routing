import { useEffect, useState, useRef } from 'react';
import './App.css';
import { GraphRenderer } from './components/GraphRenderer';
import type { GraphRendererHandle } from './components/GraphRenderer';
import { generateMockOverlayGraph } from './domain/mockGraph';
import type { GraphData } from './domain/types';

function App() {
  const [data, setData] = useState<GraphData | null>(null);
  const graphRef = useRef<GraphRendererHandle>(null);

  useEffect(() => {
    // Simulate async fetch
    const graph = generateMockOverlayGraph(500, 10); // 500 nodes, 10 shards
    setData(graph);
  }, []);

  if (!data) return <div>Loading graph...</div>;

  return (
    <div className="App">
      <GraphRenderer ref={graphRef} data={data} />
      <div style={{
        position: 'fixed',
        top: 10,
        left: 10,
        color: 'white',
        background: 'rgba(0,0,0,0.6)',
        padding: '8px 12px',
        borderRadius: '6px',
        pointerEvents: 'none',
        userSelect: 'none',
        zIndex: 9999, // Super high z-index
        backdropFilter: 'blur(2px)', // Nice effect
        fontFamily: 'monospace'
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '0.9rem', marginBottom: '4px' }}>Graph Routing Visualization</div>
        <div style={{ fontSize: '0.8rem', opacity: 0.9, marginBottom: '6px' }}>Nodes: {data.nodes.length} &middot; Edges: {data.edges.length}</div>
        <button
          onClick={() => graphRef.current?.resetView()}
          style={{
            pointerEvents: 'auto', // Re-enable clicks
            background: '#444',
            color: 'white',
            border: '1px solid #666',
            borderRadius: '4px',
            padding: '2px 8px',
            fontSize: '0.8rem',
            cursor: 'pointer'
          }}
        >
          Recenter
        </button>
      </div>
    </div>
  );
}

export default App;
