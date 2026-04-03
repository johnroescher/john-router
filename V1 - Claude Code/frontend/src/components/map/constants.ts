/**
 * Map constants, styles, and configuration
 */

import type { StyleSpecification } from 'maplibre-gl';

const THUNDERFOREST_API_KEY = process.env.NEXT_PUBLIC_THUNDERFOREST_API_KEY ?? '';
const THUNDERFOREST_ATTRIBUTION = 'Maps © Thunderforest, Data © OpenStreetMap contributors';

const buildThunderforestStyle = (styleId: 'cycle' | 'outdoors'): StyleSpecification => ({
  version: 8,
  sources: {
    thunderforest: {
      type: 'raster',
      tiles: [
        `https://tile.thunderforest.com/${styleId}/{z}/{x}/{y}.png?apikey=${THUNDERFOREST_API_KEY}`,
      ],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 22,
      attribution: THUNDERFOREST_ATTRIBUTION,
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: { 'background-color': '#FFF8F1' },
    },
    {
      id: 'thunderforest',
      type: 'raster',
      source: 'thunderforest',
      minzoom: 0,
      maxzoom: 22,
    },
  ],
});

export const MAP_STYLES = {
  default: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
  openCycle: buildThunderforestStyle('cycle'),
  outdoor: buildThunderforestStyle('outdoors'),
} as const;

export type MapStyleKey = keyof typeof MAP_STYLES;

export const MAP_STYLE_OPTIONS = [
  { id: 'default' as const, label: 'Default' },
  { id: 'openCycle' as const, label: 'Open Cycle Map' },
  { id: 'outdoor' as const, label: 'Outdoor Map' },
] as const;

// Fallback OSM raster style for when vector tiles fail
export const FALLBACK_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: 'raster' as const,
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background' as const,
      paint: { 'background-color': '#F3E9E2' },
    },
    {
      id: 'osm',
      type: 'raster' as const,
      source: 'osm',
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

// Route layer colors
export const ROUTE_COLORS = {
  outline: '#2B1F1A',
  main: '#BC3081',
  hover: '#FFD86B',
  selected: '#E13D7E',
} as const;

// Surface type colors for route visualization
export const SURFACE_ROUTE_COLORS = {
  pavement: ROUTE_COLORS.main,
  gravel: ROUTE_COLORS.main,
  dirt: ROUTE_COLORS.main,
  singletrack: ROUTE_COLORS.main,
  unknown: '#8B7A74',
} as const;

// MTB difficulty colors (IMBA trail rating)
export const MTB_DIFFICULTY_COLORS = {
  green: '#22c55e',
  blue: '#3b82f6',
  black: '#1f2937',
  double_black: '#7c3aed',
  unknown: '#6b7280',
} as const;

// Marker colors
export const MARKER_COLORS = {
  start: '#F7B733',
  end: '#E13D7E',
  via: '#C97C1B',
  hover: '#FFD86B',
} as const;

// Default view settings (Denver, CO)
export const DEFAULT_VIEW = {
  longitude: -104.9903,
  latitude: 39.7392,
  zoom: 12,
} as const;

// Map interaction settings
export const MAP_SETTINGS = {
  minZoom: 2,
  maxZoom: 20,
  scrollZoom: true,
  boxZoom: true,
  dragRotate: false, // Disable rotation for simpler UX
  dragPan: true,
  keyboard: true,
  doubleClickZoom: true,
  touchZoomRotate: true,
} as const;

// Layer IDs
export const LAYER_IDS = {
  routeOutline: 'route-outline',
  routeLine: 'route-line',
  routeSurfacePaved: 'route-surface-paved',
  routeSurfaceUnpaved: 'route-surface-unpaved',
  routeSurfaceUnknown: 'route-surface-unknown',
  hoverPoint: 'hover-point',
} as const;

// Source IDs
export const SOURCE_IDS = {
  route: 'route',
  routeSurface: 'route-surface',
  hoverPoint: 'hover-point',
} as const;

// Surface sampling source and layers (for surface inference)
export const SURFACE_SAMPLE_SOURCE = 'surface-sample';
export const SURFACE_SAMPLE_LAYERS = {
  trail: 'surface-sample-trail',
  road: 'surface-sample-road',
  landcover: 'surface-sample-landcover',
  landuse: 'surface-sample-landuse',
  park: 'surface-sample-park',
} as const;
