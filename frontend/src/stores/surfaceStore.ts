/**
 * Surface Store - Manages segment-level surface data for routes
 * 
 * This store handles:
 * - Storing per-segment surface data for accurate map visualization
 * - Triggering surface enrichment via Overpass API
 * - Computing accurate surface breakdowns from segment data
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { SurfaceBreakdown, SurfaceSegment, SegmentedSurfaceData, SurfaceType } from '@/types';
import { getSimplifiedSurfaceMix, type SurfaceMix } from '@/lib/surfaceMix';

interface SurfaceState {
  // Segment-level surface data for the current route
  segmentedSurface: SegmentedSurfaceData | null;
  
  // Loading state for enrichment
  isEnriching: boolean;
  
  // Error message if enrichment fails
  enrichmentError: string | null;
  
  // Whether auto-enrichment is enabled
  autoEnrichEnabled: boolean;
  
  // Actions
  setSegmentedSurface: (data: SegmentedSurfaceData | null) => void;
  setIsEnriching: (isEnriching: boolean) => void;
  setEnrichmentError: (error: string | null) => void;
  clearSurface: () => void;
  
  // Compute aggregated surface breakdown from segments
  getAggregatedBreakdown: () => SurfaceBreakdown;
  
  // Compute simplified surface breakdown (paved/unpaved/unknown) from segments
  getSimplifiedBreakdown: () => SurfaceMix;
}

export const useSurfaceStore = create<SurfaceState>()(
  immer((set, get) => ({
    segmentedSurface: null,
    isEnriching: false,
    enrichmentError: null,
    autoEnrichEnabled: true,
    
    setSegmentedSurface: (data) => set((state) => {
      state.segmentedSurface = data;
      state.enrichmentError = null;
    }),
    
    setIsEnriching: (isEnriching) => set((state) => {
      state.isEnriching = isEnriching;
    }),
    
    setEnrichmentError: (error) => set((state) => {
      state.enrichmentError = error;
      state.isEnriching = false;
    }),
    
    clearSurface: () => set((state) => {
      state.segmentedSurface = null;
      state.enrichmentError = null;
      state.isEnriching = false;
    }),
    
    getAggregatedBreakdown: () => {
      const { segmentedSurface } = get();
      
      if (!segmentedSurface || segmentedSurface.segments.length === 0) {
        return { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
      }
      
      const totals: Record<SurfaceType, number> = {
        pavement: 0,
        gravel: 0,
        dirt: 0,
        singletrack: 0,
        unknown: 0,
      };
      
      for (const segment of segmentedSurface.segments) {
        totals[segment.surfaceType] += segment.distanceMeters;
      }
      
      const totalDistance = segmentedSurface.totalDistanceMeters || 1;
      
      return {
        pavement: (totals.pavement / totalDistance) * 100,
        gravel: (totals.gravel / totalDistance) * 100,
        dirt: (totals.dirt / totalDistance) * 100,
        singletrack: (totals.singletrack / totalDistance) * 100,
        unknown: (totals.unknown / totalDistance) * 100,
      };
    },
    
    getSimplifiedBreakdown: () => {
      const detailedBreakdown = get().getAggregatedBreakdown();
      return getSimplifiedSurfaceMix(detailedBreakdown);
    },
  }))
);
