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
  
  // Computed: aggregated breakdown (reactive selector)
  aggregatedBreakdown: SurfaceBreakdown;
}

export const useSurfaceStore = create<SurfaceState>()(
  immer((set, get) => ({
    segmentedSurface: null,
    isEnriching: false,
    enrichmentError: null,
    autoEnrichEnabled: true,
    aggregatedBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
    
    setSegmentedSurface: (data) => set((state) => {
      // Create a new object reference to ensure Zustand detects the change
      // This is important for React components to re-render
      state.segmentedSurface = data ? {
        ...data,
        segments: [...data.segments],
        qualityMetrics: data.qualityMetrics ? { ...data.qualityMetrics } : null,
      } : null;
      state.enrichmentError = null;
      // Update computed aggregated breakdown when segmented surface changes
      // Calculate directly from the new data to ensure we use the latest
      if (data && data.segments.length > 0) {
        const totals: Record<SurfaceType, number> = {
          pavement: 0,
          gravel: 0,
          dirt: 0,
          singletrack: 0,
          unknown: 0,
        };
        
        for (const segment of data.segments) {
          totals[segment.surfaceType] += segment.distanceMeters;
        }
        
        const totalDistance = data.totalDistanceMeters || 1;
        state.aggregatedBreakdown = {
          pavement: (totals.pavement / totalDistance) * 100,
          gravel: (totals.gravel / totalDistance) * 100,
          dirt: (totals.dirt / totalDistance) * 100,
          singletrack: (totals.singletrack / totalDistance) * 100,
          unknown: (totals.unknown / totalDistance) * 100,
        };
        console.info('[surface-store] Updated segmented surface and aggregated breakdown:', {
          segments_count: data.segments.length,
          aggregated_breakdown: state.aggregatedBreakdown,
        });
      } else {
        state.aggregatedBreakdown = { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
      }
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
      state.aggregatedBreakdown = { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
    }),
    
    getAggregatedBreakdown: () => {
      const { segmentedSurface } = get();
      
      if (!segmentedSurface || segmentedSurface.segments.length === 0) {
        console.debug('[surface-store] No segmented surface data, returning default');
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
      
      const breakdown = {
        pavement: (totals.pavement / totalDistance) * 100,
        gravel: (totals.gravel / totalDistance) * 100,
        dirt: (totals.dirt / totalDistance) * 100,
        singletrack: (totals.singletrack / totalDistance) * 100,
        unknown: (totals.unknown / totalDistance) * 100,
      };
      
      console.info('[surface-store] Aggregated breakdown from segments:', {
        segments_count: segmentedSurface.segments.length,
        total_distance_m: totalDistance,
        distance_totals: totals,
        breakdown_percentages: breakdown,
        data_quality: segmentedSurface.dataQuality,
        enrichment_source: segmentedSurface.enrichmentSource,
      });
      
      return breakdown;
    },
    
    getSimplifiedBreakdown: () => {
      const detailedBreakdown = get().getAggregatedBreakdown();
      return getSimplifiedSurfaceMix(detailedBreakdown);
    },
  }))
);
