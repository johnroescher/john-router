# John Router - Project History

A technical chronicle of architectural decisions, major changes, and lessons learned during the development of John Router.

---

## January 2026

### Surface Type Simplification Test Suite (Jan 23, 2026)

#### Context

The surface type simplification feature converts 5 detailed surface categories (pavement, gravel, dirt, singletrack, unknown) to 3 simplified categories (paved, unpaved, unknown) for display purposes. A comprehensive test suite was created to ensure this conversion works correctly across all layers of the application.

#### Test Suite Structure

Created 42 tests across 3 test files:

1. **`src/lib/__tests__/surfaceMix.test.ts`** (25 tests)
   - Core mapping functions (`mapSurfaceTypeToSimplified`)
   - Aggregation functions (`getSimplifiedSurfaceMix`)
   - Data flow integration
   - Edge cases and normalization

2. **`src/stores/__tests__/surfaceStore.test.ts`** (11 tests)
   - Store-level segment aggregation
   - Detailed to simplified conversion
   - Long routes with many segments

3. **`src/lib/__tests__/surfaceEnrichment.test.ts`** (6 tests)
   - Enrichment integration
   - Feature creation with simplified types
   - End-to-end data flow

#### Running the Tests

Added npm script for easy test execution:

```bash
npm run test:surface
```

Or use the full command:
```bash
npm test -- --testPathPattern="surface"
```

#### Test Coverage

The test suite verifies:
- ✅ All 5 surface types mapped correctly to 3 simplified types
- ✅ Aggregation of unpaved types (gravel + dirt + singletrack)
- ✅ Percentage normalization (always sums to 100)
- ✅ Edge cases (empty data, invalid percentages)
- ✅ Real-world route scenarios
- ✅ Store-level aggregation
- ✅ Enrichment integration
- ✅ End-to-end data flow

#### Documentation

Created comprehensive testing documentation:
- `TESTING.md` - Quick reference guide for running tests
- `TEST_PLAN_SURFACE_SIMPLIFICATION.md` - Detailed test plan
- `SURFACE_SIMPLIFICATION_TEST_SUMMARY.md` - Test summary

All tests pass successfully (42/42) with execution time ~0.4s.

---

### Map Component Architecture Rebuild (Jan 20-22, 2026)

#### Context

The original `MapView.tsx` was a monolithic 2300+ line component that handled all map rendering, user interactions, route display, markers, drawing tools, and profile synchronization. While functional, it had grown difficult to maintain and was experiencing intermittent rendering issues.

#### The Problem

Users reported that the map would sometimes fail to load on page refresh, displaying only a gray box with attribution text. Curiously, the map would render correctly when the browser's developer console was opened. This "loads only with console open" behavior pointed to a timing/initialization issue.

#### Root Cause Analysis

After extensive debugging, the root cause was identified in the `MapContainer` component's dimension-gating logic:

```typescript
// PROBLEMATIC CODE
const MapContainer = () => {
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  
  useEffect(() => {
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();  // Called too early!
    if (rect.width > 0 && rect.height > 0) {
      setDimensions({ width: rect.width, height: rect.height });
    }
    
    const observer = new ResizeObserver((entries) => {
      // Only fires on CHANGES, not initial state
    });
    observer.observe(el);
  }, []);
  
  // Map never renders because dimensions stay at 0x0
  return dimensions.width > 0 ? <MapCore /> : <Skeleton />;
};
```

**The race condition:**
1. `getBoundingClientRect()` was called synchronously before the browser completed its layout pass
2. This returned `{ width: 0, height: 0 }` because the element hadn't been laid out yet
3. `ResizeObserver` only fires on *changes* to element dimensions
4. Since the element was always the correct size (just not measured correctly on first paint), the callback never fired
5. Opening dev console triggered a browser reflow, which caused ResizeObserver to fire

#### The Solution

Removed dimension-gating entirely and switched to CSS-based sizing:

