/**
 * Test suite for surface type simplification
 * 
 * Tests the conversion from 5 detailed surface categories to 3 simplified categories:
 * - paved = pavement
 * - unpaved = gravel + dirt + singletrack
 * - unknown = unknown
 */

import {
  mapSurfaceTypeToSimplified,
  getSimplifiedSurfaceMix,
  getDetailedSurfaceMix,
  normalizeSurfaceBreakdown,
  type SurfaceMix,
  type SimplifiedSurfaceType,
} from '../surfaceMix';
import type { SurfaceBreakdown, SurfaceType } from '@/types';

describe('Surface Type Simplification', () => {
  describe('mapSurfaceTypeToSimplified', () => {
    it('should map pavement to paved', () => {
      expect(mapSurfaceTypeToSimplified('pavement')).toBe('paved');
    });

    it('should map gravel to unpaved', () => {
      expect(mapSurfaceTypeToSimplified('gravel')).toBe('unpaved');
    });

    it('should map dirt to unpaved', () => {
      expect(mapSurfaceTypeToSimplified('dirt')).toBe('unpaved');
    });

    it('should map singletrack to unpaved', () => {
      expect(mapSurfaceTypeToSimplified('singletrack')).toBe('unpaved');
    });

    it('should map unknown to unknown', () => {
      expect(mapSurfaceTypeToSimplified('unknown')).toBe('unknown');
    });

    it('should handle all surface types', () => {
      const testCases: Array<{ input: SurfaceType; expected: SimplifiedSurfaceType }> = [
        { input: 'pavement', expected: 'paved' },
        { input: 'gravel', expected: 'unpaved' },
        { input: 'dirt', expected: 'unpaved' },
        { input: 'singletrack', expected: 'unpaved' },
        { input: 'unknown', expected: 'unknown' },
      ];

      testCases.forEach(({ input, expected }) => {
        expect(mapSurfaceTypeToSimplified(input)).toBe(expected);
      });
    });
  });

  describe('getSimplifiedSurfaceMix', () => {
    it('should aggregate pavement into paved', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 100,
        gravel: 0,
        dirt: 0,
        singletrack: 0,
        unknown: 0,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(100);
      expect(result.unpaved).toBe(0);
      expect(result.unknown).toBe(0);
    });

    it('should aggregate gravel, dirt, and singletrack into unpaved', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 0,
        gravel: 30,
        dirt: 40,
        singletrack: 30,
        unknown: 0,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(0);
      expect(result.unpaved).toBe(100);
      expect(result.unknown).toBe(0);
    });

    it('should preserve unknown as unknown', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 0,
        gravel: 0,
        dirt: 0,
        singletrack: 0,
        unknown: 100,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(0);
      expect(result.unpaved).toBe(0);
      expect(result.unknown).toBe(100);
    });

    it('should correctly combine mixed surfaces', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 50,
        gravel: 20,
        dirt: 15,
        singletrack: 10,
        unknown: 5,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(50);
      expect(result.unpaved).toBe(45); // 20 + 15 + 10
      expect(result.unknown).toBe(5);
    });

    it('should normalize percentages to sum to 100', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 30,
        gravel: 20,
        dirt: 10,
        singletrack: 5,
        unknown: 10,
      }; // Sum = 75

      const result = getSimplifiedSurfaceMix(breakdown);
      const total = result.paved + result.unpaved + result.unknown;
      expect(total).toBeCloseTo(100, 1);
    });

    it('should handle empty breakdown (all zero)', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 0,
        gravel: 0,
        dirt: 0,
        singletrack: 0,
        unknown: 0,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.unknown).toBe(100);
      expect(result.paved).toBe(0);
      expect(result.unpaved).toBe(0);
    });

    it('should handle partial unpaved breakdowns', () => {
      const testCases = [
        { gravel: 100, dirt: 0, singletrack: 0 },
        { gravel: 0, dirt: 100, singletrack: 0 },
        { gravel: 0, dirt: 0, singletrack: 100 },
        { gravel: 50, dirt: 50, singletrack: 0 },
        { gravel: 33.33, dirt: 33.33, singletrack: 33.34 },
      ];

      testCases.forEach(({ gravel, dirt, singletrack }) => {
        const breakdown: SurfaceBreakdown = {
          pavement: 0,
          gravel,
          dirt,
          singletrack,
          unknown: 0,
        };

        const result = getSimplifiedSurfaceMix(breakdown);
        expect(result.unpaved).toBeCloseTo(100, 1);
        expect(result.paved).toBe(0);
        expect(result.unknown).toBe(0);
      });
    });

    it('should maintain percentage accuracy for complex breakdowns', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 33.33,
        gravel: 22.22,
        dirt: 11.11,
        singletrack: 5.56,
        unknown: 27.78,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBeCloseTo(33.33, 1);
      expect(result.unpaved).toBeCloseTo(38.89, 1); // 22.22 + 11.11 + 5.56
      expect(result.unknown).toBeCloseTo(27.78, 1);
      
      const total = result.paved + result.unpaved + result.unknown;
      expect(total).toBeCloseTo(100, 1);
    });
  });

  describe('getDetailedSurfaceMix', () => {
    it('should preserve all 5 surface categories', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 20,
        gravel: 20,
        dirt: 20,
        singletrack: 20,
        unknown: 20,
      };

      const result = getDetailedSurfaceMix(breakdown);
      expect(result.pavement).toBe(20);
      expect(result.gravel).toBe(20);
      expect(result.dirt).toBe(20);
      expect(result.singletrack).toBe(20);
      expect(result.unknown).toBe(20);
    });

    it('should normalize detailed breakdown to sum to 100', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 10,
        gravel: 10,
        dirt: 10,
        singletrack: 10,
        unknown: 10,
      }; // Sum = 50

      const result = getDetailedSurfaceMix(breakdown);
      const total = result.pavement + result.gravel + result.dirt + 
                    result.singletrack + result.unknown;
      expect(total).toBeCloseTo(100, 1);
    });

    it('should handle empty breakdown', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 0,
        gravel: 0,
        dirt: 0,
        singletrack: 0,
        unknown: 0,
      };

      const result = getDetailedSurfaceMix(breakdown);
      expect(result.unknown).toBe(100);
    });
  });

  describe('Data Flow Integration', () => {
    it('should correctly convert detailed breakdown to simplified and back', () => {
      const detailed: SurfaceBreakdown = {
        pavement: 40,
        gravel: 25,
        dirt: 15,
        singletrack: 10,
        unknown: 10,
      };

      // Convert to simplified
      const simplified = getSimplifiedSurfaceMix(detailed);
      expect(simplified.paved).toBe(40);
      expect(simplified.unpaved).toBe(50); // 25 + 15 + 10
      expect(simplified.unknown).toBe(10);

      // Verify detailed is preserved
      const preserved = getDetailedSurfaceMix(detailed);
      expect(preserved.pavement).toBe(40);
      expect(preserved.gravel).toBe(25);
      expect(preserved.dirt).toBe(15);
      expect(preserved.singletrack).toBe(10);
      expect(preserved.unknown).toBe(10);
    });

    it('should handle real-world route breakdowns', () => {
      // Example: 60% paved road, 30% gravel, 10% unknown
      const breakdown: SurfaceBreakdown = {
        pavement: 60,
        gravel: 30,
        dirt: 0,
        singletrack: 0,
        unknown: 10,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(60);
      expect(result.unpaved).toBe(30);
      expect(result.unknown).toBe(10);
    });

    it('should handle MTB route with mixed unpaved surfaces', () => {
      // Example: 20% paved, 40% singletrack, 30% dirt, 10% unknown
      const breakdown: SurfaceBreakdown = {
        pavement: 20,
        gravel: 0,
        dirt: 30,
        singletrack: 40,
        unknown: 10,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBe(20);
      expect(result.unpaved).toBe(70); // 0 + 30 + 40
      expect(result.unknown).toBe(10);
    });
  });

  describe('Edge Cases', () => {
    it('should handle breakdowns that sum to more than 100', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 50,
        gravel: 30,
        dirt: 20,
        singletrack: 10,
        unknown: 5,
      }; // Sum = 115

      const result = getSimplifiedSurfaceMix(breakdown);
      const total = result.paved + result.unpaved + result.unknown;
      expect(total).toBeCloseTo(100, 1);
    });

    it('should handle breakdowns that sum to less than 100', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 30,
        gravel: 20,
        dirt: 10,
        singletrack: 5,
        unknown: 0,
      }; // Sum = 65

      const result = getSimplifiedSurfaceMix(breakdown);
      const total = result.paved + result.unpaved + result.unknown;
      expect(total).toBeCloseTo(100, 1);
    });

    it('should handle very small percentages', () => {
      const breakdown: SurfaceBreakdown = {
        pavement: 0.1,
        gravel: 0.2,
        dirt: 0.3,
        singletrack: 0.4,
        unknown: 99,
      };

      const result = getSimplifiedSurfaceMix(breakdown);
      expect(result.paved).toBeCloseTo(0.1, 1);
      expect(result.unpaved).toBeCloseTo(0.9, 1); // 0.2 + 0.3 + 0.4
      expect(result.unknown).toBeCloseTo(99, 1);
    });
  });

  describe('normalizeSurfaceBreakdown', () => {
    it('should handle simplified input (paved/unpaved)', () => {
      const input = {
        paved: 60,
        unpaved: 40,
      };

      const result = normalizeSurfaceBreakdown(input);
      expect(result.pavement).toBe(60);
      expect(result.unknown).toBeGreaterThanOrEqual(0);
    });

    it('should handle detailed input', () => {
      const input: SurfaceBreakdown = {
        pavement: 50,
        gravel: 30,
        dirt: 10,
        singletrack: 5,
        unknown: 5,
      };

      const result = normalizeSurfaceBreakdown(input);
      expect(result.pavement).toBe(50);
      expect(result.gravel).toBe(30);
      expect(result.dirt).toBe(10);
      expect(result.singletrack).toBe(5);
      expect(result.unknown).toBe(5);
    });
  });
});
