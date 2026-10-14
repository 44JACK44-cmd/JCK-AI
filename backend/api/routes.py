"""
API routes for NEXUS AI.
"""
from fastapi import APIRouter
from api.endpoints import (
    providers,
    conversations,
    tasks,
    files,
    terminal,
    projects,
    brain,
    memory,
    devices,
    auth,
    keys,
    git,
    tools,
    agent,
    scheduler,
)

# Main API router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    providers.router,
    prefix="/providers",
    tags=["AI Providers"]
)

api_router.include_router(
    conversations.router,
    prefix="/conversations",
    tags=["Conversations"]
)

api_router.include_router(
    tasks.router,
    prefix="/tasks",
    tags=["Tasks"]
)

api_router.include_router(
    files.router,
    prefix="/files",
    tags=["Files"]
)

api_router.include_router(
    terminal.router,
    prefix="/terminal",
    tags=["Terminal"]
)

api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["Projects"]
)

api_router.include_router(
    git.router,
    prefix="/projects/git",
    tags=["Git"]
)

api_router.include_router(
    brain.router,
    prefix="/brain",
    tags=["Brain"]
)

api_router.include_router(
    memory.router,
    prefix="/memory",
    tags=["Memory"]
)

api_router.include_router(
    devices.router,
    prefix="/devices",
    tags=["Devices"]
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

api_router.include_router(
    keys.router,
    prefix="/keys",
    tags=["API Keys"]
)

api_router.include_router(
    tools.router,
    prefix="/tools",
    tags=["Web Tools"]
)

api_router.include_router(
    agent.router,
    prefix="/agent",
    tags=["Autonomous Agent"]
)

api_router.include_router(
    scheduler.router,
    prefix="/scheduler",
    tags=["Task Scheduler"]
)