import React, { useState, useRef } from 'react';

export interface ShardControlItem {
    id: string;
    visible: boolean;
}

interface ShardManagerProps {
    shards: ShardControlItem[];
    onAddShard: (id: string) => void;
    onToggleShard: (id: string, visible: boolean) => void;
    onRemoveShard: (id: string) => void;
    onHighlightShard: (id: string) => void;
}

export const ShardManager: React.FC<ShardManagerProps> = ({
    shards,
    onAddShard,
    onToggleShard,
    onRemoveShard,
    onHighlightShard
}) => {
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [inputValue, setInputValue] = useState('');
    const listRef = useRef<HTMLDivElement>(null);

    const handleAdd = () => {
        const id = inputValue.trim();
        if (!id) return;

        const existing = shards.find(s => s.id === id);
        if (existing) {
            onHighlightShard(id);
            if (!existing.visible) {
                onToggleShard(id, true);
            }
            // Scroll to it
            const el = document.getElementById(`shard-item-${id}`);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            onAddShard(id);
            // Scroll to bottom after render
            setTimeout(() => {
                const el = document.getElementById(`shard-item-${id}`);
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 50);
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
                            borderLeft: shard.visible ? '3px solid #00ff88' : '3px solid #666',
                            opacity: shard.visible ? 1 : 0.6
                        }}
                    >
                        <span>ID: {shard.id}</span>
                        <div style={{ display: 'flex', gap: '4px' }}>
                            <button
                                onClick={() => onToggleShard(shard.id, !shard.visible)}
                                title={shard.visible ? "Hide" : "Show"}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '2px',
                                    fontSize: '14px'
                                }}
                            >
                                {shard.visible ? '👁️' : '🚫'}
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
