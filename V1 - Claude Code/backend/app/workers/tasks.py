"""Celery background tasks."""
import asyncio
from uuid import UUID

from .celery_app import celery_app


def run_async(coro):
    """Run async function in Celery task."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@celery_app.task(bind=True)
def generate_route_task(self, constraints_dict: dict):
    """Background task for generating routes (Quality Mode)."""
    from app.services.routing import get_routing_service
    from app.schemas.route import RouteConstraints

    async def _generate():
        constraints = RouteConstraints(**constraints_dict)
        routing_service = await get_routing_service()
        return await routing_service.generate_route(constraints)

    return run_async(_generate())


@celery_app.task(bind=True)
def analyze_route_task(self, route_id: str, geometry_dict: dict):
    """Background task for route analysis."""
    from app.services.analysis import get_analysis_service

    async def _analyze():
        analysis_service = await get_analysis_service()
        return (await analysis_service.analyze_route(geometry_dict)).model_dump()

    return run_async(_analyze())


@celery_app.task(bind=True)
def validate_route_task(self, route_id: str, geometry_dict: dict, constraints_dict: dict = None):
    """Background task for route validation."""
    from app.services.validation import get_validation_service
    from app.schemas.route import RouteConstraints

    async def _validate():
        validation_service = await get_validation_service()
        constraints = RouteConstraints(**constraints_dict) if constraints_dict else None
        result = await validation_service.validate_route(geometry_dict, constraints=constraints)
        return result.model_dump()

    return run_async(_validate())
