/**
 * Hook for regenerating route when waypoints change
 * Rebuilds the route through all waypoints (start → via1 → via2 → ... → back to start for loops)
 */
import { useCallback, useRef } from 'react';
import { useRouteStore } from '@/stores/routeStore';
import { api } from '@/lib/api';
import { buildSegmentsFromGeometry, type ManualRouteSegment } from '@/lib/routeSegmentation';
import type { Coordinate } from '@/types';

const OPTIMISTIC_SEGMENT_TIMEOUT_MS = 650;
const ROUTING_PARALLEL_ENABLED = (process.env.NEXT_PUBLIC_ROUTING_PARALLEL ?? 'true') !== 'false';
const ROUTING_PARALLEL_MAX_IN_FLIGHT = 4;
const MAX_RETRY_DISTANCE_METERS = 150000;
const ROUTE_TRACE_ENABLED = (process.env.NEXT_PUBLIC_ROUTE_TRACE ?? 'true') !== 'false';

const logRouteTrace = (level: 'debug' | 'info' | 'warn' | 'error', message: string, data?: Record<string, unknown>) => {
  if (!ROUTE_TRACE_ENABLED) return;
  const payload = { message, ...data };
  console[level](`[route-trace] ${message}`, payload);
};

const TRAIL_BIKE_TYPES = new Set(['mtb', 'gravel', 'emtb']);
const AVERAGE_SPEED_MPS: Record<string, number> = {
  road: 7.0,
  gravel: 5.5,
  mtb: 4.2,
  emtb: 5.5,
};

