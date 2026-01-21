export interface BoundingBox {
    minLat: number;
    maxLat: number;
    minLon: number;
    maxLon: number;
}

export interface Region {
    id: string;
    name: string;
    bounds: BoundingBox;
}

export const PREDEFINED_REGIONS: Region[] = [
    {
        id: 'szczecin',
        name: 'Szczecin, Poland',
        // Approximate bounds for Szczecin
        bounds: {
            minLat: 53.3800,
            maxLat: 53.5000,
            minLon: 14.4800,
            maxLon: 14.6500
        }
    },
    {
        id: 'warsaw',
        name: 'Warsaw, Poland',
        bounds: {
            minLat: 52.10,
            maxLat: 52.40,
            minLon: 20.80,
            maxLon: 21.20
        }
    },
    {
        id: 'poland',
        name: 'Poland',
        bounds: {
            minLat: 49.00,
            maxLat: 54.85,
            minLon: 14.10,
            maxLon: 24.20
        }
    }
];

export const DEFAULT_REGION = PREDEFINED_REGIONS[0];
