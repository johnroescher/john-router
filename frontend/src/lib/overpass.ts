import type { Coordinate, SurfaceBreakdown } from '@/types';
import { coverageFromBreakdown, type SurfaceCategory, type SurfaceInferenceCandidate } from '@/lib/surfaceInference';

type OverpassElement = {
  type: 'way';
  id: number;
  tags?: Record<string, string>;
  center?: { lat: number; lon: number };
};

type OverpassResponse = {
  elements: OverpassElement[];
};

const overpassCache = new Map<string, { expiresAt: number; result: SurfaceInferenceCandidate }>();
const cacheTtlMs = 5 * 60 * 1000;

const toRadians = (value: number) => (value * Math.PI) / 180;

const haversineDistanceMeters = (a: Coordinate, b: Coordinate) => {
  const earthRadiusMeters = 6371000;
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const deltaLat = toRadians(b.lat - a.lat);
  const deltaLng = toRadians(b.lng - a.lng);
  const sinLat = Math.sin(deltaLat / 2);
  const sinLng = Math.sin(deltaLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(sinLat * sinLat + Math.cos(lat1) * Math.cos(lat2) * sinLng * sinLng), Math.sqrt(1 - sinLat * sinLat - Math.cos(lat1) * Math.cos(lat2) * sinLng * sinLng));
  return earthRadiusMeters * c;
};

const PAVED_SURFACES = new Set(['paved', 'asphalt', 'concrete', 'concrete:lanes', 'concrete:plates', 'paving_stones', 'sett', 'cobblestone', 'cobblestone:flattened', 'chipseal']);
const GRAVEL_SURFACES = new Set(['gravel', 'fine_gravel', 'pebblestone', 'compacted', 'gravelled']);
const DIRT_SURFACES = new Set(['dirt', 'earth', 'ground', 'mud', 'sand', 'grass', 'soil', 'wood', 'woodchips', 'unpaved']);
const TRAIL_CLASSES = new Set(['path', 'footway', 'track', 'trail', 'bridleway', 'cycleway', 'steps', 'mountainbike']);
const ROAD_CLASSES = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'residential', 'service', 'unclassified', 'living_street', 'road', 'street']);
const TRACKTYPE_GRAVEL = new Set(['grade1', 'grade2']);
const TRACKTYPE_DIRT = new Set(['grade3', 'grade4', 'grade5']);

const asLowerString = (value: unknown) => (value === undefined || value === null ? '' : String(value).toLowerCase());

const classifyOverpassTags = (tags: Record<string, string> | undefined): SurfaceCategory | null => {
  if (!tags) return null;
  const surface = asLowerString(tags.surface);
  const tracktype = asLowerString(tags.tracktype);
  const highway = asLowerString(tags.highway || tags.cycleway || tags.footway);

  if (surface) {
    if (PAVED_SURFACES.has(surface) || surface.includes('paved')) return 'pavement';
    if (GRAVEL_SURFACES.has(surface)) return 'gravel';
    if (DIRT_SURFACES.has(surface)) return 'dirt';
  }

  if (tracktype) {
    if (TRACKTYPE_GRAVEL.has(tracktype)) return 'gravel';
    if (TRACKTYPE_DIRT.has(tracktype)) return 'dirt';
  }

  if (TRAIL_CLASSES.has(highway)) return highway === 'track' ? 'dirt' : 'singletrack';
  if (ROAD_CLASSES.has(highway)) return 'pavement';

  return null;
};

const buildCacheKey = (points: Coordinate[], radiusMeters: number) => {
  const lngs = points.map((p) => p.lng);
  const lats = points.map((p) => p.lat);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const round = (value: number) => Math.round(value * 1000) / 1000;
  return `${round(minLng)}:${round(minLat)}:${round(maxLng)}:${round(maxLat)}:${radiusMeters}`;
};

const buildOverpassQuery = (points: Coordinate[], radiusMeters: number) => {
  const pointClauses = points.map((point) => `way(around:${radiusMeters},${point.lat},${point.lng})["highway"];`).join('');
  return `[out:json][timeout:25];(${pointClauses});out tags center;`;
};

const fetchOverpassWays = async (points: Coordinate[], radiusMeters: number, signal?: AbortSignal) => {
  if (points.length === 0) return [];
  const query = buildOverpassQuery(points, radiusMeters);
  const response = await fetch('https://overpass-api.de/api/interpreter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ data: query }),
    signal,
  });
  if (!response.ok) {
    throw new Error(`Overpass error: ${response.status}`);
  }
  const data = (await response.json()) as OverpassResponse;
  return data.elements || [];
};

export const inferSurfaceFromOverpass = async (params: {
  points: Coordinate[];
  radiusMeters?: number;
  signal?: AbortSignal;
}) => {
  const { points, radiusMeters = 35, signal } = params;
  if (!points.length) return null;

  const cacheKey = buildCacheKey(points, radiusMeters);
  const cached = overpassCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.result;
  }

  const chunkSize = 20;
  const totals: Record<SurfaceCategory, number> = {
    pavement: 0,
    gravel: 0,
    dirt: 0,
    singletrack: 0,
    unknown: 0,
  };
  let missing = 0;

  for (let i = 0; i < points.length; i += chunkSize) {
    const chunk = points.slice(i, i + chunkSize);
    const ways = await fetchOverpassWays(chunk, radiusMeters, signal);
    for (const point of chunk) {
      let nearest: OverpassElement | null = null;
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const way of ways) {
        if (!way.center) continue;
        const distance = haversineDistanceMeters(point, { lat: way.center.lat, lng: way.center.lon });
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearest = way;
        }
      }
      if (!nearest || nearestDistance > radiusMeters) {
        missing += 1;
        continue;
      }
      const category = classifyOverpassTags(nearest.tags);
      if (!category) {
        missing += 1;
        continue;
      }
      totals[category] += 1;
    }
  }

  const sampleCount = points.length;
  const coverage = 1 - missing / sampleCount;
  if (coverage < 0.25) return null;

  const surfaceBreakdown: SurfaceBreakdown = {
    pavement: (totals.pavement / sampleCount) * 100,
    gravel: (totals.gravel / sampleCount) * 100,
    dirt: (totals.dirt / sampleCount) * 100,
    singletrack: (totals.singletrack / sampleCount) * 100,
    unknown: (missing / sampleCount) * 100,
  };

  const result: SurfaceInferenceCandidate = {
    surfaceBreakdown,
    coverage: coverageFromBreakdown(surfaceBreakdown),
    source: 'overpass',
  };

  overpassCache.set(cacheKey, {
    expiresAt: Date.now() + cacheTtlMs,
    result,
  });

  return result;
};
