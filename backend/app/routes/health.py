from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe for load balancers and monitoring."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness probe kept separate from liveness for container orchestration."""
    return {
        "status": "ready",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