const haversineDistanceMeters = (a: number[], b: number[]) => {
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

const estimateDurationSeconds = (distanceMeters: number, bikeType: string) => {
  const speed = AVERAGE_SPEED_MPS[bikeType] ?? 5.0;
  return speed > 0 ? distanceMeters / speed : 0;
};

const coordsMatch = (coord: number[], target: Coordinate) =>
  Math.abs(coord[0] - target.lng) < 1e-6 && Math.abs(coord[1] - target.lat) < 1e-6;

/**
 * Validates that a route segment follows roads/trails, not a straight line.
 * Allows short 2-point segments (≤100 ft / 30.5m) for trail-to-road transitions,
 * but rejects longer straight-line segments that don't follow the network.
 */
const MAX_STRAIGHT_LINE_DISTANCE_METERS = 30.48; // 100 feet

const isSegmentValid = (coords: number[][]): boolean => {
  if (!Array.isArray(coords) || coords.length < 2) {
    return false;
  }
  
  // If segment has only 2 points, check if distance is too large
  // Allow short 2-point segments (≤100 ft) for trail-to-road transitions
  // Reject longer 2-point segments as they indicate the router failed to find a proper route
  if (coords.length === 2) {
    const distance = haversineDistanceMeters(coords[0], coords[1]);
    // Allow 2-point segments up to 100 ft (30.48m) for trail-to-road transitions
    if (distance > MAX_STRAIGHT_LINE_DISTANCE_METERS) {
      return false;
    }
    // Allow short 2-point segments (≤100 ft) as they may be valid trail-to-road connections
    return true;
  }
  
  // Segments with 3+ points are likely following roads/trails
  return true;
};

const buildInitialSegments = (points: Coordinate[], bikeType: string, buildFallback: (start: Coordinate, end: Coordinate, bikeType: string) => ManualRouteSegment) =>
  points.slice(0, -1).map((start, index) => buildFallback(start, points[index + 1], bikeType));

export function useRouteRegeneration() {
  const setManualSegments = useRouteStore((state) => state.setManualSegments);
  const setRouteSegments = useRouteStore((state) => state.setRouteSegments);
  const clearManualSegments = useRouteStore((state) => state.clearManualSegments);
  const setIsGenerating = useRouteStore((state) => state.setIsGenerating);
  const setIsRoutingDegraded = useRouteStore((state) => state.setIsRoutingDegraded);
  
  // Track ongoing regeneration to prevent duplicate calls
  const regenerationInProgress = useRef(false);
  const pendingChangeRef = useRef<{ type: 'move' | 'insert' | 'remove' | 'start' | 'end'; viaIndex?: number } | null>(null);

  /**
   * Regenerate the entire route through all waypoints
   * Creates segments: start → via1, via1 → via2, ..., lastVia → start (for loops)
   */
  const buildRoutePoints = useCallback(
    (constraints: { start?: Coordinate; viaPoints: Coordinate[]; end?: Coordinate }, includeStartEnd: boolean) => {
      const { start, viaPoints, end } = constraints;
      const points: Coordinate[] = [];

      if (start) {
        points.push(start);
      } else if (includeStartEnd) {
        return [];
      }

      points.push(...viaPoints);

      if (includeStartEnd && end) {
        points.push(end);
      }

      return points;
    },
    []
  );



  const routeAllPoints = useCallback(
    async (
      points: Coordinate[],
      bikeType: string,
      options?: {
        onSegment?: (segmentIndex: number, start: Coordinate, end: Coordinate, segment: ManualRouteSegment) => void;
        allowShortStraightLineFallback?: boolean;
      }
    ): Promise<ManualRouteSegment[] | null> => {
      try {
        logRouteTrace('info', 'routeAllPoints start', {
          bikeType,
          pointCount: points.length,
          start: points[0],
          end: points[points.length - 1],
          parallel: ROUTING_PARALLEL_ENABLED,
        });
        // Use the requested bike type to avoid biasing routes away from major roads.
        const routingBikeType = bikeType;
        const allowShortStraightLineFallback = options?.allowShortStraightLineFallback ?? false;
        if (ROUTING_PARALLEL_ENABLED && points.length > 2) {
          const startedAt = performance.now();
          const segments = await routeSegmentsInParallel(
            points,
            routingBikeType,
            options?.onSegment,
            allowShortStraightLineFallback
          );
          console.debug('[useRouteRegeneration] routeAllPoints parallel elapsed_ms', Math.round(performance.now() - startedAt));
          if (segments.length !== points.length - 1 || segments.some((segment) => !segment)) {
            console.error('[useRouteRegeneration] Parallel routing returned incomplete segments');
            setIsRoutingDegraded(true);
            return null;
          }
          const invalidSegments = segments.filter((segment) => segment && !isSegmentValid(segment.coordinates));
          if (invalidSegments.length > 0) {
            console.warn(`[useRouteRegeneration] ${invalidSegments.length} invalid segments detected`);
            setIsRoutingDegraded(true);
          }
          logRouteTrace('info', 'routeAllPoints parallel complete', {
            bikeType,
            elapsedMs: Math.round(performance.now() - startedAt),
            segmentCount: segments.length,
            invalidSegments: invalidSegments.length,
          });
          return segments as ManualRouteSegment[];
        }

        const startedAt = performance.now();
        const result = await api.routePointToPoint(points, routingBikeType);
        console.debug('[useRouteRegeneration] routeAllPoints elapsed_ms', Math.round(performance.now() - startedAt));
        
        if (result.degraded) {
          const reason = result.degraded_reason ? ` (${result.degraded_reason})` : '';
          console.warn(`[useRouteRegeneration] Route routing degraded${reason}`);
          setIsRoutingDegraded(true);
        }
        
        const coords = result?.geometry?.coordinates;
        if (!coords || coords.length < 2) {
          console.error('[useRouteRegeneration] Invalid geometry: no coordinates');
          setIsRoutingDegraded(true);
          if (allowShortStraightLineFallback && points.length === 2) {
            const distanceMeters = haversineDistanceMeters(
              [points[0].lng, points[0].lat],
              [points[1].lng, points[1].lat]
            );
            if (distanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
              console.warn('[useRouteRegeneration] Using short straight-line fallback (no geometry)', {
                distanceMeters: Math.round(distanceMeters),
              });
              return [buildFallbackSegment(points[0], points[1], bikeType)];
            }
          }
          return null;
        }
        
        const segments = buildSegmentsFromGeometry(coords, points);
        if (!segments) {
          console.error('[useRouteRegeneration] Failed to build segments from geometry');
          setIsRoutingDegraded(true);
          if (allowShortStraightLineFallback && points.length === 2) {
            const distanceMeters = haversineDistanceMeters(
              [points[0].lng, points[0].lat],
              [points[1].lng, points[1].lat]
            );
            if (distanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
              console.warn('[useRouteRegeneration] Using short straight-line fallback (segment build failed)', {
                distanceMeters: Math.round(distanceMeters),
              });
              return [buildFallbackSegment(points[0], points[1], bikeType)];
            }
          }
          return null;
        }
        const invalidSegments = segments.filter((segment) => !isSegmentValid(segment.coordinates));
        if (invalidSegments.length > 0) {
          console.warn(`[useRouteRegeneration] ${invalidSegments.length} invalid segments detected`);
          setIsRoutingDegraded(true);
          if (allowShortStraightLineFallback && points.length === 2) {
            const distanceMeters = haversineDistanceMeters(
              [points[0].lng, points[0].lat],
              [points[1].lng, points[1].lat]
            );
            if (distanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
              console.warn('[useRouteRegeneration] Using short straight-line fallback (invalid segment)', {
                distanceMeters: Math.round(distanceMeters),
              });
              return [buildFallbackSegment(points[0], points[1], bikeType)];
            }
          }
        }
        logRouteTrace('info', 'routeAllPoints complete', {
          bikeType,
          elapsedMs: Math.round(performance.now() - startedAt),
          segmentCount: segments.length,
          invalidSegments: invalidSegments.length,
          degraded: result?.degraded ?? false,
          degradedReason: result?.degraded_reason ?? null,
        });
        return segments;
      } catch (error) {
        console.error('[useRouteRegeneration] Failed to route full path:', error);
        setIsRoutingDegraded(true);
        logRouteTrace('error', 'routeAllPoints failed', {
          bikeType,
          pointCount: points.length,
          message: (error as Error)?.message ?? String(error),
        });
        const allowShortStraightLineFallback = options?.allowShortStraightLineFallback ?? false;
        if (allowShortStraightLineFallback && points.length === 2) {
          const distanceMeters = haversineDistanceMeters(
            [points[0].lng, points[0].lat],
            [points[1].lng, points[1].lat]
          );
          if (distanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[useRouteRegeneration] Using short straight-line fallback (routeAllPoints failed)', {
              distanceMeters: Math.round(distanceMeters),
            });
            return [buildFallbackSegment(points[0], points[1], bikeType)];
          }
        }
        return null;
      }
    },
    [setIsRoutingDegraded]
  );

  /**
   * Creates a straight-line segment for short manual fallbacks or placeholders.
   * Used only when routing cannot find a network path and the gap is ≤100 ft.
   */
  const buildFallbackSegment = useCallback(
    (start: Coordinate, end: Coordinate, bikeType: string): ManualRouteSegment => {
      const distanceMeters = haversineDistanceMeters([start.lng, start.lat], [end.lng, end.lat]);
      return {
        coordinates: [
          [start.lng, start.lat],
          [end.lng, end.lat],
        ],
        distanceMeters,
        elevationGain: 0,
        durationSeconds: estimateDurationSeconds(distanceMeters, bikeType),
        surfaceBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
      };
    },
    []
  );

  const routeSingleSegment = useCallback(
    async (
      start: Coordinate,
      end: Coordinate,
      bikeType: string,
      retryCount: number = 0,
      allowShortStraightLineFallback: boolean = false
    ): Promise<ManualRouteSegment | null> => {
      const MAX_RETRIES = 2;
      const MAX_503_RETRIES = 1;
      const directDistanceMeters = haversineDistanceMeters([start.lng, start.lat], [end.lng, end.lat]);
      const skipRetryForDistance = directDistanceMeters > MAX_RETRY_DISTANCE_METERS;
      try {
        logRouteTrace('info', 'routeSingleSegment start', {
          bikeType,
          retryCount,
          start,
          end,
          directDistanceMeters: Math.round(directDistanceMeters),
        });
        const startedAt = performance.now();
        const result = await api.routePointToPoint([start, end], bikeType);
        const elapsed = Math.round(performance.now() - startedAt);
        console.debug('[useRouteRegeneration] routeSingleSegment elapsed_ms', elapsed);
        
        if (result.degraded) {
          const reason = result.degraded_reason ? ` (${result.degraded_reason})` : '';
          console.warn(`[useRouteRegeneration] Segment routing degraded${reason}`);
          setIsRoutingDegraded(true);
        }
        
        const coords = result?.geometry?.coordinates;
        if (!coords || coords.length < 2) {
          console.error('[useRouteRegeneration] Invalid geometry: no coordinates');
          setIsRoutingDegraded(true);
          if (allowShortStraightLineFallback && directDistanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[useRouteRegeneration] Using short straight-line fallback (no geometry)', {
              distanceMeters: Math.round(directDistanceMeters),
              start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
              end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
            });
            return buildFallbackSegment(start, end, bikeType);
          }
          return null;
        }
        
        // Calculate distance for better error messages
        const distance = haversineDistanceMeters(coords[0], coords[coords.length - 1]);
        const startGapMeters = haversineDistanceMeters(coords[0], [start.lng, start.lat]);
        const endGapMeters = haversineDistanceMeters(coords[coords.length - 1], [end.lng, end.lat]);
        const isShortStraightLine = coords.length === 2 && distance <= MAX_STRAIGHT_LINE_DISTANCE_METERS;
        const hasEndpointGap = startGapMeters > 1 || endGapMeters > 1;
        if (hasEndpointGap || coords.length === 2 || result.degraded) {
          console.info('[route-jump-debug] segment routing summary', {
            bikeType,
            pointCount: coords.length,
            directDistanceMeters: Math.round(directDistanceMeters),
            geometryDistanceMeters: Math.round(distance),
            startGapMeters: Math.round(startGapMeters),
            endGapMeters: Math.round(endGapMeters),
            isShortStraightLine,
            degraded: result?.degraded ?? false,
            degradedReason: result?.degraded_reason ?? null,
            requestedStart: `${start.lat.toFixed(6)},${start.lng.toFixed(6)}`,
            requestedEnd: `${end.lat.toFixed(6)},${end.lng.toFixed(6)}`,
            geometryStart: `${coords[0][1].toFixed(6)},${coords[0][0].toFixed(6)}`,
            geometryEnd: `${coords[coords.length - 1][1].toFixed(6)},${coords[coords.length - 1][0].toFixed(6)}`,
          });
        }

        // Reject router "straight-line" responses (2-point geometries) in manual mode.
        // If the gap is truly tiny, fall back to a local straight-line segment
        // between the actual waypoints instead of snapping to nearby roads.
        if (coords.length === 2) {
          console.warn('[useRouteRegeneration] Router returned straight-line geometry; rejecting', {
            distanceMeters: Math.round(distance),
            start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
            end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
          });
          setIsRoutingDegraded(true);
          logRouteTrace('warn', 'routeSingleSegment straight-line geometry', {
            bikeType,
            pointCount: coords.length,
            distanceMeters: Math.round(distance),
            degraded: result?.degraded ?? false,
            degradedReason: result?.degraded_reason ?? null,
          });
          if (allowShortStraightLineFallback && directDistanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[useRouteRegeneration] Using short straight-line fallback (router returned straight line)', {
              distanceMeters: Math.round(directDistanceMeters),
              start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
              end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
            });
            return buildFallbackSegment(start, end, bikeType);
          }
          return null;
        }
        
        if (!isSegmentValid(coords)) {
          console.warn('[useRouteRegeneration] Segment validation failed - rejecting straight-line segment', {
            distanceMeters: Math.round(distance),
            pointCount: coords.length,
            start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
            end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
          });
          setIsRoutingDegraded(true);
          logRouteTrace('warn', 'routeSingleSegment invalid', {
            bikeType,
            pointCount: coords.length,
            distanceMeters: Math.round(distance),
            degraded: result?.degraded ?? false,
            degradedReason: result?.degraded_reason ?? null,
          });
          if (allowShortStraightLineFallback && directDistanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[useRouteRegeneration] Using short straight-line fallback (invalid segment)', {
              distanceMeters: Math.round(directDistanceMeters),
              start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
              end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
            });
            return buildFallbackSegment(start, end, bikeType);
          }
          return null;
        }
        logRouteTrace('info', 'routeSingleSegment complete', {
          bikeType,
          elapsedMs: elapsed,
          pointCount: coords.length,
          distanceMeters: Math.round(distance),
          degraded: result?.degraded ?? false,
          degradedReason: result?.degraded_reason ?? null,
        });
        return {
          coordinates: coords,
          distanceMeters: result.distance_meters,
          elevationGain: result.elevation_gain,
          durationSeconds: result.duration_seconds,
          surfaceBreakdown: (() => {
            const raw = result.surface_breakdown || {};
            const pavement = raw.paved || 0;
            const gravel = (raw.gravel || 0) + (raw.unpaved || 0);
            const dirt = raw.ground || 0;
            const singletrack = 0;
            // Calculate unknown as remainder to ensure percentages add up to 100
            const known = pavement + gravel + dirt + singletrack;
            const unknown = Math.max(0, 100 - known);
            
            const breakdown = {
              pavement,
              gravel,
              dirt,
              singletrack,
              unknown,
            };
            console.info('[route-regeneration] Surface breakdown from API for segment:', {
              segment_start: `${start.lat.toFixed(6)},${start.lng.toFixed(6)}`,
              segment_end: `${end.lat.toFixed(6)},${end.lng.toFixed(6)}`,
              raw_api_response: raw,
              mapped_breakdown: breakdown,
              total: Object.values(breakdown).reduce((a, b) => a + b, 0),
              distance_meters: Math.round(result.distance_meters || 0),
            });
            return breakdown;
          })(),
        };
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        const is503 = errorMessage.includes('503');
        const shouldRetry503 = is503 && retryCount < MAX_503_RETRIES;
        const shouldRetry = retryCount < MAX_RETRIES && !is503 && !skipRetryForDistance;
        console.error('[useRouteRegeneration] Failed to route segment:', {
          error: errorMessage,
          start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
          end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
          bikeType,
          retryCount,
        });
        logRouteTrace('warn', 'routeSingleSegment failed', {
          bikeType,
          retryCount,
          is503,
          shouldRetry,
          shouldRetry503,
          message: errorMessage,
        });

        if (shouldRetry503) {
          console.log(`[useRouteRegeneration] Retrying after 503 (attempt ${retryCount + 1}/${MAX_503_RETRIES})`);
          return routeSingleSegment(start, end, bikeType, retryCount + 1, allowShortStraightLineFallback);
        }
        
        // Retry with same bike type if it's not a network error
        if (shouldRetry) {
          console.log(`[useRouteRegeneration] Retrying with same bike type (attempt ${retryCount + 1}/${MAX_RETRIES})`);
          return routeSingleSegment(start, end, bikeType, retryCount + 1, allowShortStraightLineFallback);
        }
        if (skipRetryForDistance) {
          console.warn('[useRouteRegeneration] Skipping retries for long segment', {
            distanceMeters: Math.round(directDistanceMeters),
            start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
            end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
          });
        }
        
        setIsRoutingDegraded(true);
        if (allowShortStraightLineFallback && directDistanceMeters <= MAX_STRAIGHT_LINE_DISTANCE_METERS) {
          console.warn('[useRouteRegeneration] Using short straight-line fallback (routing failed)', {
            distanceMeters: Math.round(directDistanceMeters),
            start: `${start.lat.toFixed(4)},${start.lng.toFixed(4)}`,
            end: `${end.lat.toFixed(4)},${end.lng.toFixed(4)}`,
          });
          return buildFallbackSegment(start, end, bikeType);
        }
        return null;
      }
    },
    [buildFallbackSegment, setIsRoutingDegraded]
  );

  const routeSegmentsInParallel = useCallback(
    async (
      points: Coordinate[],
      bikeType: string,
      onSegment?: (segmentIndex: number, start: Coordinate, end: Coordinate, segment: ManualRouteSegment) => void,
      allowShortStraightLineFallback: boolean = false
    ): Promise<Array<ManualRouteSegment | null>> => {
      const segmentCount = Math.max(0, points.length - 1);
      const results: Array<ManualRouteSegment | null> = new Array(segmentCount).fill(null);
      let cursor = 0;
      const workerCount = Math.min(ROUTING_PARALLEL_MAX_IN_FLIGHT, segmentCount);

      const worker = async () => {
        while (cursor < segmentCount) {
          const segmentIndex = cursor;
          cursor += 1;
          const start = points[segmentIndex];
          const end = points[segmentIndex + 1];
          const segment = await routeSingleSegment(start, end, bikeType, 0, allowShortStraightLineFallback);
          if (segment) {
            results[segmentIndex] = segment;
            onSegment?.(segmentIndex, start, end, segment);
          }
        }
      };

      await Promise.all(Array.from({ length: workerCount }, () => worker()));
      return results;
    },
    [routeSingleSegment]
  );

  const replaceSegmentIfMatching = useCallback(
    (segmentIndex: number, start: Coordinate, end: Coordinate, segment: ManualRouteSegment) => {
      const { manualSegments, segmentedImportedRoute } = useRouteStore.getState();
      if (segmentIndex < 0 || segmentIndex >= manualSegments.length) return;

      const existing = manualSegments[segmentIndex];
      if (!existing?.coordinates?.length) return;
      const first = existing.coordinates[0];
      const last = existing.coordinates[existing.coordinates.length - 1];
      if (!coordsMatch(first, start) || !coordsMatch(last, end)) return;

      const nextSegments = manualSegments.slice();
      nextSegments[segmentIndex] = segment;
      if (segmentedImportedRoute) {
        setRouteSegments(nextSegments);
      } else {
        setManualSegments(nextSegments);
      }
    },
    [setManualSegments, setRouteSegments]
  );

  const routeSingleSegmentOptimistic = useCallback(
    async (
      start: Coordinate,
      end: Coordinate,
      bikeType: string,
      segmentIndex: number,
      allowShortStraightLineFallback: boolean = false
    ): Promise<ManualRouteSegment | null> => {
      // Use the requested bike type to avoid biasing routes away from major roads.
      const routingBikeType = bikeType;
      return routeSingleSegment(start, end, routingBikeType, 0, allowShortStraightLineFallback);
    },
    [routeSingleSegment]
  );

  const regenerateRoute = useCallback(async (options?: { ignoreInProgress?: boolean }) => {
    // Prevent concurrent regeneration
    if (regenerationInProgress.current && !options?.ignoreInProgress) {
      console.log('[useRouteRegeneration] Already in progress, skipping');
      return;
    }

    // Get the LATEST state directly from the store (not from closure)
    const { constraints, currentRoute, segmentedImportedRoute } = useRouteStore.getState();
    const bikeType = constraints.sportType || 'road';
    const includeStartEnd = Boolean(currentRoute && currentRoute.id !== 'manual-route');
    const allowShortStraightLineFallback = !includeStartEnd;
    
    console.log('[useRouteRegeneration] Regenerating with', constraints.viaPoints.length, 'via points');
    
    // If no via points, clear the route
    if (!includeStartEnd && constraints.viaPoints.length === 0) {
      console.log('[useRouteRegeneration] No via points, clearing route');
      clearManualSegments();
      return;
    }

    const totalPoints = buildRoutePoints(constraints, includeStartEnd).length;
    if (totalPoints < 2) {
      console.log('[useRouteRegeneration] Not enough points to build route');
      clearManualSegments();
      return;
    }

    regenerationInProgress.current = true;
    setIsGenerating(true);
    setIsRoutingDegraded(false);
    console.log('[useRouteRegeneration] Starting regeneration...');

    try {
      const allPoints = buildRoutePoints(constraints, includeStartEnd);
      console.log('[useRouteRegeneration] Regenerating route through', allPoints.length, 'points');
      console.log('[useRouteRegeneration] All points:', JSON.stringify(allPoints));
      if (ROUTING_PARALLEL_ENABLED && allPoints.length > 2) {
        const initialSegments = buildInitialSegments(allPoints, bikeType, buildFallbackSegment);
        if (initialSegments.length > 0) {
          if (includeStartEnd || segmentedImportedRoute) {
            setRouteSegments(initialSegments);
          } else {
            setManualSegments(initialSegments);
          }
        }
      }
      const segments = await routeAllPoints(allPoints, bikeType, {
        onSegment: (segmentIndex, start, end, segment) => {
          if (!ROUTING_PARALLEL_ENABLED) return;
          replaceSegmentIfMatching(segmentIndex, start, end, segment);
        },
        allowShortStraightLineFallback,
      });
      if (!segments || segments.length === 0) {
        console.warn('[useRouteRegeneration] No valid route generated');
        setIsRoutingDegraded(true);
        return;
      }
      console.log('[useRouteRegeneration] Setting', segments.length, 'new segments');
      if (includeStartEnd) {
        setRouteSegments(segments);
      } else {
        setManualSegments(segments);
      }
    } catch (error) {
      console.error('[useRouteRegeneration] Failed to regenerate route:', error);
    } finally {
      regenerationInProgress.current = false;
      setIsGenerating(false);
    }
  }, [setManualSegments, clearManualSegments, setIsGenerating, buildRoutePoints, routeAllPoints]);

  const regenerateRoutePartially = useCallback(
    async (change: { type: 'move' | 'insert' | 'remove' | 'start' | 'end'; viaIndex?: number }) => {
      if (regenerationInProgress.current) {
        console.log('[useRouteRegeneration] Already in progress, queueing partial regen');
        pendingChangeRef.current = change;
        return;
      }
      const { constraints, manualSegments, currentRoute, segmentedImportedRoute } = useRouteStore.getState();
      const includeStartEnd = Boolean(currentRoute && currentRoute.id !== 'manual-route');
      const usePartialOnImported = includeStartEnd && segmentedImportedRoute;
      const allowShortStraightLineFallback = !includeStartEnd;
      const bikeType = constraints.sportType || 'road';

      if (includeStartEnd && !usePartialOnImported) {
        await regenerateRoute({ ignoreInProgress: true });
        return;
      }

      const points = buildRoutePoints(constraints, includeStartEnd);
      if (points.length < 2) {
        clearManualSegments();
        return;
      }

      regenerationInProgress.current = true;
      setIsGenerating(true);
      setIsRoutingDegraded(false);

      try {
        const nextSegments = manualSegments.slice();
        const applySegments = usePartialOnImported ? setRouteSegments : setManualSegments;

        if (change.type === 'start') {
          if (points.length < 2) {
            console.error('[useRouteRegeneration] Start: Need at least 2 points');
            setIsRoutingDegraded(true);
            return;
          }
          const segment = await routeSingleSegmentOptimistic(
            points[0],
            points[1],
            bikeType,
            0,
            allowShortStraightLineFallback
          );
          if (!segment) {
            console.error(
              '[useRouteRegeneration] Start: Failed to route segment',
              `from start to waypoint 1`,
              `(${points[0].lat.toFixed(4)},${points[0].lng.toFixed(4)} → ${points[1].lat.toFixed(4)},${points[1].lng.toFixed(4)})`
            );
            setIsRoutingDegraded(true);
            return;
          }
          if (nextSegments.length === 0) {
            nextSegments.push(segment);
          } else {
            nextSegments[0] = segment;
          }
          applySegments(nextSegments);
          return;
        }

        if (change.type === 'move') {
          const viaIndex = change.viaIndex;
          if (viaIndex === undefined) return;
          const pointIndex = viaIndex + 1;
          if (pointIndex <= 0 || pointIndex >= points.length) return;

          const prevPromise =
            pointIndex - 1 >= 0
              ? routeSingleSegmentOptimistic(
                  points[pointIndex - 1],
                  points[pointIndex],
                  bikeType,
                  pointIndex - 1,
                  allowShortStraightLineFallback
                )
              : Promise.resolve(null);
          const nextPromise =
            pointIndex < points.length - 1
              ? routeSingleSegmentOptimistic(
                  points[pointIndex],
                  points[pointIndex + 1],
                  bikeType,
                  pointIndex,
                  allowShortStraightLineFallback
                )
              : Promise.resolve(null);
          const [prevSegment, nextSegment] = await Promise.all([prevPromise, nextPromise]);

          if (pointIndex - 1 >= 0) {
            if (!prevSegment) return;
            nextSegments[pointIndex - 1] = prevSegment;
          }
          if (pointIndex < points.length - 1) {
            if (!nextSegment) return;
            nextSegments[pointIndex] = nextSegment;
          }
          applySegments(nextSegments);
          return;
        }

        if (change.type === 'insert') {
          const viaIndex = change.viaIndex;
          if (viaIndex === undefined) {
            console.error('[useRouteRegeneration] Insert: viaIndex undefined');
            setIsRoutingDegraded(true);
            return;
          }
          const pointIndex = viaIndex + 1;
          if (pointIndex <= 0 || pointIndex >= points.length) {
            console.error('[useRouteRegeneration] Insert: invalid pointIndex', pointIndex, 'points.length', points.length);
            setIsRoutingDegraded(true);
            return;
          }

          // Route from previous point to new waypoint
          const prevPromise = routeSingleSegmentOptimistic(
            points[pointIndex - 1],
            points[pointIndex],
            bikeType,
            pointIndex - 1,
            allowShortStraightLineFallback
          );
          const nextPromise =
            pointIndex < points.length - 1
              ? routeSingleSegmentOptimistic(
                  points[pointIndex],
                  points[pointIndex + 1],
                  bikeType,
                  pointIndex,
                  allowShortStraightLineFallback
                )
              : Promise.resolve(null);
          let prevSegment = await prevPromise;
          
          // If optimistic routing failed, try direct routing (bypassing timeout)
          if (!prevSegment) {
            const distance = haversineDistanceMeters(
              [points[pointIndex - 1].lng, points[pointIndex - 1].lat],
              [points[pointIndex].lng, points[pointIndex].lat]
            );
            console.warn(
              '[useRouteRegeneration] Insert: Optimistic routing failed, retrying without timeout',
              `from waypoint ${pointIndex - 1} to waypoint ${pointIndex}`,
              `(${points[pointIndex - 1].lat.toFixed(4)},${points[pointIndex - 1].lng.toFixed(4)} → ${points[pointIndex].lat.toFixed(4)},${points[pointIndex].lng.toFixed(4)})`,
              `distance: ${Math.round(distance)}m`
            );
            
            prevSegment = await routeSingleSegment(
              points[pointIndex - 1],
              points[pointIndex],
              bikeType,
              0,
              allowShortStraightLineFallback
            );
          }
          
          if (!prevSegment) {
            const distance = haversineDistanceMeters(
              [points[pointIndex - 1].lng, points[pointIndex - 1].lat],
              [points[pointIndex].lng, points[pointIndex].lat]
            );
            console.error(
              '[useRouteRegeneration] Insert: Failed to route segment after retry',
              `from waypoint ${pointIndex - 1} to waypoint ${pointIndex}`,
              `(${points[pointIndex - 1].lat.toFixed(4)},${points[pointIndex - 1].lng.toFixed(4)} → ${points[pointIndex].lat.toFixed(4)},${points[pointIndex].lng.toFixed(4)})`,
              `distance: ${Math.round(distance)}m`
            );
            setIsRoutingDegraded(true);
            return;
          }

          // If this is the last waypoint, just add the segment
          if (pointIndex === points.length - 1) {
            // Handle case where we're creating the first segment (nextSegments is empty)
            if (nextSegments.length === 0) {
              nextSegments.push(prevSegment);
            } else {
              nextSegments.splice(pointIndex - 1, 0, prevSegment);
            }
            applySegments(nextSegments);
            return;
          }

          // Route from new waypoint to next waypoint
          const nextSegment = await nextPromise;
          if (!nextSegment) {
            console.error(
              '[useRouteRegeneration] Insert: Failed to route next segment',
              `from waypoint ${pointIndex} to waypoint ${pointIndex + 1}`,
              `(${points[pointIndex].lat.toFixed(4)},${points[pointIndex].lng.toFixed(4)} → ${points[pointIndex + 1].lat.toFixed(4)},${points[pointIndex + 1].lng.toFixed(4)})`
            );
            setIsRoutingDegraded(true);
            // Still add the previous segment so at least part of the route is created
            if (nextSegments.length === 0) {
              nextSegments.push(prevSegment);
            } else {
              nextSegments.splice(pointIndex - 1, 0, prevSegment);
            }
            applySegments(nextSegments);
            return;
          }

          // Replace the old segment with two new segments
          if (nextSegments.length === 0) {
            // Creating first segments
            nextSegments.push(prevSegment, nextSegment);
          } else {
            nextSegments.splice(pointIndex - 1, 1, prevSegment, nextSegment);
          }
          applySegments(nextSegments);
          return;
        }

        if (change.type === 'remove') {
          const viaIndex = change.viaIndex;
          if (viaIndex === undefined) return;
          const pointIndex = viaIndex + 1;
          const segmentIndex = viaIndex;

          if (segmentIndex >= nextSegments.length) return;

          if (pointIndex >= points.length) {
            nextSegments.splice(segmentIndex, 1);
            applySegments(nextSegments);
            return;
          }

          const segment = await routeSingleSegmentOptimistic(
            points[segmentIndex],
            points[segmentIndex + 1],
            bikeType,
            segmentIndex,
            allowShortStraightLineFallback
          );
          if (!segment) return;
          nextSegments.splice(segmentIndex, 2, segment);
          applySegments(nextSegments);
          return;
        }
      } finally {
        regenerationInProgress.current = false;
        setIsGenerating(false);
        if (pendingChangeRef.current) {
          const queued = pendingChangeRef.current;
          pendingChangeRef.current = null;
          regenerateRoutePartially(queued);
        }
      }
    },
    [
      regenerateRoute,
      buildRoutePoints,
      routeSingleSegment,
      routeSingleSegmentOptimistic,
      clearManualSegments,
      setIsGenerating,
      setIsRoutingDegraded,
      setManualSegments,
      setRouteSegments,
    ]
  );

  return {
    regenerateRoute,
    regenerateRoutePartially,
  };
}
