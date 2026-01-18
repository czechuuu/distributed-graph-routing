import React, { useState } from 'react';
import { PREDEFINED_REGIONS, type Region } from '../domain/MapMetadata';
import { DEFAULT_SETTINGS, type AppSettings } from '../domain/AppSettings';

interface StartupModalProps {
    onSelectRegion: (region: Region, settings: AppSettings) => void;
}

export const StartupModal: React.FC<StartupModalProps> = ({ onSelectRegion }) => {
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [settings, setSettings] = useState<AppSettings>({ ...DEFAULT_SETTINGS });

    const updateSetting = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
        setSettings(prev => ({ ...prev, [key]: value }));
    };

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
                maxWidth: '450px',
                width: '90%',
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
                            onClick={() => onSelectRegion(region, settings)}
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

                {/* Collapsible Advanced Settings */}
                <div style={{ marginTop: '24px' }}>
                    <button
                        onClick={() => setIsSettingsOpen(prev => !prev)}
                        style={{
                            background: 'transparent',
                            border: '1px solid #555',
                            color: '#aaa',
                            padding: '10px 16px',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            width: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px',
                            fontSize: '0.95rem',
                            transition: 'all 0.2s'
                        }}
                        onMouseEnter={e => {
                            e.currentTarget.style.borderColor = '#777';
                            e.currentTarget.style.color = '#ccc';
                        }}
                        onMouseLeave={e => {
                            e.currentTarget.style.borderColor = '#555';
                            e.currentTarget.style.color = '#aaa';
                        }}
                    >
                        <span style={{
                            transform: isSettingsOpen ? 'rotate(90deg)' : 'rotate(0deg)',
                            transition: 'transform 0.2s',
                            display: 'inline-block'
                        }}>▶</span>
                        ⚙️ Advanced Settings
                    </button>

                    {isSettingsOpen && (
                        <div style={{
                            marginTop: '16px',
                            padding: '16px',
                            background: 'rgba(0,0,0,0.3)',
                            borderRadius: '8px',
                            border: '1px solid #444',
                            textAlign: 'left'
                        }}>
                            {/* Data Source Toggle */}
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold', fontSize: '0.9rem' }}>
                                    Data Source
                                </label>
                                <div style={{ display: 'flex', gap: '16px' }}>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                                        <input
                                            type="radio"
                                            name="dataSource"
                                            checked={settings.useRemote}
                                            onChange={() => updateSetting('useRemote', true)}
                                        />
                                        Remote Server
                                    </label>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                                        <input
                                            type="radio"
                                            name="dataSource"
                                            checked={!settings.useRemote}
                                            onChange={() => updateSetting('useRemote', false)}
                                        />
                                        Mock Data
                                    </label>
                                </div>
                            </div>

                            {/* Server URL */}
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold', fontSize: '0.9rem' }}>
                                    Data Domain Server URL
                                </label>
                                <input
                                    type="text"
                                    value={settings.dataDomainUrl}
                                    onChange={e => updateSetting('dataDomainUrl', e.target.value)}
                                    disabled={!settings.useRemote}
                                    placeholder="http://localhost:8000"
                                    style={{
                                        width: '100%',
                                        padding: '10px 12px',
                                        borderRadius: '6px',
                                        border: '1px solid #555',
                                        background: settings.useRemote ? 'rgba(255,255,255,0.1)' : 'rgba(100,100,100,0.2)',
                                        color: settings.useRemote ? 'white' : '#888',
                                        fontSize: '0.95rem',
                                        boxSizing: 'border-box'
                                    }}
                                />
                            </div>

                            {/* S2 Cell Level */}
                            <div>
                                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold', fontSize: '0.9rem' }}>
                                    S2 Cell Level (1-30)
                                </label>
                                <input
                                    type="number"
                                    min={1}
                                    max={30}
                                    value={settings.s2CellLevel}
                                    onChange={e => {
                                        const val = parseInt(e.target.value, 10);
                                        if (!isNaN(val) && val >= 1 && val <= 30) {
                                            updateSetting('s2CellLevel', val);
                                        }
                                    }}
                                    style={{
                                        width: '80px',
                                        padding: '10px 12px',
                                        borderRadius: '6px',
                                        border: '1px solid #555',
                                        background: 'rgba(255,255,255,0.1)',
                                        color: 'white',
                                        fontSize: '0.95rem'
                                    }}
                                />
                                <span style={{ marginLeft: '12px', color: '#888', fontSize: '0.85rem' }}>
                                    (smaller = larger cells)
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
