import React, { useState } from 'react';

interface PathControlProps {
    onFindPath: (src: string, dst: string) => void;
    isLoading?: boolean;
}

export const PathControl: React.FC<PathControlProps> = ({ onFindPath, isLoading }) => {
    const [srcId, setSrcId] = useState('');
    const [dstId, setDstId] = useState('');

    const handleSearch = () => {
        if (srcId.trim() && dstId.trim()) {
            onFindPath(srcId.trim(), dstId.trim());
        }
    };

    return (
        <div style={{
            position: 'fixed',
            top: 10,
            right: 10,
            background: 'rgba(30,30,30,0.95)',
            border: '1px solid #444',
            borderRadius: '8px',
            padding: '10px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            zIndex: 9999,
            color: 'white',
            fontFamily: 'monospace',
            width: '200px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(4px)'
        }}>
            <div style={{ fontWeight: 'bold', borderBottom: '1px solid #444', paddingBottom: '4px' }}>
                Find Path
            </div>

            <input
                type="text"
                value={srcId}
                onChange={e => setSrcId(e.target.value)}
                placeholder="Source Node ID"
                style={{
                    background: '#222',
                    border: '1px solid #555',
                    color: 'white',
                    padding: '4px 8px',
                    borderRadius: '4px'
                }}
            />

            <input
                type="text"
                value={dstId}
                onChange={e => setDstId(e.target.value)}
                placeholder="Dest Node ID"
                style={{
                    background: '#222',
                    border: '1px solid #555',
                    color: 'white',
                    padding: '4px 8px',
                    borderRadius: '4px'
                }}
            />

            <button
                onClick={handleSearch}
                disabled={isLoading}
                style={{
                    background: isLoading ? '#666' : '#2196F3',
                    border: 'none',
                    color: 'white',
                    padding: '6px',
                    borderRadius: '4px',
                    cursor: isLoading ? 'wait' : 'pointer',
                    fontWeight: 'bold'
                }}
            >
                {isLoading ? 'Searching...' : 'Find Path'}
            </button>
        </div>
    );
};
