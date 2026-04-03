'use client';

import { Box, Typography, Grid, Alert } from '@mui/material';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';
import { usePreferencesStore } from '@/stores/preferencesStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { useCallback, useEffect, useRef } from 'react';
import type { MouseEvent as ReactMouseEvent } from 'react';
import {
  formatDistance,
  formatElevation,
  formatDuration,
  formatGrade,
  estimateRideTimeSeconds,
} from '@/lib/utils';
import { normalizeSurfaceBreakdown } from '@/lib/surfaceMix';
import ElevationChart from '@/components/inspector/ElevationChart';
import SurfaceBreakdownChart from '@/components/inspector/SurfaceBreakdownChart';

function StatCard({ label, value, unit }: { label: string; value: string | number; unit?: string }) {
  return (
    <Box sx={{ textAlign: 'center' }}>
      <Typography 
        sx={{ 
          fontWeight: 600, 
          fontSize: '1.5rem',
          lineHeight: 1.2,
          color: 'text.primary',
        }}
      >
        {value}
        {unit && (
          <Typography 
            component="span" 
            sx={{ 
              fontSize: '0.75rem', 
              fontWeight: 400,
              color: 'text.secondary',
              ml: 0.5,
            }}
          >
            {unit}
          </Typography>
        )}
      </Typography>
      <Typography 
        sx={{ 
          fontSize: '0.6875rem', 
          color: 'text.secondary',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          mt: 0.25,
        }}
      >
        {label}
      </Typography>
    </Box>
  );
}

function SummaryTab() {
  const { currentRoute, candidates, selectedCandidateIndex, constraints, manualAnalysis, isAnalyzing } = useRouteStore();
  const { units, fitnessLevel, typicalSpeedMph, mtbSkill, riskTolerance } = usePreferencesStore((state) => ({
    units: state.units,
    fitnessLevel: state.fitnessLevel,
    typicalSpeedMph: state.typicalSpeedMph,
    mtbSkill: state.mtbSkill,
    riskTolerance: state.riskTolerance,
  }));
  const segmentedSurface = useSurfaceStore((state) => state.segmentedSurface);
  const enrichmentError = useSurfaceStore((state) => state.enrichmentError);
  const isEnrichingSurface = useSurfaceStore((state) => state.isEnriching);
  // Get surface data - prefer enriched data if available, normalize to ensure validity
  const aggregatedBreakdown = useSurfaceStore((state) => state.aggregatedBreakdown);
  const manualAnalysisError = useRouteStore((state) => state.manualAnalysisError);

  const analysis = candidates[selectedCandidateIndex]?.analysis;
  const route = currentRoute;

  // Show helpful message when no route yet
  if (!route) {
    const hasWaypoints = constraints.viaPoints && constraints.viaPoints.length > 0;
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          {hasWaypoints && constraints.viaPoints.length === 1
            ? 'Click another point on the map to start building your route'
            : 'Generate a route or use the waypoint tool (+) to build one manually'}
        </Typography>
      </Box>
    );
  }
  const rawSurfaceBreakdown =
    segmentedSurface && segmentedSurface.dataQuality > 20
      ? aggregatedBreakdown
      : route.surfaceBreakdown;
  const surfaceBreakdown = normalizeSurfaceBreakdown(rawSurfaceBreakdown);

  const estimatedTimeSeconds =
    route.estimatedTimeSeconds && route.estimatedTimeSeconds > 0
      ? route.estimatedTimeSeconds
      : estimateRideTimeSeconds({
          distanceMeters: route.distanceMeters,
          elevationGainMeters: route.elevationGainMeters,
          surfaceBreakdown,
          sportType: route.sportType,
          technicalDifficulty: route.technicalDifficulty,
          riskRating: route.riskRating,
          mtbDifficultyBreakdown: route.mtbDifficultyBreakdown,
          avgGradePercent: analysis?.avgGradePercent,
          hikeABikeDistanceMeters: analysis?.hikeABikeDistanceMeters,
          viaPointsCount: constraints.viaPoints?.length || 0,
          waypointCount: route.waypoints?.length || 0,
          preferences: {
            fitnessLevel,
            typicalSpeedMph,
            mtbSkill,
            riskTolerance,
          },
        });

  // Get elevation profile for chart
  const candidateAnalysis = candidates[selectedCandidateIndex]?.analysis;
  const elevationAnalysis = candidateAnalysis?.elevationProfile?.length
    ? candidateAnalysis
    : manualAnalysis;

  // Use candidate analysis first, fall back to manualAnalysis for grade stats
  const gradeAnalysis = analysis || manualAnalysis;

  return (
    <Box sx={{ p: 2 }}>
      <Grid container spacing={3} columns={10}>
        {/* Big numbers */}
        <Grid item xs={2}>
          <StatCard
            label="Distance"
            value={route.distanceMeters ? formatDistance(route.distanceMeters, units).split(' ')[0] : '-'}
            unit={units === 'imperial' ? 'mi' : 'km'}
          />
        </Grid>
        <Grid item xs={2}>
          <StatCard
            label="Elevation"
            value={route.elevationGainMeters ? formatElevation(route.elevationGainMeters, units).split(' ')[0] : '-'}
            unit={units === 'imperial' ? 'ft' : 'm'}
          />
        </Grid>
        <Grid item xs={2}>
          <StatCard
            label="Est. Time"
            value={formatDuration(estimatedTimeSeconds)}
          />
        </Grid>
        <Grid item xs={2}>
          <StatCard
            label="AVG Grade"
            value={typeof gradeAnalysis?.avgGradePercent === 'number' ? formatGrade(gradeAnalysis.avgGradePercent) : '-'}
          />
        </Grid>
        <Grid item xs={2}>
          <StatCard
            label="Max"
            value={typeof gradeAnalysis?.maxGradePercent === 'number' ? formatGrade(gradeAnalysis.maxGradePercent) : '-'}
          />
        </Grid>
      </Grid>

      {(enrichmentError || manualAnalysisError) && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          {enrichmentError && (
            <Typography variant="body2" component="span" display="block">
              Surface enrichment: {enrichmentError}
            </Typography>
          )}
          {manualAnalysisError && (
            <Typography variant="body2" component="span" display="block">
              Elevation: {manualAnalysisError}
            </Typography>
          )}
        </Alert>
      )}
      {isEnrichingSurface && !enrichmentError && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Enriching surface segments on the map…
        </Typography>
      )}

      {/* Elevation chart */}
      <Box sx={{ mt: 0.75 }}>
        {elevationAnalysis?.elevationProfile?.length ? (
          <ElevationChart profile={elevationAnalysis.elevationProfile} />
        ) : (
          <Box sx={{ p: 3, textAlign: 'center' }}>
            <Typography color="text.secondary">
              {isAnalyzing
                ? 'Analyzing elevation data...'
                : manualAnalysisError
                  ? 'Elevation profile could not be loaded.'
                  : 'No elevation data available'}
            </Typography>
          </Box>
        )}
      </Box>

      <Box sx={{ mt: 1.5 }}>
        <SurfaceBreakdownChart />
      </Box>
    </Box>
  );
}


