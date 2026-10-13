"""
Main FastAPI application for NEXUS AI.
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
import time

from config import settings
from api.routes import api_router
from database.session import SessionLocal, engine
from database.base import Base
import database.models  # noqa: F401 — register all tables on Base.metadata

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"FREE MODE: {'ENABLED' if settings.free_mode_enabled else 'DISABLED'}")
    logger.info(f"Database URL: {settings.database_url}")
    
    # Create database tables (async-aware)
    try:
        from sqlalchemy.ext.asyncio import AsyncEngine
        if isinstance(engine, AsyncEngine):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise
    
    # Load initial data
    await load_initial_data()
    
    yield
    
    # Shutdown
    logger.info("Shutting down NEXUS AI...")
    # Cleanup resources here


async def load_initial_data():
    """Load initial data into the database."""
    logger.info("Loading initial configuration...")
    
    # Check available AI providers
    providers = settings.available_providers
    available_count = sum(1 for p in providers if p["available"])
    free_count = sum(1 for p in providers if p["free"] and p["available"])
    
    logger.info(f"AI Providers: {available_count} available, {free_count} free")
    for provider in providers:
        status_icon = "✅" if provider["available"] else "❌"
        free_icon = "🆓" if provider["free"] else "💰"
        logger.info(f"  {status_icon} {provider['name']} ({provider['provider_id']}) - {provider['status']} {free_icon}")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Plataforma Multi-IA Universal para Windows y Android",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(api_router, prefix="/api/v1")

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "free_mode": settings.free_mode_enabled,
        "timestamp": time.time(),
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else "disabled in production",
        "api_version": "v1",
        "endpoints": {
            "health": "/health",
            "api_docs": "/docs",
            "api_base": "/api/v1",
        },
        "features": {
            "free_mode": settings.free_mode_enabled,
            "multi_ai": True,
            "autonomous_agent": True,
            "real_time_brain": True,
            "progressive_learning": settings.memory_enabled,
        },
    }


# Development static files
if settings.debug:
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=settings.reload_on_change,
        log_level=settings.log_level.lower(),
    )