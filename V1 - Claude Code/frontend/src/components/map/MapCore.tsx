'use client';

/**
 * MapCore - Main map component using react-map-gl/maplibre with controlled state
 */
import React, { useRef, useCallback, useEffect, useState, memo } from 'react';
import Map, { type MapRef, type MapLayerMouseEvent } from 'react-map-gl/maplibre';
import maplibregl, { type StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Box, Chip, Menu, MenuItem } from '@mui/material';

import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';
import { buildRouteDistanceData } from '@/lib/surfaceInference';

import { useMapViewState } from './hooks/useMapViewState';
import { useRouteInteraction } from './hooks/useRouteInteraction';
import { useDrawingMode } from './hooks/useDrawingMode';
import { useManualRouteAnalysis } from './hooks/useManualRouteAnalysis';
import { useRouteRegeneration } from './hooks/useRouteRegeneration';
import { useSurfaceEnrichment } from './hooks/useSurfaceEnrichment';

import RouteLayer from './layers/RouteLayer';
import MarkerLayer from './layers/MarkerLayer';
import SearchMarkerLayer from './layers/SearchMarkerLayer';
import HoverMarker from './layers/HoverMarker';
import RouteInsertMarker from './layers/RouteInsertMarker';
import MapControls from './MapControls';
import DrawingTools from './DrawingTools';

import { FALLBACK_STYLE, MAP_STYLES, MAP_SETTINGS, ROUTE_COLORS } from './constants';
import type { MapStyleKey } from './constants';
import type { Coordinate } from '@/types';

