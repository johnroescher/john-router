'use client';

/**
 * RouteLayer - Renders the route line using declarative Source/Layer components
 * 
 * Supports two modes for surface coloring:
 * 1. Segment-level coloring (accurate) - Uses enriched surface data with per-segment surface types
 * 2. Proportional coloring (fallback) - Distributes colors based on overall breakdown percentages
 */
import React, { useMemo, memo } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';
import type { LineLayerSpecification } from 'maplibre-gl';
import { useRouteStore } from '@/stores/routeStore';
import { useUIStore } from '@/stores/uiStore';
import { useSurfaceStore } from '@/stores/surfaceStore';
import { createSurfaceSegmentFeatures } from '@/lib/surfaceEnrichment';
import { mapSurfaceTypeToSimplified } from '@/lib/surfaceMix';
import { SIMPLIFIED_SURFACE_COLORS } from '@/lib/surfaceColors';
import { ROUTE_COLORS, SOURCE_IDS, LAYER_IDS } from '../constants';
import type { SimplifiedSurfaceType } from '@/lib/surfaceMix';

// Line layer paint specs
const routeOutlinePaint: LineLayerSpecification['paint'] = {
  'line-color': ROUTE_COLORS.outline,
  'line-width': 6,
  'line-opacity': 0.9,
};

const routeLinePaint: LineLayerSpecification['paint'] = {
  'line-color': ROUTE_COLORS.main,
  'line-width': 4,
  'line-opacity': 1,
};

