import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.schemas.route import SportType


class MockRoutingService:
    ORS_PROFILES = {SportType.ROAD: "driving-car"}
    BROUTER_PROFILES = {SportType.ROAD: "fastbike"}

    def __init__(self):
        self.graphhopper_api_key = None

    async def _call_ors_directions_interactive(self, *args, **kwargs):
        return {"routes": []}

    def _parse_ors_response(self, _response):
        return {
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [-97.0, 30.0],
                    [-97.0001, 30.0001],
                    [-97.0002, 30.0002],
                ],
            },
            "distance_meters": 120,
            "duration_seconds": 30,
            "elevation_gain": 2,
            "surface_breakdown": {"paved": 100, "unpaved": 0, "gravel": 0, "ground": 0, "unknown": 0},
        }


@pytest.fixture
def client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_point_to_point_route_success(client):
    mock_service = MockRoutingService()

    with patch("app.api.routes.get_routing_service", new=AsyncMock(return_value=mock_service)):
        response = client.post(
            "/api/routes/point-to-point",
            json={
                "coordinates": [
                    {"lat": 30.0, "lng": -97.0},
                    {"lat": 30.0002, "lng": -97.0002},
                ],
                "sport_type": "road",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["geometry"]["type"] == "LineString"
    assert len(data["geometry"]["coordinates"]) >= 3
    assert data["distance_meters"] == 120
