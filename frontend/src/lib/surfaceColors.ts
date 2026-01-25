export const SURFACE_COLORS = {
  pavement: '#F7B733',    // Logo gold
  gravel: '#FFD86B',      // Logo light gold
  dirt: '#C97C1B',        // Logo deep amber
  singletrack: '#E13D7E', // Logo magenta
  unknown: '#8B7A74',     // Warm neutral
} as const;

export const SURFACE_ORDER: Array<keyof typeof SURFACE_COLORS> = [
  'singletrack',
  'gravel',
  'dirt',
  'pavement',
  'unknown',
];

export type SurfaceType = keyof typeof SURFACE_COLORS;

// Simplified surface colors for paved/unpaved/unknown display
export const SIMPLIFIED_SURFACE_COLORS = {
  paved: '#BC3081',
  unpaved: '#FFB156',
  unknown: '#8B7A74',    // Warm neutral for unknown
} as const;

export type SimplifiedSurfaceType = keyof typeof SIMPLIFIED_SURFACE_COLORS;
