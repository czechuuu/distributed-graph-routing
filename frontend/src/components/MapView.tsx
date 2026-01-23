import { useMemo } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import type { Coordinate, ExpandedSegment } from '../api/types'

L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
})

type MapViewProps = {
  center: Coordinate
  start: Coordinate | null
  end: Coordinate | null
  onMapClick: (point: Coordinate) => void
  polylines: ExpandedSegment[]
}

function MapClickHandler({ onMapClick }: { onMapClick: (point: Coordinate) => void }) {
  useMapEvents({
    click(event) {
      onMapClick({ lat: event.latlng.lat, lng: event.latlng.lng })
    },
  })
  return null
}

function toLatLngs(polyline: Coordinate[]): [number, number][] {
  return polyline.map((point) => [point.lat, point.lng])
}

export default function MapView({
  center,
  start,
  end,
  onMapClick,
  polylines,
}: MapViewProps) {
  const position = useMemo<[number, number]>(
    () => [center.lat, center.lng],
    [center.lat, center.lng],
  )

  return (
    <MapContainer className="map" center={position} zoom={13} scrollWheelZoom>
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapClickHandler onMapClick={onMapClick} />
      {start && <Marker position={[start.lat, start.lng]} />}
      {end && <Marker position={[end.lat, end.lng]} />}
      {polylines.map((segment) => (
        <Polyline
          key={`${segment.u.node_id}-${segment.v.node_id}`}
          positions={toLatLngs(segment.polyline)}
          pathOptions={{ color: '#2563eb', weight: 4 }}
        />
      ))}
    </MapContainer>
  )
}
