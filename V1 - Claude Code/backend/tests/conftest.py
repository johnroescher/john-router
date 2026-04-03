"""Pytest configuration and shared fixtures."""
import asyncio
from typing import Generator
from unittest.mock import MagicMock, AsyncMock
import pytest


@pytest.fixture(autouse=True)
def mock_planning_tools(monkeypatch):
    """Mock planning tools to avoid external routing calls in tests."""
    try:
        import app.services.ride_brief_loop as ride_brief_loop
        ride_brief_loop._ride_brief_service = None
    except Exception:
        pass
    fake_geometry = {
        "type": "LineString",
        "coordinates": [
            [-105.2705, 40.0150],
            [-105.2715, 40.0160],
            [-105.2725, 40.0155],
            [-105.2705, 40.0150],
        ],
    }
    fake_route = {"geometry": fake_geometry}
    fake_analysis = {
        "distance_meters": 12000,
        "estimated_time_seconds": 2400,
        "elevation_gain_meters": 250,
        "max_grade_percent": 6.5,
        "surface_breakdown": {"pavement": 20, "gravel": 40, "dirt": 30, "singletrack": 10, "unknown": 0},
        "mtb_difficulty_breakdown": {"green": 60, "blue": 30, "black": 10, "double_black": 0},
        "confidence_score": 0.8,
    }
    fake_validation = {"errors": [], "warnings": []}

    monkeypatch.setattr(
        "app.services.planning_tools.route_generate",
        AsyncMock(return_value=fake_route),
    )
    monkeypatch.setattr(
        "app.services.planning_tools.route_analyze",
        AsyncMock(return_value=fake_analysis),
    )
    monkeypatch.setattr(
        "app.services.planning_tools.route_validate",
        AsyncMock(return_value=fake_validation),
    )
    monkeypatch.setattr(
        "app.services.ride_brief_loop.route_generate",
        AsyncMock(return_value=fake_route),
    )
    monkeypatch.setattr(
        "app.services.ride_brief_loop.route_analyze",
        AsyncMock(return_value=fake_analysis),
    )
    monkeypatch.setattr(
        "app.services.ride_brief_loop.route_validate",
        AsyncMock(return_value=fake_validation),
    )
    monkeypatch.setattr(
        "app.services.route_modifier.route_generate",
        AsyncMock(return_value=fake_route),
    )
    monkeypatch.setattr(
        "app.services.route_modifier.route_analyze",
        AsyncMock(return_value=fake_analysis),
    )
    monkeypatch.setattr(
        "app.services.route_modifier.route_validate",
        AsyncMock(return_value=fake_validation),
    )
    monkeypatch.setattr(
        "app.services.ride_brief_loop.geocode_place",
        AsyncMock(return_value={"point": {"lat": 40.0150, "lng": -105.2705}}),
    )
    monkeypatch.setattr(
        "app.services.routing.RoutingService._validate_surface_data_quality",
        lambda self, candidate, max_unknown_pct: (True, "ok"),
    )

    class MockCacheService:
        def _make_key(self, prefix: str, *args, **kwargs) -> str:
            return f"test:{prefix}"

        async def get(self, key: str):
            return None

        async def set(self, key: str, value, ttl_seconds: int = 3600):
            return True

        async def delete(self, key: str):
            return True

    async def _get_cache_service():
        return MockCacheService()

    monkeypatch.setattr(
        "app.services.cache_service.get_cache_service",
        _get_cache_service,
    )
    monkeypatch.setattr(
        "app.services.ride_brief_loop.get_cache_service",
        _get_cache_service,
    )
    monkeypatch.setattr(
        "app.services.knowledge_retrieval.get_cache_service",
        _get_cache_service,
    )
    monkeypatch.setattr(
        "app.services.trail_database.get_cache_service",
        _get_cache_service,
    )

    try:
        from app.core.config import settings
        settings.nvidia_api_key = None
        settings.anthropic_api_key = None
        settings.openai_api_key = None
        settings.trailforks_api_key = None
    except Exception:
        pass


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_scalars.scalar_one_or_none.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    session.scalars = AsyncMock(return_value=mock_scalars)
    session.flush = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def db_session(mock_db_session):
    """Alias fixture for tests expecting a db_session."""
    return mock_db_session


