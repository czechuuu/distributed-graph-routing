import { useCallback, useEffect, useRef, useState } from 'react'
import { searchPlaces, type GeocodingResult } from '../api/geocoding'
import type { Coordinate } from '../api/types'

export type PinMode = 'source' | 'dest' | null

type LocationValue = {
    coord: Coordinate
    label: string
}

type FloatingSearchBarProps = {
    source: LocationValue | null
    destination: LocationValue | null
    onSourceChange: (value: LocationValue | null) => void
    onDestinationChange: (value: LocationValue | null) => void
    pinMode: PinMode
    onPinModeChange: (mode: PinMode) => void
    onRoute: () => void
    onClear: () => void
    isRouting: boolean
    canRoute: boolean
    status: string | null
}

function useDebounce<T>(value: T, delay: number): T {
    const [debounced, setDebounced] = useState(value)
    useEffect(() => {
        const timer = setTimeout(() => setDebounced(value), delay)
        return () => clearTimeout(timer)
    }, [value, delay])
    return debounced
}

type SearchInputProps = {
    placeholder: string
    value: LocationValue | null
    onChange: (value: LocationValue | null) => void
    isPinActive: boolean
    onPinClick: () => void
    colorClass: 'source' | 'dest'
    clearQuery: boolean
    onQueryCleared: () => void
}

function SearchInput({
    placeholder,
    value,
    onChange,
    isPinActive,
    onPinClick,
    colorClass,
    clearQuery,
    onQueryCleared,
}: SearchInputProps) {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState<GeocodingResult[]>([])
    const [isOpen, setIsOpen] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)
    const dropdownRef = useRef<HTMLDivElement>(null)

    const debouncedQuery = useDebounce(query, 300)

    useEffect(() => {
        if (clearQuery) {
            setQuery('')
            setResults([])
            onQueryCleared()
        }
    }, [clearQuery, onQueryCleared])

    useEffect(() => {
        if (!debouncedQuery.trim()) {
            setResults([])
            return
        }
        setIsLoading(true)
        searchPlaces(debouncedQuery)
            .then(setResults)
            .finally(() => setIsLoading(false))
    }, [debouncedQuery])

    useEffect(() => {
        if (value?.label && !query) {
            setQuery(value.label)
        }
    }, [value?.label])

    const handleSelect = useCallback(
        (result: GeocodingResult) => {
            onChange({ coord: { lat: result.lat, lng: result.lng }, label: result.name })
            setQuery(result.name)
            setIsOpen(false)
            setResults([])
        },
        [onChange],
    )

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        setQuery(e.target.value)
        setIsOpen(true)
        if (!e.target.value.trim()) {
            onChange(null)
        }
    }, [onChange])

    const handleFocus = useCallback(() => {
        if (results.length > 0) {
            setIsOpen(true)
        }
    }, [results.length])

    const handleBlur = useCallback((e: React.FocusEvent) => {
        if (dropdownRef.current?.contains(e.relatedTarget as Node)) {
            return
        }
        setTimeout(() => setIsOpen(false), 150)
    }, [])

    return (
        <div className={`search-input ${colorClass} ${isPinActive ? 'pin-active' : ''}`}>
            <button
                type="button"
                className={`pin-btn ${isPinActive ? 'active' : ''}`}
                onClick={onPinClick}
                title={isPinActive ? 'Click map to set location' : 'Pick from map'}
            >
                📍
            </button>
            <div className="input-wrapper">
                <input
                    ref={inputRef}
                    type="text"
                    placeholder={placeholder}
                    value={query}
                    onChange={handleInputChange}
                    onFocus={handleFocus}
                    onBlur={handleBlur}
                />
                {isLoading && <span className="loading-indicator">...</span>}
                {isOpen && results.length > 0 && (
                    <div ref={dropdownRef} className="autocomplete-dropdown">
                        {results.map((result, idx) => (
                            <button
                                key={idx}
                                type="button"
                                className="autocomplete-item"
                                onClick={() => handleSelect(result)}
                            >
                                {result.name}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}

export default function FloatingSearchBar({
    source,
    destination,
    onSourceChange,
    onDestinationChange,
    pinMode,
    onPinModeChange,
    onRoute,
    onClear,
    isRouting,
    canRoute,
    status,
}: FloatingSearchBarProps) {
    const [clearSourceQuery, setClearSourceQuery] = useState(false)
    const [clearDestQuery, setClearDestQuery] = useState(false)

    const handleSourcePinClick = useCallback(() => {
        const newMode = pinMode === 'source' ? null : 'source'
        onPinModeChange(newMode)
        if (newMode === 'source') {
            onSourceChange(null)
            setClearSourceQuery(true)
        }
    }, [pinMode, onPinModeChange, onSourceChange])

    const handleDestPinClick = useCallback(() => {
        const newMode = pinMode === 'dest' ? null : 'dest'
        onPinModeChange(newMode)
        if (newMode === 'dest') {
            onDestinationChange(null)
            setClearDestQuery(true)
        }
    }, [pinMode, onPinModeChange, onDestinationChange])

    return (
        <div className="floating-search-bar">
            <div className="search-row">
                <SearchInput
                    placeholder="Source"
                    value={source}
                    onChange={onSourceChange}
                    isPinActive={pinMode === 'source'}
                    onPinClick={handleSourcePinClick}
                    colorClass="source"
                    clearQuery={clearSourceQuery}
                    onQueryCleared={() => setClearSourceQuery(false)}
                />
                <div className="action-buttons">
                    <button
                        type="button"
                        className="search-btn"
                        onClick={onRoute}
                        disabled={!canRoute || isRouting}
                        title="Compute route"
                    >
                        {isRouting ? '⏳' : '🔍'}
                    </button>
                    <button
                        type="button"
                        className="clear-btn"
                        onClick={onClear}
                        title="Clear all"
                    >
                        🗑️
                    </button>
                </div>
                <SearchInput
                    placeholder="Destination"
                    value={destination}
                    onChange={onDestinationChange}
                    isPinActive={pinMode === 'dest'}
                    onPinClick={handleDestPinClick}
                    colorClass="dest"
                    clearQuery={clearDestQuery}
                    onQueryCleared={() => setClearDestQuery(false)}
                />
            </div>
            {status && <div className="status-message">{status}</div>}
        </div>
    )
}
