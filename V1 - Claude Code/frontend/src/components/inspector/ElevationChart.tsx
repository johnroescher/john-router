'use client';

import React, { useCallback, useMemo, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { usePreferencesStore } from '@/stores/preferencesStore';
import { useUIStore } from '@/stores/uiStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { formatDistance, formatElevation, getGradeColor } from '@/lib/utils';
import { SURFACE_COLORS, SIMPLIFIED_SURFACE_COLORS, type SurfaceType, type SimplifiedSurfaceType } from '@/lib/surfaceColors';
import { getSimplifiedSurfaceMix, mapSurfaceTypeToSimplified, normalizeSurfaceBreakdown } from '@/lib/surfaceMix';
import type { ElevationPoint } from '@/types';

interface Props {
  profile: ElevationPoint[];
}

const simplifiedSurfaceLabel = (surface: SimplifiedSurfaceType) => {
  const labels: Record<SimplifiedSurfaceType, string> = {
    paved: 'Paved',
    unpaved: 'Unpaved',
    unknown: 'Unknown',
  };
  return labels[surface] || 'Unknown';
};

export default function ElevationChart({ profile }: Props) {
  const { units } = usePreferencesStore();
  const { profileHover, setProfileHover, clearProfileHover } = useUIStore();
  const segmentedSurface = useSurfaceStore((state) => state.segmentedSurface);
  const aggregatedBreakdown = useSurfaceStore((state) => state.aggregatedBreakdown);
  
  // Log when surface data changes to debug reactivity (only in development, and not during render)
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      console.debug('[ElevationChart] Render with surface data:', {
        hasSegmentedSurface: !!segmentedSurface,
        segmentsCount: segmentedSurface?.segments.length || 0,
        dataQuality: segmentedSurface?.dataQuality || 0,
        aggregatedBreakdown,
      });
    }
  }, [segmentedSurface, aggregatedBreakdown]);

  // Get simplified surface types (paved/unpaved/unknown) mapped to each profile point
  const simplifiedSurfaceTypes = useMemo<SimplifiedSurfaceType[]>(() => {
    if (!profile.length) return [];
    
    // If we have enriched segment data with good quality, use it for accurate per-point surface types
    if (segmentedSurface && segmentedSurface.dataQuality > 20 && segmentedSurface.segments.length > 0) {
      const assignments: SimplifiedSurfaceType[] = [];
      const segments = segmentedSurface.segments;

      // Prefer index-based mapping when segment indices align with elevation profile length
      const canUseIndexMapping = segments.every(
        (segment) => segment.startIndex >= 0 && segment.endIndex < profile.length
      );
      if (canUseIndexMapping) {
        const indexedAssignments = new Array(profile.length).fill('unknown') as SimplifiedSurfaceType[];
        for (const segment of segments) {
          const simplified = mapSurfaceTypeToSimplified(segment.surfaceType);
          const endIndex = Math.min(segment.endIndex, profile.length - 1);
          for (let i = segment.startIndex; i <= endIndex; i += 1) {
            indexedAssignments[i] = simplified;
          }
        }
        return indexedAssignments;
      }
      
      // Debug: log segment ranges and profile range
      if (process.env.NODE_ENV === 'development' && segments.length > 0) {
        const profileStart = profile[0]?.distanceMeters || 0;
        const profileEnd = profile[profile.length - 1]?.distanceMeters || 0;
        console.debug('[ElevationChart] Matching profile points to segments:', {
          profile_range: `${profileStart.toFixed(1)}m - ${profileEnd.toFixed(1)}m`,
          profile_points: profile.length,
          segments_count: segments.length,
          segment_ranges: segments.slice(0, 5).map(s => ({
            surface: s.surfaceType,
            range: `${s.startDistanceMeters.toFixed(1)}m - ${s.endDistanceMeters.toFixed(1)}m`,
          })),
        });
      }
      
      // Map each profile point to its corresponding surface segment, then simplify
      for (const point of profile) {
        // Find which segment this point belongs to using explicit distances
        let foundSurface: SurfaceType = 'unknown';

        if (segments.length > 0) {
          // Handle edge case: if point is at or before the start, use first segment
          if (point.distanceMeters <= segments[0].startDistanceMeters) {
            foundSurface = segments[0].surfaceType;
          } else {
            // Find the segment that contains this point
            // Use >= for start to include points exactly at segment boundaries
            for (const segment of segments) {
              if (point.distanceMeters >= segment.startDistanceMeters && point.distanceMeters < segment.endDistanceMeters) {
                foundSurface = segment.surfaceType;
                break;
              }
            }
            // If point is at or beyond the last segment's end, use last segment
            if (foundSurface === 'unknown' && segments.length > 0) {
              const lastSegment = segments[segments.length - 1];
              if (point.distanceMeters >= lastSegment.endDistanceMeters) {
                foundSurface = lastSegment.surfaceType;
              } else {
                // Point is between segments (shouldn't happen, but fallback to last segment)
                foundSurface = lastSegment.surfaceType;
              }
            }
          }
        }

        assignments.push(mapSurfaceTypeToSimplified(foundSurface));
      }
      
      // Debug: log assignment results
      if (process.env.NODE_ENV === 'development') {
        const assignmentCounts = assignments.reduce((acc, a) => {
          acc[a] = (acc[a] || 0) + 1;
          return acc;
        }, {} as Record<SimplifiedSurfaceType, number>);
        console.debug('[ElevationChart] Surface type assignments:', {
          total_points: assignments.length,
          assignments: assignmentCounts,
          sample: assignments.slice(0, 10),
        });
      }
      
      return assignments;
    }

    // Fallback: show unknown when surface data is low quality
    return profile.map(() => 'unknown');
  }, [profile, segmentedSurface]);

  // Get simplified surface percentages for legend (paved/unpaved/unknown)
  // Normalize surface breakdown to ensure it's valid
  const surfacePercentages = useMemo(() => {
    if (segmentedSurface && segmentedSurface.dataQuality > 20 && segmentedSurface.segments.length > 0) {
      const normalized = normalizeSurfaceBreakdown(aggregatedBreakdown);
      return getSimplifiedSurfaceMix(normalized);
    }
    return { paved: 0, unpaved: 0, unknown: 100 };
  }, [segmentedSurface, aggregatedBreakdown]);

  // Transform data for chart - use simplified surface types (paved/unpaved/unknown)
  const data = useMemo(() => profile.map((point, index) => {
    const surfaceType = simplifiedSurfaceTypes[index] || 'unknown';
    const elevation = units === 'imperial'
      ? point.elevationMeters * 3.28084
      : point.elevationMeters;
    
    // Create data object with elevation for each simplified surface type
    const dataPoint: any = {
      distance: units === 'imperial'
        ? point.distanceMeters / 1609.34
        : point.distanceMeters / 1000,
      elevation,
      grade: point.gradePercent,
      rawDistance: point.distanceMeters,
      rawElevation: point.elevationMeters,
      coordinate: point.coordinate,
      surfaceType,
      surfaceLabel: simplifiedSurfaceLabel(surfaceType),
    };

    // Set elevation only for the current surface type, null for others
    dataPoint.surface_paved = surfaceType === 'paved' ? elevation : null;
    dataPoint.surface_unpaved = surfaceType === 'unpaved' ? elevation : null;
    dataPoint.surface_unknown = surfaceType === 'unknown' ? elevation : null;

    return dataPoint;
  }), [profile, simplifiedSurfaceTypes, units]);

  const surfaceGradientStops = useMemo(() => {
    if (!data.length) return [];
    const minDistance = data[0].rawDistance;
    const maxDistance = data[data.length - 1].rawDistance;
    const range = maxDistance - minDistance || 1;

    const stops: Array<{ offset: number; color: string }> = [];
    let prevSurface = data[0].surfaceType as SimplifiedSurfaceType;
    let prevColor = SIMPLIFIED_SURFACE_COLORS[prevSurface] || SIMPLIFIED_SURFACE_COLORS.unknown;
    stops.push({ offset: 0, color: prevColor });

    for (let i = 1; i < data.length; i += 1) {
      const currentSurface = data[i].surfaceType as SimplifiedSurfaceType;
      if (currentSurface !== prevSurface) {
        const offset = ((data[i].rawDistance - minDistance) / range) * 100;
        const currentColor = SIMPLIFIED_SURFACE_COLORS[currentSurface] || SIMPLIFIED_SURFACE_COLORS.unknown;
        stops.push({ offset, color: prevColor });
        stops.push({ offset, color: currentColor });
        prevSurface = currentSurface;
        prevColor = currentColor;
      }
    }

    stops.push({ offset: 100, color: prevColor });
    return stops;
  }, [data]);

  const minElevation = Math.min(...data.map((d) => d.elevation));
  const maxElevation = Math.max(...data.map((d) => d.elevation));
  const elevationRange = maxElevation - minElevation;

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const point = payload[0].payload;
      return (
        <Box
          sx={{
            bgcolor: 'background.paper',
            borderRadius: 1,
            p: 1.25,
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          }}
        >
          <Typography sx={{ fontSize: '0.6875rem', display: 'block', mb: 0.25 }}>
            Distance: {formatDistance(point.rawDistance, units)}
          </Typography>
          <Typography sx={{ fontSize: '0.6875rem', display: 'block', mb: 0.25 }}>
            Elevation: {formatElevation(point.rawElevation, units)}
          </Typography>
          <Typography
            sx={{ fontSize: '0.6875rem', display: 'block', mb: 0.25, color: getGradeColor(point.grade) }}
          >
            Grade: {point.grade.toFixed(1)}%
          </Typography>
          <Typography
            sx={{ fontSize: '0.6875rem', display: 'block', color: SIMPLIFIED_SURFACE_COLORS[point.surfaceType as SimplifiedSurfaceType] }}
          >
            Surface: {point.surfaceLabel}
          </Typography>
        </Box>
      );
    }
    return null;
  };

  const handleMouseMove = useCallback((state: any) => {
    if (!state?.activePayload?.length) return;
    const point = state.activePayload[0].payload;
    if (point?.rawDistance === undefined || !point?.coordinate) return;
    setProfileHover({
      distanceMeters: point.rawDistance,
      coordinate: point.coordinate,
      surfaceType: point.surfaceType,
      source: 'chart',
    });
  }, [setProfileHover]);

  const handleMouseLeave = useCallback(() => {
    if (profileHover?.source === 'chart') {
      clearProfileHover();
    }
  }, [profileHover?.source, clearProfileHover]);

  const mapHoverX = useMemo(() => {
    if (!profileHover || profileHover.source !== 'map') return null;
    return units === 'imperial'
      ? profileHover.distanceMeters / 1609.34
      : profileHover.distanceMeters / 1000;
  }, [profileHover, units]);

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ height: 78 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            key={`elevation-chart-${segmentedSurface?.segments.length || 0}-${segmentedSurface?.dataQuality || 0}`}
            data={data}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          >
            <defs>
              <linearGradient id="surfaceStroke" x1="0" y1="0" x2="1" y2="0">
                {surfaceGradientStops.map((stop, index) => (
                  <stop key={`stroke-${index}`} offset={`${stop.offset}%`} stopColor={stop.color} />
                ))}
              </linearGradient>
              <linearGradient id="surfaceFill" x1="0" y1="0" x2="1" y2="0">
                {surfaceGradientStops.map((stop, index) => (
                  <stop
                    key={`fill-${index}`}
                    offset={`${stop.offset}%`}
                    stopColor={stop.color}
                    stopOpacity={0.28}
                  />
                ))}
              </linearGradient>
            </defs>
            <XAxis
              dataKey="distance"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(v) => `${v.toFixed(1)}`}
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[
                Math.floor(minElevation - elevationRange * 0.1),
                Math.ceil(maxElevation + elevationRange * 0.1),
              ]}
              tickFormatter={(v) => `${Math.round(v)}`}
              tick={{ fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* Continuous elevation area colored by surface type */}
            <Area
              type="monotone"
              dataKey="elevation"
              stroke="url(#surfaceStroke)"
              strokeWidth={1.5}
              fill="url(#surfaceFill)"
              isAnimationActive={false}
              connectNulls
            />
            {mapHoverX !== null && (
              <ReferenceLine x={mapHoverX} stroke="#111827" strokeDasharray="3 3" />
            )}
            {/* Reference lines for notable elevations */}
            <ReferenceLine
              y={minElevation}
              stroke="#666"
              strokeDasharray="3 3"
            />
            <ReferenceLine
              y={maxElevation}
              stroke="#666"
              strokeDasharray="3 3"
            />
          </AreaChart>
        </ResponsiveContainer>
      </Box>

      {/* Axis labels */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', px: 1, mt: 0.25 }}>
        <Typography sx={{ fontSize: '0.6875rem', color: 'text.secondary' }}>
          Distance ({units === 'imperial' ? 'mi' : 'km'})
        </Typography>
        <Typography sx={{ fontSize: '0.6875rem', color: 'text.secondary' }}>
          Elevation ({units === 'imperial' ? 'ft' : 'm'})
        </Typography>
      </Box>

      {/* Simplified surface type legend with percentages - always show all three categories */}
      <Box sx={{ display: 'flex', gap: 2, mt: 0.75, px: 1, flexWrap: 'wrap' }}>
        {(['paved', 'unpaved', 'unknown'] as SimplifiedSurfaceType[]).map((surface) => {
          const percent = surfacePercentages[surface] || 0;
          return (
            <Box key={surface} sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Box
                sx={{
                  width: 12,
                  height: 12,
                  borderRadius: 0.5,
                  bgcolor: SIMPLIFIED_SURFACE_COLORS[surface],
                  flexShrink: 0,
                }}
              />
              <Typography sx={{ fontSize: '0.6875rem', color: 'text.secondary' }}>
                {simplifiedSurfaceLabel(surface)}: {percent.toFixed(1)}%
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
