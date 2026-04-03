/**
 * Surface Enrichment Service
 * 
 * Enriches routes with accurate segment-level surface data from OpenStreetMap.
 * Queries Overpass API to get way data along the route and maps surface types
 * to specific route segments.
 */
import type { Coordinate, SurfaceBreakdown, SurfaceSegment, SegmentedSurfaceData, SurfaceType } from '@/types';

// OSM way with surface data
interface OSMWay {
  id: number;
  tags: Record<string, string>;
  geometry?: Array<{ lat: number; lon: number }>;
  nodes?: number[];
}

interface OverpassWayResponse {
  elements: Array<{
    type: 'way';
    id: number;
    tags?: Record<string, string>;
    geometry?: Array<{ lat: number; lon: number }>;
    nodes?: number[];
  }>;
}

class OverpassError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'OverpassError';
    this.status = status;
  }
}

type CachedSurface = {
  data: SegmentedSurfaceData;
  cachedAt: number;
};

const SURFACE_CACHE_TTL_MS = 10 * 60 * 1000;
const surfaceCache = new Map<string, CachedSurface>();

// Surface classification from OSM tags
const PAVED_SURFACES = new Set([
  'paved', 'asphalt', 'concrete', 'concrete:lanes', 'concrete:plates',
  'paving_stones', 'sett', 'cobblestone', 'cobblestone:flattened', 'chipseal',
  'metal', 'rubber',
]);

const GRAVEL_SURFACES = new Set([
  'gravel', 'fine_gravel', 'pebblestone', 'compacted', 'crushed_limestone',
]);

const DIRT_SURFACES = new Set([
  'dirt', 'earth', 'ground', 'mud', 'sand', 'grass', 'soil', 'clay',
  'wood', 'woodchips', 'unpaved',
]);

// Highway types that are almost always paved (high confidence)
const PAVED_HIGHWAY_TYPES = new Set([
  'motorway', 'trunk', 'primary', 'secondary',
  'motorway_link', 'trunk_link', 'primary_link', 'secondary_link',
]);

// Highway types that vary widely; avoid assuming paved without explicit tags
const VARIABLE_PAVED_HIGHWAY_TYPES = new Set([
  'tertiary', 'tertiary_link',
  'residential', 'living_street', 'service', 'unclassified',
]);

// Highway types that are typically trails/singletrack
const TRAIL_HIGHWAY_TYPES = new Set([
  'path', 'footway', 'bridleway', 'steps',
]);

// Highway types that need surface tag to determine type
const VARIABLE_HIGHWAY_TYPES = new Set([
  'track', 'cycleway',
]);

// Track grade to surface mapping
const TRACKTYPE_SURFACES: Record<string, SurfaceType> = {
  'grade1': 'gravel',  // Solid, usually paved or heavily compacted
  'grade2': 'gravel',  // Gravel/compacted
  'grade3': 'dirt',    // Soft surface
  'grade4': 'dirt',    // Very soft surface
  'grade5': 'dirt',    // Very soft, often grass
};

function hasExplicitSurfaceTags(tags: Record<string, string>): boolean {
  return Boolean(tags.surface || tags.tracktype || tags['mtb:scale']);
}

/**
 * Classify surface type from OSM way tags
 */
