import React, { useState } from 'react';

interface PathControlProps {
    sourceId: string;
    targetId: string;
    onSetSource: (id: string) => void;
    onSetTarget: (id: string) => void;
    onFindPath: () => void;
    onClearPath: () => void;
    isLoading?: boolean;
}

export const PathControl: React.FC<PathControlProps> = ({
    sourceId, targetId, onSetSource, onSetTarget, onFindPath, onClearPath, isLoading
}) => {
    const [isCollapsed, setIsCollapsed] = useState(false);

    const handleSearch = () => {
        if (sourceId.trim() && targetId.trim()) {
            onFindPath();
        }
    };

    if (isCollapsed) {
        return (
            <button
                onClick={() => setIsCollapsed(false)}
                title="Open Path Finder"
                style={{
                    position: 'fixed', top: 10, right: 10,
                    background: '#333', color: 'white',
                    border: '1px solid #555', borderRadius: '50%',
                    width: '40px', height: '40px', fontSize: '20px',
                    cursor: 'pointer', zIndex: 9999,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 4px 6px rgba(0,0,0,0.3)'
                }}
            >
                🗺️
            </button>
        );
    }

    return (
        <div style={{
            position: 'fixed', top: 10, right: 10,
            background: 'rgba(30,30,30,0.95)', border: '1px solid #444', borderRadius: '8px',
            padding: '10px', display: 'flex', flexDirection: 'column', gap: '8px',
            zIndex: 9999, color: 'white', fontFamily: 'monospace', width: '220px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)'
        }}>
            <div style={{
                fontWeight: 'bold', borderBottom: '1px solid #444', paddingBottom: '4px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
                <span>Find Path</span>
                <button
                    onClick={() => setIsCollapsed(true)}
                    style={{ background: 'transparent', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '16px' }}
                >✕</button>
            </div>

            <div style={{ position: 'relative' }}>
                <input
                    type="text"
                    value={sourceId}
                    onChange={e => onSetSource(e.target.value)}
                    placeholder="Source Node ID"
                    style={{
                        width: '100%',
                        boxSizing: 'border-box',
                        background: '#222', border: '1px solid #555', color: 'white',
                        padding: '4px 28px 4px 8px', borderRadius: '4px'
                    }}
                />
                {sourceId && (
                    <button
                        onClick={() => onSetSource('')}
                        title="Clear source"
                        style={{
                            position: 'absolute', right: '4px', top: '50%', transform: 'translateY(-50%)',
                            background: 'transparent', border: 'none', color: '#888',
                            cursor: 'pointer', fontSize: '14px', padding: '2px 4px'
                        }}
                    >×</button>
                )}
            </div>

            <div style={{ position: 'relative' }}>
                <input
                    type="text"
                    value={targetId}
                    onChange={e => onSetTarget(e.target.value)}
                    placeholder="Dest Node ID"
                    style={{
                        width: '100%',
                        boxSizing: 'border-box',
                        background: '#222', border: '1px solid #555', color: 'white',
                        padding: '4px 28px 4px 8px', borderRadius: '4px'
                    }}
                />
                {targetId && (
                    <button
                        onClick={() => onSetTarget('')}
                        title="Clear destination"
                        style={{
                            position: 'absolute', right: '4px', top: '50%', transform: 'translateY(-50%)',
                            background: 'transparent', border: 'none', color: '#888',
                            cursor: 'pointer', fontSize: '14px', padding: '2px 4px'
                        }}
                    >×</button>
                )}
            </div>

            <div style={{ display: 'flex', gap: '4px' }}>
                <button
                    onClick={handleSearch}
                    disabled={isLoading}
                    style={{
                        flex: 1,
                        background: isLoading ? '#666' : '#2196F3',
                        border: 'none', color: 'white', padding: '6px', borderRadius: '4px',
                        cursor: isLoading ? 'wait' : 'pointer', fontWeight: 'bold'
                    }}
                >
                    {isLoading ? '...' : 'Find'}
                </button>
                <button
                    onClick={onClearPath}
                    title="Clear Path"
                    style={{
                        background: '#444', border: 'none', color: 'white',
                        padding: '6px 10px', borderRadius: '4px', cursor: 'pointer'
                    }}
                >
                    🗑️
                </button>
            </div>
        </div>
    );
};
