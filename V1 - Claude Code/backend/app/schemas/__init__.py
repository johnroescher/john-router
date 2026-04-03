"""Pydantic schemas for request/response validation."""
from .route import (
    RouteCreate,
    RouteUpdate,
    RouteResponse,
    RouteListResponse,
    RouteConstraints,
    RouteCandidateResponse,
    RouteAnalysis,
    RouteValidation,
    WaypointCreate,
    WaypointResponse,
    SegmentResponse,
    GPXExport,
    GPXImport,
)
from .user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPreferences,
    Token,
    TokenData,
)
from .chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ToolCall,
    ToolResult,
)
from .common import (
    Coordinate,
    BoundingBox,
    GeoJSONLineString,
    GeoJSONPoint,
)

__all__ = [
    # Route
    "RouteCreate",
    "RouteUpdate",
    "RouteResponse",
    "RouteListResponse",
    "RouteConstraints",
    "RouteCandidateResponse",
    "RouteAnalysis",
    "RouteValidation",
    "WaypointCreate",
    "WaypointResponse",
    "SegmentResponse",
    "GPXExport",
    "GPXImport",
    # User
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserPreferences",
    "Token",
    "TokenData",
    # Chat
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ToolCall",
    "ToolResult",
    # Common
    "Coordinate",
    "BoundingBox",
    "GeoJSONLineString",
    "GeoJSONPoint",
]