export function classifyWaySurface(tags: Record<string, string>): { surfaceType: SurfaceType; confidence: number } {
  const surface = tags.surface?.toLowerCase();
  const highway = tags.highway?.toLowerCase();
  const tracktype = tags.tracktype?.toLowerCase();
  const mtbScale = tags['mtb:scale'];
  
  // Explicit surface tag is most reliable
  if (surface) {
    if (PAVED_SURFACES.has(surface)) {
      return { surfaceType: 'pavement', confidence: 0.95 };
    }
    if (GRAVEL_SURFACES.has(surface)) {
      return { surfaceType: 'gravel', confidence: 0.95 };
    }
    if (DIRT_SURFACES.has(surface)) {
      return { surfaceType: 'dirt', confidence: 0.95 };
    }
    // Catch-all for unknown surface values
    if (surface.includes('paved')) {
      return { surfaceType: 'pavement', confidence: 0.8 };
    }
    if (surface.includes('gravel') || surface.includes('compacted')) {
      return { surfaceType: 'gravel', confidence: 0.8 };
    }
  }
  
  // Tracktype is second-best indicator
  if (tracktype && TRACKTYPE_SURFACES[tracktype]) {
    return { surfaceType: TRACKTYPE_SURFACES[tracktype], confidence: 0.85 };
  }
  
  // MTB scale indicates singletrack
  if (mtbScale) {
    return { surfaceType: 'singletrack', confidence: 0.9 };
  }
  
  // Infer from highway type (conservative for variable classes)
  if (highway) {
    // Major roads (motorway, trunk, primary, secondary) are almost always paved
    if (highway === 'motorway' || highway === 'trunk' || highway === 'primary' || highway === 'secondary') {
      return { surfaceType: 'pavement', confidence: 0.9 };
    }
    // Other paved highway types
    if (PAVED_HIGHWAY_TYPES.has(highway)) {
      return { surfaceType: 'pavement', confidence: 0.8 };
    }
    if (VARIABLE_PAVED_HIGHWAY_TYPES.has(highway)) {
      return { surfaceType: 'unknown', confidence: 0.35 };
    }
    if (TRAIL_HIGHWAY_TYPES.has(highway)) {
      return { surfaceType: 'singletrack', confidence: 0.75 };
    }
    if (highway === 'track') {
      // Tracks without surface/tracktype are usually dirt
      return { surfaceType: 'dirt', confidence: 0.7 };
    }
    if (highway === 'cycleway') {
      // Cycleways without surface tag vary (paved vs. gravel)
      return { surfaceType: 'unknown', confidence: 0.4 };
    }
  }
  
  return { surfaceType: 'unknown', confidence: 0.3 };
}

/**
 * Calculate haversine distance between two points in meters
 */
function haversineDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000; // Earth radius in meters
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function buildGeometryCacheKey(geometry: number[][]): string {
  if (!geometry || geometry.length === 0) return 'empty';
  const totalPoints = geometry.length;
  const step = Math.max(1, Math.floor(totalPoints / 50));
  const sampled = [];
  for (let i = 0; i < totalPoints; i += step) {
    const [lon, lat] = geometry[i];
    sampled.push(`${lat.toFixed(5)},${lon.toFixed(5)}`);
  }
  const [firstLon, firstLat] = geometry[0];
  const [lastLon, lastLat] = geometry[totalPoints - 1];
  return `${totalPoints}:${firstLat.toFixed(5)},${firstLon.toFixed(5)}:${lastLat.toFixed(5)},${lastLon.toFixed(5)}:${sampled.join('|')}`;
}

/**
 * Calculate cumulative distances along route geometry
 */
function calculateCumulativeDistances(geometry: number[][]): number[] {
  const cumulative: number[] = [0];
  let total = 0;
  for (let i = 1; i < geometry.length; i++) {
    total += haversineDistance(
      geometry[i - 1][1], geometry[i - 1][0],
      geometry[i][1], geometry[i][0]
    );
    cumulative.push(total);
  }
  return cumulative;
}

function buildRoutePolyString(geometry: number[][], maxPoints: number): string {
  if (!geometry.length) return '';
  const totalPoints = geometry.length;
  const step = Math.max(1, Math.floor(totalPoints / maxPoints));
  const points: string[] = [];
  for (let i = 0; i < totalPoints; i += step) {
    const [lon, lat] = geometry[i];
    points.push(`${lat.toFixed(5)} ${lon.toFixed(5)}`);
  }
  const [lastLon, lastLat] = geometry[totalPoints - 1];
  const lastPoint = `${lastLat.toFixed(5)} ${lastLon.toFixed(5)}`;
  if (points[points.length - 1] !== lastPoint) {
    points.push(lastPoint);
  }
  return points.join(' ');
}

