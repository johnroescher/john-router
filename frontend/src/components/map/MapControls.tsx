'use client';

/**
 * MapControls - Zoom controls and map style picker
 */
import React, { memo, useState, useCallback } from 'react';
import { Box, IconButton, Menu, MenuItem, Tooltip } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import MyLocationIcon from '@mui/icons-material/MyLocation';
import LayersIcon from '@mui/icons-material/Layers';
import type { MapRef } from 'react-map-gl/maplibre';
import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';
import { MAP_STYLE_OPTIONS, type MapStyleKey } from './constants';

interface MapControlsProps {
  mapRef: React.RefObject<MapRef | null>;
}

const MapControls: React.FC<MapControlsProps> = ({ mapRef }) => {
  const [styleAnchorEl, setStyleAnchorEl] = useState<null | HTMLElement>(null);
  const mapLayer = useUIStore((state) => state.mapLayer);
  const setMapLayer = useUIStore((state) => state.setMapLayer);
  const constraints = useRouteStore((state) => state.constraints);
  const flyMapTo = useUIStore((state) => state.flyMapTo);

  // Zoom in
  const handleZoomIn = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) {
      map.zoomIn({ duration: 300 });
    }
  }, [mapRef]);

  // Zoom out
  const handleZoomOut = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) {
      map.zoomOut({ duration: 300 });
    }
  }, [mapRef]);

  // Center on start location
  const handleRecenter = useCallback(() => {
    if (!constraints.start) return;
    flyMapTo({
      lat: constraints.start.lat,
      lng: constraints.start.lng,
      zoom: 14,
      reason: 'user_recenter',
    });
  }, [constraints.start, flyMapTo]);

  // Open style picker menu
  const handleStyleMenuOpen = useCallback((event: React.MouseEvent<HTMLElement>) => {
    setStyleAnchorEl(event.currentTarget);
  }, []);

  // Close style picker menu
  const handleStyleMenuClose = useCallback(() => {
    setStyleAnchorEl(null);
  }, []);

  // Change map style
  const handleStyleChange = useCallback(
    (styleId: MapStyleKey) => {
      setMapLayer(styleId);
      setStyleAnchorEl(null);
    },
    [setMapLayer]
  );

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 12,
        right: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 0.75,
        zIndex: 1,
      }}
    >
      {/* Zoom controls */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          bgcolor: 'background.paper',
          borderRadius: 1,
          overflow: 'hidden',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Tooltip title="Zoom in" placement="left">
          <IconButton
            size="small"
            onClick={handleZoomIn}
            sx={{
              borderRadius: 0,
              width: 32,
              height: 32,
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            <AddIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="Zoom out" placement="left">
          <IconButton
            size="small"
            onClick={handleZoomOut}
            sx={{
              borderRadius: 0,
              width: 32,
              height: 32,
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            <RemoveIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Recenter button */}
      <Box
        sx={{
          bgcolor: 'background.paper',
          borderRadius: 1,
          overflow: 'hidden',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Tooltip title={constraints.start ? 'Center on start' : 'Set a start to recenter'} placement="left">
          <span>
            <IconButton
              size="small"
              onClick={handleRecenter}
              disabled={!constraints.start}
              sx={{
                width: 32,
                height: 32,
                '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
              }}
            >
              <MyLocationIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* Map style picker */}
      <Box
        sx={{
          bgcolor: 'background.paper',
          borderRadius: 1,
          overflow: 'hidden',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.1)',
        }}
      >
        <Tooltip title="Map style" placement="left">
          <IconButton
            size="small"
            onClick={handleStyleMenuOpen}
            sx={{
              width: 32,
              height: 32,
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.04)' },
            }}
          >
            <LayersIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
      </Box>

      <Menu
        anchorEl={styleAnchorEl}
        open={Boolean(styleAnchorEl)}
        onClose={handleStyleMenuClose}
        anchorOrigin={{
          vertical: 'top',
          horizontal: 'left',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
      >
        {MAP_STYLE_OPTIONS.map((option) => (
          <MenuItem
            key={option.id}
            selected={mapLayer === option.id}
            onClick={() => handleStyleChange(option.id)}
            sx={{
              fontSize: '0.8125rem',
              '&.Mui-selected': {
                bgcolor: 'rgba(158, 123, 47, 0.08)',
              },
            }}
          >
            {option.label}
          </MenuItem>
        ))}
      </Menu>
    </Box>
  );
};

export default memo(MapControls);
