'use client';

/**
 * MapContainer - Wrapper component that renders the map
 * This component should be dynamically imported with { ssr: false }
 * 
 * Key: We use CSS-based sizing (100% width/height) instead of measuring dimensions.
 * This avoids race conditions with getBoundingClientRect() that can cause the map
 * to not render until a browser reflow is triggered (e.g., opening dev console).
 */
import React, { memo } from 'react';
import { Box } from '@mui/material';
import MapCore from './MapCore';

const MapContainer: React.FC = () => {
  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
      }}
    >
      <MapCore />
    </Box>
  );
};

export default memo(MapContainer);
