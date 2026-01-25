/**
 * Test suite for surface store simplification
 * 
 * Tests that the surface store correctly aggregates segment-level data
 * and provides simplified breakdown (paved/unpaved/unknown).
 */

import { useSurfaceStore } from '../surfaceStore';
import type { SegmentedSurfaceData, SurfaceSegment } from '@/types';
import { getSimplifiedSurfaceMix } from '@/lib/surfaceMix';

// Helper to create mock segmented surface data
function createMockSegmentedData(segments: Array<{
  distanceMeters: number;
  surfaceType: 'pavement' | 'gravel' | 'dirt' | 'singletrack' | 'unknown';
}>): SegmentedSurfaceData {
  let cumulativeIndex = 0;
  let cumulativeDistance = 0;
  const surfaceSegments: SurfaceSegment[] = segments.map((seg, idx) => {
    const segment: SurfaceSegment = {
      startIndex: cumulativeIndex,
      endIndex: cumulativeIndex + Math.floor(seg.distanceMeters / 10), // Approximate indices
      startDistanceMeters: cumulativeDistance,
      endDistanceMeters: cumulativeDistance + seg.distanceMeters,
      distanceMeters: seg.distanceMeters,
      surfaceType: seg.surfaceType,
      confidence: 0.9,
      source: 'overpass',
    };
    cumulativeIndex = segment.endIndex + 1;
    cumulativeDistance = segment.endDistanceMeters;
    return segment;
  });

  const totalDistance = segments.reduce((sum, seg) => sum + seg.distanceMeters, 0);
  const knownDistance = segments
    .filter(seg => seg.surfaceType !== 'unknown')
    .reduce((sum, seg) => sum + seg.distanceMeters, 0);

  return {
    segments: surfaceSegments,
    knownDistanceMeters: knownDistance,
    totalDistanceMeters: totalDistance,
    dataQuality: totalDistance > 0 ? (knownDistance / totalDistance) * 100 : 0,
    lastUpdated: new Date().toISOString(),
    enrichmentSource: 'overpass',
  };
}

