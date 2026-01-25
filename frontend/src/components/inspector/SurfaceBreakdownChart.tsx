'use client';

import { Box, Typography, Grid, LinearProgress } from '@mui/material';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { useRouteStore } from '@/stores/routeStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { getSimplifiedSurfaceMix, normalizeSurfaceBreakdown } from '@/lib/surfaceMix';
import { SIMPLIFIED_SURFACE_COLORS } from '@/lib/surfaceColors';
import type { SimplifiedSurfaceType } from '@/lib/surfaceMix';

export default function SurfaceBreakdownChart() {
  const { currentRoute } = useRouteStore();
  const { segmentedSurface, isEnriching } = useSurfaceStore();

  if (!currentRoute) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          No route selected
        </Typography>
      </Box>
    );
  }

  // Get surface data - prefer enriched data if available, otherwise show unknown
  const rawSurfaceBreakdown = segmentedSurface && segmentedSurface.dataQuality > 20
    ? useSurfaceStore.getState().getAggregatedBreakdown()
    : { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };

  // Debug logging to diagnose surface data issues
  if (process.env.NODE_ENV === 'development') {
    console.log('[SurfaceBreakdownChart] Raw surface breakdown:', rawSurfaceBreakdown);
    console.log('[SurfaceBreakdownChart] Has segmented surface:', !!segmentedSurface);
    console.log('[SurfaceBreakdownChart] Segmented data quality:', segmentedSurface?.dataQuality);
  }

  // Normalize surface breakdown to ensure it's valid (handles null/undefined)
  const surfaceBreakdown = normalizeSurfaceBreakdown(rawSurfaceBreakdown);

  // Debug logging after normalization
  if (process.env.NODE_ENV === 'development') {
    console.log('[SurfaceBreakdownChart] Normalized surface breakdown:', surfaceBreakdown);
  }

  // Get simplified surface mix (paved/unpaved/unknown)
  const mix = getSimplifiedSurfaceMix(surfaceBreakdown);

  // Debug logging after simplification
  if (process.env.NODE_ENV === 'development') {
    console.log('[SurfaceBreakdownChart] Simplified mix:', mix);
  }
  const isEnriched = segmentedSurface && segmentedSurface.dataQuality > 20;
  const qualityMetrics = segmentedSurface?.qualityMetrics;

  // Prepare data for pie chart - show simplified paved/unpaved/unknown
  const simplifiedData = [
    { key: 'paved' as SimplifiedSurfaceType, name: 'Paved', value: parseFloat(mix.paved.toFixed(1)), color: SIMPLIFIED_SURFACE_COLORS.paved },
    { key: 'unpaved' as SimplifiedSurfaceType, name: 'Unpaved', value: parseFloat(mix.unpaved.toFixed(1)), color: SIMPLIFIED_SURFACE_COLORS.unpaved },
    { key: 'unknown' as SimplifiedSurfaceType, name: 'Unknown', value: parseFloat(mix.unknown.toFixed(1)), color: SIMPLIFIED_SURFACE_COLORS.unknown },
  ].filter((entry) => entry.value > 0);

  return (
    <Box sx={{ p: 2, height: '100%' }}>
      {/* Loading indicator */}
      {isEnriching && (
        <Box sx={{ mb: 2 }}>
          <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 0.5 }}>
            Enriching surface data...
          </Typography>
          <LinearProgress color="primary" />
        </Box>
      )}

      <Grid container spacing={2}>
        {/* Pie Chart */}
        <Grid item xs={5}>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie
                data={simplifiedData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={55}
                innerRadius={25}
                label={({ value }) => value > 5 ? `${value}%` : ''}
                labelLine={false}
              >
                {simplifiedData.map((entry) => (
                  <Cell key={entry.key} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [`${value}%`, 'Percentage']}
                contentStyle={{ 
                  fontSize: '0.75rem', 
                  borderRadius: 8,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </Grid>

        {/* Simplified breakdown legend */}
        <Grid item xs={7}>
          <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, mb: 1.5 }}>
            Surface Breakdown
          </Typography>

          {simplifiedData.map((surface) => (
            <Box
              key={surface.key}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                mb: 1,
              }}
            >
              <Box
                sx={{
                  width: 12,
                  height: 12,
                  borderRadius: 0.5,
                  bgcolor: surface.color,
                  flexShrink: 0,
                }}
              />
              <Typography sx={{ fontSize: '0.75rem', flex: 1, color: 'text.secondary' }}>
                {surface.name}
              </Typography>
              <Typography sx={{ fontSize: '0.75rem', fontWeight: 600 }}>
                {surface.value}%
              </Typography>
            </Box>
          ))}
        </Grid>
      </Grid>

      {/* Summary bar */}
      <Box sx={{ mt: 2 }}>
        <Typography sx={{ fontSize: '0.6875rem', fontWeight: 600, mb: 0.5, color: 'text.secondary' }}>
          Paved vs Unpaved
        </Typography>
        <Box
          sx={{
            display: 'flex',
            height: 8,
            borderRadius: 1,
            overflow: 'hidden',
            bgcolor: 'grey.200',
          }}
        >
          {mix.paved > 0 && (
            <Box sx={{ width: `${mix.paved}%`, bgcolor: SIMPLIFIED_SURFACE_COLORS.paved }} />
          )}
          {mix.unpaved > 0 && (
            <Box sx={{ width: `${mix.unpaved}%`, bgcolor: SIMPLIFIED_SURFACE_COLORS.unpaved }} />
          )}
          {mix.unknown > 0 && (
            <Box sx={{ width: `${mix.unknown}%`, bgcolor: SIMPLIFIED_SURFACE_COLORS.unknown }} />
          )}
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
          <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
            Paved {mix.paved.toFixed(0)}%
          </Typography>
          <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
            Unpaved {mix.unpaved.toFixed(0)}%
          </Typography>
          {mix.unknown > 5 && (
            <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
              Unknown {mix.unknown.toFixed(0)}%
            </Typography>
          )}
        </Box>
      </Box>

      {/* Info text */}
      <Box sx={{ mt: 2, pt: 1.5 }}>
        <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary', lineHeight: 1.4 }}>
          {isEnriched
            ? `Surface data enriched from OpenStreetMap. Coverage ${qualityMetrics?.coveragePercent?.toFixed(0) ?? '—'}%, avg confidence ${qualityMetrics?.avgConfidence?.toFixed(2) ?? '—'}.`
            : 'Surface data unavailable or low quality. Showing unknown.'
          }
        </Typography>
      </Box>
    </Box>
  );
}
