/**
 * Type definitions for John Router frontend
 */

// Common types
export interface Coordinate {
  lng: number;
  lat: number;
}

export interface BoundingBox {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
}

export type SportType = 'road' | 'gravel' | 'mtb' | 'emtb';
export type RouteType = 'loop' | 'out_and_back' | 'point_to_point';
export type MTBDifficulty = 'easy' | 'moderate' | 'hard' | 'very_hard';
export type WaypointType = 'start' | 'end' | 'via' | 'poi' | 'coffee' | 'water' | 'restroom' | 'viewpoint' | 'bike_shop';
export type RoutingService = 'auto' | 'ors' | 'brouter' | 'graphhopper';

// Route types
export interface SurfaceBreakdown {
  pavement: number;
  gravel: number;
  dirt: number;
  singletrack: number;
  unknown: number;
}

// Segment-level surface data for accurate route visualization
export type SurfaceType = 'pavement' | 'gravel' | 'dirt' | 'singletrack' | 'unknown';

export interface SurfaceSegment {
  // Start and end indices in the route geometry coordinates array
  startIndex: number;
  endIndex: number;
  // Start and end distances along the route (meters)
  startDistanceMeters: number;
  endDistanceMeters: number;
  // Distance in meters for this segment
  distanceMeters: number;
  // The surface type for this segment
  surfaceType: SurfaceType;
  // Confidence level (0-1) for this surface classification
  confidence: number;
  // Optional match distance (meters) from route to matched way
  matchDistanceMeters?: number;
  // Source of the surface data
  source: 'routing_api' | 'overpass' | 'map_inference' | 'default';
  // Optional OSM way ID if available
  osmWayId?: number;
}

export interface SegmentedSurfaceData {
  // Array of surface segments along the route
  segments: SurfaceSegment[];
  // Total distance covered by known surfaces
  knownDistanceMeters: number;
  // Total route distance
  totalDistanceMeters: number;
  // Data quality score (0-100)
  dataQuality: number;
  // Quality metrics for debugging and UI
  qualityMetrics?: {
    coveragePercent: number;
    avgConfidence: number;
    avgMatchDistanceMeters?: number;
  };
  // When this data was last updated
  lastUpdated: string;
  // Source of the enrichment
  enrichmentSource: 'routing_api' | 'overpass' | 'map_inference' | 'combined' | null;
}

export interface SurfaceMatchResponse {
  status: string;
  message?: string;
  segmentedSurface?: SegmentedSurfaceData;
}

export interface MTBDifficultyBreakdown {
  green: number;
  blue: number;
  black: number;
  double_black: number;
  unknown: number;
}

export interface RouteWaypoint {
  id: string;
  idx: number;
  waypointType: WaypointType;
  point: Coordinate;
  name?: string;
  lockStrength: 'soft' | 'hard';
}

export interface ValidationIssue {
  type: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  segmentIdx?: number;
  location?: Coordinate;
  fixSuggestion?: string;
}

export interface RouteValidation {
  status: 'valid' | 'warnings' | 'errors';
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  info: ValidationIssue[];
  confidenceScore: number;
}

export interface Route {
  id: string;
  userId?: string;
  name: string;
  description?: string;
  sportType: SportType;
  geometry?: GeoJSONLineString;

  // Stats
  distanceMeters?: number;
  elevationGainMeters?: number;
  elevationLossMeters?: number;
  estimatedTimeSeconds?: number;
  maxElevationMeters?: number;
  minElevationMeters?: number;

  // Breakdowns
  surfaceBreakdown: SurfaceBreakdown;
  mtbDifficultyBreakdown: MTBDifficultyBreakdown;

  // Difficulty
  physicalDifficulty?: number;
  technicalDifficulty?: number;
  riskRating?: number;
  overallDifficulty?: number;

  // Metadata
  tags: string[];
  isPublic: boolean;
  confidenceScore: number;

