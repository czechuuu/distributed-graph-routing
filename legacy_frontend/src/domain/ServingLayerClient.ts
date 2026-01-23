/**
 * Client for the serving layer routing API.
 * Performs real-time shortest path computation via POST /route.
 */

export interface Coordinate {
    lat: number;
    lng: number;
}

export interface RouteResponse {
    path: number[];
    coordinates: (Coordinate | null)[];
    status: string;
    steps_count: number;
}

export class ServingLayerClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    /**
     * Calculate shortest path between two nodes.
     * Requires shard IDs for both start and end nodes.
     * Note: Uses string types and manual JSON to preserve large integer precision
     * (JavaScript numbers lose precision for values > 2^53)
     */
    async findRoute(
        startNode: string,
        startShard: string,
        endNode: string,
        endShard: string
    ): Promise<RouteResponse> {
        // Manual JSON construction to preserve large integer precision
        // JavaScript's JSON.stringify would lose precision on large numbers
        const body = `{"start_node":${startNode},"start_node_shard":${startShard},"end_node":${endNode},"end_node_shard":${endShard}}`;
        console.log('ServingLayerClient payload:', body);

        const res = await fetch(`${this.baseUrl}/route`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: body
        });

        if (!res.ok) {
            throw new Error(`Route request failed: ${res.status} ${res.statusText}`);
        }

        return res.json();
    }
}
