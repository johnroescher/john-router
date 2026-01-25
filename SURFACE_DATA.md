## Surface Data: How We Get It, Store It, and Use It

Below is a single, expanded explanation of the surface-data pipeline, with code references that show exactly where each step happens.

---

## 1) Data Sources (How Surface Data Is Obtained)

### A) Overpass / OpenStreetMap (segment-level, high fidelity)
Primary enrichment happens via the backend API or frontend fallback:

- Backend endpoint: `POST /routes/surface-match` calls `SurfaceMatchService.match_geometry()` and returns `segmentedSurface`.
```
1033:1045:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
@routes_router.post("/surface-match", response_model=SurfaceMatchResponse)
async def surface_match(...):
    geometry = request.geometry.coordinates
    ...
    segmented = await surface_match_service.match_geometry(geometry)
    return SurfaceMatchResponse(status="ok", segmentedSurface=segmented)
```

- Service logic: adaptive sampling + Overpass query + nearest way matching + tag-based classification.
```
289:339:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/services/surface_match.py
total_distance = _calculate_cumulative_distances(geometry)[-1]
adaptive_sample_count = 30 if total_distance < 5000 else 50 if total_distance < 20000 else 70
buffer_meters = 25 if total_distance < 5000 else 40 if total_distance < 20000 else 50
...
ways = await _fetch_overpass_ways(query)
...
surface_type, confidence = classify_way_surface(closest_way.tags)
```

- Tag-based classification (surface/tracktype/mtb:scale/highway heuristics):
```
57:93:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/services/surface_match.py
def classify_way_surface(tags: Dict[str, str]) -> Tuple[str, float]:
    ...
    if surface in PAVED_SURFACES: return "pavement", 0.95
    if tracktype and tracktype in TRACKTYPE_SURFACES: return TRACKTYPE_SURFACES[tracktype], 0.85
    if mtb_scale: return "singletrack", 0.9
    if highway in PAVED_HIGHWAY_TYPES: return "pavement", 0.9
    ...
```

### B) Frontend Overpass fallback
If backend surface-match fails, the frontend performs the same enrichment directly, including caching and Overpass mirror fallback.
```
75:95:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/components/map/hooks/useSurfaceEnrichment.ts
const response = await api.surfaceMatch({ type: 'LineString', coordinates: routeGeometry });
...
if (!segmentedData) {
  segmentedData = await enrichRouteSurface(routeGeometry, abortControllerRef.current.signal);
}
```

```
498:748:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/lib/surfaceEnrichment.ts
const adaptiveSampleCount = totalDistance < 5000 ? 30 : totalDistance < 20000 ? 50 : 70;
const bufferMeters = totalDistance < 5000 ? 25 : totalDistance < 20000 ? 40 : 50;
const query = buildOverpassQuery(geometry, adaptiveSampleCount, bufferMeters);
...
const result = {
  segments,
  knownDistanceMeters: knownDistance,
  totalDistanceMeters: totalDistance,
  dataQuality,
  qualityMetrics: { coveragePercent, avgConfidence, avgMatchDistanceMeters },
  enrichmentSource: 'overpass',
} satisfies SegmentedSurfaceData;
```

### C) Routing engine surface summaries
When routes are generated or analyzed, surface breakdowns come from routing engines:

#### ORS (OpenRouteService)
```
1240:1309:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/services/routing.py
surface_info = extras.get("surface", {})
surface_breakdown = self._parse_ors_surface(surface_info, summary.get("distance", 0))
...
SURFACE_MAP = {
  0: "unknown", 1: "paved", 2: "unpaved", 3: "paved", ... 10: "gravel", 11: "ground", ...
}
```

#### BRouter
```
300:384:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/services/routing.py
surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 0}
...
if known_surface_dist < total_surface_dist * 0.1:
    surface_breakdown = {"paved": 0, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 100}
else:
    surface_breakdown = {k: (v / total_surface_dist) * 100 for k, v in surface_breakdown.items()}
```