  // Validation
  validationStatus: string;
  validationResults: RouteValidation;

  // Relationships
  waypoints: RouteWaypoint[];

  // Timestamps
  createdAt: string;
  updatedAt: string;
}

export interface GeoJSONLineString {
  type: 'LineString';
  coordinates: number[][];
}

export interface GeoJSONPoint {
  type: 'Point';
  coordinates: number[];
}

// Route constraints
export interface SurfacePreferences {
  pavement: number;
  gravel: number;
  singletrack: number;
}

export interface MTBFeaturePreferences {
  flow: boolean;
  berms: boolean;
  jumps: boolean;
  drops: boolean;
  rockGardens: boolean;
  roots: boolean;
  technicalClimbs: boolean;
  chunk: boolean;
}

export interface HazardAvoidances {
  exposure: boolean;
  cliffEdges: boolean;
  looseTerrain: boolean;
  waterCrossings: boolean;
  highSpeedRoadCrossings: boolean;
  nightUnsafe: boolean;
}

export interface RouteConstraints {
  start?: Coordinate;
  end?: Coordinate;
  routeType: RouteType;
  viaPoints: Coordinate[];
  avoidAreas: Coordinate[][];
  sportType: SportType;
  routingService: RoutingService;
  routingProfile?: string;

  targetDistanceMeters?: number;
  minDistanceMeters?: number;
  maxDistanceMeters?: number;
  distanceHardConstraint: boolean;

  targetTimeSeconds?: number;
  timeHardConstraint: boolean;

  targetElevationGainMeters?: number;
  maxElevationGainMeters?: number;
  elevationHardConstraint: boolean;

  climbEmphasis: number;
  surfacePreferences: SurfacePreferences;
  allowHikeABike: boolean;
  preferBikeLanes: boolean;
  preferDesignatedMtbTrails: boolean;

  mtbDifficultyTarget: MTBDifficulty;
  maxDownhillGradePercent: number;
  maxUphillGradePercent: number;
  mtbFeatures: MTBFeaturePreferences;
  hazardAvoidances: HazardAvoidances;

  avoidHighways: boolean;
  avoidUnpavedWhenRoad: boolean;
  avoidPrivate: boolean;
  requireBicycleLegal: boolean;

  qualityMode: boolean;
  numAlternatives: number;
}

// Elevation profile
export interface ElevationPoint {
  distanceMeters: number;
  elevationMeters: number;
  gradePercent: number;
  coordinate: Coordinate;
}

// Route analysis
export interface RouteAnalysis {
  distanceMeters: number;
  elevationGainMeters: number;
  elevationLossMeters: number;
  estimatedTimeSeconds: number;
  maxElevationMeters: number;
  minElevationMeters: number;

  avgGradePercent: number;
  maxGradePercent: number;
  longestClimbMeters: number;
  steepest100mPercent: number;
  steepest1kmPercent: number;
  climbingAbove8PercentMeters: number;

  surfaceBreakdown: SurfaceBreakdown;
  mtbDifficultyBreakdown: MTBDifficultyBreakdown;
  maxTechnicalRating?: number;
  hikeABikeSections: number;
  hikeABikeDistanceMeters: number;

  physicalDifficulty: number;
  technicalDifficulty: number;
  riskRating: number;
  overallDifficulty: number;

  elevationProfile: ElevationPoint[];
  confidenceScore: number;
  dataCompleteness: number;
}