```typescript
// FIXED CODE
const MapContainer = () => {
  return (
    <Box sx={{
      width: '100%',
      height: '100%',
      position: 'absolute',
      top: 0, left: 0, right: 0, bottom: 0,
    }}>
      <MapCore />
    </Box>
  );
};

// MapCore uses CSS sizing
<Map
  style={{ width: '100%', height: '100%' }}
  // ... other props
/>
```

**Why this works:**
- `react-map-gl/maplibre` handles CSS-based sizing properly
- No JavaScript measurement needed before rendering
- Map initializes immediately with the container's CSS dimensions
- No race conditions possible

#### Architectural Changes

The rebuild restructured the map into a modular component hierarchy:

```
src/components/map/
├── MapContainer.tsx      # SSR-safe wrapper, CSS-based sizing
├── MapCore.tsx           # Main map component, orchestrates everything
├── MapControls.tsx       # Zoom buttons, style picker
├── DrawingTools.tsx      # Waypoint tool, undo/redo controls
├── constants.ts          # Styles, colors, layer IDs
├── index.ts              # Public exports
├── hooks/
│   ├── useMapViewState.ts     # View state + flyTo/fitBounds
│   ├── useRouteInteraction.ts # Click/drag handling
│   └── useDrawingMode.ts      # Drawing tool state
└── layers/
    ├── RouteLayer.tsx    # Route line rendering
    ├── MarkerLayer.tsx   # Start/via/end markers
    └── HoverMarker.tsx   # Profile hover sync marker
```

**Key decisions:**

1. **SSR Protection**: Map is loaded via `next/dynamic` with `{ ssr: false }` since MapLibre requires browser APIs (WebGL, canvas)

2. **Controlled State Pattern**: View state (lng, lat, zoom) managed in React state and passed to Map component, enabling programmatic control via Zustand stores

3. **Declarative Layers**: Using `react-map-gl`'s `<Source>` and `<Layer>` components instead of imperative `map.addSource()`/`map.addLayer()` calls

4. **Separation of Concerns**: Each hook and layer component has a single responsibility, making the codebase easier to test and maintain

#### Lessons Learned

1. **Avoid measuring dimensions before render**: If you need explicit dimensions, use CSS-based sizing or ensure measurements happen after layout (e.g., in `useLayoutEffect` with `requestAnimationFrame`)

2. **ResizeObserver fires on changes only**: Don't rely on ResizeObserver for initial dimensions—it only fires when the observed element's size *changes*

3. **Clear build cache when debugging**: Stale `.next` cache can show phantom errors that don't reflect current code state. When in doubt: `rm -rf .next && npm run dev`

4. **The "console open" debugging trap**: When something only works with dev tools open, suspect timing issues—console causes layout recalculation

5. **Ghost errors from deleted files**: If console logs reference files you've deleted, the build cache is stale. This can persist even after multiple code changes and is especially insidious because the "fix" is invisible in the code—it requires cache invalidation

6. **Docker containers compound cache issues**: When running Next.js in Docker, the `.next` folder inside the container may not reflect host file deletions. Stop the container, delete the cache from the host, then restart

---

### Map Loading Issue - Post-Rebuild Recurrence (Jan 22, 2026)

#### The Symptom

After the successful architectural rebuild (v0.2.0), the map stopped loading again. The behavior was identical to before: gray box on normal page load, but map renders when browser dev console is opened.

#### Investigation

Console logs revealed something critical: errors were being thrown from `MapView.tsx`—the old monolithic component that had been deleted. Specific errors included:

- `ReferenceError: startStyleWatchdog is not defined` (from `MapView.tsx:1636`)
- `RangeError: mismatched image size. expected: 0 but got: 256` (from `MapView.tsx`)
- `SecurityError` related to CORS for `maplibre-gl.worker.js`

This was impossible—the file no longer existed in the codebase.

#### Root Cause

**Next.js build cache persistence.** The `.next` directory contained compiled artifacts from before the deletion. Because the Docker container was running continuously and Next.js hot-reloading doesn't fully invalidate deleted file references, the old `MapView.tsx` code was still being executed.

#### Resolution

```bash
# Stop the frontend container
docker compose stop frontend

# Delete the build cache from host
rm -rf frontend/.next

# Restart the container (triggers fresh build)
docker compose start frontend
```