function buildOverpassPointQuery(geometry: number[][], sampleCount: number, bufferMeters: number): string {
  const totalPoints = geometry.length;
  const optimizedSampleCount = Math.min(sampleCount, Math.max(20, Math.floor(totalPoints / 10)));
  const step = Math.max(1, Math.floor(totalPoints / optimizedSampleCount));
  const sampledPoints: number[][] = [];

  for (let i = 0; i < totalPoints; i += step) {
    sampledPoints.push(geometry[i]);
  }
  if (sampledPoints.length === 0 || sampledPoints[sampledPoints.length - 1] !== geometry[totalPoints - 1]) {
    sampledPoints.push(geometry[totalPoints - 1]);
  }

  const wayQueries = sampledPoints.map(([lon, lat]) =>
    `way(around:${bufferMeters},${lat},${lon})["highway"];`
  ).join('');

  return `[out:json][timeout:15];(${wayQueries});out tags geom;`;
}

/**
 * Build Overpass query to get ways along a route
 * Optimized for speed: uses fewer samples and more efficient query structure
 */
function buildOverpassQuery(geometry: number[][], sampleCount: number = 50, bufferMeters: number = 50): string {
  // Optimize sample count based on route length for faster queries
  // For shorter routes, use fewer samples; for longer routes, cap at reasonable max
  const totalPoints = geometry.length;
  const optimizedSampleCount = Math.min(sampleCount, Math.max(25, Math.floor(totalPoints / 8)));

  // Build a buffered polyline query to reduce mismatches at intersections
  const polyString = buildRoutePolyString(geometry, optimizedSampleCount);
  const wayQuery = polyString
    ? `way(around:${bufferMeters},poly:"${polyString}")["highway"];`
    : '';

  // Use shorter timeout for faster failure/recovery (15s instead of 30s)
  return `[out:json][timeout:15];(${wayQuery});out tags geom;`;
}

/**
 * Fetch ways from Overpass API
 * Uses user's abort signal directly - relies on Overpass API's built-in timeout (15s in query)
 */
async function fetchOverpassWays(query: string, signal?: AbortSignal): Promise<OSMWay[]> {
  const endpoints = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
  ];
  
  let lastError: Error | null = null;
  
  for (let index = 0; index < endpoints.length; index += 1) {
    const endpoint = endpoints[index];
    const isLastEndpoint = index === endpoints.length - 1;
    try {
      // Check if already aborted
      if (signal?.aborted) {
        throw new Error('Request aborted');
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ data: query }),
        signal, // Use user's signal directly - no additional timeout needed
      });
      
      if (!response.ok) {
        throw new OverpassError(response.status, `Overpass error: ${response.status}`);
      }
      
      const data: OverpassWayResponse = await response.json();
      
      // Optimize: filter and map in one pass
      const ways: OSMWay[] = [];
      for (const el of data.elements) {
        if (el.type === 'way' && el.tags?.highway) {
          ways.push({
            id: el.id,
            tags: el.tags || {},
            geometry: el.geometry,
            nodes: el.nodes,
          });
        }
      }
      
      return ways;
    } catch (error) {
      lastError = error as Error;
      // Only log as warning if it's the last endpoint or if it's not an abort error
      if (error instanceof Error && error.name === 'AbortError') {
        // Abort errors are expected when requests are cancelled - don't log as warnings
        if (isLastEndpoint) {
          console.debug(`Overpass request aborted on ${endpoint}`);
        }
      } else {
        if (isLastEndpoint) {
          console.warn(`Overpass endpoints failed, last error from ${endpoint}:`, error);
        } else {
          console.debug(`Overpass endpoint ${endpoint} failed, trying next mirror.`, error);
        }
      }
    }
  }
  
  throw lastError || new Error('All Overpass endpoints failed');
}

/**
 * Find the closest way to a route point
 * Optimized for speed while maintaining accuracy:
 * 1. Prioritizes major roads for faster matching
 * 2. Samples geometry nodes instead of checking all (for long ways)
 * 3. Only checks line segments for major roads or when node distance is close
 */
