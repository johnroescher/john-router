"""Health check endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import settings

health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.environment,
    }


@health_router.get("/health/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    """Database connectivity check."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@health_router.get("/health/services")
async def services_health():
    """Check external service connectivity."""
    services = {}

    # Check if API keys are configured
    services["anthropic"] = "configured" if settings.anthropic_api_key else "not_configured"
    services["ors"] = "configured" if settings.ors_api_key else "not_configured"
    services["mapbox"] = "configured" if settings.mapbox_access_token else "not_configured"

    all_configured = all(
        v in ["configured", True]
        for k, v in services.items()
        if k in ["anthropic", "ors"]
    )

    return {
        "status": "healthy" if all_configured else "degraded",
        "services": services,
    }
