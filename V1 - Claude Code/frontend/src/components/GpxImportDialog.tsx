'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Typography,
} from '@mui/material';
import FileUploadIcon from '@mui/icons-material/FileUpload';
import { useUIStore } from '@/stores/uiStore';
import { useRouteStore } from '@/stores/routeStore';
import { usePreferencesStore } from '@/stores/preferencesStore';
import { api } from '@/lib/api';
import { normalizeSurfaceBreakdown } from '@/lib/surfaceMix';
import { buildSegmentsFromGeometry } from '@/lib/routeSegmentation';
import type { Coordinate, Route, RouteWaypoint } from '@/types';

type ImportMode = 'replace' | 'append';

type GpxImportResponse = {
  route: any;
  waypoints_imported: number;
  tracks_imported: number;
  warnings: string[];
};

const defaultSurfaceBreakdown = {
  pavement: 0,
  gravel: 0,
  dirt: 0,
  singletrack: 0,
  unknown: 100,
};

const defaultDifficultyBreakdown = {
  green: 0,
  blue: 0,
  black: 0,
  double_black: 0,
  unknown: 100,
};

const mapRouteFromImport = (data: any): Route => {
  const validation = data.validation_results || {
    status: data.validation_status ?? 'pending',
    errors: [],
    warnings: [],
    info: [],
    confidence_score: data.confidence_score ?? 0,
  };

  return {
    id: data.id,
    userId: data.user_id ?? undefined,
    name: data.name,
    description: data.description ?? undefined,
    sportType: data.sport_type,
    geometry: data.geometry ?? undefined,
    distanceMeters: data.distance_meters ?? undefined,
    elevationGainMeters: data.elevation_gain_meters ?? undefined,
    elevationLossMeters: data.elevation_loss_meters ?? undefined,
    estimatedTimeSeconds: data.estimated_time_seconds ?? undefined,
    maxElevationMeters: data.max_elevation_meters ?? undefined,
    minElevationMeters: data.min_elevation_meters ?? undefined,
    surfaceBreakdown: normalizeSurfaceBreakdown(data.surface_breakdown || defaultSurfaceBreakdown),
    mtbDifficultyBreakdown: data.mtb_difficulty_breakdown || defaultDifficultyBreakdown,
    physicalDifficulty: data.physical_difficulty ?? undefined,
    technicalDifficulty: data.technical_difficulty ?? undefined,
    riskRating: data.risk_rating ?? undefined,
    overallDifficulty: data.overall_difficulty ?? undefined,
    tags: data.tags || [],
    isPublic: data.is_public ?? false,
    confidenceScore: data.confidence_score ?? 0,
    validationStatus: data.validation_status ?? 'pending',
    validationResults: {
      status: validation.status ?? 'pending',
      errors: validation.errors || [],
      warnings: validation.warnings || [],
      info: validation.info || [],
      confidenceScore: validation.confidence_score ?? data.confidence_score ?? 0,
    },
    waypoints: (data.waypoints || []).map((waypoint: any): RouteWaypoint => ({
      id: waypoint.id,
      idx: waypoint.idx,
      waypointType: waypoint.waypoint_type,
      point: waypoint.point,
      name: waypoint.name ?? undefined,
      lockStrength: waypoint.lock_strength,
    })),
    createdAt: data.created_at ?? new Date().toISOString(),
    updatedAt: data.updated_at ?? new Date().toISOString(),
  };
};

const waypointSort = (a: RouteWaypoint, b: RouteWaypoint) => (a.idx ?? 0) - (b.idx ?? 0);

const splitWaypoints = (waypoints: RouteWaypoint[]) => {
  const ordered = [...waypoints].sort(waypointSort);
  let start: Coordinate | undefined;
  let end: Coordinate | undefined;
  const viaPoints: Coordinate[] = [];

  ordered.forEach((waypoint) => {
    if (waypoint.waypointType === 'start') {
      start = start ?? waypoint.point;
      return;
    }
    if (waypoint.waypointType === 'end') {
      end = end ?? waypoint.point;
      return;
    }
    viaPoints.push(waypoint.point);
  });

  return { start, end, viaPoints };
};

const calculateBounds = (coords: number[][]) => {
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  coords.forEach((coord) => {
    const [lng, lat] = coord;
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  });

  return { minLng, minLat, maxLng, maxLat };
};

const coordinatesMatch = (a: number[], b: number[]) => a[0] === b[0] && a[1] === b[1];

const mergeCoordinates = (current: number[][], incoming: number[][]) => {
  if (current.length === 0) return incoming.slice();
  if (incoming.length === 0) return current.slice();
  const merged = current.slice();
  const startIndex = coordinatesMatch(merged[merged.length - 1], incoming[0]) ? 1 : 0;
  return merged.concat(incoming.slice(startIndex));
};

const toImportMode = (hasRoute: boolean, mode: ImportMode) => (hasRoute ? mode : 'replace');

