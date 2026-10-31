"""Playlist API endpoints for Phase 2 Discovery."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from lectra_backend.dependencies import get_db_session
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.discovery.url_validation import InvalidPlaylistUrlError, validate_playlist_url
from lectra_core.logging import get_logger
from lectra_core.worker import DISCOVER_JOB_TYPE
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

logger = get_logger("lectra.backend.api.playlists")

router = APIRouter(prefix="/playlists", tags=["playlists"])


# --- Schemas ---


class PlaylistSubmitRequest(BaseModel):
    url: str


class PlaylistSubmitResponse(BaseModel):
    job_id: str
    playlist_id: str
    youtube_id: str
    status: str
    message: str


class PlaylistResponse(BaseModel):
    id: str
    youtube_id: str
    url: str
    title: str
    channel_name: Optional[str]
    video_count: int
    status: str
    discovery_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class VideoResponse(BaseModel):
    id: str
    playlist_id: str
    youtube_id: str
    title: str
    url: str
    duration_seconds: Optional[float]
    position: int
    status: str
    availability: Optional[str]
    discovery_error: Optional[str]


class JobSummary(BaseModel):
    id: str
    status: str
    attempts: int
    error_summary: Optional[str]


class PlaylistStatusResponse(BaseModel):
    playlist_id: str
    youtube_id: str
    title: str
    status: str
    discovery_error: Optional[str]
    video_count: int
    discovered_count: int
    unavailable_count: int
    transcripts_ready_count: int = 0
    needs_transcription_count: int = 0
    latest_job: Optional[JobSummary] = None


# --- Helpers ---


def _find_playlist(db: Session, identifier: str) -> Optional[Playlist]:
    """Find playlist by either internal UUID or YouTube ID."""
    return db.scalars(
        select(Playlist).where((Playlist.id == identifier) | (Playlist.youtube_id == identifier))
    ).first()


# --- Endpoints ---


@router.post("", response_model=PlaylistSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_playlist(
    payload: PlaylistSubmitRequest,
    db: Session = Depends(get_db_session),
) -> PlaylistSubmitResponse:
    """Submit a YouTube playlist URL for discovery.

    Validates the URL, creates or gets the playlist record, and enqueues
    an idempotent discovery job if one is not already queued or running.
    """
    try:
        validated = validate_playlist_url(payload.url)
    except InvalidPlaylistUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Check for existing playlist record
    playlist = db.scalars(
        select(Playlist).where(Playlist.youtube_id == validated.youtube_id)
    ).first()

    if playlist is None:
        playlist = Playlist(
            youtube_id=validated.youtube_id,
            url=validated.normalized_url,
            title="Discovery Pending...",
            status="DISCOVERY_QUEUED",
        )
        db.add(playlist)
        db.flush()

    # Check if an existing active discovery job exists for this playlist
    active_job = db.scalars(
        select(Job)
        .where(
            Job.job_type == DISCOVER_JOB_TYPE,
            Job.status.in_(["QUEUED", "RUNNING"]),
        )
        .order_by(Job.created_at.desc())
    ).all()

    existing_active = None
    for j in active_job:
        if (j.payload or {}).get("playlist_url") == validated.normalized_url:
            existing_active = j
            break

    if existing_active is not None:
        return PlaylistSubmitResponse(
            job_id=existing_active.id,
            playlist_id=playlist.id,
            youtube_id=playlist.youtube_id,
            status=playlist.status,
            message="Discovery job is already queued or in progress",
        )

    # Reset status if rediscovering
    playlist.status = "DISCOVERY_QUEUED"
    playlist.discovery_error = None

    # Enqueue discovery job
    job = Job(
        job_type=DISCOVER_JOB_TYPE,
        status="QUEUED",
        payload={
            "playlist_url": validated.normalized_url,
            "playlist_id": playlist.id,
            "youtube_id": playlist.youtube_id,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(playlist)
    db.refresh(job)

    logger.info(
        "Discovery job enqueued",
        extra={"job_id": job.id, "playlist_id": playlist.id, "youtube_id": playlist.youtube_id},
    )

    return PlaylistSubmitResponse(
        job_id=job.id,
        playlist_id=playlist.id,
        youtube_id=playlist.youtube_id,
        status=playlist.status,
        message="Discovery job successfully queued",
    )


@router.get("", response_model=List[PlaylistResponse])
def list_playlists(db: Session = Depends(get_db_session)) -> List[PlaylistResponse]:
    """List all registered playlists."""
    playlists = db.scalars(select(Playlist).order_by(Playlist.created_at.desc())).all()
    return [
        PlaylistResponse(
            id=p.id,
            youtube_id=p.youtube_id,
            url=p.url,
            title=p.title,
            channel_name=p.channel_name,
            video_count=p.video_count,
            status=p.status,
            discovery_error=p.discovery_error,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in playlists
    ]


@router.get("/{playlist_id}", response_model=PlaylistResponse)
def get_playlist(playlist_id: str, db: Session = Depends(get_db_session)) -> PlaylistResponse:
    """Get metadata for a single playlist by ID or YouTube ID."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )
    return PlaylistResponse(
        id=playlist.id,
        youtube_id=playlist.youtube_id,
        url=playlist.url,
        title=playlist.title,
        channel_name=playlist.channel_name,
        video_count=playlist.video_count,
        status=playlist.status,
        discovery_error=playlist.discovery_error,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
    )


