'use client';

import { Box } from '@mui/material';
import { useCallback, useEffect, useRef } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { useUIStore } from '@/stores/uiStore';
import ChatPanel from '@/components/chat/ChatPanel';

export default function Sidebar() {
  const { sidebarWidth, sidebarOpen, setSidebarWidth } = useUIStore();
  const isResizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const onMouseMove = useCallback((event: MouseEvent) => {
    if (!isResizingRef.current) {
      return;
    }
    const delta = event.clientX - startXRef.current;
    setSidebarWidth(startWidthRef.current + delta);
  }, [setSidebarWidth]);

  const stopResize = useCallback(() => {
    if (!isResizingRef.current) {
      return;
    }
    isResizingRef.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', stopResize);
  }, [onMouseMove]);

  const startResize = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    isResizingRef.current = true;
    startXRef.current = event.clientX;
    startWidthRef.current = sidebarWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', stopResize);
  }, [onMouseMove, sidebarWidth, stopResize]);

  useEffect(() => () => stopResize(), [stopResize]);

  if (!sidebarOpen) {
    return null;
  }

  return (
    <Box
      sx={{
        width: sidebarWidth,
        minWidth: sidebarWidth,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
        position: 'relative',
      }}
    >
      <Box
        role="separator"
        aria-orientation="vertical"
        onMouseDown={startResize}
        sx={{
          position: 'absolute',
          top: 0,
          right: -3,
          width: 6,
          height: '100%',
          cursor: 'col-resize',
          zIndex: 2,
          '&:hover': {
            bgcolor: 'action.hover',
          },
        }}
      />
      <Box sx={{ flex: 1, overflow: 'hidden' }}>
        <ChatPanel />
      </Box>
    </Box>
  );
}