describe('Surface Store - Simplified Breakdown', () => {
  beforeEach(() => {
    // Reset store state
    useSurfaceStore.getState().clearSurface();
  });

  describe('getAggregatedBreakdown', () => {
    it('should aggregate segments into detailed breakdown', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 1000, surfaceType: 'pavement' },
        { distanceMeters: 500, surfaceType: 'gravel' },
        { distanceMeters: 300, surfaceType: 'dirt' },
        { distanceMeters: 200, surfaceType: 'singletrack' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const breakdown = useSurfaceStore.getState().getAggregatedBreakdown();

      expect(breakdown.pavement).toBeCloseTo(50, 1); // 1000 / 2000
      expect(breakdown.gravel).toBeCloseTo(25, 1); // 500 / 2000
      expect(breakdown.dirt).toBeCloseTo(15, 1); // 300 / 2000
      expect(breakdown.singletrack).toBeCloseTo(10, 1); // 200 / 2000
      expect(breakdown.unknown).toBe(0);
    });

    it('should handle all paved segments', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 5000, surfaceType: 'pavement' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const breakdown = useSurfaceStore.getState().getAggregatedBreakdown();

      expect(breakdown.pavement).toBe(100);
      expect(breakdown.gravel).toBe(0);
      expect(breakdown.dirt).toBe(0);
      expect(breakdown.singletrack).toBe(0);
      expect(breakdown.unknown).toBe(0);
    });

    it('should aggregate unpaved segments correctly', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 1000, surfaceType: 'gravel' },
        { distanceMeters: 1000, surfaceType: 'dirt' },
        { distanceMeters: 1000, surfaceType: 'singletrack' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const breakdown = useSurfaceStore.getState().getAggregatedBreakdown();

      expect(breakdown.pavement).toBe(0);
      expect(breakdown.gravel).toBeCloseTo(33.33, 1);
      expect(breakdown.dirt).toBeCloseTo(33.33, 1);
      expect(breakdown.singletrack).toBeCloseTo(33.33, 1);
      expect(breakdown.unknown).toBe(0);
    });

    it('should handle unknown segments', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 2000, surfaceType: 'pavement' },
        { distanceMeters: 1000, surfaceType: 'unknown' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const breakdown = useSurfaceStore.getState().getAggregatedBreakdown();

      expect(breakdown.pavement).toBeCloseTo(66.67, 1);
      expect(breakdown.unknown).toBeCloseTo(33.33, 1);
    });

    it('should return all unknown when no segments', () => {
      const breakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      expect(breakdown.unknown).toBe(100);
    });
  });

  describe('Simplified Breakdown Integration', () => {
    it('should convert aggregated breakdown to simplified correctly', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 2000, surfaceType: 'pavement' },
        { distanceMeters: 1000, surfaceType: 'gravel' },
        { distanceMeters: 500, surfaceType: 'dirt' },
        { distanceMeters: 500, surfaceType: 'singletrack' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBeCloseTo(50, 1); // 2000 / 4000
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(50, 1); // (1000 + 500 + 500) / 4000
      expect(simplifiedBreakdown.unknown).toBe(0);
    });

    it('should handle mixed route with all surface types', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 1000, surfaceType: 'pavement' },
        { distanceMeters: 500, surfaceType: 'gravel' },
        { distanceMeters: 300, surfaceType: 'dirt' },
        { distanceMeters: 200, surfaceType: 'singletrack' },
        { distanceMeters: 1000, surfaceType: 'unknown' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      const total = 3000;
      expect(simplifiedBreakdown.paved).toBeCloseTo((1000 / total) * 100, 1);
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(((500 + 300 + 200) / total) * 100, 1);
      expect(simplifiedBreakdown.unknown).toBeCloseTo((1000 / total) * 100, 1);
    });

    it('should correctly aggregate long routes with many segments', () => {
      // Simulate a 10km route with many small segments
      const segments: Array<{ distanceMeters: number; surfaceType: 'pavement' | 'gravel' | 'dirt' | 'singletrack' | 'unknown' }> = [];
      
      // 5km paved
      for (let i = 0; i < 50; i++) {
        segments.push({ distanceMeters: 100, surfaceType: 'pavement' });
      }
      
      // 3km gravel
      for (let i = 0; i < 30; i++) {
        segments.push({ distanceMeters: 100, surfaceType: 'gravel' });
      }
      
      // 1km dirt
      for (let i = 0; i < 10; i++) {
        segments.push({ distanceMeters: 100, surfaceType: 'dirt' });
      }
      
      // 1km singletrack
      for (let i = 0; i < 10; i++) {
        segments.push({ distanceMeters: 100, surfaceType: 'singletrack' });
      }

      const segmentedData = createMockSegmentedData(segments);
      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBeCloseTo(50, 1); // 5km / 10km
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(50, 1); // (3km + 1km + 1km) / 10km
      expect(simplifiedBreakdown.unknown).toBe(0);
    });
  });

  describe('Edge Cases', () => {
    it('should handle single segment routes', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 5000, surfaceType: 'pavement' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBe(100);
      expect(simplifiedBreakdown.unpaved).toBe(0);
      expect(simplifiedBreakdown.unknown).toBe(0);
    });

    it('should handle routes with only unknown segments', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 5000, surfaceType: 'unknown' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBe(0);
      expect(simplifiedBreakdown.unpaved).toBe(0);
      expect(simplifiedBreakdown.unknown).toBe(100);
    });

    it('should handle very small segments', () => {
      const segmentedData = createMockSegmentedData([
        { distanceMeters: 1, surfaceType: 'pavement' },
        { distanceMeters: 1, surfaceType: 'gravel' },
        { distanceMeters: 1, surfaceType: 'dirt' },
        { distanceMeters: 1, surfaceType: 'singletrack' },
        { distanceMeters: 1, surfaceType: 'unknown' },
      ]);

      useSurfaceStore.getState().setSegmentedSurface(segmentedData);
      const detailedBreakdown = useSurfaceStore.getState().getAggregatedBreakdown();
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBeCloseTo(20, 1);
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(60, 1); // gravel + dirt + singletrack
      expect(simplifiedBreakdown.unknown).toBeCloseTo(20, 1);
    });
  });
});
