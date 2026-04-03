"""Route evaluation schemas."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class IntentGap(BaseModel):
    """Represents a gap between route and user intent."""
    type: str  # e.g., "distance", "elevation", "location", "surface"
    description: str
    severity: float = Field(ge=0.0, le=1.0)  # 0.0 = minor, 1.0 = critical
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None


class Weakness(BaseModel):
    """Represents a weakness or issue with the route."""
    type: str  # e.g., "highway_segment", "too_short", "too_hilly", "poor_surface"
    description: str
    location: Optional[str] = None  # e.g., "km 5-7"
    severity: float = Field(ge=0.0, le=1.0)
    suggestion: Optional[str] = None  # How to fix it


class ImprovementOpportunity(BaseModel):
    """Represents an opportunity to improve the route."""
    type: str  # e.g., "add_scenic_detour", "include_poi", "better_surface"
    description: str
    location: Optional[str] = None
    potential_improvement: str  # What improvement would add


class RouteEvaluation(BaseModel):
    """Complete evaluation of a route against user intent."""
    route_id: Optional[str] = None
    intent_match_score: float = Field(ge=0.0, le=1.0)  # How well route matches intent
    quality_score: float = Field(ge=0.0, le=1.0)  # Overall route quality
    creativity_score: float = Field(ge=0.0, le=1.0)  # How creative/interesting the route is
    
    intent_gaps: List[IntentGap] = Field(default_factory=list)
    weaknesses: List[Weakness] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)  # What the route does well
    improvement_opportunities: List[ImprovementOpportunity] = Field(default_factory=list)
    
    recommendations: List[str] = Field(default_factory=list)  # LLM-generated recommendations
    summary: Optional[str] = None  # Overall evaluation summary
    
    def has_significant_issues(self) -> bool:
        """Check if route has significant issues that need fixing."""
        critical_gaps = any(gap.severity > 0.7 for gap in self.intent_gaps)
        critical_weaknesses = any(w.severity > 0.7 for w in self.weaknesses)
        low_intent_match = self.intent_match_score < 0.6
        return critical_gaps or critical_weaknesses or low_intent_match
