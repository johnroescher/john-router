/**
 * Test suite for surface enrichment simplification
 * 
 * Tests that surface enrichment correctly creates segments with detailed types
 * and that these can be mapped to simplified types for display.
 */

import {
  calculateSurfaceBreakdownFromSegments,
  createSurfaceSegmentFeatures,
  classifyWaySurface,
} from '../surfaceEnrichment';
import { mapSurfaceTypeToSimplified } from '../surfaceMix';
import { getSimplifiedSurfaceMix } from '../surfaceMix';
import type { SegmentedSurfaceData } from '@/types';

describe('Surface Enrichment - Simplification Integration', () => {
  describe('classifyWaySurface', () => {
    it('should prefer explicit surface tags', () => {
      const result = classifyWaySurface({ surface: 'asphalt', highway: 'residential' });
      expect(result.surfaceType).toBe('pavement');
      expect(result.confidence).toBeGreaterThanOrEqual(0.9);
    });

    it('should infer dirt from tracktype when surface is missing', () => {
      const result = classifyWaySurface({ highway: 'track', tracktype: 'grade3' });
      expect(result.surfaceType).toBe('dirt');
      expect(result.confidence).toBeGreaterThanOrEqual(0.8);
    });

    it('should infer singletrack from mtb:scale', () => {
      const result = classifyWaySurface({ highway: 'path', 'mtb:scale': '2' });
      expect(result.surfaceType).toBe('singletrack');
      expect(result.confidence).toBeGreaterThanOrEqual(0.8);
    });
  });
  describe('calculateSurfaceBreakdownFromSegments', () => {
    it('should calculate detailed breakdown from segments', () => {
      const segmentedData: SegmentedSurfaceData = {
        segments: [
          {
            startIndex: 0,
            endIndex: 10,
            startDistanceMeters: 0,
            endDistanceMeters: 1000,
            distanceMeters: 1000,
            surfaceType: 'pavement',
            confidence: 0.9,
            source: 'overpass',
          },
          {
            startIndex: 10,
            endIndex: 20,
            startDistanceMeters: 1000,
            endDistanceMeters: 1500,
            distanceMeters: 500,
            surfaceType: 'gravel',
            confidence: 0.85,
            source: 'overpass',
          },
          {
            startIndex: 20,
            endIndex: 30,
            startDistanceMeters: 1500,
            endDistanceMeters: 1800,
            distanceMeters: 300,
            surfaceType: 'dirt',
            confidence: 0.8,
            source: 'overpass',
          },
          {
            startIndex: 30,
            endIndex: 40,
            startDistanceMeters: 1800,
            endDistanceMeters: 2000,
            distanceMeters: 200,
            surfaceType: 'singletrack',
            confidence: 0.75,
            source: 'overpass',
          },
        ],
        knownDistanceMeters: 2000,
        totalDistanceMeters: 2000,
        dataQuality: 100,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      const breakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
      
      expect(breakdown.pavement).toBeCloseTo(50, 1); // 1000 / 2000
      expect(breakdown.gravel).toBeCloseTo(25, 1); // 500 / 2000
      expect(breakdown.dirt).toBeCloseTo(15, 1); // 300 / 2000
      expect(breakdown.singletrack).toBeCloseTo(10, 1); // 200 / 2000
      expect(breakdown.unknown).toBe(0);
    });

    it('should convert detailed breakdown to simplified', () => {
      const segmentedData: SegmentedSurfaceData = {
        segments: [
          { startIndex: 0, endIndex: 10, startDistanceMeters: 0, endDistanceMeters: 2000, distanceMeters: 2000, surfaceType: 'pavement', confidence: 0.9, source: 'overpass' },
          { startIndex: 10, endIndex: 20, startDistanceMeters: 2000, endDistanceMeters: 3000, distanceMeters: 1000, surfaceType: 'gravel', confidence: 0.85, source: 'overpass' },
          { startIndex: 20, endIndex: 30, startDistanceMeters: 3000, endDistanceMeters: 3500, distanceMeters: 500, surfaceType: 'dirt', confidence: 0.8, source: 'overpass' },
          { startIndex: 30, endIndex: 40, startDistanceMeters: 3500, endDistanceMeters: 4000, distanceMeters: 500, surfaceType: 'singletrack', confidence: 0.75, source: 'overpass' },
        ],
        knownDistanceMeters: 4000,
        totalDistanceMeters: 4000,
        dataQuality: 100,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      const detailedBreakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBeCloseTo(50, 1); // 2000 / 4000
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(50, 1); // (1000 + 500 + 500) / 4000
      expect(simplifiedBreakdown.unknown).toBe(0);
    });

    it('should handle segments with unknown surface type', () => {
      const segmentedData: SegmentedSurfaceData = {
        segments: [
          { startIndex: 0, endIndex: 10, startDistanceMeters: 0, endDistanceMeters: 1500, distanceMeters: 1500, surfaceType: 'pavement', confidence: 0.9, source: 'overpass' },
          { startIndex: 10, endIndex: 20, startDistanceMeters: 1500, endDistanceMeters: 2500, distanceMeters: 1000, surfaceType: 'unknown', confidence: 0, source: 'default' },
        ],
        knownDistanceMeters: 1500,
        totalDistanceMeters: 2500,
        dataQuality: 60,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      const detailedBreakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      expect(simplifiedBreakdown.paved).toBeCloseTo(60, 1); // 1500 / 2500
      expect(simplifiedBreakdown.unpaved).toBe(0);
      expect(simplifiedBreakdown.unknown).toBeCloseTo(40, 1); // 1000 / 2500
    });
  });

  describe('createSurfaceSegmentFeatures', () => {
    it('should create features with detailed surface types', () => {
      const geometry: number[][] = [
        [0, 0], [1, 1], [2, 2], [3, 3], [4, 4],
        [5, 5], [6, 6], [7, 7], [8, 8], [9, 9],
      ];

      const segmentedData: SegmentedSurfaceData = {
        segments: [
          {
            startIndex: 0,
            endIndex: 4,
            startDistanceMeters: 0,
            endDistanceMeters: 1000,
            distanceMeters: 1000,
            surfaceType: 'pavement',
            confidence: 0.9,
            source: 'overpass',
          },
          {
            startIndex: 4,
            endIndex: 9,
            startDistanceMeters: 1000,
            endDistanceMeters: 2000,
            distanceMeters: 1000,
            surfaceType: 'gravel',
            confidence: 0.85,
            source: 'overpass',
          },
        ],
        knownDistanceMeters: 2000,
        totalDistanceMeters: 2000,
        dataQuality: 100,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      const features = createSurfaceSegmentFeatures(geometry, segmentedData);

      expect(features).toHaveLength(2);
      expect(features[0].properties?.surfaceType).toBe('pavement');
      expect(features[1].properties?.surfaceType).toBe('gravel');
    });

    it('should map features to simplified surface types', () => {
      const geometry: number[][] = [
        [0, 0], [1, 1], [2, 2], [3, 3], [4, 4],
        [5, 5], [6, 6], [7, 7], [8, 8], [9, 9],
      ];

      const segmentedData: SegmentedSurfaceData = {
        segments: [
          { startIndex: 0, endIndex: 2, startDistanceMeters: 0, endDistanceMeters: 500, distanceMeters: 500, surfaceType: 'pavement', confidence: 0.9, source: 'overpass' },
          { startIndex: 2, endIndex: 4, startDistanceMeters: 500, endDistanceMeters: 1000, distanceMeters: 500, surfaceType: 'gravel', confidence: 0.85, source: 'overpass' },
          { startIndex: 4, endIndex: 6, startDistanceMeters: 1000, endDistanceMeters: 1500, distanceMeters: 500, surfaceType: 'dirt', confidence: 0.8, source: 'overpass' },
          { startIndex: 6, endIndex: 9, startDistanceMeters: 1500, endDistanceMeters: 2000, distanceMeters: 500, surfaceType: 'singletrack', confidence: 0.75, source: 'overpass' },
        ],
        knownDistanceMeters: 2000,
        totalDistanceMeters: 2000,
        dataQuality: 100,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      const features = createSurfaceSegmentFeatures(geometry, segmentedData);
      const simplifiedFeatures = features.map((feature) => {
        const detailedType = feature.properties?.surfaceType;
        const simplifiedType = mapSurfaceTypeToSimplified(detailedType as any);
        return {
          ...feature,
          properties: {
            ...feature.properties,
            surfaceType: simplifiedType,
          },
        };
      });

      expect(simplifiedFeatures).toHaveLength(4);
      expect(simplifiedFeatures[0].properties?.surfaceType).toBe('paved');
      expect(simplifiedFeatures[1].properties?.surfaceType).toBe('unpaved');
      expect(simplifiedFeatures[2].properties?.surfaceType).toBe('unpaved');
      expect(simplifiedFeatures[3].properties?.surfaceType).toBe('unpaved');
    });
  });

  describe('End-to-End Simplification Flow', () => {
    it('should correctly simplify a complete route with all surface types', () => {
      // Simulate a route with mixed surfaces
      const segmentedData: SegmentedSurfaceData = {
        segments: [
          { startIndex: 0, endIndex: 20, startDistanceMeters: 0, endDistanceMeters: 2000, distanceMeters: 2000, surfaceType: 'pavement', confidence: 0.95, source: 'overpass' },
          { startIndex: 20, endIndex: 30, startDistanceMeters: 2000, endDistanceMeters: 3000, distanceMeters: 1000, surfaceType: 'gravel', confidence: 0.9, source: 'overpass' },
          { startIndex: 30, endIndex: 35, startDistanceMeters: 3000, endDistanceMeters: 3500, distanceMeters: 500, surfaceType: 'dirt', confidence: 0.85, source: 'overpass' },
          { startIndex: 35, endIndex: 40, startDistanceMeters: 3500, endDistanceMeters: 4000, distanceMeters: 500, surfaceType: 'singletrack', confidence: 0.8, source: 'overpass' },
          { startIndex: 40, endIndex: 50, startDistanceMeters: 4000, endDistanceMeters: 5000, distanceMeters: 1000, surfaceType: 'unknown', confidence: 0, source: 'default' },
        ],
        knownDistanceMeters: 4000,
        totalDistanceMeters: 5000,
        dataQuality: 80,
        lastUpdated: new Date().toISOString(),
        enrichmentSource: 'overpass',
      };

      // Step 1: Calculate detailed breakdown
      const detailedBreakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
      
      // Step 2: Convert to simplified
      const simplifiedBreakdown = getSimplifiedSurfaceMix(detailedBreakdown);

      // Verify simplified breakdown
      expect(simplifiedBreakdown.paved).toBeCloseTo(40, 1); // 2000 / 5000
      expect(simplifiedBreakdown.unpaved).toBeCloseTo(40, 1); // (1000 + 500 + 500) / 5000
      expect(simplifiedBreakdown.unknown).toBeCloseTo(20, 1); // 1000 / 5000

      // Step 3: Verify individual segment mapping
      const segmentMappings = segmentedData.segments.map(seg => 
        mapSurfaceTypeToSimplified(seg.surfaceType)
      );
      
      expect(segmentMappings[0]).toBe('paved');
      expect(segmentMappings[1]).toBe('unpaved');
      expect(segmentMappings[2]).toBe('unpaved');
      expect(segmentMappings[3]).toBe('unpaved');
      expect(segmentMappings[4]).toBe('unknown');
    });
  });
});
