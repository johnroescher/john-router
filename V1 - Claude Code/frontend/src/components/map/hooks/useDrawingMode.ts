/**
 * Hook for managing drawing mode state (waypoint tool)
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { MapRef } from 'react-map-gl/maplibre';
import { useRouteStore } from '@/stores/routeStore';
import { useRouteRegeneration } from './useRouteRegeneration';

export type DrawingTool = 'waypoint' | null;

export function useDrawingMode(mapRef: React.RefObject<MapRef | null>) {
  const [activeTool, setActiveTool] = useState<DrawingTool>(null);
  const activeToolRef = useRef<DrawingTool>(null);
  const undoManualWaypoint = useRouteStore((state) => state.undoManualWaypoint);
  const redoManualWaypoint = useRouteStore((state) => state.redoManualWaypoint);
  const manualUndoStack = useRouteStore((state) => state.manualUndoStack);
  const manualRedoStack = useRouteStore((state) => state.manualRedoStack);
  const constraints = useRouteStore((state) => state.constraints);
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const currentRoute = useRouteStore((state) => state.currentRoute);
  const manualSegments = useRouteStore((state) => state.manualSegments);
  const resetRoute = useRouteStore((state) => state.resetRoute);
  const { regenerateRoute } = useRouteRegeneration();

  // Keep ref in sync for event handlers
  useEffect(() => {
    activeToolRef.current = activeTool;
    
    // Update cursor based on active tool
    const map = mapRef.current?.getMap();
    if (map) {
      const canvas = map.getCanvas();
      if (!activeTool) {
        canvas.style.cursor = '';
      }
    }
  }, [activeTool, mapRef]);

  // Toggle waypoint tool
  const toggleWaypointTool = useCallback(() => {
    setActiveTool((prev) => (prev === 'waypoint' ? null : 'waypoint'));
  }, []);

  // Clear active tool
  const clearTool = useCallback(() => {
    setActiveTool(null);
  }, []);

  // Undo last waypoint
  const handleUndo = useCallback(() => {
    undoManualWaypoint();
    const { manualSegments } = useRouteStore.getState();
    if (manualSegments.length === 0) {
      regenerateRoute({ ignoreInProgress: true });
    }
  }, [undoManualWaypoint, regenerateRoute]);

  // Redo last undone waypoint
  const handleRedo = useCallback(() => {
    redoManualWaypoint();
    const { manualSegments } = useRouteStore.getState();
    if (manualSegments.length === 0) {
      regenerateRoute({ ignoreInProgress: true });
    }
  }, [redoManualWaypoint, regenerateRoute]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (!target) return;

      const isEditable =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable;
      if (isEditable) return;

      const isUndo = (event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === 'z';
      const isRedo =
        ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'z') ||
        ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'y');

      if (isUndo && manualUndoStack.length > 0) {
        event.preventDefault();
        handleUndo();
        return;
      }

      if (isRedo && manualRedoStack.length > 0) {
        event.preventDefault();
        handleRedo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleUndo, handleRedo, manualUndoStack.length, manualRedoStack.length]);

  // Clear all waypoints and route
  const handleClearAll = useCallback(() => {
    resetRoute();
  }, [resetRoute]);

  // Check if undo is available
  const canUndo = manualUndoStack.length > 0;

  // Check if redo is available
  const canRedo = manualRedoStack.length > 0;

  // Check if there's anything to clear
  const canClear = Boolean(
    constraints.viaPoints.length > 0 ||
    constraints.start ||
    constraints.end ||
    (routeGeometry && routeGeometry.length > 0) ||
    (currentRoute && currentRoute.geometry) ||
    manualSegments.length > 0
  );

  // Check if tool is active
  const isToolActive = useCallback(
    (tool: DrawingTool) => {
      return activeTool === tool;
    },
    [activeTool]
  );

  // Get current tool for external checks
  const getActiveTool = useCallback(() => {
    return activeToolRef.current;
  }, []);

  return {
    activeTool,
    setActiveTool,
    toggleWaypointTool,
    clearTool,
    handleUndo,
    handleRedo,
    handleClearAll,
    canUndo,
    canRedo,
    canClear,
    isToolActive,
    getActiveTool,
  };
}