function findClosestWay(
  lat: number,
  lon: number,
  ways: OSMWay[],
  maxDistance: number = 100
): { way: OSMWay; distanceMeters: number } | null {
  let closest: OSMWay | null = null;
  let minDist = maxDistance;

  for (const way of ways) {
    if (!way.geometry || way.geometry.length === 0) {
      continue;
    }

    // Optimize: For long ways, sample nodes instead of checking all
    const geometry = way.geometry;
    const nodeCount = geometry.length;
    const sampleStep = nodeCount > 10 ? Math.max(1, Math.floor(nodeCount / 5)) : 1;

    let bestNodeDist = Infinity;
    let bestNodeIndex = -1;

    // Sample nodes for faster processing
    for (let idx = 0; idx < nodeCount; idx += sampleStep) {
      const node = geometry[idx];
      const dist = haversineDistance(lat, lon, node.lat, node.lon);

      if (dist < bestNodeDist) {
        bestNodeDist = dist;
        bestNodeIndex = idx;
      }

      // Early exit if we find a very close match
      if (dist < 8) {
        bestNodeDist = dist;
        bestNodeIndex = idx;
        break;
      }
    }

    // Always check last node
    if (bestNodeIndex !== nodeCount - 1) {
      const lastNode = geometry[nodeCount - 1];
      const lastDist = haversineDistance(lat, lon, lastNode.lat, lastNode.lon);
      if (lastDist < bestNodeDist) {
        bestNodeDist = lastDist;
        bestNodeIndex = nodeCount - 1;
      }
    }

    // Check line segments around the closest node for better accuracy
    if (bestNodeDist < 40) {
      const checkRange = 2;
      const startIdx = Math.max(0, bestNodeIndex - checkRange);
      const endIdx = Math.min(nodeCount - 1, bestNodeIndex + checkRange);

      for (let i = startIdx; i < endIdx; i++) {
        if (i < nodeCount - 1) {
          const node1 = geometry[i];
          const node2 = geometry[i + 1];
          const segDist = pointToLineSegmentDistance(lat, lon, node1.lat, node1.lon, node2.lat, node2.lon);
          if (segDist < bestNodeDist) {
            bestNodeDist = segDist;
          }
        }
      }
    }

    // Update closest way tracking
    if (bestNodeDist < minDist) {
      minDist = bestNodeDist;
      closest = way;
    }
  }

  if (!closest) {
    return null;
  }

  return { way: closest, distanceMeters: minDist };
}

/**
 * Calculate distance from a point to a line segment (in lat/lon coordinates)
 * Uses perpendicular distance if point projects onto segment, otherwise distance to nearest endpoint
 * Returns distance in meters using haversine formula
 */
function pointToLineSegmentDistance(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number
): number {
  // Convert lat/lon differences to approximate meters for projection calculation
  const latDiff = x2 - x1;
  const lonDiff = y2 - y1;
  const pointLatDiff = px - x1;
  const pointLonDiff = py - y1;
  
  // Calculate projection parameter
  const dot = pointLatDiff * latDiff + pointLonDiff * lonDiff;
  const lenSq = latDiff * latDiff + lonDiff * lonDiff;
  let param = 0;
  
  if (lenSq > 0) {
    param = Math.max(0, Math.min(1, dot / lenSq));
  }
  
  // Find closest point on segment
  const closestLat = x1 + param * latDiff;
  const closestLon = y1 + param * lonDiff;
  
  // Use haversine distance to get accurate distance in meters
  return haversineDistance(px, py, closestLat, closestLon);
}

type RouteSegment = {
  lat1: number;
  lon1: number;
  lat2: number;
  lon2: number;
};

function buildRouteSegments(geometry: number[][]): RouteSegment[] {
  if (geometry.length < 2) return [];
  const maxSegments = 400;
  const step = Math.max(1, Math.floor((geometry.length - 1) / maxSegments));
  const segments: RouteSegment[] = [];
  for (let i = 0; i < geometry.length - 1; i += step) {
    const [lon1, lat1] = geometry[i];
    const [lon2, lat2] = geometry[Math.min(i + step, geometry.length - 1)];
    segments.push({ lat1, lon1, lat2, lon2 });
  }
  return segments;
}

