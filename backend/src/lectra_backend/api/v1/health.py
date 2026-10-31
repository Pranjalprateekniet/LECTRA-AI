"""Health check API endpoints."""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Response, status
from lectra_backend.dependencies import get_db_session
from lectra_core.config import Settings, get_settings
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health(
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Check application, database, and system readiness."""
    db_status = "connected"
    http_status = status.HTTP_200_OK

    try:
        db.execute(select(1))
    except Exception as e:
        db_status = f"error: {str(e)}"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    response_payload = {
        "status": "ok" if http_status == status.HTTP_200_OK else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "environment": settings.environment,
        "database": db_status,
        "execution_device": settings.execution_device,
        "components": {
            "api": "healthy",
            "database": db_status,
            "qdrant_configured": bool(settings.qdrant_url),
        },
    }

    if http_status != status.HTTP_200_OK:
        response.status_code = http_status
    return response_payload
