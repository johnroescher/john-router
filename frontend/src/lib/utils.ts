/**
 * Utility functions
 */

/**
 * Format distance for display
 */
export function formatDistance(meters: number, units: 'imperial' | 'metric' = 'imperial'): string {
  if (units === 'imperial') {
    const miles = meters / 1609.34;
    if (miles < 0.1) {
      return `${Math.round(meters * 3.28084)} ft`;
    }
    return `${miles.toFixed(1)} mi`;
  } else {
    if (meters < 1000) {
      return `${Math.round(meters)} m`;
    }
    return `${(meters / 1000).toFixed(1)} km`;
  }
}

/**
 * Format elevation for display
 */
export function formatElevation(meters: number, units: 'imperial' | 'metric' = 'imperial'): string {
  if (units === 'imperial') {
    return `${Math.round(meters * 3.28084)} ft`;
  }
  return `${Math.round(meters)} m`;
}

/**
 * Format time duration
 */
export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours === 0) {
    return `${minutes} min`;
  }

  if (minutes === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${minutes}m`;
}

/**
 * Format grade percentage
 */
export function formatGrade(percent: number): string {
  return `${percent.toFixed(1)}%`;
}

/**
 * Get color for grade
 */
export function getGradeColor(percent: number): string {
  const absGrade = Math.abs(percent);
  if (absGrade < 3) return '#4CAF50'; // Green
  if (absGrade < 6) return '#8BC34A'; // Light green
  if (absGrade < 10) return '#FFC107'; // Yellow
  if (absGrade < 15) return '#FF9800'; // Orange
  return '#F44336'; // Red
}

/**
 * Get color for surface type
 */
export function getSurfaceColor(surface: string): string {
  switch (surface.toLowerCase()) {
    case 'pavement':
    case 'asphalt':
    case 'paved':
      return '#607D8B';
    case 'gravel':
    case 'fine_gravel':
      return '#795548';
    case 'dirt':
    case 'earth':
      return '#8D6E63';
    case 'singletrack':
    case 'trail':
      return '#4CAF50';
    default:
      return '#9E9E9E';
  }
}

/**
 * Get color for MTB difficulty
 */
export function getMTBDifficultyColor(difficulty: string): string {
  switch (difficulty.toLowerCase()) {
    case 'green':
    case 'easy':
      return '#4CAF50';
    case 'blue':
    case 'moderate':
      return '#2196F3';
    case 'black':
    case 'hard':
      return '#212121';
    case 'double_black':
    case 'very_hard':
      return '#000000';
    default:
      return '#9E9E9E';
  }
}

/**
 * Get label for MTB difficulty
 */
export function getMTBDifficultyLabel(difficulty: string): string {
  switch (difficulty.toLowerCase()) {
    case 'green':
    case 'easy':
      return 'Green (Easy)';
    case 'blue':
    case 'moderate':
      return 'Blue (Intermediate)';
    case 'black':
    case 'hard':
      return 'Black (Difficult)';
    case 'double_black':
    case 'very_hard':
      return 'Double Black (Expert)';
    default:
      return 'Unknown';
  }
}

/**
 * Get severity color
 */
export function getSeverityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'error':
    case 'high':
      return '#F44336';
    case 'warning':
    case 'medium':
      return '#FF9800';
    case 'info':
    case 'low':
      return '#2196F3';
    default:
      return '#9E9E9E';
  }
}

/**
 * Get credibility color
 */
export function getCredibilityColor(credibility: string): string {
  switch (credibility.toLowerCase()) {
    case 'official':
      return '#4CAF50';
    case 'trail_org':
      return '#2196F3';
    case 'news':
      return '#FF9800';
    case 'community':
      return '#9C27B0';
    default:
      return '#9E9E9E';
  }
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Calculate bounding box for coordinates
 */
export function getBoundingBox(coordinates: number[][]): [number, number, number, number] {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;

  for (const coord of coordinates) {
    minLng = Math.min(minLng, coord[0]);
    minLat = Math.min(minLat, coord[1]);
    maxLng = Math.max(maxLng, coord[0]);
    maxLat = Math.max(maxLat, coord[1]);
  }

  return [minLng, minLat, maxLng, maxLat];
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

type SurfaceMix = {
  pavement?: number;
  gravel?: number;
  dirt?: number;
  singletrack?: number;
  unknown?: number;
};

type SportType = 'road' | 'gravel' | 'mtb' | 'emtb';
type FitnessLevel = 'beginner' | 'intermediate' | 'advanced' | 'expert';
type MtbSkill = 'beginner' | 'intermediate' | 'advanced' | 'expert';
type RiskTolerance = 'low' | 'medium' | 'high';

type EstimateRideTimeInput = {
  distanceMeters?: number;
  elevationGainMeters?: number;
  surfaceBreakdown?: SurfaceMix;
  sportType?: SportType;
  technicalDifficulty?: number;
  riskRating?: number;
  mtbDifficultyBreakdown?: {
    green?: number;
    blue?: number;
    black?: number;
    double_black?: number;
    unknown?: number;
  };
  avgGradePercent?: number;
  hikeABikeDistanceMeters?: number;
  viaPointsCount?: number;
  waypointCount?: number;
  preferences?: {
    fitnessLevel?: FitnessLevel;
    typicalSpeedMph?: number;
    mtbSkill?: MtbSkill;
    riskTolerance?: RiskTolerance;
  };
};

const getWeightedMtbDifficulty = (breakdown?: EstimateRideTimeInput['mtbDifficultyBreakdown']) => {
  if (!breakdown) return undefined;
  const totals = {
    green: breakdown.green || 0,
    blue: breakdown.blue || 0,
    black: breakdown.black || 0,
    double_black: breakdown.double_black || 0,
    unknown: breakdown.unknown || 0,
  };
  const total = totals.green + totals.blue + totals.black + totals.double_black + totals.unknown;
  if (total <= 0) return undefined;
  const score =
    (totals.green * 1 + totals.blue * 2 + totals.black * 3 + totals.double_black * 4) /
    Math.max(total - totals.unknown, 1);
  return clamp(score, 1, 4);
};

const normalizeSurfaceMix = (surfaceBreakdown?: SurfaceMix) => {
  const fallback = { pavement: 0.4, gravel: 0.25, dirt: 0.2, singletrack: 0.1, unknown: 0.05 };
  if (!surfaceBreakdown) return fallback;
  const raw = {
    pavement: surfaceBreakdown.pavement || 0,
    gravel: surfaceBreakdown.gravel || 0,
    dirt: surfaceBreakdown.dirt || 0,
    singletrack: surfaceBreakdown.singletrack || 0,
    unknown: surfaceBreakdown.unknown || 0,
  };
  const total = raw.pavement + raw.gravel + raw.dirt + raw.singletrack + raw.unknown;
  if (total <= 0) return fallback;
  return {
    pavement: raw.pavement / total,
    gravel: raw.gravel / total,
    dirt: raw.dirt / total,
    singletrack: raw.singletrack / total,
    unknown: raw.unknown / total,
  };
};

/**
 * Estimate ride time using multi-factor heuristics.
 */
export function estimateRideTimeSeconds(input: EstimateRideTimeInput): number {
  const distanceMeters = Math.max(input.distanceMeters || 0, 0);
  const elevationGainMeters = Math.max(input.elevationGainMeters || 0, 0);

  if (distanceMeters <= 0) {
    return 60;
  }

  const surfaceMix = normalizeSurfaceMix(input.surfaceBreakdown);

  const defaultSpeedMph: Record<SportType, number> = {
    road: 14,
    gravel: 11,
    mtb: 8,
    emtb: 12,
  };

  const sportType = input.sportType || 'road';
  const baseSpeedMph = input.preferences?.typicalSpeedMph || defaultSpeedMph[sportType];

  const fitnessMultiplierMap: Record<FitnessLevel, number> = {
    beginner: 0.8,
    intermediate: 1,
    advanced: 1.12,
    expert: 1.25,
  };
  const fitnessMultiplier =
    input.preferences?.fitnessLevel ? fitnessMultiplierMap[input.preferences.fitnessLevel] : 1;

  const mtbSkillMultiplierMap: Record<MtbSkill, number> = {
    beginner: 0.85,
    intermediate: 1,
    advanced: 1.08,
    expert: 1.15,
  };
  const mtbSkillMultiplier =
    input.preferences?.mtbSkill ? mtbSkillMultiplierMap[input.preferences.mtbSkill] : 1;

  const surfaceSpeedMultiplier =
    surfaceMix.pavement * 1 +
    surfaceMix.gravel * 0.85 +
    surfaceMix.dirt * 0.75 +
    surfaceMix.singletrack * 0.65 +
    surfaceMix.unknown * 0.8;

  const baseSpeedMps = baseSpeedMph * 0.44704;
  const adjustedSpeedMps =
    baseSpeedMps *
    surfaceSpeedMultiplier *
    fitnessMultiplier *
    (sportType === 'mtb' ? mtbSkillMultiplier : 1);

  const safeSpeedMps = Math.max(adjustedSpeedMps, 1.2);

  let timeSeconds = distanceMeters / safeSpeedMps;

  const difficultyScore =
    input.technicalDifficulty ??
    getWeightedMtbDifficulty(input.mtbDifficultyBreakdown);
  const riskScore = input.riskRating ?? (input.preferences?.riskTolerance === 'high' ? 0.4 : 0);
  const difficultyMultiplier = clamp(1 + (difficultyScore || 0) * 0.06 + riskScore * 0.05, 0.9, 1.4);
  timeSeconds *= difficultyMultiplier;

  const verticalRateBySport: Record<SportType, number> = {
    road: 850,
    gravel: 750,
    mtb: 650,
    emtb: 1000,
  };
  const verticalRateMph =
    verticalRateBySport[sportType] * (input.preferences?.fitnessLevel ? fitnessMultiplier : 1);
  const verticalRateMps = Math.max(verticalRateMph / 3600, 0.15);
  const climbPenaltySeconds = elevationGainMeters / verticalRateMps;
  timeSeconds += climbPenaltySeconds * 0.6;

  if (input.avgGradePercent && input.avgGradePercent > 6) {
    timeSeconds *= 1 + clamp((input.avgGradePercent - 6) / 20, 0, 0.2);
  }

  if (input.hikeABikeDistanceMeters && input.hikeABikeDistanceMeters > 0) {
    const walkSpeedMps = 1.34;
    const hikeDistance = Math.min(input.hikeABikeDistanceMeters, distanceMeters);
    const walkTime = hikeDistance / walkSpeedMps;
    const rideTime = hikeDistance / safeSpeedMps;
    timeSeconds += Math.max(walkTime - rideTime, 0);
  }

  const viaPointsCount = input.viaPointsCount || 0;
  const waypointCount = input.waypointCount || 0;
  const stopPenaltySeconds = viaPointsCount * 45 + waypointCount * 30;
  timeSeconds += stopPenaltySeconds;

  return Math.max(Math.round(timeSeconds), 60);
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;

  return function (...args: Parameters<T>) {
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(() => func(...args), wait);
  };
}

/**
 * Generate unique ID
 */
export function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36);
}

/**
 * Download blob as file
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const escapeXml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');

/**
 * Build a GPX blob from a LineString geometry.
 */
export function buildGpxBlob(params: { name: string; coordinates: number[][] }): Blob {
  const safeName = params.name.trim() || 'Route';
  const points = params.coordinates
    .filter((coord) => Array.isArray(coord) && coord.length >= 2)
    .map(([lng, lat]) => {
      const latValue = Number(lat);
      const lngValue = Number(lng);
      if (!Number.isFinite(latValue) || !Number.isFinite(lngValue)) {
        return null;
      }
      return `<trkpt lat="${latValue.toFixed(6)}" lon="${lngValue.toFixed(6)}"></trkpt>`;
    })
    .filter(Boolean)
    .join('');

  const gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="John Router" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>${escapeXml(safeName)}</name>
    <trkseg>
      ${points}
    </trkseg>
  </trk>
</gpx>`;

  return new Blob([gpx], { type: 'application/gpx+xml' });
}
