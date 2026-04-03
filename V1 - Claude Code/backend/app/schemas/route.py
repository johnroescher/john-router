"""Route-related schemas."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field

from .common import Coordinate, GeoJSONLineString, BoundingBox


class SportType(str, Enum):
    """Supported sport types."""
    ROAD = "road"
    GRAVEL = "gravel"
    MTB = "mtb"
    EMTB = "emtb"


class RouteType(str, Enum):
    """Route shape types."""
    LOOP = "loop"
    OUT_AND_BACK = "out_and_back"
    POINT_TO_POINT = "point_to_point"


class RoutingService(str, Enum):
    """Routing service selector."""
    AUTO = "auto"
    ORS = "ors"
    BROUTER = "brouter"
    GRAPHOPPER = "graphhopper"
    VALHALLA = "valhalla"


class WaypointType(str, Enum):
    """Waypoint types."""
    START = "start"
    END = "end"
    VIA = "via"
    POI = "poi"
    COFFEE = "coffee"
    WATER = "water"
    RESTROOM = "restroom"
    VIEWPOINT = "viewpoint"
    BIKE_SHOP = "bike_shop"


class MTBDifficulty(str, Enum):
    """MTB difficulty ratings."""
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"
    VERY_HARD = "very_hard"


class SurfacePreferences(BaseModel):
    """Surface mix preferences (must sum to 1.0)."""
    pavement: float = Field(0.33, ge=0, le=1)
    gravel: float = Field(0.33, ge=0, le=1)
    singletrack: float = Field(0.34, ge=0, le=1)


class MTBFeaturePreferences(BaseModel):
    """MTB feature preferences."""
    flow: bool = False
    berms: bool = False
    jumps: bool = False
    drops: bool = False
    rock_gardens: bool = False
    roots: bool = False
    technical_climbs: bool = False
    chunk: bool = False


class HazardAvoidances(BaseModel):
    """Hazards to avoid."""
    exposure: bool = True
    cliff_edges: bool = True
    loose_terrain: bool = False
    water_crossings: bool = False
    high_speed_road_crossings: bool = True
    night_unsafe: bool = False


class RouteConstraints(BaseModel):
    """Constraints for route generation."""
    # Location
    start: Coordinate
    end: Optional[Coordinate] = None
    route_type: RouteType = RouteType.LOOP
    via_points: List[Coordinate] = Field(default_factory=list)
    avoid_areas: List[List[Coordinate]] = Field(default_factory=list)

    # Sport type
    sport_type: SportType = SportType.MTB

    # Routing service selection
    routing_service: RoutingService = RoutingService.AUTO
    routing_profile: Optional[str] = None

    # Distance/Time/Elevation targets
    target_distance_meters: Optional[float] = None
    min_distance_meters: Optional[float] = None
    max_distance_meters: Optional[float] = None
    distance_hard_constraint: bool = False

    target_time_seconds: Optional[int] = None
    time_hard_constraint: bool = False

    target_elevation_gain_meters: Optional[float] = None
    max_elevation_gain_meters: Optional[float] = None
    elevation_hard_constraint: bool = False

    # Climb emphasis: -1 (descent focused) to 1 (climb focused)
    climb_emphasis: float = Field(0, ge=-1, le=1)

    # Surface preferences
    surface_preferences: SurfacePreferences = Field(default_factory=SurfacePreferences)
    allow_hike_a_bike: bool = False
    prefer_bike_lanes: bool = True
    prefer_designated_mtb_trails: bool = True

    # MTB difficulty
    mtb_difficulty_target: MTBDifficulty = MTBDifficulty.MODERATE
    max_downhill_grade_percent: float = Field(15, ge=0, le=50)
    max_uphill_grade_percent: float = Field(20, ge=0, le=50)

    # MTB features
    mtb_features: MTBFeaturePreferences = Field(default_factory=MTBFeaturePreferences)

    # Hazard avoidances
    hazard_avoidances: HazardAvoidances = Field(default_factory=HazardAvoidances)

    # Safety & Legal
    avoid_highways: bool = False
    avoid_unpaved_when_road: bool = False
    avoid_private: bool = False
    require_bicycle_legal: bool = True

    # Quality mode
    quality_mode: bool = True
    num_alternatives: int = Field(3, ge=1, le=5)


class WaypointCreate(BaseModel):
    """Create a waypoint."""
    waypoint_type: WaypointType
    point: Coordinate
    name: Optional[str] = None
    lock_strength: str = "soft"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WaypointResponse(BaseModel):
    """Waypoint in response."""
    id: UUID
    idx: int
    waypoint_type: WaypointType
    point: Coordinate
    name: Optional[str]
    lock_strength: str
    metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class HazardInfo(BaseModel):
    """Information about a hazard on the route."""
    type: str
    severity: str  # high, medium, low
    description: str
    location: Optional[Coordinate] = None
    segment_idx: Optional[int] = None
    evidence: Optional[str] = None
    mitigation: Optional[str] = None


class SegmentResponse(BaseModel):
    """Route segment in response."""
    id: UUID
    idx: int
    geometry: GeoJSONLineString
    distance_meters: Optional[float]
    elevation_gain_meters: Optional[float]
    elevation_loss_meters: Optional[float]
    avg_grade: Optional[float]
    max_grade: Optional[float]
    surface: Optional[str]
    highway_type: Optional[str]
    way_name: Optional[str]
    mtb_scale: Optional[float]
    bicycle_access: str
    hazards: List[HazardInfo]
    confidence_score: float

    class Config:
        from_attributes = True


class SurfaceBreakdown(BaseModel):
    """Surface type breakdown (percentages)."""
    pavement: float = 0
    gravel: float = 0
    dirt: float = 0
    singletrack: float = 0
    unknown: float = 100


class SurfaceSegment(BaseModel):
    """Surface segment along a route."""
    startIndex: int
    endIndex: int
    startDistanceMeters: float
    endDistanceMeters: float
    distanceMeters: float
    surfaceType: str
    confidence: float
    matchDistanceMeters: Optional[float] = None
    source: str
    osmWayId: Optional[int] = None


class SurfaceQualityMetrics(BaseModel):
    """Quality metrics for surface matching."""
    coveragePercent: float
    avgConfidence: float
    avgMatchDistanceMeters: Optional[float] = None


class SegmentedSurfaceData(BaseModel):
    """Segment-level surface data for a route."""
    segments: List[SurfaceSegment]
    knownDistanceMeters: float
    totalDistanceMeters: float
    dataQuality: float
    qualityMetrics: Optional[SurfaceQualityMetrics] = None
    lastUpdated: str
    enrichmentSource: Optional[str] = None


class SurfaceMatchRequest(BaseModel):
    """Request for surface matching."""
    geometry: GeoJSONLineString


class SurfaceMatchResponse(BaseModel):
    """Response for surface matching."""
    status: str = "ok"
    message: Optional[str] = None
    segmentedSurface: Optional[SegmentedSurfaceData] = None


class MTBDifficultyBreakdown(BaseModel):
    """MTB difficulty breakdown (percentages)."""
    green: float = 0
    blue: float = 0
    black: float = 0
    double_black: float = 0
    unknown: float = 100


class ElevationPoint(BaseModel):
    """Point on elevation profile."""
    distance_meters: float
    elevation_meters: float
    grade_percent: float
    coordinate: Coordinate


class RouteAnalysis(BaseModel):
    """Detailed route analysis."""
    # Basic stats
    distance_meters: float
    elevation_gain_meters: float
    elevation_loss_meters: float
    estimated_time_seconds: int
    max_elevation_meters: float
    min_elevation_meters: float

    # Grades
    avg_grade_percent: float
    max_grade_percent: float
    longest_climb_meters: float
    steepest_100m_percent: float
    steepest_1km_percent: float
    climbing_above_8_percent_meters: float

    # Surface breakdown
    surface_breakdown: SurfaceBreakdown

    # MTB analysis
    mtb_difficulty_breakdown: MTBDifficultyBreakdown
    max_technical_rating: Optional[float]
    hike_a_bike_sections: int
    hike_a_bike_distance_meters: float

    # Difficulty ratings (0-5)
    physical_difficulty: float
    technical_difficulty: float
    risk_rating: float
    overall_difficulty: float

    # Elevation profile
    elevation_profile: List[ElevationPoint]

    # Confidence
    confidence_score: float
    data_completeness: float


class ValidationIssue(BaseModel):
    """A validation issue (error, warning, or info)."""
    type: str  # connectivity, legality, safety, difficulty, closure
    severity: str  # error, warning, info
    message: str
    segment_idx: Optional[int] = None
    location: Optional[Coordinate] = None
    fix_suggestion: Optional[str] = None


class RouteValidation(BaseModel):
    """Route validation results."""
    status: str  # valid, warnings, errors
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    info: List[ValidationIssue]
    confidence_score: float


class RouteCreate(BaseModel):
    """Create a new route."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    sport_type: SportType = SportType.MTB
    geometry: GeoJSONLineString
    tags: List[str] = Field(default_factory=list)
    is_public: bool = False


