"""Common schemas used across the application."""
from typing import List, Optional
from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    """A single coordinate point (longitude, latitude)."""
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    lat: float = Field(..., ge=-90, le=90, description="Latitude")

    def to_tuple(self) -> tuple[float, float]:
        """Return as (lng, lat) tuple."""
        return (self.lng, self.lat)

    def to_list(self) -> List[float]:
        """Return as [lng, lat] list."""
        return [self.lng, self.lat]


class BoundingBox(BaseModel):
    """Bounding box for geographic queries."""
    min_lng: float = Field(..., ge=-180, le=180)
    min_lat: float = Field(..., ge=-90, le=90)
    max_lng: float = Field(..., ge=-180, le=180)
    max_lat: float = Field(..., ge=-90, le=90)

    def to_list(self) -> List[float]:
        """Return as [min_lng, min_lat, max_lng, max_lat]."""
        return [self.min_lng, self.min_lat, self.max_lng, self.max_lat]

    def to_polygon_coords(self) -> List[List[float]]:
        """Return as polygon coordinates for GeoJSON."""
        return [
            [self.min_lng, self.min_lat],
            [self.max_lng, self.min_lat],
            [self.max_lng, self.max_lat],
            [self.min_lng, self.max_lat],
            [self.min_lng, self.min_lat],
        ]


class GeoJSONPoint(BaseModel):
    """GeoJSON Point geometry."""
    type: str = "Point"
    coordinates: List[float] = Field(..., min_length=2, max_length=3)


class GeoJSONLineString(BaseModel):
    """GeoJSON LineString geometry."""
    type: str = "LineString"
    coordinates: List[List[float]] = Field(..., min_length=2)


class GeoJSONFeature(BaseModel):
    """GeoJSON Feature."""
    type: str = "Feature"
    geometry: GeoJSONLineString | GeoJSONPoint
    properties: dict = Field(default_factory=dict)


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection."""
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)


class PaginatedResponse(BaseModel):
    """Base for paginated responses."""
    total: int
    skip: int
    limit: int
    has_more: bool


class CyclingFactsResponse(BaseModel):
    """Response payload for cycling facts."""
    facts: List[str]
