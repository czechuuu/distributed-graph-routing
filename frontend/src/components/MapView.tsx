import { useMemo } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import type { Coordinate, Segment } from '../api/types'

L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
})

// Fix for default marker icon in Vite/Webpack environments
// where the import returns a full URL but Leaflet tries to prepend a path.
delete (L.Icon.Default.prototype as any)._getIconUrl

type MapViewProps = {
  center: Coordinate
  start: Coordinate | null
  end: Coordinate | null
  onMapClick: (point: Coordinate) => void
  polylines: Segment[]
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
          key={`${segment.start.node_id}-${segment.end.node_id}`}
          positions={toLatLngs(segment.polyline)}
          pathOptions={{ color: '#2563eb', weight: 4 }}
        />
      ))}
    </MapContainer>
  )
}