const MapCore: React.FC = () => {
  const mapRef = useRef<MapRef | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapLayer = useUIStore((state) => state.mapLayer);
  const setProfileHover = useUIStore((state) => state.setProfileHover);
  const clearProfileHover = useUIStore((state) => state.clearProfileHover);
  const searchMarker = useUIStore((state) => state.searchMarker);
  const clearSearchMarker = useUIStore((state) => state.clearSearchMarker);
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const constraints = useRouteStore((state) => state.constraints);
  const manualSegments = useRouteStore((state) => state.manualSegments);
  const isRoutingDegraded = useRouteStore((state) => state.isRoutingDegraded);

  // Custom hooks
  const {
    viewState,
    onMove,
    pendingCommand,
    clearPendingCommand,
  } = useMapViewState();

  const {
    handleMapClick,
    handleStartDrag,
    getNearestPointOnRoute,
    getInsertionIndex,
    isNearRoute,
    snapToNearestRoadOrTrail,
  } = useRouteInteraction(mapRef);

  // State for insert marker
  const [insertMarkerPosition, setInsertMarkerPosition] = useState<Coordinate | null>(null);
  const [isInsertMarkerVisible, setIsInsertMarkerVisible] = useState(false);
  const [isDraggingInsertMarker, setIsDraggingInsertMarker] = useState(false);
  const routeInsertActiveRef = useRef(false);
  const insertHandledRef = useRef(false);
  const insertDragPendingRef = useRef<Coordinate | null>(null);
  const insertDragStartPointRef = useRef<{ x: number; y: number } | null>(null);
  const insertViaPoint = useRouteStore((state) => state.insertViaPoint);
  const [isDraggingMap, setIsDraggingMap] = useState(false);
  const [isDraggingMarker, setIsDraggingMarker] = useState(false);
  const markerDragEndRef = useRef(false);
  const [routeMenu, setRouteMenu] = useState<{
    mouseX: number;
    mouseY: number;
    position: Coordinate;
  } | null>(null);

  const {
    activeTool,
    setActiveTool,
    toggleWaypointTool,
    handleUndo,
    handleRedo,
    handleClearAll,
    canUndo,
    canRedo,
    canClear,
  } = useDrawingMode(mapRef);

  const { regenerateRoute, regenerateRoutePartially } = useRouteRegeneration();

  // Hook to fetch elevation analysis for manually drawn routes
  useManualRouteAnalysis();

  // Hook to enrich surface data from OpenStreetMap
  useSurfaceEnrichment();

  // Handle marker drag start
  const handleMarkerDragStart = useCallback(() => {
    setIsDraggingMarker(true);
    // Set flag immediately to prevent clicks during drag
    markerDragEndRef.current = true;
  }, []);

  // Handle marker drag end
  const handleMarkerDragEnd = useCallback(() => {
    setIsDraggingMarker(false);
    // Keep flag set for a brief moment after drag ends to prevent click events
    // that might fire synchronously with drag end
    setTimeout(() => {
      markerDragEndRef.current = false;
    }, 300);
  }, []);

  // Check if a coordinate is near any existing waypoint
  const isNearExistingWaypoint = useCallback(
    (coord: Coordinate, thresholdPx: number = 20): boolean => {
      const map = mapRef.current?.getMap();
      if (!map) return false;

      const clickedPoint = map.project([coord.lng, coord.lat]);

      // Check start point
      if (constraints.start) {
        const startPoint = map.project([constraints.start.lng, constraints.start.lat]);
        const dx = clickedPoint.x - startPoint.x;
        const dy = clickedPoint.y - startPoint.y;
        if (Math.sqrt(dx * dx + dy * dy) <= thresholdPx) {
          return true;
        }
      }

      // Check via points
      for (const point of constraints.viaPoints) {
        const waypointPoint = map.project([point.lng, point.lat]);
        const dx = clickedPoint.x - waypointPoint.x;
        const dy = clickedPoint.y - waypointPoint.y;
        if (Math.sqrt(dx * dx + dy * dy) <= thresholdPx) {
          return true;
        }
      }

      // Check end point
      if (constraints.end) {
        const endPoint = map.project([constraints.end.lng, constraints.end.lat]);
        const dx = clickedPoint.x - endPoint.x;
        const dy = clickedPoint.y - endPoint.y;
        if (Math.sqrt(dx * dx + dy * dy) <= thresholdPx) {
          return true;
        }
      }

      return false;
    },
    [constraints, mapRef]
  );

  // Handle via point drag - regenerate route when a waypoint is moved
  const handleViaDrag = useCallback(
    (index: number, _position: { lng: number; lat: number }) => {
      regenerateRoutePartially({ type: 'move', viaIndex: index });
    },
    [regenerateRoutePartially]
  );

  // Handle via point removal - regenerate route when a waypoint is deleted
  const handleViaRemove = useCallback(
    (index: number) => {
      regenerateRoutePartially({ type: 'remove', viaIndex: index });
    },
    [regenerateRoutePartially]
  );

  // Handle end marker drag - regenerate final segment when end is moved
  const handleEndDrag = useCallback(
    (_position: { lng: number; lat: number }) => {
      regenerateRoutePartially({ type: 'end' });
    },
    [regenerateRoutePartially]
  );

  // Handle start marker drag - regenerate route when start is moved
  const handleStartDragWithRegenerate = useCallback(
    (position: { lng: number; lat: number }) => {
      handleStartDrag(position);
      regenerateRoutePartially({ type: 'start' });
    },
    [handleStartDrag, regenerateRoutePartially]
  );

  // Get current map style URL
  const mapStyle = MAP_STYLES[mapLayer as MapStyleKey] || MAP_STYLES.default;
  const [activeMapStyle, setActiveMapStyle] = useState<string | StyleSpecification>(mapStyle);
  const hasFallenBackRef = useRef(false);

  useEffect(() => {
    setActiveMapStyle(mapStyle);
    hasFallenBackRef.current = false;
  }, [mapStyle]);

  const addUnpavedPattern = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map || map.hasImage('unpaved-stripe')) return;

    const size = 8;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = ROUTE_COLORS.main;
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 3, size);

    const imageData = ctx.getImageData(0, 0, size, size);
    map.addImage('unpaved-stripe', imageData, { pixelRatio: 1 });
  }, []);

  // Ensure map resizes with its container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resize = () => {
      const map = mapRef.current?.getMap();
      if (map) {
        map.resize();
      }
    };

    const observer = new ResizeObserver(resize);
    observer.observe(container);

    const raf = requestAnimationFrame(resize);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);

  // Handle map load - trigger resize to ensure WebGL canvas has correct dimensions
  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) {
      addUnpavedPattern();
      requestAnimationFrame(() => {
        map.resize();
        const attribution = map
          .getContainer()
          .querySelector<HTMLDetailsElement>('details.maplibregl-ctrl-attrib.maplibregl-compact');
        if (attribution) {
          attribution.open = false;
          attribution.classList.remove('maplibregl-compact-show');
        }
      });
    }
  }, [addUnpavedPattern]);

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const handleStyleData = () => addUnpavedPattern();
    map.on('styledata', handleStyleData);
    return () => {
      map.off('styledata', handleStyleData);
    };
  }, [addUnpavedPattern, activeMapStyle]);

  const handleMapError = useCallback((event: maplibregl.ErrorEvent) => {
    if (hasFallenBackRef.current) return;

    const message = event?.error?.message || 'Unknown map error';
    console.warn('[MapCore] Map error detected, falling back to raster style:', message);
    hasFallenBackRef.current = true;
    setActiveMapStyle(FALLBACK_STYLE);
  }, []);

  // Handle map click (for waypoint drawing)
  const handleClick = useCallback(
    async (event: MapLayerMouseEvent) => {
      if (routeInsertActiveRef.current || isDraggingInsertMarker) {
        return;
      }
      // Prevent clicks during or immediately after marker drag to avoid creating new waypoints
      if (markerDragEndRef.current || isDraggingMarker) {
        return;
      }
      if (activeTool === 'waypoint' && !isDraggingMap) {
        const clickedCoord = { lng: event.lngLat.lng, lat: event.lngLat.lat };
        
        // If clicking near an existing waypoint, don't create a new one
        // This prevents creating duplicate waypoints when dragging
        if (isNearExistingWaypoint(clickedCoord)) {
          return;
        }
        
        if (routeGeometry && routeGeometry.length > 1 && isNearRoute(clickedCoord)) {
          const nearestPoint = getNearestPointOnRoute(clickedCoord);
          setRouteMenu({
            mouseX: event.originalEvent.clientX,
            mouseY: event.originalEvent.clientY,
            position: nearestPoint,
          });
          return;
        }
        await handleMapClick(event);
      }
    },
    [
      activeTool,
      handleMapClick,
      isDraggingMap,
      isDraggingMarker,
      isNearRoute,
      routeGeometry,
      getNearestPointOnRoute,
      isDraggingInsertMarker,
      isNearExistingWaypoint,
    ]
  );

  const handleDragStart = useCallback(() => {
    if (activeTool !== 'waypoint') return;
    const map = mapRef.current?.getMap();
    if (map) {
      map.getCanvas().style.cursor = 'grab';
      map.getContainer().style.cursor = 'grab';
    }
    setIsDraggingMap(true);
  }, [activeTool]);

  const handleDragEnd = useCallback(() => {
    if (activeTool !== 'waypoint') return;
    const map = mapRef.current?.getMap();
    if (map) {
      map.getCanvas().style.cursor = 'crosshair';
      map.getContainer().style.cursor = 'crosshair';
    }
    setIsDraggingMap(false);
  }, [activeTool]);

  // Handle mouse move for profile hover sync and insert marker
  const handleMouseMove = useCallback(
    (event: MapLayerMouseEvent) => {
      if (activeTool === 'waypoint') {
        // cursor managed by map cursor effect
      }

      const map = mapRef.current?.getMap();
      if (!map) return;

      // If we have a pending insert drag, see if the user moved enough to start dragging
      if (!isDraggingInsertMarker && insertDragPendingRef.current && insertDragStartPointRef.current) {
        const currentPoint = map.project([event.lngLat.lng, event.lngLat.lat]);
        const dx = currentPoint.x - insertDragStartPointRef.current.x;
        const dy = currentPoint.y - insertDragStartPointRef.current.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance >= 6) {
          map.dragPan.disable();
          routeInsertActiveRef.current = true;
          setIsDraggingInsertMarker(true);
          setInsertMarkerPosition(insertDragPendingRef.current);
          setIsInsertMarkerVisible(true);
        }
      }

      // Update insert marker position while dragging it
      if (isDraggingInsertMarker) {
        const { lngLat } = event;
        setInsertMarkerPosition({ lng: lngLat.lng, lat: lngLat.lat });
        return;
      }

      const { lngLat } = event;
      const coord = { lng: lngLat.lng, lat: lngLat.lat };

      const mousePoint = map.project([coord.lng, coord.lat]);
      const isNearWaypoint = constraints.viaPoints.some((point) => {
        const waypointPoint = map.project([point.lng, point.lat]);
        const dx = mousePoint.x - waypointPoint.x;
        const dy = mousePoint.y - waypointPoint.y;
        return Math.sqrt(dx * dx + dy * dy) <= 18;
      });

      if (isNearWaypoint) {
        map.getCanvas().style.cursor = 'pointer';
        map.getContainer().style.cursor = 'pointer';
        setIsInsertMarkerVisible(false);
        setInsertMarkerPosition(null);
        clearProfileHover();
        return;
      }

      if (activeTool !== 'waypoint') {
        map.getCanvas().style.cursor = '';
        map.getContainer().style.cursor = '';
      }

      if (!routeGeometry || routeGeometry.length < 2) {
        setIsInsertMarkerVisible(false);
        setInsertMarkerPosition(null);
        return;
      }

      // Check if mouse is near the route
      const nearestPoint = getNearestPointOnRoute(coord);
      const nearestMapPoint = map.project([nearestPoint.lng, nearestPoint.lat]);
      const distance = Math.sqrt(
        Math.pow(mousePoint.x - nearestMapPoint.x, 2) +
        Math.pow(mousePoint.y - nearestMapPoint.y, 2)
      );

      // Show insert marker if within 15px of route
      if (distance <= 15) {
        setInsertMarkerPosition(nearestPoint);
        setIsInsertMarkerVisible(true);
      } else {
        setIsInsertMarkerVisible(false);
        setInsertMarkerPosition(null);
      }

      // Only show profile hover if within 20px of route
      if (distance > 20) {
        clearProfileHover();
        return;
      }

      // Calculate distance along route for the hover point
      const routeDistanceData = buildRouteDistanceData(routeGeometry);
      if (!routeDistanceData) return;

      // Find distance along route for this point
      let closestDistance = 0;
      let minDist = Infinity;

      for (let i = 0; i < routeGeometry.length; i++) {
        const pt = routeGeometry[i];
        const d = Math.pow(pt[0] - nearestPoint.lng, 2) + Math.pow(pt[1] - nearestPoint.lat, 2);
        if (d < minDist) {
          minDist = d;
          closestDistance = routeDistanceData.cumulative[i];
        }
      }

      setProfileHover({
        distanceMeters: closestDistance,
        coordinate: nearestPoint,
        source: 'map',
      });
    },
    [
      activeTool,
      routeGeometry,
      constraints.viaPoints,
      getNearestPointOnRoute,
      setProfileHover,
      clearProfileHover,
      isDraggingInsertMarker,
      isDraggingMap,
    ]
  );

  // Handle mouse leave
  const handleMouseLeave = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) {
      map.getCanvas().style.cursor = activeTool === 'waypoint' && !isDraggingMap ? 'none' : '';
    }
    clearProfileHover();
    insertDragPendingRef.current = null;
    insertDragStartPointRef.current = null;
    if (isDraggingInsertMarker) {
      map?.dragPan.enable();
      setIsDraggingInsertMarker(false);
    }
    setIsInsertMarkerVisible(false);
    setInsertMarkerPosition(null);
  }, [activeTool, clearProfileHover, isDraggingInsertMarker, isDraggingMap]);

  // Handle insert marker drag start
  const handleInsertMarkerDragStart = useCallback(() => {
    setIsDraggingInsertMarker(true);
  }, []);

  // Handle insert marker drag end - insert the new waypoint
  const handleInsertMarkerDragEnd = useCallback(
    (position: Coordinate) => {
      if (insertHandledRef.current) {
        return;
      }
      insertHandledRef.current = true;
      setTimeout(() => {
        insertHandledRef.current = false;
      }, 100);

      setIsDraggingInsertMarker(false);
      setIsInsertMarkerVisible(false);
      setInsertMarkerPosition(null);

      // Calculate where to insert this waypoint based on its position along the route
      const insertIndex = getInsertionIndex(position);

      // Insert the waypoint at the correct position
      insertViaPoint(insertIndex, position);

      // Regenerate only the affected segment
      regenerateRoutePartially({ type: 'insert', viaIndex: insertIndex });
    },
    [getInsertionIndex, insertViaPoint, regenerateRoutePartially]
  );

  const handleMouseDown = useCallback(
    (event: MapLayerMouseEvent) => {
      if (activeTool !== 'waypoint') return;
      if (!routeGeometry || routeGeometry.length < 2) return;
      const { lngLat } = event;
      const coord = { lng: lngLat.lng, lat: lngLat.lat };
      if (!isNearRoute(coord)) return;

      const map = mapRef.current?.getMap();
      if (!map) return;
      insertDragPendingRef.current = getNearestPointOnRoute(coord);
      const startPoint = map.project([lngLat.lng, lngLat.lat]);
      insertDragStartPointRef.current = { x: startPoint.x, y: startPoint.y };
    },
    [activeTool, routeGeometry, isNearRoute, getNearestPointOnRoute]
  );

  const handleMouseUp = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (isDraggingInsertMarker) {
      map?.dragPan.enable();
      const finalPosition = insertMarkerPosition;
      routeInsertActiveRef.current = false;
      insertDragPendingRef.current = null;
      insertDragStartPointRef.current = null;
      if (finalPosition) {
        handleInsertMarkerDragEnd(finalPosition);
      } else {
        setIsDraggingInsertMarker(false);
        setIsInsertMarkerVisible(false);
        setInsertMarkerPosition(null);
      }
      return;
    }

    // Clear any pending insert without starting a drag
    insertDragPendingRef.current = null;
    insertDragStartPointRef.current = null;
  }, [handleInsertMarkerDragEnd, insertMarkerPosition, isDraggingInsertMarker]);

  const handleRouteMenuClose = useCallback(() => {
    setRouteMenu(null);
  }, []);

  const handleRouteMenuAddWaypoint = useCallback(() => {
    if (!routeMenu) return;
    const insertIndex = getInsertionIndex(routeMenu.position);
    insertViaPoint(insertIndex, routeMenu.position);
    regenerateRoutePartially({ type: 'insert', viaIndex: insertIndex });
    setRouteMenu(null);
  }, [routeMenu, getInsertionIndex, insertViaPoint, regenerateRoutePartially]);

  // Process pending map commands (flyTo, fitBounds)
  useEffect(() => {
    if (!pendingCommand || !mapRef.current) return;

    const map = mapRef.current.getMap();
    if (!map) return;

    if (pendingCommand.type === 'flyTo') {
      map.flyTo(pendingCommand.params as maplibregl.FlyToOptions);
    } else if (pendingCommand.type === 'fitBounds') {
      const params = pendingCommand.params as {
        bounds: [[number, number], [number, number]];
        padding?: number;
        duration?: number;
        maxZoom?: number;
      };
      map.fitBounds(params.bounds, {
        padding: params.padding,
        duration: params.duration,
        maxZoom: params.maxZoom,
      });
    }

    clearPendingCommand();
  }, [pendingCommand, clearPendingCommand]);

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    if (activeTool !== 'waypoint') {
      map.getCanvas().style.cursor = '';
      map.getContainer().style.cursor = '';
      return;
    }

    const cursorStyle = isDraggingMap ? 'grab' : 'crosshair';
    const enforceCursor = () => {
      map.getCanvas().style.cursor = cursorStyle;
      map.getContainer().style.cursor = cursorStyle;
    };

    enforceCursor();
    map.on('mousemove', enforceCursor);
    map.on('mouseenter', enforceCursor);
    map.on('mouseout', enforceCursor);
    map.on('dragend', enforceCursor);
    map.on('moveend', enforceCursor);

    return () => {
      map.off('mousemove', enforceCursor);
      map.off('mouseenter', enforceCursor);
      map.off('mouseout', enforceCursor);
      map.off('dragend', enforceCursor);
      map.off('moveend', enforceCursor);
      map.getCanvas().style.cursor = '';
      map.getContainer().style.cursor = '';
    };
  }, [activeTool, isDraggingMap]);

  useEffect(() => {
    if (!searchMarker?.routeSnapshot) return;
    const snapshot = searchMarker.routeSnapshot;
    const currentSignature = {
      viaPointsCount: constraints.viaPoints.length,
      routeGeometryLength: routeGeometry?.length ?? 0,
      manualSegmentsLength: manualSegments.length,
      hasEnd: Boolean(constraints.end),
    };
    const signatureChanged =
      snapshot.viaPointsCount !== currentSignature.viaPointsCount ||
      snapshot.routeGeometryLength !== currentSignature.routeGeometryLength ||
      snapshot.manualSegmentsLength !== currentSignature.manualSegmentsLength ||
      snapshot.hasEnd !== currentSignature.hasEnd;
    if (signatureChanged) {
      clearSearchMarker();
    }
  }, [
    searchMarker,
    constraints.viaPoints.length,
    constraints.end,
    routeGeometry,
    manualSegments.length,
    clearSearchMarker,
  ]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
      }}
    >
      <Map
        ref={mapRef}
        mapLib={maplibregl}
        {...viewState}
        onMove={onMove}
        onLoad={handleMapLoad}
        onError={handleMapError}
        onClick={handleClick}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        mapStyle={activeMapStyle}
        style={{ width: '100%', height: '100%' }}
        {...MAP_SETTINGS}
        cursor={activeTool === 'waypoint' ? (isDraggingMap ? 'grab' : 'crosshair') : undefined}
        attributionControl
        styleDiffing={false}
      >
        {/* Route line layer */}
        <RouteLayer />

        {/* Start and via point markers */}
        <MarkerLayer
          onStartDrag={handleStartDragWithRegenerate}
          onViaDrag={handleViaDrag}
          onViaRemove={handleViaRemove}
          onEndDrag={handleEndDrag}
          snapToNearestRoadOrTrail={snapToNearestRoadOrTrail}
          onMarkerDragStart={handleMarkerDragStart}
          onMarkerDragEnd={handleMarkerDragEnd}
        />

        {/* Search location marker */}
        <SearchMarkerLayer onActivateWaypointTool={() => setActiveTool('waypoint')} />

        {/* Hover marker from elevation profile */}
        <HoverMarker />

        {/* Insert marker - shows when hovering near route line */}
        <RouteInsertMarker
          position={insertMarkerPosition}
          visible={isInsertMarkerVisible}
          onDragStart={handleInsertMarkerDragStart}
          onDragEnd={handleInsertMarkerDragEnd}
        />

        {/* Map controls (zoom, style picker) */}
        <MapControls mapRef={mapRef} />

        {/* Drawing tools */}
        <DrawingTools
          activeTool={activeTool}
          onToggleWaypoint={toggleWaypointTool}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onClear={handleClearAll}
          canUndo={canUndo}
          canRedo={canRedo}
          canClear={canClear}
        />
      </Map>
      {isRoutingDegraded && (
        <Box
          sx={{
            position: 'absolute',
            top: 12,
            left: 12,
            zIndex: 10,
            pointerEvents: 'none',
          }}
        >
          <Chip color="warning" size="small" label="Routing failed; segment not updated" />
        </Box>
      )}
      <Menu
        open={Boolean(routeMenu)}
        onClose={handleRouteMenuClose}
        anchorReference="anchorPosition"
        anchorPosition={routeMenu ? { top: routeMenu.mouseY, left: routeMenu.mouseX } : undefined}
      >
        <MenuItem onClick={handleRouteMenuAddWaypoint}>Add Waypoint</MenuItem>
      </Menu>
    </div>
  );
};

export default memo(MapCore);
