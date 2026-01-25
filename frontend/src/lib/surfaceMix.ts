import type { SurfaceBreakdown, SurfaceType } from '@/types';

export type SimplifiedSurfaceType = 'paved' | 'unpaved' | 'unknown';

export type SurfaceBreakdownInput = Partial<SurfaceBreakdown> & {
  paved?: number;
  unpaved?: number;
  ground?: number;
};

const toNumber = (value: unknown) => (Number.isFinite(value as number) ? (value as number) : 0);

export const normalizeSurfaceBreakdown = (input?: SurfaceBreakdownInput | null): SurfaceBreakdown => {
  if (!input) {
    return { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
  }

  // Check if input uses detailed format (pavement, gravel, dirt, singletrack)
  const hasDetailed = ['pavement', 'gravel', 'dirt', 'singletrack'].some((key) => key in input);

  const normalized: SurfaceBreakdown = {
    pavement: 0,
    gravel: 0,
    dirt: 0,
    singletrack: 0,
    unknown: 0,
  };

  if (hasDetailed) {
    // Input is already in detailed format
    normalized.pavement = toNumber(input.pavement);
    normalized.gravel = toNumber(input.gravel);
    normalized.dirt = toNumber(input.dirt);
    normalized.singletrack = toNumber(input.singletrack);
    normalized.unknown = toNumber(input.unknown);
  } else {
    // Input is in simplified/backend format (paved, unpaved, gravel, ground)
    normalized.pavement = toNumber(input.paved);
    normalized.gravel = toNumber(input.gravel);
    normalized.dirt = toNumber(input.ground);
    normalized.singletrack = toNumber(input.singletrack);
    normalized.unknown = toNumber(input.unknown);

    // Handle unpaved: if unpaved is provided and we don't have detailed unpaved breakdown,
    // distribute it to dirt (most common unpaved type)
    const unpaved = toNumber(input.unpaved);
    const hasUnpavedDetail = normalized.gravel + normalized.dirt + normalized.singletrack > 0;
    if (unpaved > 0 && !hasUnpavedDetail) {
      // If we have unpaved but no detailed breakdown, assign it to dirt
      normalized.dirt = unpaved;
    } else if (unpaved > 0 && hasUnpavedDetail) {
      // If we have both unpaved and detailed breakdown, ensure they don't conflict
      // The detailed breakdown takes precedence, but we should verify the sum
      const detailedUnpaved = normalized.gravel + normalized.dirt + normalized.singletrack;
      if (Math.abs(detailedUnpaved - unpaved) > 1) {
        // If there's a significant difference, trust the detailed breakdown
        // and ignore the unpaved aggregate
        console.warn('[normalizeSurfaceBreakdown] Mismatch between unpaved aggregate and detailed breakdown', {
          unpaved,
          detailedUnpaved,
          using: 'detailed',
        });
      }
    }
  }

  // Calculate unknown if not provided or invalid
  if (!Number.isFinite(normalized.unknown) || normalized.unknown < 0) {
    const known = normalized.pavement + normalized.gravel + normalized.dirt + normalized.singletrack;
    normalized.unknown = Math.max(0, 100 - known);
  }

  // Ensure all values are valid numbers
  normalized.pavement = Math.max(0, toNumber(normalized.pavement));
  normalized.gravel = Math.max(0, toNumber(normalized.gravel));
  normalized.dirt = Math.max(0, toNumber(normalized.dirt));
  normalized.singletrack = Math.max(0, toNumber(normalized.singletrack));
  normalized.unknown = Math.max(0, toNumber(normalized.unknown));

  return normalized;
};

export type SurfaceMix = {
  paved: number;
  unpaved: number;
  unknown: number;
};

/**
 * Detailed surface breakdown that preserves individual surface types
 */
export type DetailedSurfaceMix = {
  pavement: number;
  gravel: number;
  dirt: number;
  singletrack: number;
  unknown: number;
};

const normalizeMix = (mix: SurfaceMix): SurfaceMix => {
  const total = mix.paved + mix.unpaved + mix.unknown;
  if (total <= 0) {
    return { paved: 0, unpaved: 0, unknown: 100 };
  }
  if (total > 99 && total < 101) {
    return mix;
  }
  const scale = 100 / total;
  return {
    paved: mix.paved * scale,
    unpaved: mix.unpaved * scale,
    unknown: mix.unknown * scale,
  };
};

/**
 * Get simplified paved/unpaved/unknown mix from detailed breakdown.
 * 
 * IMPORTANT: unknown is kept separate, NOT added to paved.
 * This was a critical bug that caused all routes to appear 100% paved.
 */
export const getSurfaceMix = (surface: SurfaceBreakdown): SurfaceMix => {
  const mix = {
    paved: surface.pavement || 0,
    unpaved: (surface.gravel || 0) + (surface.dirt || 0) + (surface.singletrack || 0),
    unknown: surface.unknown || 0,
  };
  return normalizeMix(mix);
};

/**
 * Get detailed surface breakdown with all surface types preserved.
 */
export const getDetailedSurfaceMix = (surface: SurfaceBreakdown): DetailedSurfaceMix => {
  const total = (surface.pavement || 0) + (surface.gravel || 0) + 
                (surface.dirt || 0) + (surface.singletrack || 0) + (surface.unknown || 0);
  
  if (total <= 0) {
    return { pavement: 0, gravel: 0, dirt: 0, singletrack: 0, unknown: 100 };
  }
  
  const scale = total > 99 && total < 101 ? 1 : 100 / total;
  return {
    pavement: (surface.pavement || 0) * scale,
    gravel: (surface.gravel || 0) * scale,
    dirt: (surface.dirt || 0) * scale,
    singletrack: (surface.singletrack || 0) * scale,
    unknown: (surface.unknown || 0) * scale,
  };
};

/**
 * Check if surface data is mostly unknown and needs enrichment.
 */
export const needsSurfaceEnrichment = (surface: SurfaceBreakdown): boolean => {
  const unknown = surface.unknown || 0;
  // Need enrichment if more than 30% unknown
  return unknown > 30;
};

export const getSurfaceMixBreakdown = (surface: SurfaceBreakdown): SurfaceBreakdown => {
  const mix = getSurfaceMix(surface);
  return {
    pavement: mix.paved,
    gravel: mix.unpaved > 0 ? mix.unpaved : 0,
    dirt: 0,
    singletrack: 0,
    unknown: mix.unknown,
  };
};

/**
 * Map a detailed SurfaceType to a simplified surface type.
 * Used for display purposes where we only show paved/unpaved/unknown.
 */
export const mapSurfaceTypeToSimplified = (surfaceType: SurfaceType): SimplifiedSurfaceType => {
  switch (surfaceType) {
    case 'pavement':
      return 'paved';
    case 'gravel':
    case 'dirt':
    case 'singletrack':
      return 'unpaved';
    case 'unknown':
    default:
      return 'unknown';
  }
};

/**
 * Get simplified surface mix (paved/unpaved/unknown) from detailed breakdown.
 * This is an alias for getSurfaceMix for clarity in the simplified context.
 */
export const getSimplifiedSurfaceMix = (surface: SurfaceBreakdown): SurfaceMix => {
  return getSurfaceMix(surface);
};
