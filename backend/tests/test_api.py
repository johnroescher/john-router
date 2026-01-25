"""Tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.main import app
from app.core.database import get_db
from app.schemas.route import (
    RouteAnalysis,
    SurfaceBreakdown,
    MTBDifficultyBreakdown,
    RouteValidation,
)
from app.schemas.chat import ChatResponse, ChatMessage


@pytest.fixture
def client(mock_db_session):
    """Create test client."""
    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def build_route_analysis() -> RouteAnalysis:
    return RouteAnalysis(
        distance_meters=1500,
        elevation_gain_meters=50,
        elevation_loss_meters=40,
        estimated_time_seconds=600,
        max_elevation_meters=1800,
        min_elevation_meters=1700,
        avg_grade_percent=2.0,
        max_grade_percent=6.0,
        longest_climb_meters=400,
        steepest_100m_percent=5.0,
        steepest_1km_percent=4.0,
        climbing_above_8_percent_meters=0.0,
        surface_breakdown=SurfaceBreakdown(pavement=40, gravel=30, dirt=20, singletrack=10, unknown=0),
        mtb_difficulty_breakdown=MTBDifficultyBreakdown(green=50, blue=30, black=10, double_black=0, unknown=10),
        max_technical_rating=2.0,
        hike_a_bike_sections=0,
        hike_a_bike_distance_meters=0,
        physical_difficulty=2.0,
        technical_difficulty=2.5,
        risk_rating=2.0,
        overall_difficulty=2.2,
        elevation_profile=[],
        confidence_score=0.8,
        data_completeness=0.9,
    )


def build_route_validation(status: str = "valid") -> RouteValidation:
    return RouteValidation(
        status=status,
        errors=[],
        warnings=[],
        info=[],
        confidence_score=0.9,
    )


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRoutingEndpoints:
    """Test routing API endpoints."""

    @patch("app.api.routes.get_validation_service", new_callable=AsyncMock)
    @patch("app.api.routes.get_analysis_service", new_callable=AsyncMock)
    @patch("app.api.routes.get_routing_service", new_callable=AsyncMock)
    def test_generate_route_success(self, mock_routing, mock_analysis, mock_validation, client):
        """Test successful route generation."""
        mock_routing.return_value = AsyncMock(
            generate_route=AsyncMock(
                return_value=[
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-105.0, 39.7], [-105.01, 39.71]],
                        }
                    }
                ]
            )
        )
        mock_analysis.return_value = AsyncMock(analyze_route=AsyncMock(return_value=build_route_analysis()))
        mock_validation.return_value = AsyncMock(validate_route=AsyncMock(return_value=build_route_validation()))

        response = client.post(
            "/api/routes/generate",
            json={
                "start": {"lat": 39.7, "lng": -105.0},
                "end": {"lat": 39.71, "lng": -105.01},
                "sport_type": "mtb",
                "route_type": "point_to_point",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_generate_route_missing_start(self, client):
        """Test route generation with missing start point."""
        response = client.post(
            "/api/routes/generate",
            json={
                "sport_type": "mtb",
                "route_type": "loop",
            },
        )

        assert response.status_code == 422  # Validation error

    @patch("app.api.routes.get_validation_service", new_callable=AsyncMock)
    @patch("app.api.routes.get_analysis_service", new_callable=AsyncMock)
    @patch("app.api.routes.get_routing_service", new_callable=AsyncMock)
    def test_generate_loop_route(self, mock_routing, mock_analysis, mock_validation, client):
        """Test loop route generation."""
        mock_routing.return_value = AsyncMock(
            generate_route=AsyncMock(
                return_value=[
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [-105.0, 39.7],
                                [-105.01, 39.71],
                                [-105.02, 39.7],
                                [-105.0, 39.7],
                            ],
                        }
                    }
                ]
            )
        )
        mock_analysis.return_value = AsyncMock(analyze_route=AsyncMock(return_value=build_route_analysis()))
        mock_validation.return_value = AsyncMock(validate_route=AsyncMock(return_value=build_route_validation()))

        response = client.post(
            "/api/routes/generate",
            json={
                "start": {"lat": 39.7, "lng": -105.0},
                "sport_type": "gravel",
                "route_type": "loop",
                "target_distance_meters": 5000,
            },
        )

        assert response.status_code == 200


class TestAnalysisEndpoints:
    """Test analysis API endpoints."""

    @patch("app.api.routes.get_analysis_service", new_callable=AsyncMock)
    def test_analyze_route(self, mock_analysis, client):
        """Test route analysis endpoint."""
        mock_analysis.return_value = AsyncMock(analyze_route=AsyncMock(return_value=build_route_analysis()))

        response = client.post(
            "/api/routes/analyze-geometry",
            json={
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-105.0, 39.7], [-105.01, 39.71]],
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "distance_meters" in data
        assert "surface_breakdown" in data


class TestChatEndpoints:
    """Test chat API endpoints."""

    @patch("app.api.chat._build_chat_response", new_callable=AsyncMock)
    @patch("app.api.chat.get_ride_brief_service", new_callable=AsyncMock)
    def test_send_message(self, mock_get_planner, mock_build_response, client):
        """Test sending a chat message."""
        mock_planner = AsyncMock()
        mock_planner.run = AsyncMock(return_value=MagicMock())
        mock_get_planner.return_value = mock_planner

        mock_build_response.return_value = ChatResponse(
            conversation_id=uuid4(),
            message=ChatMessage(role="assistant", content="I can help you plan a route!"),
            route_updated=False,
            suggested_prompts=[],
        )

        response = client.post(
            "/api/chat/message",
            json={
                "message": "Plan a 10 mile MTB loop",
                "conversation_id": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"]["content"] == "I can help you plan a route!"

    @patch("app.api.chat._build_chat_response", new_callable=AsyncMock)
    @patch("app.api.chat.get_ride_brief_service", new_callable=AsyncMock)
    def test_chat_with_route_generation(self, mock_get_planner, mock_build_response, client):
        """Test chat that generates a route."""
        mock_planner = AsyncMock()
        mock_planner.run = AsyncMock(return_value=MagicMock())
        mock_get_planner.return_value = mock_planner

        mock_build_response.return_value = ChatResponse(
            conversation_id=uuid4(),
            message=ChatMessage(role="assistant", content="I've generated a 10 mile loop for you!"),
            route_id="gen-123",
            route_updated=True,
            suggested_prompts=[],
        )

        response = client.post(
            "/api/chat/message",
            json={
                "message": "Create a 10 mile MTB loop near Boulder",
                "conversation_id": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("route_updated") is True