export default function GpxImportDialog() {
  const { gpxImportOpen, setGpxImportOpen, fitMapToBounds } = useUIStore();
  const {
    currentRoute,
    routeGeometry,
    setCurrentRoute,
    setRouteGeometry,
    addToRouteStats,
    setImportedRouteSegments,
    updateConstraints,
    constraints,
  } = useRouteStore();
  const { bikeType } = usePreferencesStore();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importMode, setImportMode] = useState<ImportMode>('replace');
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasRoute = Boolean(currentRoute && (routeGeometry?.length || currentRoute.geometry?.coordinates?.length));
  const effectiveMode = useMemo(() => toImportMode(hasRoute, importMode), [hasRoute, importMode]);

  useEffect(() => {
    if (!gpxImportOpen) {
      setSelectedFile(null);
      setImportMode('replace');
      setIsImporting(false);
      setError(null);
    }
  }, [gpxImportOpen]);

  const handleClose = () => {
    if (isImporting) return;
    setGpxImportOpen(false);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    setError(null);
  };

  const handleImport = async () => {
    if (!selectedFile) {
      setError('Please select a GPX file to import.');
      return;
    }

    setIsImporting(true);
    setError(null);

    try {
      const baseName = selectedFile.name.replace(/\.gpx$/i, '');
      const sportType = currentRoute?.sportType || bikeType || 'mtb';
      const result = (await api.importGpx(selectedFile, baseName, sportType)) as GpxImportResponse;
      const importedRoute = mapRouteFromImport(result.route);
      const importedCoords = importedRoute.geometry?.coordinates || [];
      const importedWaypoints = importedRoute.waypoints || [];
      const waypointSplit = splitWaypoints(importedWaypoints);

      if (importedCoords.length === 0) {
        throw new Error('Imported GPX has no route geometry.');
      }

      if (effectiveMode === 'replace' || !currentRoute) {
        setCurrentRoute(importedRoute);
        const bounds = calculateBounds(importedCoords);
        fitMapToBounds({ ...bounds, reason: 'route_created' });
        const fallbackStart = importedCoords.length ? { lng: importedCoords[0][0], lat: importedCoords[0][1] } : undefined;
        const fallbackEnd = importedCoords.length
          ? { lng: importedCoords[importedCoords.length - 1][0], lat: importedCoords[importedCoords.length - 1][1] }
          : undefined;
        updateConstraints({
          start: waypointSplit.start ?? fallbackStart ?? constraints.start,
          end: waypointSplit.end ?? fallbackEnd,
          viaPoints: waypointSplit.viaPoints,
        });

        const points: Coordinate[] = [];
        const startPoint = waypointSplit.start ?? fallbackStart;
        const endPoint = waypointSplit.end ?? fallbackEnd;
        if (startPoint) points.push(startPoint);
        points.push(...waypointSplit.viaPoints);
        if (endPoint) points.push(endPoint);

        const importedSegments = buildSegmentsFromGeometry(importedCoords, points);
        if (importedSegments) {
          setImportedRouteSegments(importedSegments);
        } else {
          console.warn('[GpxImportDialog] Unable to segment imported route geometry');
        }
      } else {
        const existingCoords = routeGeometry || currentRoute.geometry?.coordinates || [];
        const mergedCoords = mergeCoordinates(existingCoords, importedCoords);
        setRouteGeometry(mergedCoords);
        addToRouteStats({
          distanceMeters: importedRoute.distanceMeters || 0,
          elevationGain: importedRoute.elevationGainMeters || 0,
          durationSeconds: importedRoute.estimatedTimeSeconds || 0,
          surfaceBreakdown: {
            paved: importedRoute.surfaceBreakdown.pavement || 0,
            gravel: importedRoute.surfaceBreakdown.gravel || 0,
            unpaved: 0,
            ground: importedRoute.surfaceBreakdown.dirt || 0,
            unknown: importedRoute.surfaceBreakdown.unknown || 0,
          },
        });
        const bounds = calculateBounds(mergedCoords);
        fitMapToBounds({ ...bounds, reason: 'route_created' });
        if (waypointSplit.viaPoints.length || waypointSplit.start || waypointSplit.end) {
          const mergedViaPoints = (constraints.viaPoints || []).concat(waypointSplit.viaPoints);
          updateConstraints({
            start: waypointSplit.start ?? constraints.start,
            end: waypointSplit.end ?? constraints.end,
            viaPoints: mergedViaPoints,
          });
        }
      }

      setGpxImportOpen(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to import GPX file.';
      setError(message);
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Dialog open={gpxImportOpen} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Import GPX</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              GPX File
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="outlined"
                component="label"
                startIcon={<FileUploadIcon />}
                disabled={isImporting}
              >
                Choose File
                <input type="file" hidden accept=".gpx" onChange={handleFileChange} />
              </Button>
              <Typography variant="body2" color="text.secondary">
                {selectedFile ? selectedFile.name : 'No file selected'}
              </Typography>
            </Stack>
          </Box>

          {hasRoute && (
            <FormControl>
              <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                When a route is already on the map
              </Typography>
              <RadioGroup
                value={effectiveMode}
                onChange={(event) => setImportMode(event.target.value as ImportMode)}
              >
                <FormControlLabel
                  value="replace"
                  control={<Radio />}
                  label="Replace the current route"
                />
                <FormControlLabel
                  value="append"
                  control={<Radio />}
                  label="Add GPX waypoints to the current route"
                />
              </RadioGroup>
            </FormControl>
          )}

          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={isImporting}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleImport} disabled={isImporting || !selectedFile}>
          {isImporting ? 'Importing...' : 'Import'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
