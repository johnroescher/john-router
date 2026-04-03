'use client';

/**
 * SearchMarkerLayer - Renders the last search location marker.
 */
import React, { memo, useCallback, useState } from 'react';
import { Marker } from 'react-map-gl/maplibre';
import { Box, Menu, MenuItem, Tooltip } from '@mui/material';
import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';

interface SearchMarkerLayerProps {
  onActivateWaypointTool?: () => void;
}

const SearchMarkerLayer: React.FC<SearchMarkerLayerProps> = ({ onActivateWaypointTool }) => {
  const searchMarker = useUIStore((state) => state.searchMarker);
  const clearSearchMarker = useUIStore((state) => state.clearSearchMarker);
  const addViaPoint = useRouteStore((state) => state.addViaPoint);
  const [contextMenu, setContextMenu] = useState<{
    mouseX: number;
    mouseY: number;
  } | null>(null);

  const handleOpenMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      mouseX: event.clientX - 2,
      mouseY: event.clientY - 4,
    });
  }, []);

  const handleCloseMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleCreateWaypoint = useCallback(() => {
    if (!searchMarker) return;
    addViaPoint(searchMarker.position);
    onActivateWaypointTool?.();
    clearSearchMarker();
    setContextMenu(null);
  }, [addViaPoint, clearSearchMarker, searchMarker, onActivateWaypointTool]);

  if (!searchMarker) return null;

  return (
    <>
      <Marker
        longitude={searchMarker.position.lng}
        latitude={searchMarker.position.lat}
        anchor="center"
      >
        <Tooltip title={searchMarker.label ?? 'Search location'} placement="top">
          <Box
            onClick={handleOpenMenu}
            sx={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              bgcolor: 'rgba(20, 20, 20, 0.85)',
              boxShadow: '0 1px 4px rgba(0,0,0,0.25)',
              cursor: 'pointer',
            }}
          />
        </Tooltip>
      </Marker>
      <Menu
        open={Boolean(contextMenu)}
        onClose={handleCloseMenu}
        anchorReference="anchorPosition"
        anchorPosition={contextMenu ? { top: contextMenu.mouseY, left: contextMenu.mouseX } : undefined}
      >
        <MenuItem onClick={handleCreateWaypoint}>Create a waypoint</MenuItem>
      </Menu>
    </>
  );
};

export default memo(SearchMarkerLayer);