#### Why "Console Open" Fixed It

The console opening triggered a browser reflow, which caused:
1. A re-render of the React tree
2. The new, correct `MapContainer`/`MapCore` components to mount
3. The stale cached components to be replaced

This was a red herring—it masked the real issue (stale cache) by temporarily working around it.

#### Prevention

- Add `.next` to Docker's volume exclusions if possible
- Before major debugging sessions, always clear the build cache
- If errors reference deleted files, assume cache staleness first

---

### Manual Route Elevation Analysis Fix (Jan 22, 2026)

#### The Problem

When users drew manual routes by clicking waypoints on the map, the Elevation tab in the Inspector panel displayed "No elevation data available" even though the route was visible and other stats (distance, duration) were calculated correctly.

#### Root Cause Analysis

The data flow for elevation profiles was:

1. **AI-generated routes**: When routes are generated via chat, the backend returns `RouteCandidate` objects that include full `analysis` data with `elevationProfile` populated
2. **Manual routes**: When users click to add waypoints, the `useRouteInteraction` hook calls `api.routePointToPoint()` to get the segment geometry and basic stats

The issue: for manual routes, **nobody was calling `api.analyzeGeometry()`** to fetch the detailed elevation profile. The API method existed but was never invoked for manually drawn routes.

The `ElevationTab` component checks for elevation data in this order:
```typescript
const candidateAnalysis = candidates[selectedCandidateIndex]?.analysis;
const analysis = candidateAnalysis?.elevationProfile?.length
  ? candidateAnalysis
  : manualAnalysis;  // <-- This was always null for manual routes!
```

Since `manualAnalysis` was never populated, the tab showed "No elevation data available".

#### The Solution

Created a new hook `useManualRouteAnalysis` that:

1. **Watches for manual route changes**: Monitors `routeGeometry`, `currentRoute.id`, and `manualSegments`
2. **Debounces API calls**: Waits 500ms after the last change to avoid hammering the API during rapid clicking
3. **Fetches elevation profile**: Calls `api.analyzeGeometry()` with the full route geometry
4. **Stores the result**: Sets `manualAnalysis` in the route store, which the Elevation tab reads

```typescript
// frontend/src/components/map/hooks/useManualRouteAnalysis.ts
export function useManualRouteAnalysis() {
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const currentRoute = useRouteStore((state) => state.currentRoute);
  const setManualAnalysis = useRouteStore((state) => state.setManualAnalysis);
  // ...

  useEffect(() => {
    const isManualRoute = currentRoute?.id === 'manual-route';
    if (!isManualRoute || !hasValidGeometry) return;

    // Debounced call to api.analyzeGeometry()
    debounceTimerRef.current = setTimeout(() => {
      analyzeRoute(routeGeometry);
    }, 500);
  }, [routeGeometry, currentRoute?.id, manualSegments.length]);
}
```

The hook is integrated into `MapCore.tsx` so it runs whenever the map is mounted.

#### Files Changed

- **Created**: `frontend/src/components/map/hooks/useManualRouteAnalysis.ts`
- **Modified**: `frontend/src/components/map/MapCore.tsx` (added hook import and call)

#### Lessons Learned

1. **Check API usage, not just existence**: The `analyzeGeometry` method was implemented but never called for manual routes—a gap between available functionality and actual usage

2. **Follow the data flow**: When a UI element shows "no data", trace backwards from the component through the store to the API call to find where the chain breaks

3. **Debounce user-triggered API calls**: When users rapidly add waypoints, each click could trigger an analysis. Debouncing prevents excessive API calls and improves UX

---

### Map Position Persistence (Jan 22, 2026)

#### The Problem

Users lost their map position every time they refreshed the page. The map would reset to either the route start location or the default Denver view, forcing users to navigate back to where they were working.

#### The Solution

Added localStorage-based persistence to the `useMapViewState` hook. The implementation:

1. **Saves position on move**: When the user pans or zooms, the new position is saved to localStorage after a 500ms debounce to avoid excessive writes during continuous scrolling

2. **Restores on page load**: On initial render, the hook checks localStorage for a saved position and uses it instead of the defaults

