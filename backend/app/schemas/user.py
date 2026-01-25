"""User-related schemas."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr


class UserPreferences(BaseModel):
    """User preferences for route planning."""
    bike_type: str = "mtb"  # road, gravel, mtb, emtb
    fitness_level: str = "intermediate"  # beginner, intermediate, advanced, expert
    ftp: Optional[int] = None  # Functional Threshold Power in watts
    typical_speed_mph: float = 12
    max_climb_tolerance_ft: int = 3000
    mtb_skill: str = "intermediate"  # beginner, intermediate, advanced, expert
    risk_tolerance: str = "medium"  # low, medium, high
    surface_preferences: Dict[str, float] = Field(
        default_factory=lambda: {"pavement": 0.2, "gravel": 0.3, "singletrack": 0.5}
    )
    avoidances: List[str] = Field(default_factory=list)
    units: str = "imperial"  # imperial, metric


class UserCreate(BaseModel):
    """Create a new user."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None
    preferences: Optional[UserPreferences] = None


class UserUpdate(BaseModel):
    """Update user profile."""
    name: Optional[str] = None
    preferences: Optional[UserPreferences] = None


class UserResponse(BaseModel):
    """User response."""
    id: UUID
    email: Optional[str]
    name: Optional[str]
    preferences: UserPreferences
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Data encoded in JWT token."""
    user_id: Optional[UUID] = None
    email: Optional[str] = None


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback request."""
    code: str
    redirect_uri: str
