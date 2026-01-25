'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { Box, Paper, Fab, Drawer, Typography, IconButton, SwipeableDrawer, Skeleton } from '@mui/material';
import CelebrationIcon from '@mui/icons-material/Celebration';
import LayersIcon from '@mui/icons-material/Layers';
import AddLocationIcon from '@mui/icons-material/AddLocation';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import CloseIcon from '@mui/icons-material/Close';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';
import { usePreferencesStore } from '@/stores/preferencesStore';
import ChatPanel from '@/components/chat/ChatPanel';
import { formatDistance, formatElevation, formatDuration } from '@/lib/utils';
import { getSurfaceMix } from '@/lib/surfaceMix';

// Map skeleton shown during loading
const MapSkeleton = () => (
  <Box
    sx={{
      width: '100%',
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      bgcolor: 'grey.100',
    }}
  >
    <Skeleton
      variant="rectangular"
      width="100%"
      height="100%"
      animation="wave"
      sx={{ bgcolor: 'grey.200' }}
    />
  </Box>
);

// Dynamic import with SSR disabled - critical for MapLibre
const MapContainer = dynamic(
  () => import('@/components/map/MapContainer'),
  {
    ssr: false,
    loading: () => <MapSkeleton />,
  }
);

function RouteSummarySheet() {
  const { bottomSheetPosition, setBottomSheetPosition } = useUIStore();
  const { currentRoute } = useRouteStore();
  const { units } = usePreferencesStore();

  const isOpen = bottomSheetPosition !== 'collapsed';

  const handleClose = () => setBottomSheetPosition('collapsed');
  const handleOpen = () => setBottomSheetPosition('half');

  if (!currentRoute) {
    return null;
  }

  return (
    <SwipeableDrawer
      anchor="bottom"
      open={isOpen}
      onClose={handleClose}
      onOpen={handleOpen}
      disableSwipeToOpen={false}
      swipeAreaWidth={56}
      ModalProps={{
        keepMounted: true,
      }}
      PaperProps={{
        sx: {
          height: bottomSheetPosition === 'full' ? '90%' : bottomSheetPosition === 'half' ? '55%' : '20%',
          borderTopLeftRadius: 16,
          borderTopRightRadius: 16,
          overflow: 'visible',
        },
      }}
    >
      {/* Drag handle */}
      <Box
        sx={{
          width: 40,
          height: 4,
          bgcolor: 'grey.500',
          borderRadius: 2,
          position: 'absolute',
          top: 8,
          left: '50%',
          transform: 'translateX(-50%)',
        }}
      />

      <Box sx={{ p: 2, pt: 3 }}>
        {/* Quick summary */}
        <Box sx={{ display: 'flex', justifyContent: 'space-around', mb: 2 }}>
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {currentRoute.distanceMeters
                ? formatDistance(currentRoute.distanceMeters, units)
                : '-'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Distance
            </Typography>
          </Box>
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {currentRoute.elevationGainMeters
                ? formatElevation(currentRoute.elevationGainMeters, units)
                : '-'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Elevation
            </Typography>
          </Box>
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {currentRoute.estimatedTimeSeconds
                ? formatDuration(currentRoute.estimatedTimeSeconds)
                : '-'}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Time
            </Typography>
          </Box>
        </Box>

        {/* Surface breakdown */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
            Surface
          </Typography>
          {(() => {
            const mix = getSurfaceMix(currentRoute.surfaceBreakdown);
            return (
              <Box sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden' }}>
                <Box sx={{ width: `${mix.paved}%`, bgcolor: '#d32f2f' }} />
                <Box
                  sx={{
                    width: `${mix.unpaved}%`,
                    bgcolor: '#d32f2f',
                    backgroundImage: 'repeating-linear-gradient(90deg, #d32f2f 0 3px, #ffffff 3px 6px)',
                  }}
                />
              </Box>
            );
          })()}
        </Box>

        {/* Expand to see more */}
        {bottomSheetPosition === 'collapsed' && (
          <Box sx={{ textAlign: 'center' }}>
            <IconButton onClick={() => setBottomSheetPosition('half')}>
              <ExpandLessIcon />
            </IconButton>
          </Box>
        )}

        {/* Full details when expanded */}
        {bottomSheetPosition !== 'collapsed' && (
          <Box>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
              Difficulty
            </Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Box>
                <Typography variant="caption" color="text.secondary">Physical</Typography>
                <Typography>{currentRoute.physicalDifficulty?.toFixed(1) || '-'}/5</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Technical</Typography>
                <Typography>{currentRoute.technicalDifficulty?.toFixed(1) || '-'}/5</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Overall</Typography>
                <Typography>{currentRoute.overallDifficulty?.toFixed(1) || '-'}/5</Typography>
              </Box>
            </Box>

            {currentRoute.validationResults.warnings.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }} color="warning.main">
                  Warnings ({currentRoute.validationResults.warnings.length})
                </Typography>
                {currentRoute.validationResults.warnings.slice(0, 3).map((w, i) => (
                  <Typography key={i} variant="body2" color="text.secondary">
                    {w.message}
                  </Typography>
                ))}
              </Box>
            )}
          </Box>
        )}
      </Box>
    </SwipeableDrawer>
  );
}

export default function MobileLayout() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Map (full screen) */}
      <Box sx={{ flex: 1, position: 'relative', minHeight: 0, height: '100%' }}>
        <MapContainer />

        {/* Floating action buttons */}
        <Box
          sx={{
            position: 'absolute',
            bottom: 80,
            right: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          <Fab size="small" onClick={() => {}}>
            <LayersIcon />
          </Fab>
          <Fab size="small" onClick={() => {}}>
            <AddLocationIcon />
          </Fab>
          <Fab size="small" onClick={() => {}}>
            <FileDownloadIcon />
          </Fab>
          <Fab color="primary" onClick={() => setChatOpen(true)}>
            <CelebrationIcon />
          </Fab>
        </Box>
      </Box>

      {/* Bottom sheet for route summary */}
      <RouteSummarySheet />

      {/* Chat drawer */}
      <Drawer
        anchor="bottom"
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        PaperProps={{
          sx: {
            height: '100%',
            borderTopLeftRadius: 16,
            borderTopRightRadius: 16,
          },
        }}
      >
        <Box sx={{ p: 1, display: 'flex', alignItems: 'center' }}>
          <Typography variant="h6" sx={{ flex: 1, pl: 1 }}>
            Chat
          </Typography>
          <IconButton onClick={() => setChatOpen(false)}>
            <CloseIcon />
          </IconButton>
        </Box>
        <Box sx={{ flex: 1, overflow: 'hidden' }}>
          <ChatPanel />
        </Box>
      </Drawer>
    </Box>
  );
}
