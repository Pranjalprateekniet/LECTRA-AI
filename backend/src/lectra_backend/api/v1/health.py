"""Health check API endpoints."""

from datetime import datetime, timezone
from pathlib import Path
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

    components: Dict[str, Any] = {
        "api": "healthy",
        "database": db_status,
    }
    if settings.app_mode == "USER":
        local_qdrant_ready = Path(settings.qdrant_path).exists()
        components["qdrant_configured"] = local_qdrant_ready or bool(settings.retrieval_api_url)
        components["qdrant_mode"] = "remote" if settings.retrieval_api_url else "local"
        components["local_qdrant_path"] = str(settings.qdrant_path)
        if settings.retrieval_api_url:
            components["retrieval_api_configured"] = True
    else:
        components["qdrant_configured"] = bool(settings.qdrant_url) or Path(settings.qdrant_path).exists()
        components["qdrant_mode"] = "cloud" if settings.qdrant_url else "local"

    response_payload = {
        "status": "ok" if http_status == status.HTTP_200_OK else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "app_mode": settings.app_mode,
        "environment": settings.environment,
        "database": db_status,
        "execution_device": settings.execution_device,
        "components": components,
    }

    if http_status != status.HTTP_200_OK:
        response.status_code = http_status
    return response_payload
