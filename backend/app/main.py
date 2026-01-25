"""Main FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.core.config import settings
from app.api import api_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting John Router API", environment=settings.environment)

    yield

    # Shutdown
    logger.info("Shutting down John Router API")

    # Cleanup services
    from app.services.routing import _routing_service
    from app.services.elevation import _elevation_service
    from app.services.geocoding import _geocoding_service

    if _routing_service:
        await _routing_service.close()
    if _elevation_service:
        await _elevation_service.close()
    if _geocoding_service:
        await _geocoding_service.close()


app = FastAPI(
    title=settings.app_name,
    description="AI-powered cycling route builder for road, gravel, and MTB",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - permissive for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
