"""Seed data script for John Router.

Creates example routes in multiple regions for testing.
"""
import asyncio
import json
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString

# Example routes with real-ish coordinates
EXAMPLE_ROUTES = [
    {
        "name": "Golden Gate Canyon Loop",
        "description": "A classic MTB loop in Golden Gate Canyon State Park with mixed singletrack and fire roads. Features beautiful aspen groves and challenging climbs.",
        "sport_type": "mtb",
        "region": "Colorado Front Range",
        "coordinates": [
            [-105.4293, 39.8321],
            [-105.4315, 39.8345],
            [-105.4342, 39.8378],
            [-105.4389, 39.8412],
            [-105.4423, 39.8456],
            [-105.4478, 39.8489],
            [-105.4512, 39.8523],
            [-105.4534, 39.8567],
            [-105.4501, 39.8598],
            [-105.4456, 39.8612],
            [-105.4398, 39.8589],
            [-105.4345, 39.8556],
            [-105.4312, 39.8512],
            [-105.4289, 39.8467],
            [-105.4278, 39.8412],
            [-105.4285, 39.8356],
            [-105.4293, 39.8321],
        ],
        "distance_meters": 24140,  # ~15 miles
        "elevation_gain_meters": 610,  # ~2000 ft
        "surface_breakdown": {"pavement": 5, "gravel": 30, "dirt": 15, "singletrack": 45, "unknown": 5},
        "mtb_difficulty_breakdown": {"green": 20, "blue": 50, "black": 25, "double_black": 0, "unknown": 5},
        "physical_difficulty": 3.5,
        "technical_difficulty": 2.8,
        "risk_rating": 2.0,
        "overall_difficulty": 3.1,
        "tags": ["loop", "mtb", "colorado", "singletrack", "views"],
    },
    {
        "name": "Marin Headlands Gravel Epic",
        "description": "Epic gravel ride through the Marin Headlands with stunning views of the Golden Gate Bridge and Pacific Ocean. Mix of fire roads and paved bike paths.",
        "sport_type": "gravel",
        "region": "San Francisco Bay Area",
        "coordinates": [
            [-122.4783, 37.8324],
            [-122.4812, 37.8356],
            [-122.4856, 37.8389],
            [-122.4912, 37.8423],
            [-122.4967, 37.8467],
            [-122.5012, 37.8512],
            [-122.5056, 37.8556],
            [-122.5089, 37.8589],
            [-122.5067, 37.8634],
            [-122.5023, 37.8667],
            [-122.4967, 37.8689],
            [-122.4912, 37.8656],
            [-122.4856, 37.8612],
            [-122.4812, 37.8567],
            [-122.4778, 37.8512],
            [-122.4756, 37.8456],
            [-122.4767, 37.8389],
            [-122.4783, 37.8324],
        ],
        "distance_meters": 32187,  # ~20 miles
        "elevation_gain_meters": 762,  # ~2500 ft
        "surface_breakdown": {"pavement": 25, "gravel": 55, "dirt": 15, "singletrack": 0, "unknown": 5},
        "mtb_difficulty_breakdown": {"green": 60, "blue": 35, "black": 0, "double_black": 0, "unknown": 5},
        "physical_difficulty": 3.8,
        "technical_difficulty": 1.5,
        "risk_rating": 1.5,
        "overall_difficulty": 2.8,
        "tags": ["loop", "gravel", "california", "views", "ocean"],
    },
    {
        "name": "Moab Slickrock Trail",
        "description": "The iconic Slickrock Trail in Moab, Utah. Technical sandstone riding with incredible desert scenery. Not for beginners!",
        "sport_type": "mtb",
        "region": "Moab, Utah",
        "coordinates": [
            [-109.5489, 38.5834],
            [-109.5512, 38.5856],
            [-109.5534, 38.5889],
            [-109.5567, 38.5912],
            [-109.5589, 38.5945],
            [-109.5612, 38.5978],
            [-109.5634, 38.6012],
            [-109.5623, 38.6045],
            [-109.5589, 38.6067],
            [-109.5545, 38.6078],
            [-109.5501, 38.6067],
            [-109.5467, 38.6034],
            [-109.5445, 38.5989],
            [-109.5456, 38.5945],
            [-109.5478, 38.5889],
            [-109.5489, 38.5834],
        ],
        "distance_meters": 19312,  # ~12 miles
        "elevation_gain_meters": 457,  # ~1500 ft
        "surface_breakdown": {"pavement": 0, "gravel": 5, "dirt": 5, "singletrack": 85, "unknown": 5},
        "mtb_difficulty_breakdown": {"green": 5, "blue": 25, "black": 50, "double_black": 15, "unknown": 5},
        "physical_difficulty": 4.0,
        "technical_difficulty": 4.5,
        "risk_rating": 3.5,
        "overall_difficulty": 4.2,
        "tags": ["loop", "mtb", "utah", "technical", "slickrock", "expert"],
    },
    {
        "name": "Boulder Road Climbing Loop",
        "description": "Classic road cycling loop in Boulder, Colorado featuring Flagstaff Mountain and Sunshine Canyon. Great for training with sustained climbs.",
        "sport_type": "road",
        "region": "Boulder, Colorado",
        "coordinates": [
            [-105.2705, 40.0150],
            [-105.2756, 40.0089],
            [-105.2834, 40.0034],
            [-105.2912, 39.9978],
            [-105.2989, 39.9923],
            [-105.3067, 39.9867],
            [-105.3112, 39.9812],
            [-105.3089, 39.9756],
            [-105.3023, 39.9723],
            [-105.2945, 39.9756],
            [-105.2867, 39.9812],
            [-105.2789, 39.9878],
            [-105.2734, 39.9945],
            [-105.2712, 40.0023],
            [-105.2705, 40.0150],
        ],
        "distance_meters": 48280,  # ~30 miles
        "elevation_gain_meters": 1219,  # ~4000 ft
        "surface_breakdown": {"pavement": 95, "gravel": 0, "dirt": 0, "singletrack": 0, "unknown": 5},
        "mtb_difficulty_breakdown": {"green": 95, "blue": 0, "black": 0, "double_black": 0, "unknown": 5},
        "physical_difficulty": 4.2,
        "technical_difficulty": 1.0,
        "risk_rating": 2.0,
        "overall_difficulty": 3.0,
        "tags": ["loop", "road", "colorado", "climbing", "training"],
    },
    {
        "name": "Bentonville Flow Trails",
        "description": "Purpose-built flow trails in Bentonville, Arkansas. Perfect for intermediate riders looking for fun, flowy singletrack with jumps and berms.",
        "sport_type": "mtb",
        "region": "Bentonville, Arkansas",
        "coordinates": [
            [-94.2088, 36.3729],
            [-94.2112, 36.3756],
            [-94.2145, 36.3789],
            [-94.2178, 36.3823],
            [-94.2201, 36.3867],
            [-94.2189, 36.3912],
            [-94.2156, 36.3945],
            [-94.2112, 36.3967],
            [-94.2067, 36.3956],
            [-94.2034, 36.3923],
            [-94.2023, 36.3878],
            [-94.2045, 36.3834],
            [-94.2078, 36.3789],
            [-94.2088, 36.3729],
        ],
        "distance_meters": 16093,  # ~10 miles
        "elevation_gain_meters": 305,  # ~1000 ft
        "surface_breakdown": {"pavement": 5, "gravel": 10, "dirt": 10, "singletrack": 70, "unknown": 5},
        "mtb_difficulty_breakdown": {"green": 30, "blue": 55, "black": 10, "double_black": 0, "unknown": 5},
        "physical_difficulty": 2.5,
        "technical_difficulty": 2.5,
        "risk_rating": 1.5,
        "overall_difficulty": 2.3,
        "tags": ["loop", "mtb", "arkansas", "flow", "jumps", "berms", "beginner-friendly"],
    },
]


