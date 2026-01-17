import React, { useState, useRef } from 'react';

export type ShardViewMode = 'ALL' | 'PATH' | 'NONE';

export interface ShardControlItem {
    id: string;
    mode: ShardViewMode;
}

interface ShardManagerProps {
    shards: ShardControlItem[];
    onAddShards: (ids: string[]) => void;
    onToggleShard: (id: string, mode: ShardViewMode) => void; // Explicit mode set
    onRemoveShard: (id: string) => void;
    onHighlightShard: (id: string) => void;
    onToggleAll: (mode: ShardViewMode) => void;
    isPointClickMode?: boolean;
    onTogglePointClickMode?: () => void;
}

export const ShardManager: React.FC<ShardManagerProps> = ({
    shards,
    onAddShards,
    onToggleShard,
    onRemoveShard,
    onHighlightShard,
    onToggleAll,
    isPointClickMode,
    onTogglePointClickMode
}) => {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [inputValue, setInputValue] = useState('');
    const listRef = useRef<HTMLDivElement>(null);

    const handleAdd = () => {
        const rawInput = inputValue;
        if (!rawInput.trim()) return;

        const ids = rawInput.split(',').map(s => s.trim()).filter(Boolean);
        const newIds: string[] = [];

        ids.forEach(id => {
            const existing = shards.find(s => s.id === id);
            if (existing) {
                onHighlightShard(id);
                // If hidden or path-only, show full
                if (existing.mode !== 'ALL') {
                    onToggleShard(id, 'ALL');
                }
                // Scroll to it
                const el = document.getElementById(`shard-item-${id}`);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } else {
                newIds.push(id);
                // Scroll to bottom after render - wait for last one
                setTimeout(() => {
                    const el = document.getElementById(`shard-item-${id}`);
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 100);
            }
        });

        if (newIds.length > 0) {
            onAddShards(newIds);
        }
        setInputValue('');
    };

    if (isCollapsed) {
        return (
            <button
                onClick={() => setIsCollapsed(false)}
                style={{
                    position: 'fixed',
                    bottom: 20,
                    left: 20,
                    background: '#333',
                    color: 'white',
                    border: '1px solid #555',
                    borderRadius: '50%',
                    width: '40px',
                    height: '40px',
                    fontSize: '20px',
                    cursor: 'pointer',
                    zIndex: 9999,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 4px 6px rgba(0,0,0,0.3)'
                }}
            >
                ⚙️
            </button>
        );
    }

    return (
        <div style={{
            position: 'fixed',
            bottom: 20,
            left: 20,
            width: '280px',
            maxHeight: '400px',
            background: 'rgba(30,30,30,0.95)',
            border: '1px solid #444',
            borderRadius: '8px',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 9999,
            color: 'white',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            backdropFilter: 'blur(4px)',
            fontFamily: 'monospace'
        }}>
            {/* Header */}
            <div style={{
                padding: '10px',
                borderBottom: '1px solid #444',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                backgroundColor: 'rgba(255,255,255,0.05)'
            }}>
                <span style={{ fontWeight: 'bold' }}>Shard Manager</span>
                <button
                    onClick={() => setIsCollapsed(true)}
                    style={{ background: 'transparent', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '18px' }}
                >
                    ✕
                </button>
            </div>

            {/* Global Controls */}
            {shards.length > 0 && (
                <div style={{ padding: '8px 10px', display: 'flex', gap: '10px', borderBottom: '1px solid #333' }}>
                    <button
                        onClick={() => onToggleAll('ALL')}
                        style={{ flex: 1, background: '#444', border: 'none', color: 'white', borderRadius: '4px', padding: '4px', cursor: 'pointer', fontSize: '12px' }}
                    >
                        👁️ Show All
                    </button>
                    <button
                        onClick={() => onToggleAll('NONE')}
                        style={{ flex: 1, background: '#444', border: 'none', color: 'white', borderRadius: '4px', padding: '4px', cursor: 'pointer', fontSize: '12px' }}
                    >
                        🚫 Hide All
                    </button>
                </div>
            )}

            {/* Input */}
            <div style={{ padding: '10px', display: 'flex', gap: '5px' }}>
                <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                    placeholder="Shard ID"
                    style={{
                        flex: 1,
                        background: '#222',
                        border: '1px solid #555',
                        color: 'white',
                        padding: '4px 8px',
                        borderRadius: '4px'
                    }}
                />
                <button
                    onClick={handleAdd}
                    style={{
                        background: '#444',
                        border: '1px solid #555',
                        color: 'white',
                        padding: '4px 10px',
                        borderRadius: '4px',
                        cursor: 'pointer'
                    }}
                >
                    Add
                </button>
                {onTogglePointClickMode && (
                    <button
                        onClick={onTogglePointClickMode}
                        title={isPointClickMode ? "Cancel point+click mode" : "Click on map to add shard"}
                        style={{
                            background: isPointClickMode ? '#1e88e5' : '#444',
                            border: isPointClickMode ? '2px solid #64b5f6' : '1px solid #555',
                            color: 'white',
                            padding: '4px 10px',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            transition: 'all 0.2s ease'
                        }}
                    >
                        📍
                    </button>
                )}
            </div>

            {/* List */}
            <div
                ref={listRef}
                style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: '0 10px 10px 10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    minHeight: '100px'
                }}
            >
                {shards.length === 0 && (
                    <div style={{ color: '#666', fontSize: '0.9rem', padding: '10px', textAlign: 'center' }}>
                        No shards loaded.
                    </div>
                )}

                {shards.map(shard => (
                    <div
                        key={shard.id}
                        id={`shard-item-${shard.id}`}
                        className="shard-item"
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            background: '#333',
                            padding: '6px 8px',
                            borderRadius: '4px',
                            borderLeft: shard.mode === 'ALL' ? '3px solid #00ff88' : (shard.mode === 'PATH' ? '3px solid #0088cc' : '3px solid #666'),
                            opacity: shard.mode !== 'NONE' ? 1 : 0.6
                        }}
                    >
                        <span>ID: {shard.id}</span>
                        <div style={{ display: 'flex', gap: '4px' }}>
                            <button
                                onClick={() => {
                                    const next = shard.mode === 'ALL' ? 'NONE' : 'ALL';
                                    onToggleShard(shard.id, next);
                                }}
                                title={shard.mode === 'ALL' ? "Hide" : "Show"}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '2px',
                                    fontSize: '14px'
                                }}
                            >
                                {shard.mode === 'ALL' ? '👁️' : (shard.mode === 'PATH' ? '🛤️' : '🚫')}
                            </button>
                            <button
                                onClick={() => onRemoveShard(shard.id)}
                                title="Remove & Clear"
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '2px',
                                    fontSize: '14px'
                                }}
                            >
                                🗑️
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
