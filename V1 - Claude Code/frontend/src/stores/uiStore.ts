/**
 * UI store using Zustand
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { Coordinate } from '@/types';

const getDefaultInspectorHeight = () => 0;

type InspectorTab = 'summary' | 'elevation' | 'cue' | 'sources';
type MapLayer = 'default' | 'openCycle' | 'outdoor';
type MapMoveReason =
  | 'search'
  | 'chat_route'
  | 'route_created'
  | 'user_recenter'
  | 'other';
type ProfileHoverSource = 'chart' | 'map';

interface MapFlyTo {
  lat: number;
  lng: number;
  zoom?: number;
  name?: string;
  issuedAt: number;
  reason?: MapMoveReason;
}

interface MapBounds {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  issuedAt: number;
  reason?: MapMoveReason;
}

interface ProfileHoverState {
  distanceMeters: number;
  coordinate: Coordinate;
  surfaceType?: string;
  source: ProfileHoverSource;
}

interface UIState {
  // Sidebar
  sidebarOpen: boolean;
  sidebarWidth: number;

  // Route inspector panel (Inspector)
  inspectorOpen: boolean;
  inspectorHeight: number;
  inspectorTab: InspectorTab;

  // Map
  mapLayer: MapLayer;
  showRouteOverlay: boolean;
  showSurfaceColoring: boolean;
  showDifficultyColoring: boolean;
  pendingMapFlyTo: MapFlyTo | null;
  pendingFitBounds: MapBounds | null;
  profileHover: ProfileHoverState | null;
  mapCenter: { lat: number; lng: number; zoom: number } | null;
  searchMarker: {
    position: Coordinate;
    label?: string;
    layer?: string;
    routeSnapshot?: {
      viaPointsCount: number;
      routeGeometryLength: number;
      manualSegmentsLength: number;
      hasEnd: boolean;
    };
  } | null;

  // Mobile
  isMobile: boolean;
  bottomSheetPosition: 'collapsed' | 'half' | 'full';

  // Modals
  settingsOpen: boolean;
  routeLibraryOpen: boolean;
  gpxImportOpen: boolean;

  // Actions
  setSidebarOpen: (open: boolean) => void;
  setSidebarWidth: (width: number) => void;
  setInspectorOpen: (open: boolean) => void;
  setInspectorHeight: (height: number) => void;
  setInspectorTab: (tab: InspectorTab) => void;
  setMapLayer: (layer: MapLayer) => void;
  toggleRouteOverlay: () => void;
  toggleSurfaceColoring: () => void;
  toggleDifficultyColoring: () => void;
  setProfileHover: (hover: ProfileHoverState | null) => void;
  clearProfileHover: () => void;
  setMapCenter: (center: { lat: number; lng: number; zoom: number }) => void;
  setSearchMarker: (marker: {
    position: Coordinate;
    label?: string;
    layer?: string;
    routeSnapshot?: {
      viaPointsCount: number;
      routeGeometryLength: number;
      manualSegmentsLength: number;
      hasEnd: boolean;
    };
  }) => void;
  clearSearchMarker: () => void;
  setIsMobile: (isMobile: boolean) => void;
  setBottomSheetPosition: (position: 'collapsed' | 'half' | 'full') => void;
  setSettingsOpen: (open: boolean) => void;
  setRouteLibraryOpen: (open: boolean) => void;
  setGpxImportOpen: (open: boolean) => void;
  flyMapTo: (location: Omit<MapFlyTo, 'issuedAt'>) => void;
  clearPendingFlyTo: () => void;
  fitMapToBounds: (bounds: Omit<MapBounds, 'issuedAt'>) => void;
  clearPendingFitBounds: () => void;
}

export const useUIStore = create<UIState>()(
  immer((set) => ({
    // Initial state
    sidebarOpen: true,
    sidebarWidth: 320,
    inspectorOpen: true,
    inspectorHeight: getDefaultInspectorHeight(),
    inspectorTab: 'summary',
    mapLayer: 'outdoor',
    showRouteOverlay: true,
    showSurfaceColoring: false,
    showDifficultyColoring: false,
    pendingMapFlyTo: null,
    pendingFitBounds: null,
    profileHover: null,
    mapCenter: null,
    searchMarker: null,
    isMobile: false,
    bottomSheetPosition: 'collapsed',
    settingsOpen: false,
    routeLibraryOpen: false,
    gpxImportOpen: false,

    // Actions
    setSidebarOpen: (open) => set((state) => {
      state.sidebarOpen = open;
    }),

    setSidebarWidth: (width) => set((state) => {
      state.sidebarWidth = Math.max(320, Math.min(520, width));
    }),

    setInspectorOpen: (open) => set((state) => {
      state.inspectorOpen = open;
    }),

    setInspectorHeight: (height) => set((state) => {
      state.inspectorHeight = Math.max(0, height);
    }),

    setInspectorTab: (tab) => set((state) => {
      state.inspectorTab = tab;
    }),

    setMapLayer: (layer) => set((state) => {
      state.mapLayer = layer;
    }),

    toggleRouteOverlay: () => set((state) => {
      state.showRouteOverlay = !state.showRouteOverlay;
    }),

    toggleSurfaceColoring: () => set((state) => {
      state.showSurfaceColoring = !state.showSurfaceColoring;
    }),

    toggleDifficultyColoring: () => set((state) => {
      state.showDifficultyColoring = !state.showDifficultyColoring;
    }),

    setProfileHover: (hover) => set((state) => {
      state.profileHover = hover;
    }),

    clearProfileHover: () => set((state) => {
      state.profileHover = null;
    }),

    setMapCenter: (center) => set((state) => {
      state.mapCenter = center;
    }),

    setSearchMarker: (marker) => set((state) => {
      state.searchMarker = marker;
    }),

    clearSearchMarker: () => set((state) => {
      state.searchMarker = null;
    }),

    setIsMobile: (isMobile) => set((state) => {
      state.isMobile = isMobile;
    }),

    setBottomSheetPosition: (position) => set((state) => {
      state.bottomSheetPosition = position;
    }),

    setSettingsOpen: (open) => set((state) => {
      state.settingsOpen = open;
    }),

    setRouteLibraryOpen: (open) => set((state) => {
      state.routeLibraryOpen = open;
    }),

    setGpxImportOpen: (open) => set((state) => {
      state.gpxImportOpen = open;
    }),

    flyMapTo: (location) => set((state) => {
      state.pendingMapFlyTo = { ...location, issuedAt: Date.now() };
    }),

    clearPendingFlyTo: () => set((state) => {
      state.pendingMapFlyTo = null;
    }),

    fitMapToBounds: (bounds) => set((state) => {
      state.pendingFitBounds = { ...bounds, issuedAt: Date.now() };
    }),

    clearPendingFitBounds: () => set((state) => {
      state.pendingFitBounds = null;
    }),
  }))
);
