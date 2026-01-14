import React from 'react';
import { PREDEFINED_REGIONS, type Region } from '../domain/MapMetadata';

interface StartupModalProps {
    onSelectRegion: (region: Region) => void;
}

export const StartupModal: React.FC<StartupModalProps> = ({ onSelectRegion }) => {
    return (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.85)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 10000,
            backdropFilter: 'blur(5px)'
        }}>
            <div style={{
                background: '#222',
                color: 'white',
                padding: '32px',
                borderRadius: '16px',
                boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
                textAlign: 'center',
                maxWidth: '400px',
                border: '1px solid #444'
            }}>
                <h1 style={{ marginTop: 0, fontSize: '1.8rem' }}>Graph Routing Viz</h1>
                <p style={{ color: '#aaa', marginBottom: '24px' }}>
                    Select a region to initialize the graph routing simulation.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {PREDEFINED_REGIONS.map(region => (
                        <button
                            key={region.id}
                            onClick={() => onSelectRegion(region)}
                            style={{
                                background: 'linear-gradient(135deg, #2196F3, #1976D2)',
                                color: 'white',
                                border: 'none',
                                padding: '16px',
                                borderRadius: '8px',
                                fontSize: '1.2rem',
                                fontWeight: 'bold',
                                cursor: 'pointer',
                                transition: 'transform 0.1s',
                                boxShadow: '0 4px 6px rgba(0,0,0,0.2)'
                            }}
                            onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.02)'}
                            onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
                        >
                            {region.name}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
};
