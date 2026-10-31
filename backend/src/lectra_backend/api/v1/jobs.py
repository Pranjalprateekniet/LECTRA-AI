"""Jobs API endpoints."""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from lectra_backend.dependencies import get_db_session
from lectra_core.db.models import Job
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobDetailResponse(BaseModel):
    id: str
    job_type: str
    status: str
    attempts: int
    max_retries: int
    error_summary: Optional[str]
    payload: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db_session)) -> JobDetailResponse:
    """Retrieve the status and attempt count of a background job."""
    job = db.scalars(select(Job).where(Job.id == job_id)).first()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return JobDetailResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        attempts=job.attempts,
        max_retries=job.max_retries,
        error_summary=job.error_summary,
        payload=job.payload,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
