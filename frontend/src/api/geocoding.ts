/**
 * Geocoding API using OpenStreetMap Nominatim
 * Free, no API key required
 */

export type GeocodingResult = {
    name: string
    lat: number
    lng: number
}

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'

export async function searchPlaces(query: string): Promise<GeocodingResult[]> {
    if (!query.trim()) {
        return []
    }

    const params = new URLSearchParams({
        q: query,
        format: 'json',
        addressdetails: '1',
        limit: '5',
    })

    const response = await fetch(`${NOMINATIM_URL}?${params}`, {
        headers: {
            'Accept': 'application/json',
            'User-Agent': 'RoutingExplorer/1.0',
        },
    })

    if (!response.ok) {
        return []
    }

    const data = await response.json()

    return data.map((item: { display_name: string; lat: string; lon: string }) => ({
        name: item.display_name,
        lat: parseFloat(item.lat),
        lng: parseFloat(item.lon),
    }))
}
