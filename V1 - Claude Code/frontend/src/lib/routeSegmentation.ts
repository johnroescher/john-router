import type { Coordinate } from '@/types';

type ManualSurfaceBreakdown = {
  pavement: number;
  gravel: number;
  dirt: number;
  singletrack: number;
  unknown: number;
};

export type ManualRouteSegment = {
  coordinates: number[][];
  distanceMeters: number;
  elevationGain: number;
  durationSeconds: number;
  surfaceBreakdown: ManualSurfaceBreakdown;
};

export const buildSegmentsFromGeometry = (
  geometry: number[][],
  points: Coordinate[]
): ManualRouteSegment[] | null => {
  if (!geometry || geometry.length < 2 || points.length < 2) return null;

  const indices: number[] = [];
  let searchStart = 0;

  for (let i = 0; i < points.length; i++) {
    const point = points[i];
    let closestIndex = -1;
    let closestDistance = Number.POSITIVE_INFINITY;

    for (let idx = searchStart; idx < geometry.length; idx++) {
      const [lng, lat] = geometry[idx];
      const dx = point.lng - lng;
      const dy = point.lat - lat;
      const dist = dx * dx + dy * dy;
      if (dist < closestDistance) {
        closestDistance = dist;
        closestIndex = idx;
      }
    }

    if (closestIndex === -1) return null;

    if (i > 0 && closestIndex <= indices[i - 1]) {
      const nextIndex = indices[i - 1] + 1;
      if (nextIndex >= geometry.length) {
        return null;
      }
      closestIndex = nextIndex;
    }

    indices.push(closestIndex);
    searchStart = closestIndex + 1;
  }

  const segments: ManualRouteSegment[] = [];
  for (let i = 0; i < indices.length - 1; i++) {
    const startIdx = indices[i];
    let endIdx = indices[i + 1];
    if (endIdx <= startIdx && startIdx + 1 < geometry.length) {
      endIdx = startIdx + 1;
    }
    if (endIdx <= startIdx) return null;
    const slice = geometry.slice(startIdx, endIdx + 1);
    if (slice.length < 2) return null;
    segments.push({
      coordinates: slice,
      distanceMeters: 0,
      elevationGain: 0,
      durationSeconds: 0,
      surfaceBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
    });
  }

  return segments;
};
