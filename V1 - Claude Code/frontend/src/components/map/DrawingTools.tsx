'use client';

/**
 * DrawingTools - Waypoint drawing toolbar with undo/redo/clear
 */
import React, { memo } from 'react';
import { Paper, IconButton, Tooltip } from '@mui/material';
import AddLocationIcon from '@mui/icons-material/AddLocation';
import UndoIcon from '@mui/icons-material/Undo';
import RedoIcon from '@mui/icons-material/Redo';
import ClearIcon from '@mui/icons-material/Clear';
import type { DrawingTool } from './hooks/useDrawingMode';

interface DrawingToolsProps {
  activeTool: DrawingTool;
  onToggleWaypoint: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  canUndo: boolean;
  canRedo: boolean;
  canClear: boolean;
}

const DrawingTools: React.FC<DrawingToolsProps> = ({
  activeTool,
  onToggleWaypoint,
  onUndo,
  onRedo,
  onClear,
  canUndo,
  canRedo,
  canClear,
}) => {
  const isWaypointActive = activeTool === 'waypoint';
  const leftRadius = '4px 0 0 4px';
  const rightRadius = '0 4px 4px 0';

  return (
    <Paper
      elevation={2}
      sx={{
        position: 'absolute',
        top: 16,
        left: 16,
        display: 'flex',
        alignItems: 'center',
        gap: 0,
        p: 0,
        height: 32,
        width: 'fit-content',
        borderRadius: 1,
        overflow: 'hidden',
        zIndex: 1,
      }}
    >
      {/* Waypoint tool toggle */}
      <Tooltip title={isWaypointActive ? 'Stop adding waypoints' : 'Add waypoints (click on map)'}>
        <IconButton
          size="small"
          onClick={onToggleWaypoint}
          aria-pressed={isWaypointActive}
          sx={{
            width: 32,
            height: 32,
            borderRadius: leftRadius,
            '&:hover': { bgcolor: 'action.hover', borderRadius: leftRadius },
            '&:active, &.Mui-focusVisible, &.Mui-disabled': { borderRadius: leftRadius },
            ...(isWaypointActive && {
              bgcolor: 'primary.main',
              color: 'primary.contrastText',
              borderRadius: leftRadius,
              '&:hover': { bgcolor: 'primary.dark', borderRadius: leftRadius },
              '&:active, &.Mui-focusVisible': { borderRadius: leftRadius },
            }),
          }}
        >
          <AddLocationIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Undo button */}
      <Tooltip title="Undo last waypoint">
        <span>
          <IconButton
            size="small"
            onClick={onUndo}
            disabled={!canUndo}
            sx={{
              width: 32,
              height: 32,
              borderRadius: 0,
              '&:hover': { bgcolor: 'action.hover', borderRadius: 0 },
              '&:active, &.Mui-focusVisible, &.Mui-disabled': { borderRadius: 0 },
            }}
          >
            <UndoIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      {/* Redo button */}
      <Tooltip title="Redo waypoint">
        <span>
          <IconButton
            size="small"
            onClick={onRedo}
            disabled={!canRedo}
            sx={{
              width: 32,
              height: 32,
              borderRadius: 0,
              '&:hover': { bgcolor: 'action.hover', borderRadius: 0 },
              '&:active, &.Mui-focusVisible, &.Mui-disabled': { borderRadius: 0 },
            }}
          >
            <RedoIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      {/* Clear all button */}
      <Tooltip title="Clear all waypoints">
        <span>
          <IconButton
            size="small"
            onClick={onClear}
            disabled={!canClear}
            color="error"
            sx={{
              width: 32,
              height: 32,
              borderRadius: rightRadius,
              '&:hover': {
                bgcolor: 'error.light',
                color: 'error.contrastText',
                borderRadius: rightRadius,
              },
              '&:active, &.Mui-focusVisible, &.Mui-disabled': { borderRadius: rightRadius },
            }}
          >
            <ClearIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    </Paper>
  );
};

export default memo(DrawingTools);
