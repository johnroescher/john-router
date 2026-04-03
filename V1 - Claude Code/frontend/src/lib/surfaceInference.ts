import maplibregl from 'maplibre-gl';
import type { Coordinate, SurfaceBreakdown } from '@/types';

export type SurfaceCategory = keyof SurfaceBreakdown;
export type SurfaceInferenceSource = 'map' | 'overpass' | 'backend';

export type SurfaceInferenceCandidate = {
  surfaceBreakdown: SurfaceBreakdown;
  coverage: number;
  source: SurfaceInferenceSource;
};

export const SURFACE_SAMPLE_SOURCE = 'surface-sample';
export const SURFACE_SAMPLE_LAYERS = {
  trail: 'surface-sample-trail',
  road: 'surface-sample-road',
  landcover: 'surface-sample-landcover',
  landuse: 'surface-sample-landuse',
  park: 'surface-sample-park',
} as const;

const toRadians = (value: number) => (value * Math.PI) / 180;

const haversineDistanceMeters = (start: number[], end: number[]) => {
  const earthRadiusMeters = 6371000;
  const lat1 = toRadians(start[1]);
  const lat2 = toRadians(end[1]);
  const deltaLat = toRadians(end[1] - start[1]);
  const deltaLng = toRadians(end[0] - start[0]);
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return earthRadiusMeters * c;
};

export const buildRouteDistanceData = (geometry: number[][]) => {
  if (!geometry || geometry.length < 2) return null;
  const cumulative: number[] = [0];
  let total = 0;
  for (let i = 1; i < geometry.length; i += 1) {
    total += haversineDistanceMeters(geometry[i - 1], geometry[i]);
    cumulative.push(total);
  }
  return { cumulative, total };
};

export const getCoordinateAtDistance = (distanceMeters: number, geometry: number[][], cumulative: number[]) => {
  if (distanceMeters <= 0) return geometry[0];
  if (distanceMeters >= cumulative[cumulative.length - 1]) return geometry[geometry.length - 1];
  let low = 0;
  let high = cumulative.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (cumulative[mid] < distanceMeters) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  const upperIndex = Math.min(low, cumulative.length - 1);
  const lowerIndex = Math.max(upperIndex - 1, 0);
  const start = geometry[lowerIndex];
  const end = geometry[upperIndex];
  const segmentDistance = Math.max(1, cumulative[upperIndex] - cumulative[lowerIndex]);
  const t = Math.max(0, Math.min(1, (distanceMeters - cumulative[lowerIndex]) / segmentDistance));
  return [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t];
};

const PAVED_SURFACES = new Set([
  'paved',
  'asphalt',
  'concrete',
  'concrete:lanes',
  'concrete:plates',
  'paving_stones',
  'sett',
  'cobblestone',
  'cobblestone:flattened',
  'chipseal',
]);

const GRAVEL_SURFACES = new Set([
  'gravel',
  'fine_gravel',
  'pebblestone',
  'compacted',
  'gravelled',
]);

const DIRT_SURFACES = new Set([
  'dirt',
  'earth',
  'ground',
  'mud',
  'sand',
  'grass',
  'soil',
  'wood',
  'woodchips',
  'unpaved',
]);

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

const LANDCOVER_SINGLETRACK = new Set(['wood', 'forest', 'scrub']);
const LANDCOVER_DIRT = new Set(['grass', 'wetland', 'sand', 'beach', 'glacier', 'snow', 'ice', 'bare_rock']);
const LANDUSE_DIRT = new Set(['park', 'forest', 'meadow', 'grass', 'recreation_ground', 'cemetery', 'pitch', 'golf_course', 'farmland']);
const PARK_DIRT = new Set(['nature_reserve', 'national_park']);

const asLowerString = (value: unknown) => (value === undefined || value === null ? '' : String(value).toLowerCase());

export const classifySurfaceFromFeature = (feature: maplibregl.MapGeoJSONFeature): SurfaceCategory | null => {
  const props = feature.properties || {};
  const layerId = asLowerString(feature.layer?.id);
  const sourceLayer = asLowerString((feature.layer as { 'source-layer'?: string } | undefined)?.['source-layer']);
  const surfaceValue = asLowerString(props.surface || props.surface_type || props.surfaceType || props.surface_type_1);
  const classValue = asLowerString(props.class || props.subclass || props.type || props.highway || props.kind);

  if (layerId === SURFACE_SAMPLE_LAYERS.trail) return 'singletrack';
  if (layerId === SURFACE_SAMPLE_LAYERS.road) return 'pavement';
  if (layerId === SURFACE_SAMPLE_LAYERS.landcover) {
    if (LANDCOVER_SINGLETRACK.has(classValue)) return 'singletrack';
    if (LANDCOVER_DIRT.has(classValue)) return 'dirt';
  }
  if (layerId === SURFACE_SAMPLE_LAYERS.landuse) {
    if (LANDUSE_DIRT.has(classValue)) return 'dirt';
  }
  if (layerId === SURFACE_SAMPLE_LAYERS.park) {
    if (PARK_DIRT.has(classValue)) return 'dirt';
  }

  if (surfaceValue) {
    if (PAVED_SURFACES.has(surfaceValue) || surfaceValue.includes('paved')) return 'pavement';
    if (GRAVEL_SURFACES.has(surfaceValue)) return 'gravel';
    if (DIRT_SURFACES.has(surfaceValue)) return 'dirt';
  }

  if (TRAIL_CLASSES.has(classValue) || layerId.includes('path') || layerId.includes('trail')) {
    return 'singletrack';
  }

  if (classValue.includes('track')) return 'dirt';

  if (ROAD_CLASSES.has(classValue) || layerId.includes('road') || layerId.includes('street') || sourceLayer.includes('transport')) {
    return 'pavement';
  }

  return null;
};