@router.get("/{playlist_id}/status", response_model=PlaylistStatusResponse)
def get_playlist_status(
    playlist_id: str, db: Session = Depends(get_db_session)
) -> PlaylistStatusResponse:
    """Get discovery and ingestion progress status for a playlist."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    # Video counts by status
    discovered_count = (
        db.scalar(
            select(func.count(Video.id)).where(
                Video.playlist_id == playlist.id, Video.status == "DISCOVERED"
            )
        )
        or 0
    )
    unavailable_count = (
        db.scalar(
            select(func.count(Video.id)).where(
                Video.playlist_id == playlist.id, Video.status == "SKIPPED_UNAVAILABLE"
            )
        )
        or 0
    )
    transcripts_ready_count = (
        db.scalar(
            select(func.count(Video.id)).where(
                Video.playlist_id == playlist.id, Video.status == "TRANSCRIPT_READY"
            )
        )
        or 0
    )
    needs_transcription_count = (
        db.scalar(
            select(func.count(Video.id)).where(
                Video.playlist_id == playlist.id, Video.status == "NEEDS_TRANSCRIPTION"
            )
        )
        or 0
    )

    # Latest discovery job
    all_jobs = db.scalars(
        select(Job).where(Job.job_type == DISCOVER_JOB_TYPE).order_by(Job.created_at.desc())
    ).all()

    latest_job = None
    for j in all_jobs:
        if (j.payload or {}).get("playlist_url") == playlist.url:
            latest_job = JobSummary(
                id=j.id,
                status=j.status,
                attempts=j.attempts,
                error_summary=j.error_summary,
            )
            break

    return PlaylistStatusResponse(
        playlist_id=playlist.id,
        youtube_id=playlist.youtube_id,
        title=playlist.title,
        status=playlist.status,
        discovery_error=playlist.discovery_error,
        video_count=playlist.video_count,
        discovered_count=discovered_count,
        unavailable_count=unavailable_count,
        transcripts_ready_count=transcripts_ready_count,
        needs_transcription_count=needs_transcription_count,
        latest_job=latest_job,
    )


@router.get("/{playlist_id}/videos", response_model=List[VideoResponse])
def get_playlist_videos(
    playlist_id: str, db: Session = Depends(get_db_session)
) -> List[VideoResponse]:
    """Get all discovered videos for a playlist in their original playlist order."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    videos = db.scalars(
        select(Video).where(Video.playlist_id == playlist.id).order_by(Video.position.asc())
    ).all()

    return [
        VideoResponse(
            id=v.id,
            playlist_id=v.playlist_id,
            youtube_id=v.youtube_id,
            title=v.title,
            url=v.url,
            duration_seconds=v.duration_seconds,
            position=v.position,
            status=v.status,
            availability=v.availability,
            discovery_error=v.discovery_error,
        )
        for v in videos
    ]