@pytest.fixture
def test_user():
    """Create a mock user for preference tests."""
    user = MagicMock()
    user.id = "test-user-id"
    return user


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def sample_route_geometry():
    """Create a sample route geometry."""
    return {
        "type": "LineString",
        "coordinates": [
            [-105.2705, 39.9986, 1750],  # Boulder
            [-105.2715, 39.9996, 1780],
            [-105.2725, 40.0006, 1820],
            [-105.2735, 40.0016, 1850],
            [-105.2745, 40.0026, 1890],
            [-105.2755, 40.0036, 1920],
            [-105.2765, 40.0046, 1880],
            [-105.2775, 40.0056, 1850],
            [-105.2785, 40.0066, 1820],
            [-105.2795, 40.0076, 1790],
        ],
    }


@pytest.fixture
def sample_elevation_profile():
    """Create a sample elevation profile."""
    return [
        {"distance_meters": 0, "elevation_meters": 1750, "grade_percent": 0},
        {"distance_meters": 150, "elevation_meters": 1780, "grade_percent": 20},
        {"distance_meters": 300, "elevation_meters": 1820, "grade_percent": 26.7},
        {"distance_meters": 450, "elevation_meters": 1850, "grade_percent": 20},
        {"distance_meters": 600, "elevation_meters": 1890, "grade_percent": 26.7},
        {"distance_meters": 750, "elevation_meters": 1920, "grade_percent": 20},
        {"distance_meters": 900, "elevation_meters": 1880, "grade_percent": -26.7},
        {"distance_meters": 1050, "elevation_meters": 1850, "grade_percent": -20},
        {"distance_meters": 1200, "elevation_meters": 1820, "grade_percent": -20},
        {"distance_meters": 1350, "elevation_meters": 1790, "grade_percent": -20},
    ]


@pytest.fixture
def sample_segments_metadata():
    """Create sample segment metadata from OSM."""
    return [
        {
            "osm_way_id": 12345,
            "highway_type": "cycleway",
            "surface": "asphalt",
            "bicycle_access": "designated",
            "mtb_scale": None,
            "sac_scale": None,
            "distance_meters": 500,
            "max_grade": 3.0,
            "name": "Boulder Creek Path",
        },
        {
            "osm_way_id": 12346,
            "highway_type": "track",
            "surface": "gravel",
            "bicycle_access": "yes",
            "mtb_scale": 0.5,
            "sac_scale": None,
            "distance_meters": 800,
            "max_grade": 8.0,
            "name": "Connector Trail",
        },
        {
            "osm_way_id": 12347,
            "highway_type": "path",
            "surface": "ground",
            "bicycle_access": "yes",
            "mtb_scale": 2.0,
            "sac_scale": "T1",
            "distance_meters": 1200,
            "max_grade": 15.0,
            "name": "Mesa Trail",
        },
    ]


@pytest.fixture
def mock_ors_response():
    """Create a mock OpenRouteService response."""
    return {
        "routes": [
            {
                "summary": {
                    "distance": 15000,
                    "duration": 5400,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-105.0, 39.7],
                        [-105.01, 39.71],
                        [-105.02, 39.72],
                        [-105.03, 39.73],
                        [-105.04, 39.74],
                    ],
                },
                "segments": [
                    {
                        "distance": 15000,
                        "duration": 5400,
                        "steps": [
                            {
                                "distance": 3000,
                                "duration": 900,
                                "type": 1,
                                "instruction": "Head north",
                                "name": "Trail Road",
                                "way_points": [0, 1],
                            },
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def mock_llm_response():
    """Create a mock OpenAI-compatible LLM response (NVIDIA NIM)."""
    mock_choice = MagicMock()
    mock_choice.message = MagicMock()
    mock_choice.message.content = "I'll help you plan a great MTB route!"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.fixture
def mock_llm_json_response():
    """Create a mock OpenAI-compatible LLM response returning JSON."""
    mock_choice = MagicMock()
    mock_choice.message = MagicMock()
    mock_choice.message.content = '{"sport_type": "mtb", "route_type": "loop"}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response