### D) Map-tile inference (present but not wired into enrichment)
There is a map-based inference utility, but it is not currently called by the enrichment hook.
```
221:283:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/lib/surfaceInference.ts
export const inferSurfaceFromMap = (params: { map, geometry, routeDistanceData, ... }): SurfaceInferenceCandidate | null => {
  ...
  const features = map.queryRenderedFeatures(...);
  ...
  return { surfaceBreakdown, coverage, source: 'map' };
};
```

---

## 2) Storage and Updates (Where Surface Data Lives)

### Route-level breakdown (DB)
Stored on `routes.surface_breakdown` as JSONB.
```
44:49:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/models/route.py
surface_breakdown = Column(
    JSONB,
    default={"pavement": 0, "gravel": 0, "dirt": 0, "singletrack": 0, "unknown": 100},
    nullable=False,
)
```

### Segment-level metadata (DB)
Per-segment surface info can be stored on `route_segments`.
```
138:163:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/models/route.py
surface = Column(String(100), nullable=True)
...
osm_way_ids = Column(ARRAY(BIGINT), default=[], nullable=False)
osm_tags = Column(JSONB, default={}, nullable=False)
```

### How route-level breakdown is written
- Create route: analysis results (including surface breakdown) are saved.
```
329:367:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
analysis = await analysis_service.analyze_route({"type": "LineString", "coordinates": coords})
...
db_route.surface_breakdown = analysis.surface_breakdown.model_dump()
```

- Update route: if geometry changes, it re-analyzes but only updates distance/gain/confidence; it does not persist surface breakdown.
```
423:439:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
if update.geometry is not None:
    analysis = await analysis_service.analyze_route({"type": "LineString", "coordinates": coords})
    route.distance_meters = analysis.distance_meters
    route.elevation_gain_meters = analysis.elevation_gain_meters
    route.confidence_score = analysis.confidence_score
```

- Route responses: surface breakdown is always returned from the route model.
```
1264:1294:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
surface_breakdown=SurfaceBreakdown(**route.surface_breakdown) if route.surface_breakdown else SurfaceBreakdown(),
```

---

## 3) Frontend Enrichment and Normalization

### Enrichment orchestration
The `useSurfaceEnrichment` hook:
- Runs when route geometry changes.
- Tries backend `/surface-match`.
- Falls back to frontend Overpass.
- Updates surface store and (optionally) route store.

```
40:120:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/components/map/hooks/useSurfaceEnrichment.ts
const response = await api.surfaceMatch({ ... });
...
if (!segmentedData) segmentedData = await enrichRouteSurface(routeGeometry, ...);
...
setSegmentedSurface(segmentedData);
if (segmentedData.dataQuality > 30 && currentRoute) {
  const enrichedBreakdown = calculateSurfaceBreakdownFromSegments(segmentedData);
  useRouteStore.getState().setManualSurfaceBreakdown(enrichedBreakdown);
}
```

### Cache
10-minute in-memory cache keyed by geometry sampling.
```
38:44:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/lib/surfaceEnrichment.ts
const SURFACE_CACHE_TTL_MS = 10 * 60 * 1000;
const surfaceCache = new Map<string, CachedSurface>();
```

### Normalization between backend and frontend formats
Backend uses `paved/unpaved/ground/...`, frontend uses `pavement/gravel/dirt/singletrack`.
```
13:58:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/lib/surfaceMix.ts
const hasDetailed = ['pavement', 'gravel', 'dirt', 'singletrack'].some((key) => key in input);
...
normalized.pavement = toNumber(input.paved);
normalized.gravel = toNumber(input.gravel);
normalized.dirt = toNumber(input.ground);
normalized.singletrack = toNumber(input.singletrack);
```

---

## 4) How Surface Data Is Used

### A) Map surface coloring (segment-level if quality > 20%)
```
65:110:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/components/map/layers/RouteLayer.tsx
if (segmentedSurface && segmentedSurface.segments.length > 0 && segmentedSurface.dataQuality > 20) {
  const features = createSurfaceSegmentFeatures(routeGeometry, segmentedSurface);
  const simplifiedFeatures = features.map((feature) => {
    const simplifiedType = mapSurfaceTypeToSimplified(feature.properties.surfaceType);
    return { ...feature, properties: { ...feature.properties, surfaceType: simplifiedType } };
  });
  return { type: 'FeatureCollection', features: simplifiedFeatures };
}
```

