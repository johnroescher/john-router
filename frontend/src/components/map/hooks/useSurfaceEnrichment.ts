/**
 * useSurfaceEnrichment - Hook that automatically enriches route surface data
 * 
 * Watches for route changes and triggers surface enrichment when:
 * - A new route is loaded
 * - Route geometry changes significantly
 * - Surface data quality is low (high unknown percentage)
 */
import { useEffect, useRef, useCallback } from 'react';
import { useRouteStore } from '@/stores/routeStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { calculateSurfaceBreakdownFromSegments } from '@/lib/surfaceEnrichment';
import { needsSurfaceEnrichment } from '@/lib/surfaceMix';
import { api } from '@/lib/api';
import type { SegmentedSurfaceData } from '@/types';

// Debounce time to avoid multiple enrichments for rapid changes
// Keep low for responsiveness but adapt for longer routes.
const BASE_ENRICHMENT_DEBOUNCE_MS = 120;

// Minimum route length to trigger enrichment (in meters approximately)
const MIN_ROUTE_POINTS = 10;

export function useSurfaceEnrichment() {
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const currentRoute = useRouteStore((state) => state.currentRoute);
  
  const setSegmentedSurface = useSurfaceStore((state) => state.setSegmentedSurface);
  const setIsEnriching = useSurfaceStore((state) => state.setIsEnriching);
  const setEnrichmentError = useSurfaceStore((state) => state.setEnrichmentError);
  const clearSurface = useSurfaceStore((state) => state.clearSurface);
  
  // Track last enriched route ID and geometry to avoid duplicate enrichments
  const lastEnrichedRouteId = useRef<string | null>(null);
  const lastEnrichedGeometryKey = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Main enrichment function
  const performEnrichment = useCallback(async () => {
    if (!routeGeometry || routeGeometry.length < MIN_ROUTE_POINTS) {
      return;
    }

    const first = routeGeometry[0];
    const last = routeGeometry[routeGeometry.length - 1];
    const geometryKey = `${routeGeometry.length}:${first?.[0]?.toFixed(5)}:${first?.[1]?.toFixed(5)}:${last?.[0]?.toFixed(5)}:${last?.[1]?.toFixed(5)}`;
    if (geometryKey === lastEnrichedGeometryKey.current) {
      return;
    }

    // Skip if we already have good enriched data for the current geometry
    const existingSegmented = useSurfaceStore.getState().segmentedSurface;
    if (existingSegmented && existingSegmented.dataQuality > 30) {
      console.log('[SurfaceEnrichment] Enriched surface data already available, skipping enrichment');
      lastEnrichedGeometryKey.current = geometryKey;
      return;
    }

    // Cancel any pending enrichment
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // Create new abort controller
    abortControllerRef.current = new AbortController();
    
    console.log('[SurfaceEnrichment] Starting enrichment for route with', routeGeometry.length, 'points');
    setIsEnriching(true);
    setEnrichmentError(null);

    try {
      let segmentedData: SegmentedSurfaceData | null = null;

      try {
        const response = await api.surfaceMatch({
          type: 'LineString',
          coordinates: routeGeometry,
        });
        if (response?.status === 'ok' && response.segmentedSurface) {
          segmentedData = response.segmentedSurface;
          console.log('[SurfaceEnrichment] Using backend surface match');
        } else if (response?.status && response.status !== 'provider_not_configured') {
          console.warn('[SurfaceEnrichment] Backend surface match unavailable:', response.status, response.message);
        }
      } catch (error) {
        console.warn('[SurfaceEnrichment] Backend surface match failed, falling back:', error);
      }

      if (!segmentedData) {
        segmentedData = {
          segments: [],
          knownDistanceMeters: 0,
          totalDistanceMeters: 0,
          dataQuality: 0,
          lastUpdated: new Date().toISOString(),
          enrichmentSource: null,
        };
      }

      // Check if we were aborted
      if (abortControllerRef.current.signal.aborted) {
        console.log('[SurfaceEnrichment] Enrichment was cancelled');
        return;
      }

      console.log('[SurfaceEnrichment] Enrichment complete:', {
        segments: segmentedData.segments.length,
        dataQuality: segmentedData.dataQuality.toFixed(1) + '%',
        knownDistance: (segmentedData.knownDistanceMeters / 1000).toFixed(1) + 'km',
      });

      // Update the surface store with enriched data
      setSegmentedSurface(segmentedData);

      // Also update the route's surface breakdown if we have better data
      if (segmentedData.dataQuality > 30 && currentRoute) {
        const enrichedBreakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
        console.log('[SurfaceEnrichment] Updated surface breakdown:', enrichedBreakdown);
        
        // Update the route store with enriched surface data
        // This is optional - the UI will use surfaceStore data preferentially
        useRouteStore.getState().setManualSurfaceBreakdown(enrichedBreakdown);
      }

      // Update last enriched route ID and geometry key
      if (currentRoute) {
        lastEnrichedRouteId.current = currentRoute.id;
      }
      lastEnrichedGeometryKey.current = geometryKey;

    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        console.log('[SurfaceEnrichment] Enrichment cancelled');
        return;
      }
      
      console.error('[SurfaceEnrichment] Enrichment failed:', error);
      setEnrichmentError((error as Error).message || 'Failed to enrich surface data');
    } finally {
      setIsEnriching(false);
    }
  }, [routeGeometry, currentRoute, setSegmentedSurface, setIsEnriching, setEnrichmentError]);

  // Watch for route changes and trigger enrichment
  useEffect(() => {
    // Clear surface data when route is cleared
    if (!routeGeometry || routeGeometry.length < 2) {
      clearSurface();
      lastEnrichedRouteId.current = null;
      return;
    }

    // Skip if we already enriched this route + geometry
    if (currentRoute && currentRoute.id === lastEnrichedRouteId.current && lastEnrichedGeometryKey.current) {
      return;
    }

    // Clear previous timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Debounce the enrichment to avoid multiple calls during rapid changes
    const debounceMs = Math.min(
      450,
      BASE_ENRICHMENT_DEBOUNCE_MS + Math.floor((routeGeometry.length - MIN_ROUTE_POINTS) / 80) * 30
    );
    debounceTimerRef.current = setTimeout(() => {
      if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
        (window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback?.(
          () => performEnrichment(),
          { timeout: 1200 }
        );
      } else {
        performEnrichment();
      }
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [routeGeometry, currentRoute?.id, performEnrichment, clearSurface]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // Return a function to manually trigger enrichment
  return {
    enrichNow: performEnrichment,
  };
}
