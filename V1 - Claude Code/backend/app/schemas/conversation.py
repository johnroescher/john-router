"""Conversation context schemas for tracking conversation state."""
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.user_context import UserPreferences
from app.schemas.planning import IntentObject, CandidateRoute


class RouteVersion(BaseModel):
    """A version of a route that has been presented or modified."""
    route_id: Optional[UUID] = None
    version_number: int = 1
    description: Optional[str] = None
    created_at: Optional[str] = None


class ConversationContext(BaseModel):
    """Structured conversation context tracking key details and state."""
    entities: Dict[str, Any] = Field(default_factory=dict)  # Extracted key entities (locations, trail names, etc.)
    user_preferences: Optional[UserPreferences] = None  # Snapshot of user prefs relevant to this convo
    discussed_topics: List[str] = Field(default_factory=list)  # Topics that have come up (e.g., safety, scenery, certain trails)
    route_history: List[RouteVersion] = Field(default_factory=list)  # Versions of routes presented or modified
    pending_clarification: Optional[str] = None  # If we asked a question to clarify something and awaiting answer
    location_region: Optional[str] = None  # Current location region being discussed
    sport_type: Optional[str] = None  # Current sport type being discussed
    last_intent: Optional[IntentObject] = None  # Last extracted intent
    last_route_candidates: List[CandidateRoute] = Field(default_factory=list)  # Last set of route candidates

    class Config:
        from_attributes = False  # This is a Pydantic model, not a database model
