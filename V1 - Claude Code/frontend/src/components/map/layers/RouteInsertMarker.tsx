'use client';

/**
 * RouteInsertMarker - Shows a ghost marker when hovering near the route line
 * Allows users to drag to insert a new waypoint
 */
import React, { memo, useCallback, useState, useRef } from 'react';
import { Marker } from 'react-map-gl/maplibre';
import { Box } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { MARKER_COLORS } from '../constants';
import type { Coordinate } from '@/types';

interface RouteInsertMarkerProps {
  /** The position to show the insert marker */
  position: Coordinate | null;
  /** Whether the marker should be visible */
  visible: boolean;
  /** Called when drag starts */
  onDragStart?: () => void;
  /** Called when the marker is dragged to a new position */
  onDrag?: (position: Coordinate) => void;
  /** Called when drag ends with the final position */
  onDragEnd?: (position: Coordinate) => void;
}

const RouteInsertMarker: React.FC<RouteInsertMarkerProps> = ({
  position,
  visible,
  onDragStart,
  onDrag,
  onDragEnd,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [dragPosition, setDragPosition] = useState<Coordinate | null>(null);
  const hasStartedDrag = useRef(false);

  const handleDragStart = useCallback(() => {
    setIsDragging(true);
    hasStartedDrag.current = true;
    if (onDragStart) {
      onDragStart();
    }
  }, [onDragStart]);

  const handleDrag = useCallback(
    (event: { lngLat: { lng: number; lat: number } }) => {
      const newPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      setDragPosition(newPosition);
      if (onDrag) {
        onDrag(newPosition);
      }
    },
    [onDrag]
  );

  const handleDragEnd = useCallback(
    (event: { lngLat: { lng: number; lat: number } }) => {
      const finalPosition = { lng: event.lngLat.lng, lat: event.lngLat.lat };
      setIsDragging(false);
      setDragPosition(null);
      hasStartedDrag.current = false;
      if (onDragEnd) {
        onDragEnd(finalPosition);
      }
    },
    [onDragEnd]
  );

  // Don't render if not visible or no position
  if (!visible || !position) {
    return null;
  }

  const displayPosition = dragPosition || position;

  return (
    <Marker
      longitude={displayPosition.lng}
      latitude={displayPosition.lat}
      anchor="center"
      draggable
      onDragStart={handleDragStart}
      onDrag={handleDrag}
      onDragEnd={handleDragEnd}
    >
      <Box
        sx={{
          width: isDragging ? 22 : 18,
          height: isDragging ? 22 : 18,
          borderRadius: '50%',
          bgcolor: isDragging ? MARKER_COLORS.via : 'rgba(59, 130, 246, 0.6)',
          border: 'none',
          boxShadow: isDragging ? '0 2px 8px rgba(0,0,0,0.3)' : 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'grab',
          transition: 'all 0.15s ease',
          '&:hover': {
            bgcolor: MARKER_COLORS.via,
            transform: 'scale(1.1)',
          },
          '&:active': { cursor: 'grabbing' },
        }}
      >
        {!isDragging && (
          <AddIcon
            sx={{
              fontSize: 14,
              color: 'white',
              opacity: 0.9,
            }}
          />
        )}
      </Box>
    </Marker>
  );
};

export default memo(RouteInsertMarker);
