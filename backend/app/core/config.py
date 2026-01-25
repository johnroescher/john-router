"""Application configuration."""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "John Router"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production"

    # Database
    database_url: str = "postgresql://johnrouter:johnrouter_dev@localhost:5432/johnrouter"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # API Keys
    anthropic_api_key: Optional[str] = None
    ors_api_key: Optional[str] = None
    graphhopper_api_key: Optional[str] = None
    valhalla_api_key: Optional[str] = None
    mapbox_access_token: Optional[str] = None
    maptiler_key: Optional[str] = None
    trailforks_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Valhalla (Stadia Maps)
    valhalla_base_url: str = "https://api.stadiamaps.com"

    # Elevation
    elevation_api_url: str = "https://api.opentopodata.org/v1/"

    # Surface Enrichment
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Feature Flags
    enable_speech_input: bool = False
    use_self_hosted_routing: bool = False

    # Rate Limits
    routing_requests_per_minute: int = 40

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    env_path = find_dotenv(".env", usecwd=True)
    if env_path:
        load_dotenv(env_path, override=True)
    return Settings()


settings = get_settings()
