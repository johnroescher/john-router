/**
 * Hook for managing map view state (position, zoom) with store integration
 * Persists map position to localStorage to restore on page refresh
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { ViewState, ViewStateChangeEvent } from 'react-map-gl/maplibre';
import { useRouteStore } from '@/stores/routeStore';
import { useUIStore } from '@/stores/uiStore';
import { DEFAULT_VIEW } from '../constants';

// LocalStorage key for persisting map position
const MAP_POSITION_KEY = 'john-router-map-position';

// Type for persisted position data
interface PersistedMapPosition {
  longitude: number;
  latitude: number;
  zoom: number;
}

// Load saved position from localStorage
function loadSavedPosition(): PersistedMapPosition | null {
  if (typeof window === 'undefined') return null;
  
  try {
    const saved = localStorage.getItem(MAP_POSITION_KEY);
    if (!saved) return null;
    
    const parsed = JSON.parse(saved);
    // Validate the saved data has required fields
    if (
      typeof parsed.longitude === 'number' &&
      typeof parsed.latitude === 'number' &&
      typeof parsed.zoom === 'number'
    ) {
      return parsed;
    }
  } catch {
    // Invalid saved data, ignore
  }
  return null;
}

// Save position to localStorage
function savePosition(position: PersistedMapPosition): void {
  if (typeof window === 'undefined') return;
  
  try {
    localStorage.setItem(MAP_POSITION_KEY, JSON.stringify(position));
  } catch {
    // localStorage might be full or disabled, ignore
  }
}

// Get initial position: saved position > route start > default
function getInitialPosition(
  constraintsStart: { lng: number; lat: number } | null | undefined,
): PersistedMapPosition {
  const saved = loadSavedPosition();
  if (saved) {
    return saved;
  }
  
  return {
    longitude: constraintsStart?.lng ?? DEFAULT_VIEW.longitude,
    latitude: constraintsStart?.lat ?? DEFAULT_VIEW.latitude,
    zoom: DEFAULT_VIEW.zoom,
  };
}

export interface MapViewState extends ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  bearing: number;
  pitch: number;
  padding: { top: number; bottom: number; left: number; right: number };
}

export function useMapViewState() {
  const constraints = useRouteStore((state) => state.constraints);
  const pendingFlyTo = useUIStore((state) => state.pendingMapFlyTo);
  const pendingFitBounds = useUIStore((state) => state.pendingFitBounds);
  const clearPendingFlyTo = useUIStore((state) => state.clearPendingFlyTo);
  const clearPendingFitBounds = useUIStore((state) => state.clearPendingFitBounds);
  const setMapCenter = useUIStore((state) => state.setMapCenter);

  // Track last processed command to prevent duplicates
  const lastFlyToRef = useRef<number>(0);
  const lastFitBoundsRef = useRef<number>(0);
  const lastManualInteractionRef = useRef<number>(0);
  
  // Debounce timer for saving position
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize with saved position or defaults
  const [viewState, setViewState] = useState<MapViewState>(() => {
    const initial = getInitialPosition(constraints.start);
    return {
      longitude: initial.longitude,
      latitude: initial.latitude,
      zoom: initial.zoom,
      bearing: 0,
      pitch: 0,
      padding: { top: 0, bottom: 0, left: 0, right: 0 },
    };
  });

  // For returning flyTo/fitBounds commands to the map
  const [pendingCommand, setPendingCommand] = useState<{
    type: 'flyTo' | 'fitBounds';
    params: Record<string, unknown>;
  } | null>(null);

  // Handle view state changes from user interaction
  const onMove = useCallback((evt: ViewStateChangeEvent) => {
    lastManualInteractionRef.current = Date.now();
    setViewState(evt.viewState as MapViewState);
  }, []);

  // Block auto-moves during manual interaction (6 second cooldown)
  const isAutoMoveBlocked = useCallback((reason?: string) => {
    if (reason && ['route_created', 'chat_route', 'search', 'user_recenter'].includes(reason)) {
      return false;
    }
    return Date.now() - lastManualInteractionRef.current < 6000;
  }, []);

  // Process pending flyTo commands from the UI store
  useEffect(() => {
    if (!pendingFlyTo || isAutoMoveBlocked(pendingFlyTo.reason)) return;
    if (pendingFlyTo.issuedAt <= lastFlyToRef.current) return;

    lastFlyToRef.current = pendingFlyTo.issuedAt;
    
    setPendingCommand({
      type: 'flyTo',
      params: {
        center: [pendingFlyTo.lng, pendingFlyTo.lat],
        zoom: pendingFlyTo.zoom ?? viewState.zoom,
        duration: 1500,
      },
    });

    // Also update view state for React state consistency
    setViewState((prev) => ({
      ...prev,
      longitude: pendingFlyTo.lng,
      latitude: pendingFlyTo.lat,
      zoom: pendingFlyTo.zoom ?? prev.zoom,
    }));

    clearPendingFlyTo();
  }, [pendingFlyTo, clearPendingFlyTo, viewState.zoom, isAutoMoveBlocked]);

  // Process pending fitBounds commands from the UI store
  useEffect(() => {
    if (!pendingFitBounds || isAutoMoveBlocked(pendingFitBounds.reason)) return;
    if (pendingFitBounds.issuedAt <= lastFitBoundsRef.current) return;

    lastFitBoundsRef.current = pendingFitBounds.issuedAt;

    setPendingCommand({
      type: 'fitBounds',
      params: {
        bounds: [
          [pendingFitBounds.minLng, pendingFitBounds.minLat],
          [pendingFitBounds.maxLng, pendingFitBounds.maxLat],
        ],
        padding: 60,
        duration: 1500,
        maxZoom: 16,
      },
    });

    clearPendingFitBounds();
  }, [pendingFitBounds, clearPendingFitBounds, isAutoMoveBlocked]);

  // Clear pending command after it's been consumed
  const clearPendingCommand = useCallback(() => {
    setPendingCommand(null);
  }, []);

  // Jump to start location when constraints change (first load)
  const jumpToStart = useCallback(() => {
    const start = constraints.start;
    if (start) {
      setViewState((prev) => ({
        ...prev,
        longitude: start.lng,
        latitude: start.lat,
      }));
    }
  }, [constraints.start]);

  // Persist map position to localStorage (debounced to avoid excessive writes)
  useEffect(() => {
    // Clear any pending save
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
    }

    // Debounce save by 500ms
    saveTimerRef.current = setTimeout(() => {
      savePosition({
        longitude: viewState.longitude,
        latitude: viewState.latitude,
        zoom: viewState.zoom,
      });
    }, 500);

    // Cleanup on unmount
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, [viewState.longitude, viewState.latitude, viewState.zoom]);

  useEffect(() => {
    setMapCenter({
      lat: viewState.latitude,
      lng: viewState.longitude,
      zoom: viewState.zoom,
    });
  }, [setMapCenter, viewState.latitude, viewState.longitude, viewState.zoom]);

  return {
    viewState,
    setViewState,
    onMove,
    pendingCommand,
    clearPendingCommand,
    jumpToStart,
    isAutoMoveBlocked,
  };
}
