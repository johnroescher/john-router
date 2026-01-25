'use client';

/**
 * HoverMarker - Shows position on route when hovering over elevation profile
 */
import React, { memo, useMemo } from 'react';
import { Marker } from 'react-map-gl/maplibre';
import { Box } from '@mui/material';
import { useUIStore } from '@/stores/uiStore';
import { MARKER_COLORS } from '../constants';

const HoverMarker: React.FC = () => {
  const profileHover = useUIStore((state) => state.profileHover);

  // Don't render if no hover state or if source is map (avoid duplicate markers)
  const shouldRender = useMemo(() => {
    return profileHover && profileHover.source === 'chart' && profileHover.coordinate;
  }, [profileHover]);

  if (!shouldRender || !profileHover) {
    return null;
  }

  return (
    <Marker
      longitude={profileHover.coordinate.lng}
      latitude={profileHover.coordinate.lat}
      anchor="center"
    >
      <Box
        sx={{
          width: 16,
          height: 16,
          borderRadius: '50%',
          bgcolor: MARKER_COLORS.hover,
          boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
          transition: 'transform 0.1s ease-out',
          '&:hover': {
            transform: 'scale(1.2)',
          },
        }}
      />
    </Marker>
  );
};

export default memo(HoverMarker);
