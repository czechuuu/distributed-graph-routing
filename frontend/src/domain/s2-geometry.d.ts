declare module 's2-geometry' {
    export const S2: {
        latLngToKey: (lat: number, lng: number, level: number) => string;
        keyToId: (key: string) => string;
        idToKey: (id: string) => string;
        keyToLatLng: (key: string) => { lat: number; lng: number };
    };
}
