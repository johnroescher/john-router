"""Ride Brief Loop schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from .common import Coordinate


LocationType = Literal["point", "place", "current_location", "same_as_start", "none"]
RouteTypeLiteral = Literal["loop", "out_and_back", "point_to_point", "any"]
DisciplineLiteral = Literal["road", "gravel", "mtb", "emtb", "urban", "bikepacking", "training", "any"]
TechnicalLevel = Literal["green", "blue", "black", "double_black", "unknown"]
TechnicalTarget = Literal["flowy", "chunky", "mixed", "unknown"]
BiasLevel = Literal["low", "med", "high"]
NavComplexity = Literal["simple", "med", "complex", "unknown"]
StopTiming = Literal["early", "mid", "late", "any", "unknown"]
SourceTag = Literal["STATED", "ASSUMED"]


class LocationSpec(BaseModel):
    type: LocationType = "none"
    value: Optional[Union[str, Coordinate]] = None


class RangeMinutes(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class RangeKm(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class RangeMeters(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class SurfaceMix(BaseModel):
    pavement: Optional[float] = None
    gravel: Optional[float] = None
    dirt: Optional[float] = None
    singletrack: Optional[float] = None


class StopPreference(BaseModel):
    wanted: bool = False
    timing: StopTiming = "unknown"
    max_gap_km: Optional[float] = None


class HardConstraint(BaseModel):
    start: LocationSpec = Field(default_factory=LocationSpec)
    end: LocationSpec = Field(default_factory=LocationSpec)
    route_type: RouteTypeLiteral = "any"
    time_minutes: RangeMinutes = Field(default_factory=RangeMinutes)
    distance_km: RangeKm = Field(default_factory=RangeKm)
    elevation_gain_m: RangeMeters = Field(default_factory=RangeMeters)
    discipline: DisciplineLiteral = "any"
    must_pass_through: List[LocationSpec] = Field(default_factory=list)
    must_avoid: List[Dict[str, Any]] = Field(default_factory=list)


class SoftPreferences(BaseModel):
    surface_mix: SurfaceMix = Field(default_factory=SurfaceMix)
    technical_max: TechnicalLevel = "unknown"
    technical_target: TechnicalTarget = "unknown"
    scenic_bias: BiasLevel = "med"
    traffic_stress_max: BiasLevel = "unknown"
    crowds_avoidance: BiasLevel = "unknown"
    navigation_complexity: NavComplexity = "unknown"
    stops: Dict[str, StopPreference] = Field(default_factory=dict)


class Ambiguity(BaseModel):
    question: str
    why_it_matters: str
    default_if_unanswered: str


class IntentSource(BaseModel):
    raw_text: str
    conversation_id: Optional[UUID] = None
    turn_id: Optional[Union[str, int]] = None


class RouteChangeIntent(BaseModel):
    strategy: Literal["auto", "modify_existing", "regenerate"] = "auto"
    rationale: Optional[str] = None
    priority: List[str] = Field(default_factory=list)
    requested_changes: List[str] = Field(default_factory=list)


class IntentObject(BaseModel):
    version: str = "1.0"
    intent_id: str
    timestamp: str
    source: IntentSource
    hard_constraints: HardConstraint = Field(default_factory=HardConstraint)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    change_intent: RouteChangeIntent = Field(default_factory=RouteChangeIntent)
    ambiguities: List[Ambiguity] = Field(default_factory=list)
    assumptions_allowed: bool = True
    confidence: float = 0.5
    notes: List[str] = Field(default_factory=list)


class Archetype(BaseModel):
    name: str
    rationale: str
    confidence: float = 0.5


class ExperiencePhase(BaseModel):
    phase: str
    goal: str
    duration_pct: float
    constraints: List[str] = Field(default_factory=list)


class TaggedValue(BaseModel):
    value: Any = None
    source: SourceTag = "ASSUMED"
    confidence: float = 0.5


class TaggedNumber(TaggedValue):
    value: Optional[float] = None


class TaggedString(TaggedValue):
    value: Optional[str] = None


class GradeLimits(BaseModel):
    up_max_pct: TaggedNumber = Field(default_factory=TaggedNumber)
    down_max_pct: TaggedNumber = Field(default_factory=TaggedNumber)


class ImplicitDefaults(BaseModel):
    pavement_max_pct: TaggedNumber = Field(default_factory=TaggedNumber)
    singletrack_min_pct: TaggedNumber = Field(default_factory=TaggedNumber)
    traffic_stress_max: TaggedString = Field(default_factory=TaggedString)
    technical_max: TaggedString = Field(default_factory=TaggedString)
    grade_limits: GradeLimits = Field(default_factory=GradeLimits)
    stop_density: TaggedString = Field(default_factory=TaggedString)


class SuccessCriterion(BaseModel):
    id: str
    description: str
    metric: str
    target: Any
    priority: Literal["P0", "P1", "P2"] = "P1"


class Tradeoff(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    if_: str = Field(..., alias="if")
    then: str
    severity: BiasLevel = "med"


class FallbackStrategy(BaseModel):
    trigger: str
    action: str


class AskUserIfNeeded(BaseModel):
    question: str
    only_if: str
    default: str


class BriefSummary(BaseModel):
    one_liner: str
    bullets: List[str]


def _default_archetype() -> Archetype:
    return Archetype(name="custom", rationale="User-defined ride", confidence=0.5)


def _default_brief_summary() -> BriefSummary:
    return BriefSummary(one_liner="Route in progress", bullets=["Processing request..."])


class RideBrief(BaseModel):
    version: str = "1.0"
    brief_id: str
    intent_id: str
    archetype: Archetype = Field(default_factory=_default_archetype)
    experience_shape: List[ExperiencePhase] = Field(default_factory=list)
    implicit_defaults: ImplicitDefaults = Field(default_factory=ImplicitDefaults)
    success_criteria: List[SuccessCriterion] = Field(default_factory=list)
    tradeoffs: List[Tradeoff] = Field(default_factory=list)
    fallback_strategies: List[FallbackStrategy] = Field(default_factory=list)
    ask_user_if_needed: List[AskUserIfNeeded] = Field(default_factory=list)
    brief_summary_for_ui: BriefSummary = Field(default_factory=_default_brief_summary)


class DiscoveryQuery(BaseModel):
    id: str
    purpose: str
    tool: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class DiscoveryStopRule(BaseModel):
    condition: str
    min_results: int


class FocusRegion(BaseModel):
    type: Literal["circle", "bbox", "polygon"]
    geometry: Dict[str, Any]


class DiscoveryPlan(BaseModel):
    version: str = "1.0"
    plan_id: str
    brief_id: str
    search_radius_km: float = 15.0
    focus_regions: List[FocusRegion] = Field(default_factory=list)
    queries: List[DiscoveryQuery] = Field(default_factory=list)
    stop_when: List[DiscoveryStopRule] = Field(default_factory=list)


class IngredientNetwork(BaseModel):
    name: str
    geometry: Dict[str, Any]
    tags: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.5


class IngredientConnector(BaseModel):
    type: str
    geometry: Dict[str, Any]
    tags: Dict[str, Any] = Field(default_factory=dict)
    stress_score: float = 0.5


class IngredientPoi(BaseModel):
    type: str
    name: str
    point: Coordinate
    confidence: float = 0.5


class IngredientAvoidZone(BaseModel):
    reason: str
    geometry: Dict[str, Any]


class IngredientSet(BaseModel):
    version: str = "1.0"
    ingredients_id: str
    brief_id: str
    networks: List[IngredientNetwork] = Field(default_factory=list)
    connectors: List[IngredientConnector] = Field(default_factory=list)
    pois: List[IngredientPoi] = Field(default_factory=list)
    avoid_zones: List[IngredientAvoidZone] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class CandidateWaypoint(BaseModel):
    type: str
    point: Coordinate
    lock: Literal["none", "soft", "hard"] = "none"
    name: Optional[str] = None


class GradeSpike(BaseModel):
    pct: float
    length_m: float
    at_km: float


class GradeStats(BaseModel):
    up_max_pct: float = 0
    down_max_pct: float = 0
    spikes: List[GradeSpike] = Field(default_factory=list)


class SurfaceMixComputed(BaseModel):
    pavement: float = 0
    gravel: float = 0
    dirt: float = 0
    singletrack: float = 0
    unknown: float = 0


class TechnicalComputed(BaseModel):
    mtb_scale_max: Optional[float] = None
    distribution: Dict[str, float] = Field(default_factory=dict)


class TrafficStress(BaseModel):
    avg: float = 0
    max: float = 0
    hotspots: List[Dict[str, float]] = Field(default_factory=list)


class StopDensity(BaseModel):
    intersections_per_km: Optional[float] = None
    signals_est: Optional[float] = None


class CandidateComputed(BaseModel):
    distance_km: float
    time_est_min: float
    elevation_gain_m: float
    grade_stats: GradeStats
    surface_mix: SurfaceMixComputed
    technical: TechnicalComputed
    traffic_stress: TrafficStress
    stop_density: StopDensity
    data_confidence: float


class ValidationIssue(BaseModel):
    severity: Literal["error", "warn", "info"]
    type: str
    message: str
    location: Optional[Coordinate] = None
    fix_hint: Optional[str] = None


class CandidateValidation(BaseModel):
    status: Literal["pass", "warn", "fail"]
    issues: List[ValidationIssue] = Field(default_factory=list)


class CandidateRoute(BaseModel):
    version: str = "1.0"
    candidate_id: str
    brief_id: str
    label: str
    routing_profile: str
    generation_strategy: str
    geometry: Dict[str, Any]
    waypoints: List[CandidateWaypoint] = Field(default_factory=list)
    computed: CandidateComputed
    validation: CandidateValidation
    transition_segments: List[Dict[str, Any]] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    criterion_id: str
    score: float
    reason: str
    evidence: List[str]


class RankedCandidate(BaseModel):
    candidate_id: str
    score_total: float
    score_breakdown: List[ScoreBreakdown] = Field(default_factory=list)
    major_mismatches: List[str] = Field(default_factory=list)
    best_for: str
    recommendation: Literal["primary", "secondary", "reject"]


class NextAction(BaseModel):
    action: str
    rationale: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class BriefUpdate(BaseModel):
    path: str
    new_value: Any
    reason: str
    confidence: float


class CritiqueReport(BaseModel):
    version: str = "1.0"
    brief_id: str
    ranked_candidates: List[RankedCandidate] = Field(default_factory=list)
    next_actions: List[NextAction] = Field(default_factory=list)
    brief_updates: List[BriefUpdate] = Field(default_factory=list)


class PlanningLoopResult(BaseModel):
    intent: IntentObject
    ride_brief: RideBrief
    discovery_plan: Optional[DiscoveryPlan] = None
    ingredients: Optional[IngredientSet] = None
    candidates: List[CandidateRoute] = Field(default_factory=list)
    critique: CritiqueReport
    iteration: int = 1
    status: str = "in_progress"
    selected_candidate_id: Optional[str] = None
    max_iterations: int = 3
    max_candidates_total: int = 12
    failure_reason: Optional[str] = None
    fallback_suggestion: Optional[str] = None


class PlanningBriefUpdateRequest(BaseModel):
    conversation_id: UUID
    updates: Dict[str, Any]
    current_route_context: Optional[Dict[str, Any]] = None
