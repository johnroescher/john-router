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
import type { SegmentedSurfaceData, SurfaceSegment, SurfaceType } from '@/types';

// Debounce time to avoid multiple enrichments for rapid changes
// Keep low for responsiveness but adapt for longer routes.
const BASE_ENRICHMENT_DEBOUNCE_MS = 120;

// Minimum points/length to trigger enrichment.
const MIN_ROUTE_POINTS = 2;
const MIN_ROUTE_DISTANCE_METERS = 30; // ~100 ft

const haversineDistanceMeters = (a: number[], b: number[]): number => {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const lat1 = toRad(a[1]);
  const lon1 = toRad(a[0]);
  const lat2 = toRad(b[1]);
  const lon2 = toRad(b[0]);
  const dlat = lat2 - lat1;
  const dlon = lon2 - lon1;
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
};

const estimateRouteDistance = (geometry: number[][]): number => {
  if (geometry.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < geometry.length; i += 1) {
    total += haversineDistanceMeters(geometry[i - 1], geometry[i]);
  }
  return total;
};

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
    const routeDistanceMeters = estimateRouteDistance(routeGeometry);
    if (routeDistanceMeters < MIN_ROUTE_DISTANCE_METERS) {
      return;
    }

    const first = routeGeometry[0];
    const last = routeGeometry[routeGeometry.length - 1];
    const geometryKey = `${routeGeometry.length}:${first?.[0]?.toFixed(5)}:${first?.[1]?.toFixed(5)}:${last?.[0]?.toFixed(5)}:${last?.[1]?.toFixed(5)}`;
    if (geometryKey === lastEnrichedGeometryKey.current) {
      return;
    }

    // Check if we have manual segments with per-segment surface data
    // If so, use those instead of calling the API (which returns a single segment for the whole route)
    const { manualSegments } = useRouteStore.getState();
    if (manualSegments && manualSegments.length > 1) {
      // Check if segments have meaningful surface data (not all unknown)
      const hasSurfaceData = manualSegments.some(
        (seg) => seg.surfaceBreakdown && 
        (seg.surfaceBreakdown.pavement > 0 || seg.surfaceBreakdown.gravel > 0 || 
         seg.surfaceBreakdown.dirt > 0 || seg.surfaceBreakdown.singletrack > 0)
      );
      
      if (hasSurfaceData) {
        // Build SegmentedSurfaceData from manual segments
        // CRITICAL: Calculate distances from the full routeGeometry, not individual segments
        // The elevation profile uses distances calculated from routeGeometry, so we must match it exactly
        if (!routeGeometry || routeGeometry.length < 2) {
          console.warn('[SurfaceEnrichment] Cannot create segments: routeGeometry is missing or invalid');
          return;
        }
        
        // Calculate cumulative distances along the full route geometry (same as elevation profile)
        const cumulativeDistances: number[] = [0];
        for (let i = 1; i < routeGeometry.length; i++) {
          const dist = haversineDistanceMeters(routeGeometry[i - 1], routeGeometry[i]);
          cumulativeDistances.push(cumulativeDistances[i - 1] + dist);
        }
        
        // Track position in routeGeometry as we process manual segments
        // routeGeometry is built by: first segment all points, then subsequent segments with first point removed
        let routeGeometryIndex = 0;
        const segments: SurfaceSegment[] = [];
        let knownDistance = 0;
        
        for (let i = 0; i < manualSegments.length; i++) {
          const seg = manualSegments[i];
          const segCoords = seg.coordinates;
          if (!segCoords || segCoords.length < 2) continue;
          
          // Determine how many points from this segment are in routeGeometry
          // First segment: all points, subsequent segments: all but first (overlapping point removed)
          const pointsInRouteGeometry = i === 0 ? segCoords.length : segCoords.length - 1;
          
          // Calculate segment distance from routeGeometry (not from segCoords)
          // This ensures alignment with elevation profile distances
          const segStartIndex = routeGeometryIndex;
          const segEndIndex = Math.min(routeGeometryIndex + pointsInRouteGeometry - 1, routeGeometry.length - 1);
          
          const segStartDistance = cumulativeDistances[segStartIndex];
          const segEndDistance = cumulativeDistances[segEndIndex];
          const segDistance = segEndDistance - segStartDistance;
          
          if (segDistance <= 0) {
            console.warn(`[SurfaceEnrichment] Invalid segment distance for segment ${i}, skipping`);
            routeGeometryIndex = segEndIndex + 1;
            continue;
          }
          
          const breakdown = seg.surfaceBreakdown;
          
          // Create sub-segments for each surface type proportional to the breakdown
          const surfaceTypes: Array<{ type: SurfaceType; percent: number }> = [
            { type: 'pavement', percent: breakdown.pavement || 0 },
            { type: 'gravel', percent: breakdown.gravel || 0 },
            { type: 'dirt', percent: breakdown.dirt || 0 },
            { type: 'singletrack', percent: breakdown.singletrack || 0 },
            { type: 'unknown', percent: breakdown.unknown || 0 },
          ].filter(s => s.percent > 0.1); // Only include surface types with > 0.1%
          
          // Calculate cumulative distance for sub-segments
          let subSegmentStartDistance = segStartDistance;
          
          for (const surfaceInfo of surfaceTypes) {
            const subSegmentDistance = (segDistance * surfaceInfo.percent) / 100;
            if (subSegmentDistance < 0.1) continue; // Skip tiny segments
            
            const confidence = surfaceInfo.type !== 'unknown' ? 0.8 : 0.3;
            if (surfaceInfo.type !== 'unknown') {
              knownDistance += subSegmentDistance;
            }
            
            segments.push({
              startIndex: segStartIndex,
              endIndex: segEndIndex,
              startDistanceMeters: subSegmentStartDistance,
              endDistanceMeters: subSegmentStartDistance + subSegmentDistance,
              distanceMeters: subSegmentDistance,
              surfaceType: surfaceInfo.type,
              confidence,
              matchDistanceMeters: null,
              source: 'routing_api',
              osmWayId: null,
            });
            
            subSegmentStartDistance += subSegmentDistance;
          }
          
          // Update routeGeometry index for next segment
          // For first segment, we used all points; for subsequent, we skip the first (overlapping) point
          routeGeometryIndex = i === 0 ? segCoords.length : routeGeometryIndex + (segCoords.length - 1);
        }
        
        // Use the total distance from routeGeometry (same as elevation profile uses)
        const totalDistance = cumulativeDistances[cumulativeDistances.length - 1] || routeDistanceMeters;
        const dataQuality = totalDistance > 0 ? (knownDistance / totalDistance) * 100 : 0;
        
        const segmentedData: SegmentedSurfaceData = {
          segments,
          knownDistanceMeters: knownDistance,
          totalDistanceMeters: totalDistance,
          dataQuality,
          qualityMetrics: {
            coveragePercent: dataQuality,
            avgConfidence: segments.reduce((sum, s) => sum + s.confidence, 0) / segments.length || 0,
            avgMatchDistanceMeters: null,
          },
          lastUpdated: new Date().toISOString(),
          enrichmentSource: 'routing_api',
        };
        
        console.info('[SurfaceEnrichment] Using per-segment data from route regeneration:', {
          segments_count: segments.length,
          data_quality: dataQuality.toFixed(1) + '%',
          known_distance: (knownDistance / 1000).toFixed(1) + 'km',
          total_distance: Math.round(totalDistance),
          route_geometry_points: routeGeometry.length,
          segment_samples: segments.slice(0, 10).map(s => ({
            surfaceType: s.surfaceType,
            distanceMeters: Math.round(s.distanceMeters),
            startDistance: Math.round(s.startDistanceMeters),
            endDistance: Math.round(s.endDistanceMeters),
          })),
          surface_totals: segments.reduce((acc, s) => {
            acc[s.surfaceType] = (acc[s.surfaceType] || 0) + s.distanceMeters;
            return acc;
          }, {} as Record<SurfaceType, number>),
        });
        
        setSegmentedSurface(segmentedData);
        lastEnrichedGeometryKey.current = geometryKey;
        if (currentRoute) {
          lastEnrichedRouteId.current = currentRoute.id;
        }
        return;
      }
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
      if (process.env.NODE_ENV === 'development') {
        console.log('[SurfaceEnrichment] Geometry sample:', {
          pointCount: routeGeometry.length,
          first: JSON.stringify(routeGeometry[0]),
          second: JSON.stringify(routeGeometry[1]),
          last: JSON.stringify(routeGeometry[routeGeometry.length - 1]),
        });
        console.log('[SurfaceEnrichment] Surface match response:', segmentedData);
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
        console.info('[SurfaceEnrichment] Calculated breakdown from segments:', {
          segments_count: segmentedData.segments.length,
          segment_samples: segmentedData.segments.slice(0, 5).map(s => ({
            surfaceType: s.surfaceType,
            distanceMeters: Math.round(s.distanceMeters),
            confidence: s.confidence,
          })),
          calculated_breakdown: enrichedBreakdown,
          data_quality: segmentedData.dataQuality,
          enrichment_source: segmentedData.enrichmentSource,
        });
        
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
