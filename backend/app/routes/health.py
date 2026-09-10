from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from app.core.deps import get_supabase
from app.feature_runtime.readiness import ReadinessProbe

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
async def readiness_check(request: Request, response: Response, sb=Depends(get_supabase)) -> dict:
    """Bounded readiness; missing schemas or recovery workers produce HTTP 503."""
    probe = getattr(request.app.state, "readiness_probe", None)
    if probe is None:
        probe = ReadinessProbe()
        request.app.state.readiness_probe = probe
    result = await probe.check(sb)
    response.status_code = 200 if result["status"] == "ready" else 503
    return result