### B) Elevation chart coloring and legend
Per-point mapping from segment distances to simplified surface types.
```
40:76:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/components/inspector/ElevationChart.tsx
if (segmentedSurface && segmentedSurface.dataQuality > 20 && segmentedSurface.segments.length > 0) {
  for (const point of profile) {
    ...
    if (point.distanceMeters > segment.startDistanceMeters && point.distanceMeters <= segment.endDistanceMeters) {
      foundSurface = segment.surfaceType;
    }
    assignments.push(mapSurfaceTypeToSimplified(foundSurface));
  }
}
```

### C) Surface breakdown UI (paved vs unpaved vs unknown)
```
25:38:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/frontend/src/components/inspector/SurfaceBreakdownChart.tsx
const rawSurfaceBreakdown = segmentedSurface && segmentedSurface.dataQuality > 20
  ? useSurfaceStore.getState().getAggregatedBreakdown()
  : { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
```

### D) Validation (constraints: avoid / prefer / require)
```
285:337:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/services/validation.py
surface_map = {
  "pavement": "paved",
  "paved": "paved",
  "gravel": "gravel",
  "dirt": "unpaved",
  "singletrack": "ground",
}
...
if actual_pct > 10: issues.append(...)
if actual_pct < 60: issues.append(...)
if actual_pct < 80: issues.append(...)
```

### E) Candidate ranking / scoring (surface preferences + unknown penalty)
```
1620:1642:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
actual = {
  "pavement": analysis.surface_breakdown.pavement / 100,
  "gravel": analysis.surface_breakdown.gravel / 100,
  "singletrack": (analysis.surface_breakdown.singletrack + analysis.surface_breakdown.dirt) / 100,
}
...
if analysis.surface_breakdown.unknown > 60:
    score *= 0.6
```

### F) Manual point-to-point routing response
Surface breakdown is returned to the frontend directly from the routing service response.
```
888:916:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
surface_data = parsed.get("surface_breakdown", {})
...
surface_breakdown=SurfaceBreakdownResponse(
    paved=surface_data.get("paved", 0),
    unpaved=surface_data.get("unpaved", 0),
    gravel=surface_data.get("gravel", 0),
    ground=surface_data.get("ground", 0),
    unknown=surface_data.get("unknown", 0),
),
```

---

## 5) Exactly Where It’s Saved or Updated

- Create route: persists `surface_breakdown` from analysis.
```
329:367:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
db_route.surface_breakdown = analysis.surface_breakdown.model_dump()
```

- Update route: re-analyzes but does not persist surface breakdown (only distance/elevation/confidence).
```
423:439:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
analysis = await analysis_service.analyze_route(...)
route.distance_meters = analysis.distance_meters
route.elevation_gain_meters = analysis.elevation_gain_meters
route.confidence_score = analysis.confidence_score
```

- Route responses: always read from `route.surface_breakdown`.
```
1264:1294:/Users/johnroescher/Desktop/JOHN ROUTER/V1 - Claude Code/backend/app/api/routes.py
surface_breakdown=SurfaceBreakdown(**route.surface_breakdown) if route.surface_breakdown else SurfaceBreakdown(),
```

---

## 6) Summary Flow (End-to-End)

1. Route is generated or manually drawn.
   - Routing engine returns `surface_breakdown` (ORS or BRouter).
   - Point-to-point API returns `surface_breakdown` to frontend.
2. Surface enrichment (segment-level).
   - `useSurfaceEnrichment` tries backend `/surface-match`, then frontend Overpass fallback.
   - Produces `SegmentedSurfaceData` with `segments`, `dataQuality`, `qualityMetrics`.
3. Storage.
   - On route creation, analysis writes `surface_breakdown` to DB.
   - Segment metadata can live on `route_segments`.
4. Usage.
   - Map coloring, elevation chart, and breakdown charts consume `segmentedSurface`.
   - Validation and scoring use the route-level breakdown.