const RouteLayer: React.FC = () => {
  const routeGeometry = useRouteStore((state) => state.routeGeometry);
  const showRouteOverlay = useUIStore((state) => state.showRouteOverlay);
  const showSurfaceColoring = useUIStore((state) => state.showSurfaceColoring);
  const segmentedSurface = useSurfaceStore((state) => state.segmentedSurface);
  
  // Automatically enable surface coloring when we have good quality surface data
  // This ensures the route line colors match the elevation graph
  const shouldShowSurfaceColoring = useMemo(() => {
    if (showSurfaceColoring) return true; // User explicitly enabled it
    // Auto-enable if we have good quality surface data
    return segmentedSurface && 
           segmentedSurface.segments.length > 0 && 
           segmentedSurface.dataQuality > 20;
  }, [showSurfaceColoring, segmentedSurface]);

  // Create GeoJSON data from route geometry
  const routeGeoJSON = useMemo(() => {
    if (!routeGeometry || routeGeometry.length < 2) {
      return {
        type: 'FeatureCollection' as const,
        features: [],
      };
    }

    return {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          properties: {},
          geometry: {
            type: 'LineString' as const,
            coordinates: routeGeometry,
          },
        },
      ],
    };
  }, [routeGeometry]);

  // Create surface-colored segments
  // Priority: Use segment-level data if available (accurate), otherwise fall back to proportional
  const surfaceGeoJSON = useMemo(() => {
    if (!shouldShowSurfaceColoring || !routeGeometry || routeGeometry.length < 2) {
      return {
        type: 'FeatureCollection' as const,
        features: [],
      };
    }

    // If we have enriched segment-level surface data, use it for accurate coloring
    if (segmentedSurface && segmentedSurface.segments.length > 0 && segmentedSurface.dataQuality > 20) {
      const features = createSurfaceSegmentFeatures(routeGeometry, segmentedSurface);
      
      // Map detailed surface types to simplified types (paved/unpaved/unknown)
      const simplifiedFeatures = features.map((feature) => {
        const detailedSurfaceType = feature.properties?.surfaceType;
        const simplifiedType = mapSurfaceTypeToSimplified(detailedSurfaceType ?? 'unknown');
        return {
          ...feature,
          properties: {
            ...feature.properties,
            surfaceType: simplifiedType,
          },
        };
      });
      
      // Merge adjacent segments with the same simplified surface type for smoother rendering
      const mergedFeatures: GeoJSON.Feature[] = [];
      let currentFeature: GeoJSON.Feature | null = null;
      
      for (const feature of simplifiedFeatures) {
        const surfaceType = feature.properties?.surfaceType as SimplifiedSurfaceType;
        if (feature.geometry.type !== 'LineString') continue;
        const coords = feature.geometry.coordinates as number[][];
        
        if (!currentFeature || currentFeature.properties?.surfaceType !== surfaceType) {
          // Start a new merged feature
          if (currentFeature) {
            mergedFeatures.push(currentFeature);
          }
          currentFeature = {
            ...feature,
            geometry: {
              ...feature.geometry,
              coordinates: [...coords],
            },
          };
        } else {
          if (currentFeature.geometry.type !== 'LineString') continue;
          // Merge with current feature - append coordinates (skip first point to avoid duplicates)
          const currentCoords = currentFeature.geometry.coordinates as number[][];
          const lastCoord = currentCoords[currentCoords.length - 1];
          const firstCoord = coords[0];
          
          // Check if coordinates match (allowing for floating point precision)
          const coordsMatch = lastCoord && firstCoord &&
            Math.abs(lastCoord[0] - firstCoord[0]) < 0.000001 &&
            Math.abs(lastCoord[1] - firstCoord[1]) < 0.000001;
          
          currentFeature.geometry.coordinates = [
            ...currentCoords,
            ...(coordsMatch ? coords.slice(1) : coords), // Skip first if it matches, otherwise include all
          ];
        }
      }
      
      // Add the last feature
      if (currentFeature) {
        mergedFeatures.push(currentFeature);
      }
      
      return {
        type: 'FeatureCollection' as const,
        features: mergedFeatures,
      };
    }

    // Fallback: show unknown when surface data is low quality
    const features: GeoJSON.Feature[] = [
      {
        type: 'Feature',
        properties: { surfaceType: 'unknown' as SimplifiedSurfaceType },
        geometry: { type: 'LineString', coordinates: routeGeometry },
      },
    ];

    return {
      type: 'FeatureCollection' as const,
      features,
    };
  }, [shouldShowSurfaceColoring, routeGeometry, segmentedSurface]);

  if (!showRouteOverlay || !routeGeometry || routeGeometry.length < 2) {
    return null;
  }

  return (
    <>
      {/* Main route source and layers */}
      <Source id={SOURCE_IDS.route} type="geojson" data={routeGeoJSON}>
        <Layer
          id={LAYER_IDS.routeOutline}
          type="line"
          layout={{
            'line-join': 'round',
            'line-cap': 'round',
          }}
          paint={routeOutlinePaint}
        />
        {!shouldShowSurfaceColoring && (
          <Layer
            id={LAYER_IDS.routeLine}
            type="line"
            layout={{
              'line-join': 'round',
              'line-cap': 'round',
            }}
            paint={routeLinePaint}
          />
        )}
      </Source>

      {/* Surface-colored route overlay - using simplified surface types (paved/unpaved/unknown) */}
      {shouldShowSurfaceColoring && surfaceGeoJSON.features.length > 0 && (
        <Source id={SOURCE_IDS.routeSurface} type="geojson" data={surfaceGeoJSON}>
          <Layer
            id={LAYER_IDS.routeSurfacePaved}
            type="line"
            filter={['==', ['get', 'surfaceType'], 'paved']}
            layout={{
              'line-join': 'round',
              'line-cap': 'round',
            }}
            paint={{
              'line-color': SIMPLIFIED_SURFACE_COLORS.paved,
              'line-width': 4,
            }}
          />
          <Layer
            id={LAYER_IDS.routeSurfaceUnpaved}
            type="line"
            filter={['==', ['get', 'surfaceType'], 'unpaved']}
            layout={{
              'line-join': 'round',
              'line-cap': 'round',
            }}
            paint={{
              'line-color': SIMPLIFIED_SURFACE_COLORS.unpaved,
              'line-width': 4,
            }}
          />
          <Layer
            id={LAYER_IDS.routeSurfaceUnknown}
            type="line"
            filter={['==', ['get', 'surfaceType'], 'unknown']}
            layout={{
              'line-join': 'round',
              'line-cap': 'round',
            }}
            paint={{
              'line-color': SIMPLIFIED_SURFACE_COLORS.unknown,
              'line-width': 4,
              'line-opacity': 0.8,
            }}
          />
        </Source>
      )}
    </>
  );
};

export default memo(RouteLayer);