export default function RouteInspectorPanel() {
  const { inspectorOpen, inspectorHeight, setInspectorOpen, setInspectorHeight } = useUIStore();
  const isResizingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(0);
  const heightRef = useRef(inspectorHeight);
  const lastOpenHeightRef = useRef(inspectorHeight);
  const ignoreCollapsedClickRef = useRef(false);
  const collapsedDragStartYRef = useRef(0);
  const collapsedDragActiveRef = useRef(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const contentSizerRef = useRef<HTMLDivElement>(null);

  const COLLAPSE_THRESHOLD = 30;
  const DEFAULT_OPEN_HEIGHT = 300;

  useEffect(() => {
    heightRef.current = inspectorHeight;
    if (inspectorOpen && inspectorHeight > COLLAPSE_THRESHOLD) {
      lastOpenHeightRef.current = inspectorHeight;
    }
  }, [inspectorHeight, inspectorOpen]);

  const getMaxHeight = useCallback(() => {
    if (typeof window === 'undefined') {
      return DEFAULT_OPEN_HEIGHT;
    }
    return Math.max(120, Math.floor(window.innerHeight * 0.5));
  }, []);

  const clampHeight = useCallback((height: number) => Math.min(height, getMaxHeight()), [getMaxHeight]);

  const getRestoreHeight = useCallback(() => {
    if (typeof window === 'undefined') {
      return DEFAULT_OPEN_HEIGHT;
    }
    return Math.max(120, Math.floor(window.innerHeight * 0.3));
  }, []);

  useEffect(() => {
    if (!inspectorOpen || inspectorHeight > COLLAPSE_THRESHOLD || isResizingRef.current) {
      return;
    }
    const contentSizer = contentSizerRef.current;
    if (!contentSizer) {
      return;
    }
    const observer = new ResizeObserver(() => {
      const nextHeight = clampHeight(Math.ceil(contentSizer.scrollHeight));
      if (nextHeight > COLLAPSE_THRESHOLD && nextHeight !== inspectorHeight) {
        setInspectorHeight(nextHeight);
      }
    });
    observer.observe(contentSizer);
    return () => observer.disconnect();
  }, [clampHeight, inspectorHeight, inspectorOpen, setInspectorHeight]);

  const onMouseMove = useCallback((event: MouseEvent) => {
    if (!isResizingRef.current) {
      return;
    }
    const delta = startYRef.current - event.clientY;
    const nextHeight = clampHeight(startHeightRef.current + delta);
    heightRef.current = nextHeight;
    setInspectorHeight(nextHeight);
  }, [clampHeight, setInspectorHeight]);

  const stopResize = useCallback(() => {
    if (!isResizingRef.current) {
      return;
    }
    isResizingRef.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', stopResize);

    if (heightRef.current <= COLLAPSE_THRESHOLD) {
      ignoreCollapsedClickRef.current = true;
      setInspectorOpen(false);
      setInspectorHeight(0);
      window.setTimeout(() => {
        ignoreCollapsedClickRef.current = false;
      }, 0);
    }
  }, [onMouseMove, setInspectorHeight, setInspectorOpen]);

  const startResize = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    isResizingRef.current = true;
    startYRef.current = event.clientY;
    startHeightRef.current = inspectorHeight;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', stopResize);
  }, [inspectorHeight, onMouseMove, stopResize]);

  const startResizeFromCollapsed = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    collapsedDragStartYRef.current = event.clientY;
    collapsedDragActiveRef.current = true;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!collapsedDragActiveRef.current) {
        return;
      }
      if (Math.abs(collapsedDragStartYRef.current - moveEvent.clientY) < 4) {
        return;
      }
      collapsedDragActiveRef.current = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      ignoreCollapsedClickRef.current = true;
      setInspectorOpen(true);
      setInspectorHeight(0);
      isResizingRef.current = true;
      startYRef.current = moveEvent.clientY;
      startHeightRef.current = 0;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', stopResize);
      window.setTimeout(() => {
        ignoreCollapsedClickRef.current = false;
      }, 0);
    };

    const handleMouseUp = () => {
      if (!collapsedDragActiveRef.current) {
        return;
      }
      collapsedDragActiveRef.current = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, [onMouseMove, setInspectorHeight, setInspectorOpen, stopResize]);

  useEffect(() => () => stopResize(), [stopResize]);
  useEffect(() => {
    const handleResize = () => {
      if (!inspectorOpen) {
        return;
      }
      const maxHeight = getMaxHeight();
      if (inspectorHeight > maxHeight) {
        setInspectorHeight(maxHeight);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [getMaxHeight, inspectorHeight, inspectorOpen, setInspectorHeight]);

  if (!inspectorOpen) {
    return (
      <Box sx={{ position: 'relative', width: '100%', height: 0 }}>
        <Box
          sx={{
            position: 'absolute',
            bottom: 12,
            left: 12,
            height: 16,
            width: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: 8,
            cursor: 'pointer',
            bgcolor: 'background.paper',
            boxShadow: 1,
            '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.02)' },
            transition: 'background-color 0.15s',
            zIndex: 3,
          }}
          onClick={() => {
            if (ignoreCollapsedClickRef.current) {
              return;
            }
            setInspectorOpen(true);
            const targetHeight =
              inspectorHeight <= COLLAPSE_THRESHOLD
                ? getRestoreHeight()
                : inspectorHeight;
            setInspectorHeight(clampHeight(targetHeight));
          }}
          onMouseDown={startResizeFromCollapsed}
        >
          <ExpandLessIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        height: inspectorHeight > COLLAPSE_THRESHOLD ? inspectorHeight : 'auto',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'background.paper',
        position: 'relative',
      }}
    >
      <Box
        role="separator"
        aria-orientation="horizontal"
        onMouseDown={startResize}
        sx={{
          position: 'absolute',
          top: -3,
          left: 0,
          right: 0,
          height: 6,
          cursor: 'row-resize',
          zIndex: 2,
          '&:hover': {
            bgcolor: 'action.hover',
          },
        }}
      />

      {/* Content */}
      <Box ref={contentRef} sx={{ flex: 1, overflow: 'auto' }}>
        <Box ref={contentSizerRef} sx={{ pt: 1 }}>
          <SummaryTab />
        </Box>
      </Box>
    </Box>
  );
}
