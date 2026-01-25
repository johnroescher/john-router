'use client';

/**
 * MarkerLayer - Renders start marker and via point markers with drag support
 */
import React, { memo, useCallback, useState } from 'react';
import { Marker } from 'react-map-gl/maplibre';
import { Box, Menu, MenuItem, Tooltip } from '@mui/material';
import { useRouteStore } from '@/stores/routeStore';
import { MARKER_COLORS } from '../constants';
import type { Coordinate } from '@/types';

interface MarkerLayerProps {
  onStartDrag?: (position: Coordinate) => void;
  onViaDrag?: (index: number, position: Coordinate) => void;
  onViaRemove?: (index: number) => void;
  onEndDrag?: (position: Coordinate) => void;
  snapToNearestRoadOrTrail?: (position: Coordinate) => Coordinate;
  onMarkerDragStart?: () => void;
  onMarkerDragEnd?: () => void;
}

const MARKER_DIAMETER = 16;
const COORDINATE_MATCH_METERS = 5;

const haversineDistanceMeters = (a: Coordinate, b: Coordinate) => {
  const toRad = (value: number) => (value * Math.PI) / 180;
  const lat1 = toRad(a.lat);
  const lon1 = toRad(a.lng);
  const lat2 = toRad(b.lat);
  const lon2 = toRad(b.lng);
  const dlat = lat2 - lat1;
  const dlon = lon2 - lon1;
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
};

const isSameCoordinate = (a?: Coordinate, b?: Coordinate) => {
  if (!a || !b) return false;
  return haversineDistanceMeters(a, b) <= COORDINATE_MATCH_METERS;
};

