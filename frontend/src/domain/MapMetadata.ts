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
    }
];

export const DEFAULT_REGION = PREDEFINED_REGIONS[0];