export const coverageFromBreakdown = (surfaceBreakdown: SurfaceBreakdown) => {
  return Math.max(0, Math.min(1, 1 - surfaceBreakdown.unknown / 100));
};

export const mergeSurfaceCandidates = (candidates: SurfaceInferenceCandidate[]) => {
  const usable = candidates.filter((candidate) => candidate.coverage > 0.05);
  if (usable.length === 0) return null;
  const sorted = [...usable].sort((a, b) => b.coverage - a.coverage);
  if (sorted.length === 1) return sorted[0];

  const top = sorted[0];
  const runnerUp = sorted[1];
  if (top.coverage - runnerUp.coverage >= 0.2) return top;

  const weights = sorted.map((candidate) => Math.pow(candidate.coverage, 2));
  const weightSum = weights.reduce((sum, w) => sum + w, 0) || 1;
  const merged: SurfaceBreakdown = {
    pavement: 0,
    gravel: 0,
    dirt: 0,
    singletrack: 0,
    unknown: 0,
  };

  sorted.forEach((candidate, index) => {
    const weight = weights[index] / weightSum;
    merged.pavement += candidate.surfaceBreakdown.pavement * weight;
    merged.gravel += candidate.surfaceBreakdown.gravel * weight;
    merged.dirt += candidate.surfaceBreakdown.dirt * weight;
    merged.singletrack += candidate.surfaceBreakdown.singletrack * weight;
    merged.unknown += candidate.surfaceBreakdown.unknown * weight;
  });

  const knownTotal = merged.pavement + merged.gravel + merged.dirt + merged.singletrack;
  if (knownTotal > 0 && knownTotal <= 100) {
    merged.unknown = Math.max(0, 100 - knownTotal);
  }

  return {
    surfaceBreakdown: merged,
    coverage: coverageFromBreakdown(merged),
    source: top.source,
  };
};

export const inferSurfaceFromMap = (params: {
  map: maplibregl.Map;
  geometry: number[][];
  routeDistanceData: { cumulative: number[]; total: number };
  bufferPx?: number;
  sampleCountMax?: number;
}): SurfaceInferenceCandidate | null => {
  const { map, geometry, routeDistanceData, bufferPx = 6, sampleCountMax = 400 } = params;
  if (!geometry || geometry.length < 2 || routeDistanceData.total <= 0) return null;

  const totalDistance = routeDistanceData.total;
  const sampleCount = Math.min(sampleCountMax, Math.max(30, Math.ceil(totalDistance / 40)));
  const stepDistance = totalDistance / sampleCount;
  const totals: Record<SurfaceCategory, number> = {
    pavement: 0,
    gravel: 0,
    dirt: 0,
    singletrack: 0,
    unknown: 0,
  };
  let missingSamples = 0;

  for (let i = 0; i < sampleCount; i += 1) {
    const distance = stepDistance * (i + 0.5);
    const coordinate = getCoordinateAtDistance(distance, geometry, routeDistanceData.cumulative);
    const point = map.project(coordinate as [number, number]);
    const bbox: [[number, number], [number, number]] = [
      [point.x - bufferPx, point.y - bufferPx],
      [point.x + bufferPx, point.y + bufferPx],
    ];
    const features = map.queryRenderedFeatures(bbox, {
      layers: Object.values(SURFACE_SAMPLE_LAYERS),
    });
    let category: SurfaceCategory | null = null;
    for (const feature of features) {
      category = classifySurfaceFromFeature(feature);
      if (category) break;
    }
    if (!category) {
      missingSamples += 1;
      continue;
    }
    totals[category] += stepDistance;
  }

  const coverage = 1 - missingSamples / sampleCount;
  if (coverage < 0.15) return null;

  const knownDistance = totals.pavement + totals.gravel + totals.dirt + totals.singletrack;
  const unknownDistance = Math.max(0, totalDistance - knownDistance);
  const surfaceBreakdown: SurfaceBreakdown = {
    pavement: (totals.pavement / totalDistance) * 100,
    gravel: (totals.gravel / totalDistance) * 100,
    dirt: (totals.dirt / totalDistance) * 100,
    singletrack: (totals.singletrack / totalDistance) * 100,
    unknown: (unknownDistance / totalDistance) * 100,
  };

  return {
    surfaceBreakdown,
    coverage,
    source: 'map',
  };
};

export const buildSamplePoints = (geometry: number[][], routeDistanceData: { cumulative: number[]; total: number }, count: number) => {
  if (!geometry || geometry.length < 2 || routeDistanceData.total <= 0) return [];
  const points: Coordinate[] = [];
  const stepDistance = routeDistanceData.total / count;
  for (let i = 0; i < count; i += 1) {
    const distance = stepDistance * (i + 0.5);
    const coordinate = getCoordinateAtDistance(distance, geometry, routeDistanceData.cumulative);
    points.push({ lng: coordinate[0], lat: coordinate[1] });
  }
  return points;
};