const MarkerLayer: React.FC<MarkerLayerProps> = ({
  onStartDrag,
  onViaDrag,
  onViaRemove,
  onEndDrag,
  snapToNearestRoadOrTrail,
  onMarkerDragStart,
  onMarkerDragEnd,
}) => {
  const constraints = useRouteStore((state) => state.constraints);
  const setConstraintStart = useRouteStore((state) => state.setConstraintStart);
  const setConstraintEnd = useRouteStore((state) => state.setConstraintEnd);
  const removeViaPoint = useRouteStore((state) => state.removeViaPoint);
  const moveViaPoint = useRouteStore((state) => state.moveViaPoint);
  const [contextMenu, setContextMenu] = useState<{
    mouseX: number;
    mouseY: number;
    index: number;
  } | null>(null);

  const handleStartDragStart = useCallback(() => {
    if (onMarkerDragStart) {
      onMarkerDragStart();
    }
  }, [onMarkerDragStart]);

  const handleStartDragEnd = useCallback(
    (event: { lngLat: { lng: number; lat: number } }) => {
      const newPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      const snappedPosition = snapToNearestRoadOrTrail ? snapToNearestRoadOrTrail(newPosition) : newPosition;
      setConstraintStart(snappedPosition);
      if (onStartDrag) {
        onStartDrag(snappedPosition);
      }
      if (onMarkerDragEnd) {
        onMarkerDragEnd();
      }
    },
    [setConstraintStart, onStartDrag, snapToNearestRoadOrTrail, onMarkerDragEnd]
  );

  const handleEndDragStart = useCallback(() => {
    if (onMarkerDragStart) {
      onMarkerDragStart();
    }
  }, [onMarkerDragStart]);

  const handleEndDragEnd = useCallback(
    (event: { lngLat: { lng: number; lat: number } }) => {
      const newPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      const snappedPosition = snapToNearestRoadOrTrail ? snapToNearestRoadOrTrail(newPosition) : newPosition;
      setConstraintEnd(snappedPosition);
      if (onEndDrag) {
        onEndDrag(snappedPosition);
      }
      if (onMarkerDragEnd) {
        onMarkerDragEnd();
      }
    },
    [setConstraintEnd, onEndDrag, snapToNearestRoadOrTrail, onMarkerDragEnd]
  );

  const handleViaDragStart = useCallback(() => {
    if (onMarkerDragStart) {
      onMarkerDragStart();
    }
  }, [onMarkerDragStart]);

  const handleViaDragEnd = useCallback(
    (index: number) => (event: { lngLat: { lng: number; lat: number } }) => {
      const newPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      const snappedPosition = snapToNearestRoadOrTrail ? snapToNearestRoadOrTrail(newPosition) : newPosition;
      moveViaPoint(index, snappedPosition);
      if (onViaDrag) {
        onViaDrag(index, snappedPosition);
      }
      if (onMarkerDragEnd) {
        onMarkerDragEnd();
      }
    },
    [moveViaPoint, onViaDrag, snapToNearestRoadOrTrail, onMarkerDragEnd]
  );

  const removeViaPointByIndex = useCallback(
    (index: number) => {
      removeViaPoint(index);
      if (onViaRemove) {
        onViaRemove(index);
      }
    },
    [removeViaPoint, onViaRemove]
  );

  const handleRemoveViaPoint = useCallback(
    (index: number) => (event: React.MouseEvent) => {
      event.stopPropagation();
      event.preventDefault();
      removeViaPointByIndex(index);
    },
    [removeViaPointByIndex]
  );

  const handleContextMenu = useCallback(
    (index: number) => (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      setContextMenu({
        mouseX: event.clientX - 2,
        mouseY: event.clientY - 4,
        index,
      });
    },
    []
  );

  const handleCloseContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleDeleteFromMenu = useCallback(() => {
    if (contextMenu) {
      removeViaPointByIndex(contextMenu.index);
    }
    setContextMenu(null);
  }, [contextMenu, removeViaPointByIndex]);

  const renderStartMarker = () => {
    if (!constraints.start) return null;
    return (
      <Marker
        longitude={constraints.start.lng}
        latitude={constraints.start.lat}
        draggable
        onDragStart={handleStartDragStart}
        onDragEnd={handleStartDragEnd}
        anchor="center"
      >
        <Tooltip title="Start location (drag to move)" placement="top">
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              cursor: 'grab',
              '&:active': { cursor: 'grabbing' },
            }}
          >
            <Box
              sx={{
                width: MARKER_DIAMETER,
                height: MARKER_DIAMETER,
                borderRadius: '50%',
                bgcolor: MARKER_COLORS.start,
                boxSizing: 'border-box',
                boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
              }}
            />
          </Box>
        </Tooltip>
      </Marker>
    );
  };

  const renderViaMarkers = () => {
    const hasExplicitEnd = Boolean(constraints.end);
    const lastViaIndex = constraints.viaPoints.length - 1;
    return constraints.viaPoints.map((point, index) => {
      if (!hasExplicitEnd && index === lastViaIndex) {
        return null;
      }
      if (isSameCoordinate(point, constraints.end)) {
        return null;
      }

      return (
        <Marker
          key={`via-${index}`}
          longitude={point.lng}
          latitude={point.lat}
          anchor="center"
          draggable
          onDragStart={handleViaDragStart}
          onDragEnd={handleViaDragEnd(index)}
        >
          <Tooltip title={`Waypoint ${index + 2} (drag to move, right click for options)`} placement="top">
            <Box
              sx={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'grab',
                '&:active': { cursor: 'grabbing' },
              }}
              onContextMenu={handleContextMenu(index)}
            >
              <Box
                sx={{
                  width: MARKER_DIAMETER,
                  height: MARKER_DIAMETER,
                  borderRadius: '50%',
                  bgcolor: MARKER_COLORS.via,
                  boxSizing: 'border-box',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  fontSize: '8px',
                  fontWeight: 500,
                }}
              >
                {index + 2}
              </Box>
            </Box>
          </Tooltip>
        </Marker>
      );
    });
  };

  const renderEndMarker = () => {
    const hasExplicitEnd = Boolean(constraints.end);
    const lastViaIndex = constraints.viaPoints.length - 1;
    const endPoint = hasExplicitEnd
      ? constraints.end
      : lastViaIndex >= 0
        ? constraints.viaPoints[lastViaIndex]
        : undefined;
    if (!endPoint) return null;

    const handleFinishDragStart = () => {
      if (onMarkerDragStart) {
        onMarkerDragStart();
      }
    };

    const handleFinishDragEnd = (event: { lngLat: { lng: number; lat: number } }) => {
      if (hasExplicitEnd) {
        handleEndDragEnd(event);
        return;
      }
      if (lastViaIndex < 0) return;
      const newPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      const snappedPosition = snapToNearestRoadOrTrail ? snapToNearestRoadOrTrail(newPosition) : newPosition;
      moveViaPoint(lastViaIndex, snappedPosition);
      if (onViaDrag) {
        onViaDrag(lastViaIndex, snappedPosition);
      }
      if (onMarkerDragEnd) {
        onMarkerDragEnd();
      }
    };
    return (
      <Marker
        longitude={endPoint.lng}
        latitude={endPoint.lat}
        anchor="center"
        draggable
        onDragStart={handleFinishDragStart}
        onDragEnd={handleFinishDragEnd}
      >
        <Tooltip title="Finish (drag to move)" placement="top">
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              cursor: 'grab',
              '&:active': { cursor: 'grabbing' },
            }}
          >
            <Box
              sx={{
                width: MARKER_DIAMETER,
                height: MARKER_DIAMETER,
                borderRadius: '50%',
                backgroundImage:
                  'linear-gradient(45deg, #000 25%, transparent 25%), linear-gradient(-45deg, #000 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #000 75%), linear-gradient(-45deg, transparent 75%, #000 75%)',
                backgroundSize: '6px 6px',
                backgroundPosition: '0 0, 0 3px, 3px -3px, -3px 0',
                backgroundColor: '#fff',
                boxSizing: 'border-box',
                boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
              }}
            />
          </Box>
        </Tooltip>
      </Marker>
    );
  };

  return (
    <>
      {renderStartMarker()}
      {renderViaMarkers()}
      {renderEndMarker()}
      <Menu
        open={Boolean(contextMenu)}
        onClose={handleCloseContextMenu}
        anchorReference="anchorPosition"
        anchorPosition={
          contextMenu ? { top: contextMenu.mouseY, left: contextMenu.mouseX } : undefined
        }
      >
        <MenuItem onClick={handleDeleteFromMenu}>Delete</MenuItem>
      </Menu>
    </>
  );
};

export default memo(MarkerLayer);
