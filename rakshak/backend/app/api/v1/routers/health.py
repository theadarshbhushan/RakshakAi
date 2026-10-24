"""
Health router (/api/v1/health).
Kubernetes-ready liveness and readiness probe endpoints.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.db.mongo import ping_db
from app.jobs.scheduler import scheduler

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Liveness probe: verifies process is alive."""
    return {
        "status": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_probe(response: Response):
    """
    Readiness probe: checks MongoDB cluster connectivity and scheduler status.
    Returns 503 Service Unavailable if database is unreachable.
    """
    db_status = await ping_db()
    is_ready = db_status.get("connected", False)

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "unhealthy",
        "database": db_status,
        "scheduler_running": scheduler.running,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("")
async def general_health():
    """General health check endpoint."""
    db_status = await ping_db()
    return {
        "status": "ok" if db_status.get("connected") else "degraded",
        "db": "connected" if db_status.get("connected") else "disconnected",
        "mode": db_status.get("mode", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
