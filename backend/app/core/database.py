"""Database connection and session management."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
import structlog

from .config import settings

# Convert sync URL to async
database_url = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(
    database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()
logger = structlog.get_logger()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            try:
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.warning("Database commit failed; skipping", error=str(exc))
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