3. **Graceful fallbacks**: If no saved position exists or the data is invalid, falls back to route start location, then to the default Denver view

```typescript
// localStorage key
const MAP_POSITION_KEY = 'john-router-map-position';

// Saved data structure
interface PersistedMapPosition {
  longitude: number;
  latitude: number;
  zoom: number;
}

// Priority order for initial position
function getInitialPosition(constraintsStart) {
  const saved = loadSavedPosition();
  if (saved) return saved;  // 1. Saved position
  
  if (constraintsStart) {   // 2. Route start
    return { ...constraintsStart, zoom: DEFAULT_VIEW.zoom };
  }
  
  return DEFAULT_VIEW;      // 3. Default (Denver)
}
```

#### Design Decisions

- **localStorage over sessionStorage**: Persists across browser sessions, not just tabs
- **Debounced saves (500ms)**: Prevents hammering localStorage during continuous pan/zoom
- **SSR-safe**: Checks `typeof window !== 'undefined'` before accessing localStorage
- **Validation on load**: Verifies saved data has required numeric fields before using it
- **Silent failure**: If localStorage is full or disabled, saves fail silently without breaking the app

#### Files Changed

- **Modified**: `frontend/src/components/map/hooks/useMapViewState.ts`

---

### Waypoint Drag-to-Edit and Route Regeneration (Jan 22, 2026)

#### The Feature Request

Users needed standard route-building interactions like those found in Strava Route Builder or Ride with GPS:
1. Drag a waypoint to move it, and the route regenerates to accommodate the new position
2. Delete a waypoint, and the route regenerates without it
3. Click on the route line and drag to insert a new waypoint at that location

#### Implementation

**New Store Actions** (`routeStore.ts`):
- `moveViaPoint(index, coord)`: Updates an existing via point's position
- `insertViaPoint(index, coord)`: Inserts a new via point at a specific index
- `clearManualSegments()`: Clears all route segments

**New Hook** (`useRouteRegeneration.ts`):
A hook that rebuilds the entire route through all waypoints when any waypoint changes.

**Updated Components**:
- `MarkerLayer.tsx`: Made via point markers draggable with `onDragEnd` handlers
- `MapCore.tsx`: Added insert marker that appears when hovering near the route line
- `RouteInsertMarker.tsx`: New component showing a ghost marker that can be dragged to insert waypoints

**Route Interaction Updates** (`useRouteInteraction.ts`):
- `getInsertionIndex(coord)`: Calculates where along the existing route a new waypoint should be inserted based on its position

#### The Bug: Route Not Regenerating

After implementing the feature, dragging waypoints or inserting new ones via the ghost marker did NOT regenerate the route. The waypoints moved visually, but the route line stayed the same.

**Initial Debugging**: Added console logs throughout the callback chain:
```
[MarkerLayer] handleViaDragEnd called
[MapCore] handleViaDrag called
[useRouteRegeneration] regenerateRoute called
[useRouteRegeneration] Setting 4 segments
```

The logs showed the callbacks were firing correctly, but the route wasn't updating properly.

#### Root Cause #1: Stale React Closures

The first issue was that `regenerateRoute` captured `constraints` from React's closure:

```typescript
// PROBLEMATIC CODE
const constraints = useRouteStore((state) => state.constraints);

const regenerateRoute = useCallback(async () => {
  const { start, viaPoints } = constraints; // ← Stale value!
  // ...
}, [constraints]);
```

When `moveViaPoint()` updated the store and then immediately called `regenerateRoute()`, the function still had the OLD constraint values from before the state update, because React hadn't re-rendered yet.

**Fix**: Get state directly from the store inside the callback:

```typescript
// FIXED CODE
const regenerateRoute = useCallback(async () => {
  // Get LATEST state directly from store
  const { constraints } = useRouteStore.getState();
  const { start, viaPoints } = constraints; // ← Always fresh!
  // ...
}, []);
```

This is a common Zustand pattern—use `.getState()` when you need the absolute latest state inside a callback that may be called before React re-renders.

#### Root Cause #2: Default Start Position Mismatch

