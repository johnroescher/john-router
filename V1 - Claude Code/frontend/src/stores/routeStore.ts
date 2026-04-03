/**
 * Route store using Zustand
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import type {
  Route,
  RouteConstraints,
  RouteCandidate,
  Coordinate,
  SportType,
  RouteType,
  MTBDifficulty,
  RouteAnalysis,
} from '@/types';
import { normalizeSurfaceBreakdown } from '@/lib/surfaceMix';

type ManualSurfaceBreakdown = {
  pavement: number;
  gravel: number;
  dirt: number;
  singletrack: number;
  unknown: number;
};

type ManualRouteSegment = {
  coordinates: number[][];
  distanceMeters: number;
  elevationGain: number;
  durationSeconds: number;
  surfaceBreakdown: ManualSurfaceBreakdown;
};

type RouteUndoEntry = {
  viaPoints: Coordinate[];
  manualSegments: ManualRouteSegment[];
};

const cloneViaPoints = (viaPoints: Coordinate[]) =>
  viaPoints.map((point) => ({ lat: point.lat, lng: point.lng }));

const cloneManualSegments = (segments: ManualRouteSegment[]) =>
  segments.map((segment) => ({
    coordinates: segment.coordinates.map((coord) => coord.slice()),
    distanceMeters: segment.distanceMeters,
    elevationGain: segment.elevationGain,
    durationSeconds: segment.durationSeconds,
    surfaceBreakdown: { ...segment.surfaceBreakdown },
  }));

const snapshotRoute = (state: RouteState): RouteUndoEntry => ({
  viaPoints: cloneViaPoints(state.constraints.viaPoints),
  manualSegments: cloneManualSegments(state.manualSegments),
});

const buildManualRouteGeometry = (segments: ManualRouteSegment[]) => {
  if (segments.length === 0) return null;
  let coordinates: number[][] = [];
  segments.forEach((segment, index) => {
    if (index === 0) {
      coordinates = segment.coordinates.slice();
    } else {
      coordinates = coordinates.concat(segment.coordinates.slice(1));
    }
  });
  return coordinates;
};

const buildManualRouteStats = (segments: ManualRouteSegment[]) => {
  const distanceMeters = segments.reduce((sum, segment) => sum + segment.distanceMeters, 0);
  const elevationGain = segments.reduce((sum, segment) => sum + segment.elevationGain, 0);
  const durationSeconds = segments.reduce((sum, segment) => sum + segment.durationSeconds, 0);

  if (distanceMeters <= 0) {
    return {
      distanceMeters,
      elevationGain,
      durationSeconds,
      surfaceBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
    };
  }

  const weightedSurface = segments.reduce(
    (acc, segment) => {
      acc.pavement += segment.surfaceBreakdown.pavement * segment.distanceMeters;
      acc.gravel += segment.surfaceBreakdown.gravel * segment.distanceMeters;
      acc.dirt += segment.surfaceBreakdown.dirt * segment.distanceMeters;
      acc.singletrack += segment.surfaceBreakdown.singletrack * segment.distanceMeters;
      acc.unknown += segment.surfaceBreakdown.unknown * segment.distanceMeters;
      return acc;
    },
    { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 0 }
  );

  const aggregatedBreakdown = {
    pavement: weightedSurface.pavement / distanceMeters,
    gravel: weightedSurface.gravel / distanceMeters,
    dirt: weightedSurface.dirt / distanceMeters,
    singletrack: weightedSurface.singletrack / distanceMeters,
    unknown: weightedSurface.unknown / distanceMeters,
  };

  console.info('[route-store] Aggregating surface breakdown from segments:', {
    segments_count: segments.length,
    segment_breakdowns: segments.map((s, i) => ({
      index: i,
      distance_m: Math.round(s.distanceMeters),
      breakdown: s.surfaceBreakdown,
    })),
    weighted_totals: weightedSurface,
    total_distance_m: distanceMeters,
    aggregated_breakdown: aggregatedBreakdown,
  });

  return {
    distanceMeters,
    elevationGain,
    durationSeconds,
    surfaceBreakdown: aggregatedBreakdown,
  };
};

const syncConstraintsToGeometry = (state: RouteState, geometry: number[][] | null) => {
  if (!geometry || geometry.length === 0) {
    state.constraints.end = undefined;
    return;
  }

  const [startLng, startLat] = geometry[0];
  const [endLng, endLat] = geometry[geometry.length - 1];
  state.constraints.start = { lat: startLat, lng: startLng };
  state.constraints.end = { lat: endLat, lng: endLng };
};

/**
 * Calculate haversine distance between two coordinates in meters
 */
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

