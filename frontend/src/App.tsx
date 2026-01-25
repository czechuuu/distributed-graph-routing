import { useCallback, useMemo, useRef, useState } from 'react'
import MapView from './components/MapView'
import FloatingSearchBar, { type PinMode } from './components/FloatingSearchBar'
import { expandSegments, fetchRoute } from './api/client'
import type {
  Coordinate,
  RouteResponse,
  Segment,
} from './api/types'

const DEFAULT_CENTER: Coordinate = { lat: 52.2297, lng: 21.0122 }

type LocationValue = {
  coord: Coordinate
  label: string
}

function segmentKey(segment: Segment): string {
  return `${segment.start.node_id}-${segment.end.node_id}`
}

function formatTime(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  if (totalMinutes < 60) {
    return `${totalMinutes} min`
  }
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours} h ${minutes} min`
}

function App() {
  const [source, setSource] = useState<LocationValue | null>(null)
  const [destination, setDestination] = useState<LocationValue | null>(null)
  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [expanded, setExpanded] = useState<Record<string, Segment>>({})
  const [status, setStatus] = useState<string | null>(null)
  const [isRouting, setIsRouting] = useState(false)
  const [pinMode, setPinMode] = useState<PinMode>(null)

  const segments = route?.segments ?? []

  const abortControllerRef = useRef<AbortController | null>(null)

  const handleClear = useCallback(() => {
    // Abort any pending requests
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setSource(null)
    setDestination(null)
    setRoute(null)
    setExpanded({})
    setStatus(null)
    setPinMode(null)
    setIsRouting(false)
  }, [])

  const handleMapClick = useCallback(
    (point: Coordinate) => {
      if (pinMode === 'source') {
        setSource({ coord: point, label: `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}` })
        setPinMode(null)
        setRoute(null)
        setExpanded({})
        setStatus(null)
      } else if (pinMode === 'dest') {
        setDestination({ coord: point, label: `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}` })
        setPinMode(null)
        setRoute(null)
        setExpanded({})
        setStatus(null)
      }
    },
    [pinMode],
  )

  const handleRoute = useCallback(async () => {
    if (!source || !destination) {
      return
    }
    // Abort any previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsRouting(true)
    setStatus(null)
    try {
      const response = await fetchRoute({ start: source.coord, end: destination.coord }, controller.signal)
      if (controller.signal.aborted) return
      setRoute(response)
      setExpanded({})
      if (!response.path_found) {
        setStatus('No route found for the selected points.')
        return
      }

      // Auto-expand all expandable segments
      const expandable = response.segments.filter((s) => s.expandable)
      if (expandable.length > 0) {
        try {
          const expandResponse = await expandSegments(expandable, controller.signal)
          if (controller.signal.aborted) return
          const newExpanded: Record<string, Segment> = {}
          expandable.forEach((original, idx) => {
            const exp = expandResponse.segments[idx]
            if (exp) {
              newExpanded[segmentKey(original)] = exp
            }
          })
          setExpanded(newExpanded)

          if (expandResponse.errors.length > 0) {
            const failedCount = expandResponse.errors.length
            setStatus(`${failedCount} segment(s) could not be expanded.`)
          }
        } catch (expandError) {
          if (controller.signal.aborted) return
          setStatus(expandError instanceof Error ? expandError.message : 'Expansion failed.')
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return
      setRoute(null)
      setExpanded({})
      setStatus(error instanceof Error ? error.message : 'Route failed.')
    } finally {
      if (!controller.signal.aborted) {
        setIsRouting(false)
      }
    }
  }, [source, destination])

  const mapSegments = useMemo(
    () => segments.map((segment) => expanded[segmentKey(segment)] ?? segment),
    [segments, expanded],
  )

  const canRoute = Boolean(source && destination)

  return (
    <div className="app-container">
      <FloatingSearchBar
        source={source}
        destination={destination}
        onSourceChange={setSource}
        onDestinationChange={setDestination}
        pinMode={pinMode}
        onPinModeChange={setPinMode}
        onRoute={handleRoute}
        onClear={handleClear}
        isRouting={isRouting}
        canRoute={canRoute}
        status={status}
      />
      <div className="map-area">
        <MapView
          center={DEFAULT_CENTER}
          start={source?.coord ?? null}
          end={destination?.coord ?? null}
          onMapClick={handleMapClick}
          polylines={mapSegments}
          pinMode={pinMode}
        />
      </div>
      {route && route.path_found && (
        <div className="route-summary">
          <strong>Travel Time: </strong>
          <span>{formatTime(route.summary.distance_m)}</span>
        </div>
      )}
    </div>
  )
}

export default App
