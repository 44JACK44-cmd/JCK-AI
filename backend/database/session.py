"""
Database session management for SQLAlchemy.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging

from config import settings
from database.base import Base

logger = logging.getLogger(__name__)

# Determine if we should use async or sync engine based on database URL
database_url = settings.database_url
is_async = database_url.startswith(("postgresql+asyncpg", "sqlite+aiosqlite"))

if is_async:
    # SQLite (aiosqlite) uses NullPool — pool_size/max_overflow are invalid there.
    is_sqlite = database_url.startswith("sqlite")
    engine_kwargs = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        engine_kwargs.update({
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
        })

    # Async engine for asyncpg or aiosqlite
    engine = create_async_engine(database_url, **engine_kwargs)
    
    # Async session factory
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # For compatibility, also create a sync session factory
    sync_url = database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    sync_kwargs = {"echo": settings.debug}
    if not sync_url.startswith("sqlite"):
        sync_kwargs.update({
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
        })
    sync_engine = create_engine(sync_url, **sync_kwargs)
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine,
    )
    
else:
    # Sync engine for regular connections
    engine = create_engine(
        database_url,
        echo=settings.debug,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
    )
    
    # Sync session factory
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    
    # For async compatibility, create a dummy async session
    AsyncSessionLocal = None

logger.info(f"Database configured with URL: {database_url}")
logger.info(f"Async mode: {is_async}")


def get_db():
    """
    Dependency for getting database session (sync version).
    
    Yields:
        SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """
    Dependency for getting async database session.
    
    Yields:
        Async SQLAlchemy session.
    
    Raises:
        RuntimeError: If async mode is not configured.
    """
    if not is_async:
        raise RuntimeError("Async database not configured. Use sync get_db() instead.")
    
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()


def init_db():
    """Initialize database by creating all tables."""
    if is_async:
        # For async, we need to run sync
        import asyncio
        
        async def async_init():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        
        asyncio.run(async_init())
    else:
        Base.metadata.create_all(bind=engine)
    
    logger.info("Database tables created successfully")


def drop_db():
    """Drop all database tables (for testing/reset)."""
    if is_async:
        import asyncio
        
        async def async_drop():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        
        asyncio.run(async_drop())
    else:
        Base.metadata.drop_all(bind=engine)
    
    logger.info("Database tables dropped successfully")