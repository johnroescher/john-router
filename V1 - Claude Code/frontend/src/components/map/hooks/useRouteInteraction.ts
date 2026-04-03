/**
 * Hook for handling route interaction (clicking to add via points, dragging markers)
 */
import { useCallback, useRef, useMemo } from 'react';
import type { MapRef } from 'react-map-gl/maplibre';
import type { MapLayerMouseEvent } from 'react-map-gl/maplibre';
import type { MapGeoJSONFeature } from 'maplibre-gl';
import { useRouteStore } from '@/stores/routeStore';
import { useRouteRegeneration } from './useRouteRegeneration';
import type { Coordinate } from '@/types';

type DragState = {
  active: boolean;
  viaIndex: number | null;
  isStart: boolean;
};

const TRAIL_CLASSES = new Set([
  'path',
  'footway',
  'track',
  'trail',
  'bridleway',
  'cycleway',
  'steps',
  'mountainbike',
]);

const ROAD_CLASSES = new Set([
  'motorway',
  'trunk',
  'primary',
  'secondary',
  'tertiary',
  'residential',
  'service',
  'unclassified',
  'living_street',
  'road',
  'street',
  'major_road',
  'minor_road',
]);

type ScreenPoint = { x: number; y: number };

const asLowerString = (value: unknown) =>
  value === undefined || value === null ? '' : String(value).toLowerCase();

const isRoadOrTrailFeature = (feature: MapGeoJSONFeature) => {
  const props = feature.properties || {};
  const layerId = asLowerString(feature.layer?.id);
  const sourceLayer = asLowerString((feature.layer as { 'source-layer'?: string } | undefined)?.['source-layer']);
  const classValue = asLowerString(props.class || props.subclass || props.type || props.highway || props.kind);
  const highwayValue = asLowerString(props.highway || props.road || props.road_type);

  if (TRAIL_CLASSES.has(classValue) || TRAIL_CLASSES.has(highwayValue)) return true;
  if (ROAD_CLASSES.has(classValue) || ROAD_CLASSES.has(highwayValue)) return true;
  if (layerId.includes('trail') || layerId.includes('path')) return true;
  if (layerId.includes('road') || layerId.includes('street')) return true;
  if (sourceLayer.includes('transport') || sourceLayer.includes('road')) return true;

  return false;
};

type SegmentMatch = { point: ScreenPoint; distanceSq: number };

const getNearestPointOnSegment = (
  target: ScreenPoint,
  start: ScreenPoint,
  end: ScreenPoint,
): SegmentMatch => {
  const abx = end.x - start.x;
  const aby = end.y - start.y;
  const abLenSq = abx * abx + aby * aby;
  if (abLenSq === 0) {
    const dx = target.x - start.x;
    const dy = target.y - start.y;
    return { point: start, distanceSq: dx * dx + dy * dy };
  }
  const apx = target.x - start.x;
  const apy = target.y - start.y;
  const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / abLenSq));
  const closest: ScreenPoint = { x: start.x + abx * t, y: start.y + aby * t };
  const dx = target.x - closest.x;
  const dy = target.y - closest.y;
  return { point: closest, distanceSq: dx * dx + dy * dy };
};