After fixing the closure issue, routes STILL weren't regenerating correctly. Console logs revealed the real problem:

```
[useRouteRegeneration] All points: [
  {"lat":39.7392,"lng":-104.9903},      // ← Denver, CO (default)
  {"lng":-97.776,"lat":30.268},          // ← Austin, TX
  {"lng":-97.770,"lat":30.275},          // ← Austin, TX
  ...
  {"lat":39.7392,"lng":-104.9903}        // ← Denver, CO (loop back)
]
```

The `constraints.start` was set to **Denver, CO** (the default value), but the user had been building a route in **Austin, TX**. The regeneration was trying to route:
- Denver → Austin point 1 (900+ miles - API failure)
- Austin 1 → Austin 2 (works)
- Austin N → Denver (900+ miles - API failure)

**Why this happened**: When users manually build routes by clicking waypoints, they're adding `viaPoints` to the route. The first click becomes via point 1, not an update to `constraints.start`. The start position remains at its default value (Denver) because it's never explicitly set during manual route building.

**Fix**: For manual routes, the regeneration should route between via points only, not include `constraints.start`:

```typescript
// FIXED CODE
if (viaPoints.length >= 1) {
  // Route between via points only
  allPoints = [...viaPoints];
  
  // For loops, route back to the first via point
  if (routeType === 'loop') {
    allPoints.push(viaPoints[0]);
  }
} else {
  // Fallback: use start + via points (for AI-generated routes)
  allPoints = [start, ...viaPoints];
}
```

This creates routes like:
- Via point 1 → Via point 2
- Via point 2 → Via point 3
- Via point N → Via point 1 (for loops)

#### Files Changed

- **Created**: `frontend/src/components/map/hooks/useRouteRegeneration.ts`
- **Created**: `frontend/src/components/map/layers/RouteInsertMarker.tsx`
- **Modified**: `frontend/src/stores/routeStore.ts` (added `moveViaPoint`, `insertViaPoint`, `clearManualSegments`)
- **Modified**: `frontend/src/components/map/layers/MarkerLayer.tsx` (made via markers draggable)
- **Modified**: `frontend/src/components/map/MapCore.tsx` (integrated regeneration callbacks and insert marker)
- **Modified**: `frontend/src/components/map/hooks/useRouteInteraction.ts` (added `getInsertionIndex`, `isNearRoute`)

#### Lessons Learned

1. **Zustand `.getState()` for callbacks**: When a callback needs the latest state and may be called before React re-renders, use `useStore.getState()` instead of relying on the selector-captured value

2. **Trace the data, not just the code flow**: Console logs showed the callbacks were firing, but the CONTENT of the data (Denver coordinates mixed with Austin coordinates) revealed the real bug

3. **Default values can cause subtle bugs**: The default `constraints.start` (Denver) was never updated during manual route building, causing regeneration to fail when the user was actually working in a different location

4. **Manual vs AI-generated routes have different semantics**: AI-generated routes have a meaningful start point from the constraints. Manual routes are built incrementally by clicking—the "start" is effectively the first via point, not `constraints.start`

5. **Cross-country API failures are silent**: The routing API gracefully returns null for impossible routes (900+ mile segments), but this silent failure can mask the root cause if you don't inspect the actual coordinates being requested

---

## Architecture Decisions Record

### ADR-001: react-map-gl/maplibre over raw MapLibre GL JS

**Status**: Adopted

**Context**: Need to render maps in a React application with declarative components.

**Decision**: Use `react-map-gl/maplibre` wrapper instead of raw MapLibre GL JS.

**Rationale**:
- Declarative `<Source>` and `<Layer>` components integrate naturally with React
- Controlled component pattern enables React state management
- Automatic cleanup of sources/layers on unmount
- TypeScript support out of the box

**Consequences**:
- Slight abstraction overhead
- Some advanced MapLibre features require accessing underlying `map.getMap()`
- Must use `maplibre` export specifically (not the default mapbox export)

---

### ADR-002: Zustand for State Management

**Status**: Adopted

**Context**: Need shared state between map, sidebar, and inspector components.

**Decision**: Use Zustand with separate stores for different domains.

