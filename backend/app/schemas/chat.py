"""Chat-related schemas."""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Coordinate
from app.schemas.planning import PlanningLoopResult
from app.schemas.route import RouteCandidateResponse


class ToolCall(BaseModel):
    """A tool call made by the AI."""
    id: str
    name: str
    arguments: Dict[str, Any]


class ToolResult(BaseModel):
    """Result of a tool call."""
    tool_call_id: str
    name: str
    result: Any
    error: Optional[str] = None


class ActionChip(BaseModel):
    """Clickable action chip in AI response."""
    id: str
    label: str
    action: str  # apply_change, try_alternatives, modify_constraint, etc.
    data: Dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """A single chat message."""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # For assistant messages
    tool_calls: List[ToolCall] = Field(default_factory=list)
    action_chips: List[ActionChip] = Field(default_factory=list)
    confidence: Optional[float] = None

    # For tool messages
    tool_result: Optional[ToolResult] = None


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str
    conversation_id: Optional[UUID] = None
    route_id: Optional[UUID] = None

    # Optional context
    current_constraints: Optional[Dict[str, Any]] = None
    current_route_geometry: Optional[List[List[float]]] = None
    map_center: Optional[Coordinate] = None

    # Mode settings
    quality_mode: bool = True
    explain_mode: bool = True


class RouteData(BaseModel):
    """Route data included in chat response."""
    geometry: Dict[str, Any]  # GeoJSON geometry
    distance_meters: float
    elevation_gain: float
    duration_seconds: float
    sport_type: str
    route_type: str
    surface_breakdown: Optional[Dict[str, float]] = None  # Surface percentages


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    conversation_id: UUID
    message: ChatMessage
    route_id: Optional[str] = None

    # If route was generated/modified
    route_updated: bool = False
    route_diff: Optional[Dict[str, Any]] = None
    route_data: Optional[RouteData] = None  # Full route data for display

    # Suggested follow-up prompts
    suggested_prompts: List[str] = Field(default_factory=list)

    # Ride Brief Loop payload
    planning: Optional[PlanningLoopResult] = None
    route_candidates: Optional[List[RouteCandidateResponse]] = None


class ConversationResponse(BaseModel):
    """Full conversation response."""
    id: UUID
    user_id: Optional[UUID]
    route_id: Optional[UUID]
    messages: List[ChatMessage]
    current_constraints: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConstraintInterpretation(BaseModel):
    """Interpreted constraints from user message."""
    understood: Dict[str, Any]
    ambiguous: List[str]
    clarifying_questions: List[str]
    confidence: float


class StatusUpdate(BaseModel):
    """Real-time status update during chat processing."""
    stage: str  # e.g., "extracting_intent", "geocoding", "discovering_trails", etc.
    message: str  # Human-readable status message
    progress: Optional[float] = None  # Progress from 0.0 to 1.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
