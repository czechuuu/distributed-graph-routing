import { useCallback, useMemo, useState } from 'react'
import MapView from './components/MapView'
import SegmentsPanel from './components/SegmentsPanel'
import { expandSegments, fetchRoute } from './api/client'
import type {
  Coordinate,
  ExpandedSegment,
  RouteResponse,
  Segment,
} from './api/types'

const DEFAULT_CENTER: Coordinate = { lat: 52.2297, lng: 21.0122 }

function segmentKey(segment: Segment): string {
  return `${segment.u.node_id}-${segment.v.node_id}`
}

function App() {
  const [start, setStart] = useState<Coordinate | null>(null)
  const [end, setEnd] = useState<Coordinate | null>(null)
  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [expanded, setExpanded] = useState<Record<string, ExpandedSegment>>({})
  const [status, setStatus] = useState<string | null>(null)
  const [isRouting, setIsRouting] = useState(false)
  const [isExpanding, setIsExpanding] = useState<Record<string, boolean>>({})

  const segments = route?.segments ?? []
  const hasRoute = Boolean(route?.path_found)

  const handleReset = useCallback(() => {
    setStart(null)
    setEnd(null)
    setRoute(null)
    setExpanded({})
    setStatus(null)
  }, [])

  const handleMapClick = useCallback(
    (point: Coordinate) => {
      if (!start) {
        setStart(point)
        setRoute(null)
        setExpanded({})
        setStatus(null)
        return
      }
      if (!end) {
        setEnd(point)
        setRoute(null)
        setExpanded({})
        setStatus(null)
        return
      }
      setStart(point)
      setEnd(null)
      setRoute(null)
      setExpanded({})
      setStatus(null)
    },
    [start, end],
  )

  const handleRoute = useCallback(async () => {
    if (!start || !end) {
      return
    }
    setIsRouting(true)
    setStatus(null)
    try {
      const response = await fetchRoute({ start, end })
      setRoute(response)
      setExpanded({})
      if (!response.path_found) {
        setStatus('No route found for the selected points.')
      }
    } catch (error) {
      setRoute(null)
      setExpanded({})
      setStatus(error instanceof Error ? error.message : 'Route failed.')
    } finally {
      setIsRouting(false)
    }
  }, [start, end])

  const handleExpand = useCallback(
    async (segment: Segment) => {
      const key = segmentKey(segment)
      if (!segment.expandable || expanded[key]) {
        return
      }
      setIsExpanding((prev) => ({ ...prev, [key]: true }))
      setStatus(null)
      try {
        const response = await expandSegments([segment])
        const expandedSegment = response.expanded[0]
        if (expandedSegment) {
          setExpanded((prev) => ({ ...prev, [key]: expandedSegment }))
        }
        if (response.errors.length > 0) {
          const firstError = response.errors[0]
          setStatus(
            `Segment expansion failed: ${firstError.error ?? 'unknown error'}`,
          )
        }
      } catch (error) {
        setStatus(error instanceof Error ? error.message : 'Expand failed.')
      } finally {
        setIsExpanding((prev) => ({ ...prev, [key]: false }))
      }
    },
    [expanded],
  )

  const mapSegments = useMemo(
    () =>
      segments.map((segment) => {
        const key = segmentKey(segment)
        return expanded[key] ?? {
          u: segment.u,
          v: segment.v,
          polyline: [
            { lat: segment.u.lat, lng: segment.u.lng },
            { lat: segment.v.lat, lng: segment.v.lng },
          ],
        }
      }),
    [segments, expanded],
  )

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <header>
          <h1>Routing Explorer</h1>
          <p>Select two points, compute a route, expand segments.</p>
        </header>
        <section className="panel">
          <div className="panel-row">
            <div>
              <div className="label">Start</div>
              <div className="value">
                {start ? `${start.lat.toFixed(5)}, ${start.lng.toFixed(5)}` : 'Click map'}
              </div>
            </div>
            <div>
              <div className="label">End</div>
              <div className="value">
                {end ? `${end.lat.toFixed(5)}, ${end.lng.toFixed(5)}` : 'Click map'}
              </div>
            </div>
          </div>
          <div className="panel-row">
            <button
              type="button"
              onClick={handleRoute}
              disabled={!start || !end || isRouting}
            >
              {isRouting ? 'Routing...' : 'Compute route'}
            </button>
            <button type="button" onClick={handleReset}>
              Reset
            </button>
          </div>
          {route && (
            <div className="summary">
              <div>
                <strong>Segments</strong>: {route.summary.segments_count}
              </div>
              <div>
                <strong>Distance</strong>: {route.summary.distance_m.toFixed(1)} m
              </div>
            </div>
          )}
          {status && <div className="status">{status}</div>}
        </section>
        <SegmentsPanel
          segments={segments}
          expandedKeys={new Set(Object.keys(expanded))}
          onExpand={handleExpand}
          isExpanding={isExpanding}
          disabled={!hasRoute}
        />
      </aside>
      <main className="map-area">
        <MapView
          center={DEFAULT_CENTER}
          start={start}
          end={end}
          onMapClick={handleMapClick}
          polylines={mapSegments}
        />
      </main>
    </div>
  )
}

export default App
