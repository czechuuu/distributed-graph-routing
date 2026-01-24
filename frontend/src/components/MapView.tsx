import { useMemo } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import type { Coordinate, Segment } from '../api/types'
import type { PinMode } from './FloatingSearchBar'

L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
})

// Fix for default marker icon in Vite/Webpack environments
delete (L.Icon.Default.prototype as any)._getIconUrl

// Custom colored markers
const blueIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
})

const greenIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
})

type MapViewProps = {
  center: Coordinate
  start: Coordinate | null
  end: Coordinate | null
  onMapClick: (point: Coordinate) => void
  polylines: Segment[]
  pinMode: PinMode
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
  pinMode,
}: MapViewProps) {
  const position = useMemo<[number, number]>(
    () => [center.lat, center.lng],
    [center.lat, center.lng],
  )

  const mapClassName = useMemo(() => {
    if (pinMode === 'source') return 'map pin-mode-source'
    if (pinMode === 'dest') return 'map pin-mode-dest'
    return 'map'
  }, [pinMode])

  return (
    <MapContainer className={mapClassName} center={position} zoom={13} scrollWheelZoom>
      <TileLayer
        attribution="&copy; OpenStreetMap contributors"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapClickHandler onMapClick={onMapClick} />
      {start && <Marker position={[start.lat, start.lng]} icon={blueIcon} />}
      {end && <Marker position={[end.lat, end.lng]} icon={greenIcon} />}
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
