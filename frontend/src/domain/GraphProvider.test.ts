import { describe, it, expect } from 'vitest';
import { MockGraphProvider } from './GraphProvider';

describe('MockGraphProvider', () => {
    it('should return consistent data for the same shard ID', async () => {
        const provider = new MockGraphProvider();
        const data1 = await provider.getShard('1');
        const data2 = await provider.getShard('1');

        expect(data1).toEqual(data2);
        expect(data1.nodes.length).toBeGreaterThan(0);
        expect(data1.nodes[0].shard_id).toBe('1');
    });

    it('should return different data for different shard IDs', async () => {
        const provider = new MockGraphProvider();
        const data1 = await provider.getShard('1');
        const data2 = await provider.getShard('2');

        expect(data1).not.toEqual(data2);
    });

    it('should return an overlay graph with bridges and shortcuts', async () => {
        const provider = new MockGraphProvider();
        const overlay = await provider.getOverlayGraph();

        expect(overlay).toBeDefined();
        // We expect some bridges in our connected grid
        expect(overlay.bridges.length).toBeGreaterThan(0);
        // Shortcuts might be 0 if random chance fails, but likely > 0
        // checks strict structure
        expect(Array.isArray(overlay.bridges)).toBe(true);
        expect(Array.isArray(overlay.shortcuts)).toBe(true);
    });
});