export function useRouteInteraction(mapRef: React.RefObject<MapRef | null>) {
  const constraints = useRouteStore((state) => state.constraints);
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const setConstraintStart = useRouteStore((state) => state.setConstraintStart);
  const addViaPoint = useRouteStore((state) => state.addViaPoint);
  const setConstraintEnd = useRouteStore((state) => state.setConstraintEnd);
  const manualSegments = useRouteStore((state) => state.manualSegments);
  const { regenerateRoutePartially } = useRouteRegeneration();

  const dragStateRef = useRef<DragState>({
    active: false,
    viaIndex: null,
    isStart: false,
  });

  const snapToNearestRoadOrTrail = useCallback(
    (coordinate: Coordinate): Coordinate => {
      const map = mapRef.current?.getMap();
      if (!map) return coordinate;

      const targetPoint = map.project([coordinate.lng, coordinate.lat]);
      const searchRadii = [8, 16, 32, 64];
      let best: SegmentMatch | null = null;

      for (const radius of searchRadii) {
        const bbox: [[number, number], [number, number]] = [
          [targetPoint.x - radius, targetPoint.y - radius],
          [targetPoint.x + radius, targetPoint.y + radius],
        ];
        const features = map
          .queryRenderedFeatures(bbox)
          .filter((feature) => feature.geometry.type !== 'Point' && isRoadOrTrailFeature(feature));

        for (const feature of features) {
          const geometry = feature.geometry;
          if (geometry.type === 'LineString') {
            const coords = geometry.coordinates as number[][];
            for (let i = 0; i < coords.length - 1; i += 1) {
              const start = map.project(coords[i] as [number, number]);
              const end = map.project(coords[i + 1] as [number, number]);
              const candidate = getNearestPointOnSegment(targetPoint, start, end);
              if (!best || candidate.distanceSq < best.distanceSq) {
                best = candidate;
              }
            }
          } else if (geometry.type === 'MultiLineString') {
            const lines = geometry.coordinates as number[][][];
            for (const line of lines) {
              for (let i = 0; i < line.length - 1; i += 1) {
                const start = map.project(line[i] as [number, number]);
                const end = map.project(line[i + 1] as [number, number]);
                const candidate = getNearestPointOnSegment(targetPoint, start, end);
                if (!best || candidate.distanceSq < best.distanceSq) {
                  best = candidate;
                }
              }
            }
          }
        }

        const hit = best;
        if (hit !== null && hit.distanceSq <= radius * radius) {
          break;
        }
      }

      if (!best) return coordinate;
      const snapped = map.unproject([best.point.x, best.point.y]);
      return { lng: snapped.lng, lat: snapped.lat };
    },
    [mapRef]
  );

  // Get the last point of the current route (for ordering)
  const lastRoutePoint = useMemo<Coordinate | null>(() => {
    if (routeGeometry && routeGeometry.length > 0) {
      const last = routeGeometry[routeGeometry.length - 1];
      return { lat: last[1], lng: last[0] };
    }
    if (constraints.viaPoints.length > 0) {
      return constraints.viaPoints[constraints.viaPoints.length - 1];
    }
    return constraints.start ?? null;
  }, [routeGeometry, constraints.viaPoints, constraints.start]);

  // Find the closest point on the route to a given coordinate
  const getNearestPointOnRoute = useCallback(
    (coordinate: Coordinate): Coordinate => {
      const map = mapRef.current?.getMap();
      if (!map || !routeGeometry || routeGeometry.length < 2) return coordinate;

      const target = map.project([coordinate.lng, coordinate.lat]);
      let closestDistance = Number.POSITIVE_INFINITY;
      let closestPoint: Coordinate = coordinate;

      for (let i = 0; i < routeGeometry.length - 1; i++) {
        const start = map.project(routeGeometry[i] as [number, number]);
        const end = map.project(routeGeometry[i + 1] as [number, number]);

        const abx = end.x - start.x;
        const aby = end.y - start.y;
        const abLenSq = abx * abx + aby * aby;
        if (abLenSq === 0) continue;

        const apx = target.x - start.x;
        const apy = target.y - start.y;
        const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / abLenSq));

        const closestX = start.x + abx * t;
        const closestY = start.y + aby * t;
        const dx = target.x - closestX;
        const dy = target.y - closestY;
        const distanceSq = dx * dx + dy * dy;

        if (distanceSq < closestDistance) {
          closestDistance = distanceSq;
          const closest = map.unproject([closestX, closestY]);
          closestPoint = { lat: closest.lat, lng: closest.lng };
        }
      }

      return closestPoint;
    },
    [mapRef, routeGeometry]
  );

  // Get index along route for a coordinate
  const getRouteIndexForCoord = useCallback(
    (coordinate: Coordinate): number => {
      const map = mapRef.current?.getMap();
      if (!map || !routeGeometry || routeGeometry.length < 2) return 0;

      const target = map.project([coordinate.lng, coordinate.lat]);
      let closestDistance = Number.POSITIVE_INFINITY;
      let closestIndex = 0;

      for (let i = 0; i < routeGeometry.length - 1; i++) {
        const start = map.project(routeGeometry[i] as [number, number]);
        const end = map.project(routeGeometry[i + 1] as [number, number]);

        const abx = end.x - start.x;
        const aby = end.y - start.y;
        const abLenSq = abx * abx + aby * aby;
        if (abLenSq === 0) continue;

        const apx = target.x - start.x;
        const apy = target.y - start.y;
        const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / abLenSq));

        const closestX = start.x + abx * t;
        const closestY = start.y + aby * t;
        const dx = target.x - closestX;
        const dy = target.y - closestY;
        const distanceSq = dx * dx + dy * dy;

        if (distanceSq < closestDistance) {
          closestDistance = distanceSq;
          closestIndex = i + t;
        }
      }

      return closestIndex;
    },
    [mapRef, routeGeometry]
  );

  // Get the fractional position (0-1) along the route for a coordinate
  const getRouteProgress = useCallback(
    (coordinate: Coordinate): number => {
      if (!routeGeometry || routeGeometry.length < 2) return 0;
      
      const routeIndex = getRouteIndexForCoord(coordinate);
      return routeIndex / (routeGeometry.length - 1);
    },
    [routeGeometry, getRouteIndexForCoord]
  );

  // Calculate which via point index to insert a new waypoint at, based on route position
  const getInsertionIndex = useCallback(
    (coordinate: Coordinate): number => {
      if (!routeGeometry || routeGeometry.length < 2) return 0;
      
      const viaPoints = constraints.viaPoints;
      if (viaPoints.length === 0) return 0;
      
      // Get the progress (0-1) of the new coordinate along the route
      const newProgress = getRouteProgress(coordinate);
      
      // Calculate progress for each existing via point
      const viaProgresses = viaPoints.map(vp => getRouteProgress(vp));
      
      // Find where to insert based on progress
      for (let i = 0; i < viaProgresses.length; i++) {
        if (newProgress < viaProgresses[i]) {
          return i;
        }
      }
      
      // Insert at the end if after all existing via points
      return viaPoints.length;
    },
    [routeGeometry, constraints.viaPoints, getRouteProgress]
  );

  // Check if a coordinate is near the route (within threshold pixels)
  const isNearRoute = useCallback(
    (coordinate: Coordinate, thresholdPx: number = 15): boolean => {
      const map = mapRef.current?.getMap();
      if (!map || !routeGeometry || routeGeometry.length < 2) return false;

      const nearestPoint = getNearestPointOnRoute(coordinate);
      const mousePoint = map.project([coordinate.lng, coordinate.lat]);
      const nearestMapPoint = map.project([nearestPoint.lng, nearestPoint.lat]);
      
      const distance = Math.sqrt(
        Math.pow(mousePoint.x - nearestMapPoint.x, 2) +
        Math.pow(mousePoint.y - nearestMapPoint.y, 2)
      );

      return distance <= thresholdPx;
    },
    [mapRef, routeGeometry, getNearestPointOnRoute]
  );

  // Handle clicking on the map to add a waypoint
  const handleMapClick = useCallback(
    async (event: MapLayerMouseEvent) => {
      const { lng, lat } = event.lngLat;
      const clickedPoint: Coordinate = { lng, lat };
      const snappedPoint = snapToNearestRoadOrTrail(clickedPoint);

      const isStartingFresh =
        !constraints.start &&
        !routeGeometry &&
        constraints.viaPoints.length === 0 &&
        manualSegments.length === 0;
      if (isStartingFresh) {
        setConstraintStart(snappedPoint);
        setConstraintEnd(undefined);
        return;
      }

      // Add via point and route only the new segment
      const newViaIndex = constraints.viaPoints.length;
      addViaPoint(snappedPoint);
      regenerateRoutePartially({ type: 'insert', viaIndex: newViaIndex });
    },
    [
      addViaPoint,
      routeGeometry,
      constraints.start,
      constraints.viaPoints.length,
      manualSegments.length,
      setConstraintStart,
      setConstraintEnd,
      regenerateRoutePartially,
      snapToNearestRoadOrTrail,
    ]
  );

  // Handle start marker drag
  const handleStartDrag = useCallback(
    (newPosition: Coordinate) => {
      setConstraintStart(newPosition);
    },
    [setConstraintStart]
  );

  // Start dragging
  const startDrag = useCallback(
    (options: { isStart?: boolean; viaIndex?: number }) => {
      dragStateRef.current = {
        active: true,
        isStart: options.isStart ?? false,
        viaIndex: options.viaIndex ?? null,
      };
    },
    []
  );

  // End dragging
  const endDrag = useCallback(() => {
    dragStateRef.current = {
      active: false,
      isStart: false,
      viaIndex: null,
    };
  }, []);

  // Check if currently dragging
  const isDragging = useCallback(() => {
    return dragStateRef.current.active;
  }, []);

  return {
    handleMapClick,
    handleStartDrag,
    getNearestPointOnRoute,
    getRouteIndexForCoord,
    getRouteProgress,
    getInsertionIndex,
    isNearRoute,
    startDrag,
    endDrag,
    isDragging,
    lastRoutePoint,
    snapToNearestRoadOrTrail,
  };
}
