'use client';

import dynamic from 'next/dynamic';
import { Box, Skeleton } from '@mui/material';
import { useUIStore } from '@/stores/uiStore';
import AppBar from '@/components/AppBar';
import GpxImportDialog from '@/components/GpxImportDialog';
import Sidebar from '@/components/Sidebar';
import RouteInspectorPanel from '@/components/Inspector';
import MobileLayout from '@/components/MobileLayout';

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

export default function PlannerPage() {
  const isMobile = useUIStore((state) => state.isMobile);

  if (isMobile) {
    return <MobileLayout />;
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Top App Bar */}
      <AppBar />
      <GpxImportDialog />

      {/* Main Content */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0, minWidth: 0 }}>
        {/* Left Sidebar */}
        <Sidebar />

        {/* Map + Route Inspector Panel */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', minHeight: 0, minWidth: 0, height: '100%' }}>
          {/* Map */}
          <Box sx={{ flex: 1, position: 'relative', minHeight: 0, height: '100%' }}>
            <MapContainer />
          </Box>

          {/* Bottom Route Inspector Panel */}
          <RouteInspectorPanel />
        </Box>
      </Box>
    </Box>
  );
}
