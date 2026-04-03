"""Celery application for background tasks."""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "johnrouter",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.knowledge_tasks", "app.workers.prefetch_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes
    task_soft_time_limit=540,  # 9 minutes
)