class RouteUpdate(BaseModel):
    """Update an existing route."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    sport_type: Optional[SportType] = None
    geometry: Optional[GeoJSONLineString] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None


class RouteResponse(BaseModel):
    """Full route response."""
    id: UUID
    user_id: Optional[UUID]
    name: str
    description: Optional[str]
    sport_type: SportType
    geometry: Optional[GeoJSONLineString]

    # Stats
    distance_meters: Optional[float]
    elevation_gain_meters: Optional[float]
    elevation_loss_meters: Optional[float]
    estimated_time_seconds: Optional[int]
    max_elevation_meters: Optional[float]
    min_elevation_meters: Optional[float]

    # Breakdowns
    surface_breakdown: SurfaceBreakdown
    mtb_difficulty_breakdown: MTBDifficultyBreakdown

    # Difficulty
    physical_difficulty: Optional[float]
    technical_difficulty: Optional[float]
    risk_rating: Optional[float]
    overall_difficulty: Optional[float]

    # Metadata
    tags: List[str]
    is_public: bool
    confidence_score: float

    # Validation
    validation_status: str
    validation_results: RouteValidation

    # Relationships
    waypoints: List[WaypointResponse] = Field(default_factory=list)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RouteListResponse(BaseModel):
    """Route list item (summary)."""
    id: UUID
    name: str
    sport_type: SportType
    distance_meters: Optional[float]
    elevation_gain_meters: Optional[float]
    estimated_time_seconds: Optional[int]
    surface_breakdown: SurfaceBreakdown
    overall_difficulty: Optional[float]
    confidence_score: float
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RouteCandidateResponse(BaseModel):
    """A candidate route with comparison info."""
    route: RouteResponse
    analysis: RouteAnalysis
    validation: RouteValidation
    rank: int
    explanation: str
    tradeoffs: Dict[str, str]


class GPXExport(BaseModel):
    """GPX export options."""
    route_id: UUID
    include_waypoints: bool = True
    include_extensions: bool = True
    simplify_tolerance: Optional[float] = None


class GPXImport(BaseModel):
    """GPX import result."""
    route: RouteResponse
    waypoints_imported: int
    tracks_imported: int
    warnings: List[str]


class CueSheetItem(BaseModel):
    """Single item in cue sheet."""
    idx: int
    instruction: str
    distance_meters: float
    cumulative_distance_meters: float
    turn_type: Optional[str]
    way_name: Optional[str]
    notes: Optional[str]


class CueSheet(BaseModel):
    """Full cue sheet for a route."""
    route_id: UUID
    items: List[CueSheetItem]
    total_distance_meters: float


class PointToPointRequest(BaseModel):
    """Request for point-to-point routing between coordinates."""
    coordinates: List[Coordinate] = Field(..., min_length=2, description="List of coordinates to route between")
    sport_type: SportType = SportType.MTB


class GeometryAnalysisRequest(BaseModel):
    """Request for analyzing route geometry."""
    geometry: GeoJSONLineString


class SurfaceBreakdownResponse(BaseModel):
    """Surface type breakdown percentages."""
    paved: float = 0
    unpaved: float = 0
    gravel: float = 0
    ground: float = 0
    unknown: float = 0


class PointToPointResponse(BaseModel):
    """Response for point-to-point routing."""
    geometry: GeoJSONLineString
    distance_meters: float
    duration_seconds: float
    elevation_gain: float
    surface_breakdown: SurfaceBreakdownResponse
    degraded: bool = False
    degraded_reason: Optional[str] = None