// Maximum allowed straight-line distance for trail-to-road transitions (100 feet = 30.48 meters)
const MAX_STRAIGHT_LINE_DISTANCE_METERS = 30.48;

const applyManualRoute = (state: RouteState, options?: { preserveCurrentRoute?: boolean }) => {
  if (state.manualSegments.length === 0) {
    state.routeGeometry = null;
    state.constraints.end = undefined;
    if (state.currentRoute) {
      state.currentRoute.geometry = undefined;
      state.currentRoute.distanceMeters = 0;
      state.currentRoute.elevationGainMeters = 0;
      state.currentRoute.estimatedTimeSeconds = 0;
      state.currentRoute.surfaceBreakdown = { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
      state.currentRoute.updatedAt = new Date().toISOString();
    }
    if (!options?.preserveCurrentRoute && state.currentRoute?.id === 'manual-route') {
      state.currentRoute = null;
    }
    state.manualAnalysis = null;
    return;
  }

  const geometry = buildManualRouteGeometry(state.manualSegments);
  const stats = buildManualRouteStats(state.manualSegments);

  console.info('[route-store] applyManualRoute - aggregating segments:', {
    segments_count: state.manualSegments.length,
    segment_surface_breakdowns: state.manualSegments.map((s, i) => ({
      index: i,
      distance_m: Math.round(s.distanceMeters),
      breakdown: s.surfaceBreakdown,
    })),
    aggregated_stats: stats,
  });

  state.routeGeometry = geometry;
  syncConstraintsToGeometry(state, geometry);

  if (options?.preserveCurrentRoute && state.currentRoute && state.currentRoute.id !== 'manual-route') {
    state.currentRoute.geometry = geometry ? { type: 'LineString', coordinates: geometry } : undefined;
    // Preserve imported/generated route stats; partial reroutes should not zero them out.
    state.currentRoute.updatedAt = new Date().toISOString();
  } else if (!state.currentRoute || state.currentRoute.id !== 'manual-route') {
    state.currentRoute = {
      id: 'manual-route',
      name: 'Manual Route',
      sportType: state.constraints.sportType || 'mtb',
      geometry: geometry ? { type: 'LineString', coordinates: geometry } : undefined,
      distanceMeters: stats.distanceMeters,
      elevationGainMeters: stats.elevationGain,
      estimatedTimeSeconds: stats.durationSeconds,
      surfaceBreakdown: stats.surfaceBreakdown,
      mtbDifficultyBreakdown: { green: 0, blue: 0, black: 0, double_black: 0, unknown: 100 },
      tags: [],
      isPublic: false,
      confidenceScore: 0.8,
      validationStatus: 'pending',
      validationResults: { status: 'valid' as const, errors: [], warnings: [], info: [], confidenceScore: 0.8 },
      waypoints: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    } as Route;
  } else {
    state.currentRoute.geometry = geometry ? { type: 'LineString', coordinates: geometry } : undefined;
    state.currentRoute.distanceMeters = stats.distanceMeters;
    state.currentRoute.elevationGainMeters = stats.elevationGain;
    state.currentRoute.estimatedTimeSeconds = stats.durationSeconds;
    state.currentRoute.surfaceBreakdown = stats.surfaceBreakdown;
    state.currentRoute.updatedAt = new Date().toISOString();
  }
};

interface RouteState {
  // Current route
  currentRoute: Route | null;
  routeGeometry: number[][] | null;
  selectedSegmentIndex: number | null;
  manualAnalysis: RouteAnalysis | null;

  // Candidates
  candidates: RouteCandidate[];
  selectedCandidateIndex: number;

  // Constraints
  constraints: RouteConstraints;

  // Manual route segments (click-to-add)
  manualSegments: ManualRouteSegment[];
  segmentedImportedRoute: boolean;
  manualUndoStack: RouteUndoEntry[];
  manualRedoStack: RouteUndoEntry[];

  // Editing state
  isEditing: boolean;
  isDragging: boolean;
  snappingEnabled: boolean;
  lockedSegments: number[];

  // Loading states
  isGenerating: boolean;
  isAnalyzing: boolean;
  isSaving: boolean;
  isRoutingDegraded: boolean;

  // Actions
  setCurrentRoute: (route: Route | null) => void;
  setRouteGeometry: (geometry: number[][] | null) => void;
  selectSegment: (index: number | null) => void;
  setCandidates: (candidates: RouteCandidate[]) => void;
  selectCandidate: (index: number) => void;
  updateConstraints: (updates: Partial<RouteConstraints>) => void;
  setConstraintStart: (coord: Coordinate | undefined) => void;
  setConstraintEnd: (coord: Coordinate | undefined) => void;
  addViaPoint: (coord: Coordinate) => void;
  removeViaPoint: (index: number) => void;
  moveViaPoint: (index: number, coord: Coordinate) => void;
  insertViaPoint: (index: number, coord: Coordinate) => void;
  clearManualSegments: () => void;
  addManualSegment: (segment: ManualRouteSegment) => void;
  setManualSegments: (segments: ManualRouteSegment[]) => void;
  setImportedRouteSegments: (segments: ManualRouteSegment[]) => void;
  setRouteSegments: (segments: ManualRouteSegment[]) => void;
  clearManualRedo: () => void;
  undoManualWaypoint: () => void;
  redoManualWaypoint: () => void;
  addAvoidArea: (polygon: Coordinate[]) => void;
  removeAvoidArea: (index: number) => void;
  toggleSnapping: () => void;
  lockSegment: (index: number) => void;
  unlockSegment: (index: number) => void;
  setIsGenerating: (isGenerating: boolean) => void;
  setIsAnalyzing: (isAnalyzing: boolean) => void;
  setIsSaving: (isSaving: boolean) => void;
  setIsRoutingDegraded: (isRoutingDegraded: boolean) => void;
  resetRoute: () => void;
  updateRouteStats: (stats: { distanceMeters: number; elevationGain: number; durationSeconds: number }) => void;
  setManualAnalysis: (analysis: RouteAnalysis | null) => void;
  setManualSurfaceBreakdown: (surfaceBreakdown: {
    pavement: number;
    gravel: number;
    dirt: number;
    singletrack: number;
    unknown: number;
  }) => void;
  addToRouteStats: (stats: {
    distanceMeters: number;
    elevationGain: number;
    durationSeconds: number;
    surfaceBreakdown?: { paved: number; unpaved: number; gravel: number; ground: number; unknown: number };
  }) => void;
}

const defaultConstraints: RouteConstraints = {
  start: undefined,
  end: undefined,
  routeType: 'point_to_point',
  viaPoints: [],
  avoidAreas: [],
  sportType: 'road',
  routingService: 'auto',
  routingProfile: undefined,

  targetDistanceMeters: undefined,
  minDistanceMeters: undefined,
  maxDistanceMeters: undefined,
  distanceHardConstraint: true,

  targetTimeSeconds: undefined,
  timeHardConstraint: false,

  targetElevationGainMeters: undefined,
  maxElevationGainMeters: undefined,
  elevationHardConstraint: false,

  climbEmphasis: 0,
  surfacePreferences: { pavement: 0.2, gravel: 0.3, singletrack: 0.5 },
  allowHikeABike: false,
  preferBikeLanes: true,
  preferDesignatedMtbTrails: true,

  mtbDifficultyTarget: 'moderate',
  maxDownhillGradePercent: 15,
  maxUphillGradePercent: 20,
  mtbFeatures: {
    flow: false,
    berms: false,
    jumps: false,
    drops: false,
    rockGardens: false,
    roots: false,
    technicalClimbs: false,
    chunk: false,
  },
  hazardAvoidances: {
    exposure: true,
    cliffEdges: true,
    looseTerrain: false,
    waterCrossings: false,
    highSpeedRoadCrossings: true,
    nightUnsafe: false,
  },

  avoidHighways: false,
  avoidUnpavedWhenRoad: false,
  avoidPrivate: false,
  requireBicycleLegal: true,

  qualityMode: true,
  numAlternatives: 5,
};

export const useRouteStore = create<RouteState>()(
  persist(
    immer((set) => ({
      // Initial state
      currentRoute: null,
      routeGeometry: null,
      selectedSegmentIndex: null,
      manualAnalysis: null,
      candidates: [],
      selectedCandidateIndex: 0,
      constraints: defaultConstraints,
      manualSegments: [],
      segmentedImportedRoute: false,
      manualUndoStack: [],
      manualRedoStack: [],
      isEditing: false,
      isDragging: false,
      snappingEnabled: true,
      lockedSegments: [],
      isGenerating: false,
      isAnalyzing: false,
      isSaving: false,
      isRoutingDegraded: false,

      // Actions
      setCurrentRoute: (route) => set((state) => {
        console.log('routeStore.setCurrentRoute called', route?.id, route?.geometry?.coordinates?.length, 'coords');
        if (route) {
          console.log('[routeStore] Raw surface breakdown from route:', route.surfaceBreakdown);
          const normalized = normalizeSurfaceBreakdown(route.surfaceBreakdown);
          console.log('[routeStore] Normalized surface breakdown:', normalized);
          state.currentRoute = {
            ...route,
            surfaceBreakdown: normalized,
          };
        } else {
          state.currentRoute = null;
        }
        state.manualSegments = [];
        state.segmentedImportedRoute = false;
        state.manualUndoStack = [];
        state.manualRedoStack = [];
        state.manualAnalysis = null;
        if (route?.geometry) {
          state.routeGeometry = route.geometry.coordinates;
          console.log('routeGeometry set to', state.routeGeometry?.length, 'points');
          syncConstraintsToGeometry(state, state.routeGeometry);
        } else {
          state.routeGeometry = null;
          state.constraints.end = undefined;
        }
        if (route?.sportType) {
          state.constraints.sportType = route.sportType;
        }
        if (route?.distanceMeters) {
          state.constraints.targetDistanceMeters = route.distanceMeters;
        }
      }),

    setRouteGeometry: (geometry) => set((state) => {
      state.routeGeometry = geometry;
      syncConstraintsToGeometry(state, geometry);
    }),

    selectSegment: (index) => set((state) => {
      state.selectedSegmentIndex = index;
    }),

    setCandidates: (candidates) => set((state) => {
      state.candidates = candidates;
      state.selectedCandidateIndex = 0;
      state.manualSegments = [];
      state.segmentedImportedRoute = false;
      state.manualUndoStack = [];
      state.manualRedoStack = [];
      state.manualAnalysis = null;
      if (candidates.length > 0) {
        state.currentRoute = candidates[0].route;
        if (candidates[0].route.geometry) {
          state.routeGeometry = candidates[0].route.geometry.coordinates;
          syncConstraintsToGeometry(state, state.routeGeometry);
        }
      }
    }),

    selectCandidate: (index) => set((state) => {
      state.selectedCandidateIndex = index;
      state.manualSegments = [];
      state.segmentedImportedRoute = false;
      state.manualUndoStack = [];
      state.manualRedoStack = [];
      state.manualAnalysis = null;
      if (state.candidates[index]) {
        state.currentRoute = state.candidates[index].route;
        if (state.candidates[index].route.geometry) {
          state.routeGeometry = state.candidates[index].route.geometry.coordinates;
          syncConstraintsToGeometry(state, state.routeGeometry);
        }
      }
    }),

    updateConstraints: (updates) => set((state) => {
      Object.assign(state.constraints, updates);
    }),

    setConstraintStart: (coord) => set((state) => {
      state.constraints.start = coord;
    }),

    setConstraintEnd: (coord) => set((state) => {
      state.constraints.end = coord;
    }),

    addViaPoint: (coord) => set((state) => {
      state.manualUndoStack.push(snapshotRoute(state));
      state.manualRedoStack = [];
      state.constraints.viaPoints.push(coord);
    }),

    removeViaPoint: (index) => set((state) => {
      if (index < 0 || index >= state.constraints.viaPoints.length) return;
      state.manualUndoStack.push(snapshotRoute(state));
      state.manualRedoStack = [];
      state.constraints.viaPoints.splice(index, 1);
    }),

    moveViaPoint: (index, coord) => set((state) => {
      if (index >= 0 && index < state.constraints.viaPoints.length) {
        state.manualUndoStack.push(snapshotRoute(state));
        state.manualRedoStack = [];
        state.constraints.viaPoints[index] = coord;
      }
    }),

    insertViaPoint: (index, coord) => set((state) => {
      state.manualUndoStack.push(snapshotRoute(state));
      state.manualRedoStack = [];
      state.constraints.viaPoints.splice(index, 0, coord);
    }),

    clearManualSegments: () => set((state) => {
      state.manualSegments = [];
      state.segmentedImportedRoute = false;
      state.manualUndoStack = [];
      state.manualRedoStack = [];
      state.routeGeometry = null;
      state.manualAnalysis = null;
      if (state.currentRoute?.id === 'manual-route') {
        state.currentRoute = null;
      }
    }),

    addManualSegment: (segment) => set((state) => {
      state.manualSegments.push(segment);
      state.segmentedImportedRoute = false;
      applyManualRoute(state);
    }),

    setManualSegments: (segments) => set((state) => {
      // Filter out invalid segments (straight lines that don't follow roads/trails)
      const validSegments = segments.filter((segment) => {
        if (!segment?.coordinates || !Array.isArray(segment.coordinates)) {
          return false;
        }
        // Allow short 2-point segments (≤100 ft) for trail-to-road transitions
        // Reject longer 2-point segments (>100 ft) as they don't follow the network
        if (segment.coordinates.length === 2) {
          const distance = haversineDistanceMeters(segment.coordinates[0], segment.coordinates[1]);
          if (distance > MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[routeStore] Filtering out invalid straight-line segment (exceeds 100 ft)', { distance: Math.round(distance) });
            return false;
          }
        }
        return segment.coordinates.length >= 2;
      });
      state.manualSegments = validSegments;
      state.segmentedImportedRoute = false;
      applyManualRoute(state);
    }),

    setImportedRouteSegments: (segments) => set((state) => {
      state.manualSegments = segments;
      state.segmentedImportedRoute = true;
      applyManualRoute(state, { preserveCurrentRoute: true });
    }),

    setRouteSegments: (segments) => set((state) => {
      // Filter out invalid segments (straight lines that don't follow roads/trails)
      const validSegments = segments.filter((segment) => {
        if (!segment?.coordinates || !Array.isArray(segment.coordinates)) {
          return false;
        }
        // Allow short 2-point segments (≤100 ft) for trail-to-road transitions
        // Reject longer 2-point segments (>100 ft) as they don't follow the network
        if (segment.coordinates.length === 2) {
          const distance = haversineDistanceMeters(segment.coordinates[0], segment.coordinates[1]);
          if (distance > MAX_STRAIGHT_LINE_DISTANCE_METERS) {
            console.warn('[routeStore] Filtering out invalid straight-line segment (exceeds 100 ft)', { distance: Math.round(distance) });
            return false;
          }
        }
        return segment.coordinates.length >= 2;
      });
      state.manualSegments = validSegments;
      applyManualRoute(state, { preserveCurrentRoute: true });
    }),

    clearManualRedo: () => set((state) => {
      state.manualRedoStack = [];
    }),

    undoManualWaypoint: () => set((state) => {
      if (state.manualUndoStack.length === 0) return;
      const previous = state.manualUndoStack.pop();
      if (!previous) return;
      state.manualRedoStack.push(snapshotRoute(state));
      state.constraints.viaPoints = cloneViaPoints(previous.viaPoints);
      state.manualSegments = cloneManualSegments(previous.manualSegments);
      applyManualRoute(state);
    }),

    redoManualWaypoint: () => set((state) => {
      if (state.manualRedoStack.length === 0) return;
      const next = state.manualRedoStack.pop();
      if (!next) return;
      state.manualUndoStack.push(snapshotRoute(state));
      state.constraints.viaPoints = cloneViaPoints(next.viaPoints);
      state.manualSegments = cloneManualSegments(next.manualSegments);
      applyManualRoute(state);
    }),

    addAvoidArea: (polygon) => set((state) => {
      state.constraints.avoidAreas.push(polygon);
    }),

    removeAvoidArea: (index) => set((state) => {
      state.constraints.avoidAreas.splice(index, 1);
    }),

    toggleSnapping: () => set((state) => {
      state.snappingEnabled = !state.snappingEnabled;
    }),

    lockSegment: (index) => set((state) => {
      if (!state.lockedSegments.includes(index)) {
        state.lockedSegments.push(index);
      }
    }),

    unlockSegment: (index) => set((state) => {
      const idx = state.lockedSegments.indexOf(index);
      if (idx > -1) {
        state.lockedSegments.splice(idx, 1);
      }
    }),

    setIsGenerating: (isGenerating) => set((state) => {
      state.isGenerating = isGenerating;
    }),

    setIsAnalyzing: (isAnalyzing) => set((state) => {
      state.isAnalyzing = isAnalyzing;
    }),

    setIsSaving: (isSaving) => set((state) => {
      state.isSaving = isSaving;
    }),

    setIsRoutingDegraded: (isRoutingDegraded) => set((state) => {
      state.isRoutingDegraded = isRoutingDegraded;
    }),

    resetRoute: () => set((state) => {
      state.currentRoute = null;
      state.routeGeometry = null;
      state.selectedSegmentIndex = null;
      state.candidates = [];
      state.selectedCandidateIndex = 0;
      state.lockedSegments = [];
      state.manualSegments = [];
      state.segmentedImportedRoute = false;
      state.manualUndoStack = [];
      state.manualRedoStack = [];
      state.manualAnalysis = null;
      state.isAnalyzing = false;
      state.isRoutingDegraded = false;
      state.constraints = defaultConstraints;
    }),

    updateRouteStats: (stats) => set((state) => {
      if (!state.currentRoute) {
        // Create a minimal route object if none exists
        state.currentRoute = {
          id: 'manual-route',
          name: 'Manual Route',
          sportType: state.constraints.sportType || 'mtb',
          geometry: state.routeGeometry ? { type: 'LineString', coordinates: state.routeGeometry } : null,
          distanceMeters: stats.distanceMeters,
          elevationGainMeters: stats.elevationGain,
          estimatedTimeSeconds: stats.durationSeconds,
          surfaceBreakdown: { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 },
          mtbDifficultyBreakdown: { green: 0, blue: 0, black: 0, double_black: 0, unknown: 100 },
          tags: [],
          isPublic: false,
          confidenceScore: 0.8,
          validationStatus: 'pending',
          validationResults: { status: 'valid' as const, errors: [], warnings: [], info: [], confidenceScore: 0.8 },
          waypoints: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        } as Route;
      } else {
        state.currentRoute.distanceMeters = stats.distanceMeters;
        state.currentRoute.elevationGainMeters = stats.elevationGain;
        state.currentRoute.estimatedTimeSeconds = stats.durationSeconds;
      }
    }),

    setManualAnalysis: (analysis) => set((state) => {
      state.manualAnalysis = analysis;
    }),

    setManualSurfaceBreakdown: (surfaceBreakdown) => set((state) => {
      if (!state.currentRoute || state.currentRoute.id !== 'manual-route') return;
      state.currentRoute.surfaceBreakdown = surfaceBreakdown;
      state.currentRoute.updatedAt = new Date().toISOString();
    }),

      addToRouteStats: (stats) => set((state) => {
        // Convert API surface breakdown to our format
        const surfaceData = stats.surfaceBreakdown || { paved: 0, unpaved: 0, gravel: 0, ground: 0, unknown: 100 };
        const normalizedSurface = {
          pavement: surfaceData.paved || 0,
          gravel: (surfaceData.gravel || 0) + (surfaceData.unpaved || 0),
          dirt: surfaceData.ground || 0,
          singletrack: 0,
          unknown: surfaceData.unknown || 0,
        };

        if (!state.currentRoute) {
          // Create a minimal route object if none exists
          state.currentRoute = {
            id: 'manual-route',
            name: 'Manual Route',
            sportType: state.constraints.sportType || 'mtb',
            geometry: state.routeGeometry ? { type: 'LineString', coordinates: state.routeGeometry } : null,
            distanceMeters: stats.distanceMeters,
            elevationGainMeters: stats.elevationGain,
            estimatedTimeSeconds: stats.durationSeconds,
            surfaceBreakdown: normalizedSurface,
            mtbDifficultyBreakdown: { green: 0, blue: 0, black: 0, double_black: 0, unknown: 100 },
            tags: [],
            isPublic: false,
            confidenceScore: 0.8,
            validationStatus: 'pending',
            validationResults: { status: 'valid' as const, errors: [], warnings: [], info: [], confidenceScore: 0.8 },
            waypoints: [],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          } as Route;
        } else {
          // Add to existing stats
          const prevDist = state.currentRoute.distanceMeters || 0;
          const newDist = stats.distanceMeters;
          const totalDist = prevDist + newDist;

          state.currentRoute.distanceMeters = totalDist;
          state.currentRoute.elevationGainMeters = (state.currentRoute.elevationGainMeters || 0) + stats.elevationGain;
          state.currentRoute.estimatedTimeSeconds = (state.currentRoute.estimatedTimeSeconds || 0) + stats.durationSeconds;

          // Weighted average of surface breakdown
          if (totalDist > 0) {
            const prevSurface = state.currentRoute.surfaceBreakdown;
            state.currentRoute.surfaceBreakdown = {
              pavement: (prevSurface.pavement * prevDist + normalizedSurface.pavement * newDist) / totalDist,
              gravel: (prevSurface.gravel * prevDist + normalizedSurface.gravel * newDist) / totalDist,
              dirt: (prevSurface.dirt * prevDist + normalizedSurface.dirt * newDist) / totalDist,
              singletrack: (prevSurface.singletrack * prevDist + normalizedSurface.singletrack * newDist) / totalDist,
              unknown: (prevSurface.unknown * prevDist + normalizedSurface.unknown * newDist) / totalDist,
            };
          }

          // Keep geometry in sync
          if (state.routeGeometry) {
            state.currentRoute.geometry = { type: 'LineString', coordinates: state.routeGeometry };
          }
        }
      }),
    })),
    {
      name: 'john-router-route',
      partialize: (state) => ({
        currentRoute: state.currentRoute,
        routeGeometry: state.routeGeometry,
        constraints: state.constraints,
        manualSegments: state.manualSegments,
        segmentedImportedRoute: state.segmentedImportedRoute,
        selectedSegmentIndex: state.selectedSegmentIndex,
        lockedSegments: state.lockedSegments,
      }),
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.warn('[routeStore] Rehydration error:', error);
          return;
        }
        if (!state) return;
        console.log('[routeStore] Rehydrating from localStorage', {
          hasCurrentRoute: !!state.currentRoute,
          hasRouteGeometry: !!state.routeGeometry,
          routeGeometryLength: state.routeGeometry?.length,
          currentRouteGeometryLength: state.currentRoute?.geometry?.coordinates?.length,
        });
        // Ensure routeGeometry is set from currentRoute if missing
        if (!state.routeGeometry && state.currentRoute?.geometry?.coordinates) {
          state.routeGeometry = state.currentRoute.geometry.coordinates;
          console.log('[routeStore] Restored routeGeometry from currentRoute', state.routeGeometry.length, 'points');
        }
        if (state.routeGeometry) {
          syncConstraintsToGeometry(state, state.routeGeometry);
          // Force a state update to ensure components re-render
          // This ensures RouteLayer and other components see the rehydrated geometry
          state.routeGeometry = [...state.routeGeometry];
        }
      },
    }
  )
);