function isWayWithinRouteBuffer(
  way: OSMWay,
  routeSegments: RouteSegment[],
  bufferMeters: number
): boolean {
  if (!way.geometry || way.geometry.length === 0) {
    return true;
  }
  const nodeCount = way.geometry.length;
  const sampleStep = nodeCount > 30 ? Math.max(1, Math.floor(nodeCount / 10)) : 1;
  for (let idx = 0; idx < nodeCount; idx += sampleStep) {
    const node = way.geometry[idx];
    for (const segment of routeSegments) {
      const dist = pointToLineSegmentDistance(node.lat, node.lon, segment.lat1, segment.lon1, segment.lat2, segment.lon2);
      if (dist <= bufferMeters) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Main enrichment function - enriches route with segment-level surface data
 */
export async function enrichRouteSurface(
  geometry: number[][],
  signal?: AbortSignal
): Promise<SegmentedSurfaceData> {
  if (!geometry || geometry.length < 2) {
    return {
      segments: [],
      knownDistanceMeters: 0,
      totalDistanceMeters: 0,
      dataQuality: 0,
      lastUpdated: new Date().toISOString(),
      enrichmentSource: null,
    };
  }
  
  // Cache lookup
  const cacheKey = buildGeometryCacheKey(geometry);
  const cached = surfaceCache.get(cacheKey);
  if (cached && Date.now() - cached.cachedAt < SURFACE_CACHE_TTL_MS) {
    return cached.data;
  }

  // Calculate cumulative distances
  const cumulativeDistances = calculateCumulativeDistances(geometry);
  const totalDistance = cumulativeDistances[cumulativeDistances.length - 1];
  
  // Build and execute Overpass query
  // Optimize: reduce sample count for faster queries while maintaining accuracy
  // Use adaptive sampling: fewer samples for shorter routes, more for longer routes
  const adaptiveSampleCount = totalDistance < 5000 
    ? 30  // Short routes: fewer samples
    : totalDistance < 20000
    ? 50  // Medium routes: moderate samples
    : 70; // Long routes: more samples but still capped
  const bufferMeters = totalDistance < 5000 ? 25 : totalDistance < 20000 ? 40 : 50;
  const query = buildOverpassQuery(geometry, adaptiveSampleCount, bufferMeters);
  let ways: OSMWay[] = [];
  try {
    ways = await fetchOverpassWays(query, signal);
  } catch (error) {
    if (error instanceof OverpassError && error.status === 400) {
      console.warn('[SurfaceEnrichment] Poly query failed (400). Retrying with point sampling.');
      const fallbackQuery = buildOverpassPointQuery(geometry, adaptiveSampleCount, bufferMeters);
      ways = await fetchOverpassWays(fallbackQuery, signal);
    } else {
      throw error;
    }
  }

  // Filter out ways that do not intersect the route corridor
  const routeSegments = buildRouteSegments(geometry);
  if (routeSegments.length > 0) {
    ways = ways.filter((way) => isWayWithinRouteBuffer(way, routeSegments, bufferMeters));
  }
  
  if (ways.length === 0) {
    console.warn('No OSM ways found along route');
    return {
      segments: [{
        startIndex: 0,
        endIndex: geometry.length - 1,
        startDistanceMeters: 0,
        endDistanceMeters: totalDistance,
        distanceMeters: totalDistance,
        surfaceType: 'unknown',
        confidence: 0,
        source: 'default',
      }],
      knownDistanceMeters: 0,
      totalDistanceMeters: totalDistance,
      dataQuality: 0,
      lastUpdated: new Date().toISOString(),
      enrichmentSource: 'overpass',
    };
  }
  
  // Assign surface type to each route segment
  const segments: SurfaceSegment[] = [];
  let currentSegment: SurfaceSegment | null = null;
  let knownDistance = 0;
  let confidenceSum = 0;
  let matchDistanceSum = 0;
  let segmentCount = 0;
  
  // Optimize sampling frequency for speed while maintaining accuracy
  // Use adaptive sampling: more frequent for shorter routes, less frequent for longer routes
  // This balances accuracy with performance to meet 700ms target
  const targetSampleDistance = totalDistance < 5000 
    ? 50   // Short routes: sample every 50m for accuracy
    : totalDistance < 20000
    ? 75   // Medium routes: sample every 75m
    : 100; // Long routes: sample every 100m for speed
  const avgPointSpacing = totalDistance / geometry.length;
  const sampleStep = Math.max(1, Math.floor(targetSampleDistance / avgPointSpacing));
  
  console.log('[SurfaceEnrichment] Processing route:', {
    totalPoints: geometry.length,
    totalDistance: (totalDistance / 1000).toFixed(1) + 'km',
    sampleStep,
    waysFound: ways.length,
  });
  
  for (let i = 0; i < geometry.length - 1; i += sampleStep) {
    const [lon, lat] = geometry[i];
    const closestResult = findClosestWay(lat, lon, ways, bufferMeters);
    const closestWay = closestResult?.way ?? null;
    
    let surfaceType: SurfaceType = 'unknown';
    let confidence = 0;
    let osmWayId: number | undefined;
    let matchDistanceMeters: number | undefined;
    
    if (closestWay) {
      const classification = classifyWaySurface(closestWay.tags);
      surfaceType = classification.surfaceType;
      confidence = classification.confidence;
      osmWayId = closestWay.id;
      matchDistanceMeters = closestResult?.distanceMeters;
      
      // Log when we find major roads to help debug
      if (i % (sampleStep * 10) === 0 && closestWay.tags?.highway) {
        const highway = closestWay.tags.highway;
        if (['motorway', 'trunk', 'primary', 'secondary'].includes(highway)) {
          console.debug(`[SurfaceEnrichment] Found ${highway} at point ${i}, classified as ${surfaceType} (confidence: ${confidence.toFixed(2)})`);
        }
      }
    } else {
      // Optimize: Skip expensive nearby ways check for most points
      // Only check every 5th sample point to reduce computation
      if (i % (sampleStep * 5) === 0) {
        // If no way found, check if any nearby ways exist (within 100m)
        // This helps catch cases where the closest way algorithm missed something
        const nearbyWays = ways.map((way) => {
          if (!way.geometry || way.geometry.length === 0) return false;
          // Optimize: only check first and last nodes for speed
          const firstNode = way.geometry[0];
          const lastNode = way.geometry[way.geometry.length - 1];
          const firstDist = haversineDistance(lat, lon, firstNode.lat, firstNode.lon);
          const lastDist = haversineDistance(lat, lon, lastNode.lat, lastNode.lon);
          const minDist = Math.min(firstDist, lastDist);
          return minDist <= bufferMeters ? { way, minDist } : false;
        }).filter(Boolean) as Array<{ way: OSMWay; minDist: number }>;
        
        // If we found nearby ways, try to classify from them (prioritize major roads)
        if (nearbyWays.length > 0) {
          // Prefer explicit surface tags, then nearest distance
          nearbyWays.sort((a, b) => {
            const aExplicit = hasExplicitSurfaceTags(a.way.tags);
            const bExplicit = hasExplicitSurfaceTags(b.way.tags);
            if (aExplicit !== bExplicit) return aExplicit ? -1 : 1;
            return a.minDist - b.minDist;
          });
          
          // Use the best matching way
          const bestMatch = nearbyWays[0];
          const classification = classifyWaySurface(bestMatch.way.tags);
          surfaceType = classification.surfaceType;
          confidence = Math.max(0.5, classification.confidence * 0.9); // Slightly lower confidence since it wasn't the closest
          osmWayId = bestMatch.way.id;
          matchDistanceMeters = bestMatch.minDist;
        }
      }
      
      if (i % (sampleStep * 20) === 0 && surfaceType === 'unknown') {
        // Log when we can't find ways (helps debug)
        console.debug(`[SurfaceEnrichment] No way found near point ${i} (${lat.toFixed(4)}, ${lon.toFixed(4)})`);
      }
    }
    
    // Determine segment end index
    const endIdx = Math.min(i + sampleStep, geometry.length - 1);
    const segmentStartDistance = cumulativeDistances[i];
    const segmentEndDistance = cumulativeDistances[endIdx];
    const segmentDistance = segmentEndDistance - segmentStartDistance;
    if (segmentDistance <= 0) {
      continue;
    }
    
    // Check if we should extend current segment or start a new one
    if (currentSegment && currentSegment.surfaceType === surfaceType) {
      // Extend current segment
      currentSegment.endIndex = endIdx;
      currentSegment.endDistanceMeters = segmentEndDistance;
      currentSegment.distanceMeters += segmentDistance;
      if (matchDistanceMeters !== undefined) {
        currentSegment.matchDistanceMeters = Math.min(
          currentSegment.matchDistanceMeters ?? matchDistanceMeters,
          matchDistanceMeters
        );
      }
    } else {
      // Save current segment and start new one
      if (currentSegment) {
        segments.push(currentSegment);
      }
      
      currentSegment = {
        startIndex: i,
        endIndex: endIdx,
        startDistanceMeters: segmentStartDistance,
        endDistanceMeters: segmentEndDistance,
        distanceMeters: segmentDistance,
        surfaceType,
        confidence,
        source: closestWay ? 'overpass' : 'default',
        osmWayId,
        matchDistanceMeters,
      };
    }
    
    if (surfaceType !== 'unknown') {
      knownDistance += segmentDistance;
      confidenceSum += confidence * segmentDistance;
      if (matchDistanceMeters !== undefined) {
        matchDistanceSum += matchDistanceMeters * segmentDistance;
      }
      segmentCount++;
    }
  }
  
  // Don't forget the last segment
  if (currentSegment) {
    segments.push(currentSegment);
  }
  
  // Calculate data quality score
  const coveragePercent = totalDistance > 0
    ? (knownDistance / totalDistance) * 100
    : 0;
  const dataQuality = coveragePercent;
  const avgConfidence = knownDistance > 0 ? (confidenceSum / knownDistance) : 0;
  const avgMatchDistanceMeters = matchDistanceSum > 0 && knownDistance > 0
    ? (matchDistanceSum / knownDistance)
    : undefined;

  const result = {
    segments,
    knownDistanceMeters: knownDistance,
    totalDistanceMeters: totalDistance,
    dataQuality,
    qualityMetrics: {
      coveragePercent,
      avgConfidence,
      avgMatchDistanceMeters,
    },
    lastUpdated: new Date().toISOString(),
    enrichmentSource: 'overpass',
  } satisfies SegmentedSurfaceData;

  surfaceCache.set(cacheKey, { data: result, cachedAt: Date.now() });

  return result;
}

/**
 * Calculate surface breakdown from segmented data
 */
export function calculateSurfaceBreakdownFromSegments(
  segmentedData: SegmentedSurfaceData
): SurfaceBreakdown {
  if (!segmentedData.segments.length || segmentedData.totalDistanceMeters <= 0) {
    return { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
  }
  
  const totals: Record<SurfaceType, number> = {
    pavement: 0,
    gravel: 0,
    dirt: 0,
    singletrack: 0,
    unknown: 0,
  };
  
  for (const segment of segmentedData.segments) {
    totals[segment.surfaceType] += segment.distanceMeters;
  }
  
  const total = segmentedData.totalDistanceMeters;
  
  return {
    pavement: (totals.pavement / total) * 100,
    gravel: (totals.gravel / total) * 100,
    dirt: (totals.dirt / total) * 100,
    singletrack: (totals.singletrack / total) * 100,
    unknown: (totals.unknown / total) * 100,
  };
}

/**
 * Create GeoJSON features for surface-colored route segments
 * 
 * Note: Returns features with detailed surface types (pavement, gravel, dirt, singletrack, unknown).
 * For display purposes, these should be mapped to simplified types (paved/unpaved/unknown)
 * using mapSurfaceTypeToSimplified from surfaceMix.ts.
 */
export function createSurfaceSegmentFeatures(
  geometry: number[][],
  segmentedData: SegmentedSurfaceData
): GeoJSON.Feature[] {
  const features: GeoJSON.Feature[] = [];
  
  for (const segment of segmentedData.segments) {
    // Extract coordinates for this segment
    const coords = geometry.slice(segment.startIndex, segment.endIndex + 1);
    
    if (coords.length < 2) continue;
    
    features.push({
      type: 'Feature',
      properties: {
        surfaceType: segment.surfaceType,
        confidence: segment.confidence,
        distanceMeters: segment.distanceMeters,
        source: segment.source,
      },
      geometry: {
        type: 'LineString',
        coordinates: coords,
      },
    });
  }
  
  return features;
}
