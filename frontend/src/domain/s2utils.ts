import { S2 } from 's2-geometry';

/** Default S2 cell level for point+click shard selection */
export const DEFAULT_S2_LEVEL = 12;

/**
 * Get the S2 cell ID as a decimal string for a given lat/lng at a specific level.
 * @param lat - Latitude
 * @param lng - Longitude  
 * @param level - S2 cell level (0-30), defaults to DEFAULT_S2_LEVEL (12)
 * @returns S2 cell ID as decimal string (e.g. "5163949838739439616")
 */
export function getS2CellId(lat: number, lng: number, level: number = DEFAULT_S2_LEVEL): string {
    // Get the S2 key (e.g. "2/03020133...")
    const key = S2.latLngToKey(lat, lng, level);

    // Convert the key to a numeric cell ID (decimal string)
    const cellId = S2.keyToId(key);

    return cellId;
}