// Chat types
export interface ActionChip {
  id: string;
  label: string;
  action: string;
  data: Record<string, unknown>;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface StatusUpdate {
  stage: string;
  message: string;
  progress?: number;
  timestamp: string;
}

export interface CyclingFactsResponse {
  facts: string[];
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: string;
  toolCalls?: ToolCall[];
  actionChips?: ActionChip[];
  confidence?: number;
  isStatus?: boolean; // Temporary status message that will be replaced
  statusUpdate?: StatusUpdate; // Current status update for status messages
}

export interface ChatRequest {
  message: string;
  conversationId?: string;
  routeId?: string;
  currentConstraints?: Partial<RouteConstraints>;
  currentRouteGeometry?: number[][];
  mapCenter?: Coordinate;
  qualityMode: boolean;
  explainMode: boolean;
}

export interface RouteData {
  geometry: GeoJSONLineString;
  distance_meters: number;
  elevation_gain: number;
  duration_seconds: number;
  sport_type: string;
  route_type: string;
  surface_breakdown?: {
    pavement: number;
    gravel: number;
    dirt: number;
    singletrack: number;
    unknown: number;
  };
}

export interface IntentObject {
  intent_id: string;
  timestamp: string;
  hard_constraints: {
    time_minutes?: { min?: number | null; max?: number | null };
    distance_km?: { min?: number | null; max?: number | null };
  };
  change_intent?: {
    strategy?: 'auto' | 'modify_existing' | 'regenerate';
    rationale?: string | null;
    priority?: string[];
    requested_changes?: string[];
  };
}

export interface RideBriefSummary {
  one_liner: string;
  bullets: string[];
}

export interface RideBrief {
  brief_id: string;
  intent_id: string;
  implicit_defaults: {
    pavement_max_pct: { value?: number | null; source: string; confidence: number };
    technical_max: { value?: string | null; source: string; confidence: number };
    traffic_stress_max: { value?: string | null; source: string; confidence: number };
  };
  brief_summary_for_ui: RideBriefSummary;
}

export interface CandidateIssue {
  severity: 'error' | 'warn' | 'info';
  type: string;
  message: string;
}

export interface CandidateRoute {
  candidate_id: string;
  label: string;
  routing_profile: string;
  generation_strategy: string;
  geometry: GeoJSONLineString;
  computed: {
    distance_km: number;
    time_est_min: number;
    elevation_gain_m: number;
    surface_mix: {
      pavement: number;
      gravel: number;
      dirt: number;
      singletrack: number;
      unknown: number;
    };
    data_confidence: number;
  };
  validation: {
    status: 'pass' | 'warn' | 'fail';
    issues: CandidateIssue[];
  };
}

export interface CritiqueReport {
  ranked_candidates: Array<{
    candidate_id: string;
    score_total: number;
    recommendation: 'primary' | 'secondary' | 'reject';
  }>;
}

export interface PlanningLoopResult {
  intent: IntentObject;
  ride_brief: RideBrief;
  candidates: CandidateRoute[];
  critique: CritiqueReport;
  iteration: number;
  status: string;
  selected_candidate_id?: string | null;
  failure_reason?: string | null;
  fallback_suggestion?: string | null;
}

export interface ChatResponse {
  conversationId: string;
  message: ChatMessage;
  routeId?: string;
  routeUpdated: boolean;
  routeDiff?: Record<string, unknown>;
  routeData?: RouteData;  // Full route data for immediate display
  suggestedPrompts: string[];
  planning?: PlanningLoopResult;
  routeCandidates?: RouteCandidate[];
}

// User types
export interface UserPreferences {
  bikeType: SportType;
  fitnessLevel: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  ftp?: number;
  typicalSpeedMph: number;
  maxClimbToleranceFt: number;
  mtbSkill: 'beginner' | 'intermediate' | 'advanced' | 'expert';
  riskTolerance: 'low' | 'medium' | 'high';
  surfacePreferences: SurfacePreferences;
  avoidances: string[];
  units: 'imperial' | 'metric';
}

export interface User {
  id: string;
  email?: string;
  name?: string;
  preferences: UserPreferences;
  createdAt: string;
  updatedAt: string;
}

// Candidate route
export interface RouteCandidate {
  route: Route;
  analysis: RouteAnalysis;
  validation: RouteValidation;
  rank: number;
  explanation: string;
  tradeoffs: Record<string, string>;
}