async def seed_routes(database_url: str):
    """Seed the database with example routes."""
    # Convert sync URL to async
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(async_url, echo=True)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        for route_data in EXAMPLE_ROUTES:
            # Create LineString geometry
            line = LineString(route_data["coordinates"])

            # Create route record
            from app.models.route import Route

            route = Route(
                id=uuid4(),
                name=route_data["name"],
                description=route_data["description"],
                sport_type=route_data["sport_type"],
                geometry=from_shape(line, srid=4326),
                distance_meters=route_data["distance_meters"],
                elevation_gain_meters=route_data["elevation_gain_meters"],
                elevation_loss_meters=route_data["elevation_gain_meters"] * 0.95,  # Approximate
                estimated_time_seconds=int(route_data["distance_meters"] / 5),  # ~5 m/s average
                max_elevation_meters=2500,  # Placeholder
                min_elevation_meters=1800,  # Placeholder
                surface_breakdown=route_data["surface_breakdown"],
                mtb_difficulty_breakdown=route_data["mtb_difficulty_breakdown"],
                physical_difficulty=route_data["physical_difficulty"],
                technical_difficulty=route_data["technical_difficulty"],
                risk_rating=route_data["risk_rating"],
                overall_difficulty=route_data["overall_difficulty"],
                tags=route_data["tags"],
                is_public=True,
                confidence_score=75.0,
                validation_status="valid",
                validation_results={"errors": [], "warnings": [], "info": []},
            )

            session.add(route)
            print(f"Added route: {route.name}")

        await session.commit()
        print(f"\nSuccessfully seeded {len(EXAMPLE_ROUTES)} example routes!")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://johnrouter:johnrouter_dev@localhost:5432/johnrouter"
    )

    asyncio.run(seed_routes(database_url))