**Stores**:
- `routeStore`: Route geometry, constraints, waypoints, manual segments
- `uiStore`: Map layer, profile hover, flyTo commands, UI state
- `preferencesStore`: User preferences (bike type, units)

**Rationale**:
- Minimal boilerplate compared to Redux
- No provider wrapper needed
- Excellent TypeScript support
- Easy to split into domain-specific stores

---

### ADR-003: CARTO Basemaps over Mapbox

**Status**: Adopted

**Context**: Need vector tile basemaps for the application.

**Decision**: Use CARTO's free vector tile styles as default.

**Rationale**:
- No API key required for basic usage
- Clean, readable cartography
- Good performance
- Reduces dependency on Mapbox tokens

**Map Styles**:
- Default: `https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json`
- Light: `https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`

---

### ADR-004: Dynamic Import with SSR Disabled for Map

**Status**: Adopted

**Context**: MapLibre requires browser APIs (WebGL, canvas) that don't exist in Node.js.

**Decision**: Use Next.js dynamic import with `ssr: false`.

```typescript
const MapContainer = dynamic(
  () => import('@/components/map/MapContainer'),
  { ssr: false, loading: () => <MapSkeleton /> }
);
```

**Rationale**:
- Prevents "window is not defined" errors during SSR
- Shows loading skeleton during client-side hydration
- Map only initializes in browser environment

---

## Changelog

### v0.2.4 (January 22, 2026)
- **Added**: Drag-to-edit waypoint functionality - drag any via point marker to move it
- **Added**: Route regeneration on waypoint changes - route automatically rebuilds when waypoints are moved, inserted, or deleted
- **Added**: Insert waypoints by dragging route line - hover near the route to see a ghost marker, drag it to insert a new waypoint
- **Added**: `useRouteRegeneration` hook for rebuilding routes through all waypoints
- **Added**: `RouteInsertMarker` component for the drag-to-insert interaction
- **Fixed**: Stale closure bug where `regenerateRoute` used outdated constraint values
- **Fixed**: Default start position (Denver) incorrectly included in manual route regeneration
- **Location**: Multiple files in `frontend/src/components/map/`

### v0.2.3 (January 22, 2026)
- **Added**: Map position persistence across page refreshes
- **Feature**: Map now remembers its last position (longitude, latitude, zoom) and restores it on page load
- **Implementation**: Uses localStorage with debounced saves (500ms) to avoid excessive writes during panning
- **Location**: `frontend/src/components/map/hooks/useMapViewState.ts`
- **Priority**: Saved position > Route start location > Default (Denver, CO)

### v0.2.2 (January 22, 2026)
- **Fixed**: Elevation tab showing "No elevation data available" for manually drawn routes
- **Root Cause**: `api.analyzeGeometry()` was never called for manual routes, leaving `manualAnalysis` null
- **Added**: `useManualRouteAnalysis` hook that watches route geometry and fetches elevation profile
- **Location**: `frontend/src/components/map/hooks/useManualRouteAnalysis.ts`

### v0.2.1 (January 22, 2026)
- **Fixed**: Persistent map loading failure after rebuild
- **Root Cause**: Stale Next.js build cache retaining references to deleted `MapView.tsx`
- **Resolution**: Full cache clear (`rm -rf frontend/.next`) and dev server restart
- **Note**: Console logs showing errors from "deleted" files is a telltale sign of stale build artifacts

### v0.2.0 (January 22, 2026)
- **BREAKING**: Replaced monolithic `MapView.tsx` with modular map component system
- **Fixed**: Map failing to render on page load (dimension measurement race condition)
- **Added**: `useMapViewState`, `useRouteInteraction`, `useDrawingMode` hooks
- **Added**: Declarative `RouteLayer`, `MarkerLayer`, `HoverMarker` components
- **Improved**: CSS-based map sizing eliminates measurement dependencies

### v0.1.0 (Initial Release)
- Chat-first route planning with AI copilot
- Multi-discipline support (Road, Gravel, MTB, Urban, Bikepacking)
- Surface analysis and elevation profiles
- GPX import/export
