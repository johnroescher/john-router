"""API routes module."""
from fastapi import APIRouter

from .routes import routes_router
from .chat import chat_router
from .users import users_router
from .health import health_router
from .planning import planning_router
from .facts import facts_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(routes_router, prefix="/routes", tags=["routes"])
api_router.include_router(chat_router, prefix="/chat", tags=["chat"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(planning_router, prefix="/planning", tags=["planning"])
api_router.include_router(facts_router, prefix="/facts", tags=["facts"])

__all__ = ["api_router"]
