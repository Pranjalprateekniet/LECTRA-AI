"""Playlist API endpoints for Ingestion Dashboard and Discovery."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from lectra_backend.dependencies import get_db_session
from lectra_core.config import Settings, get_settings
from lectra_core.db.models import (
    Job,
    Playlist,
    ProcessingStage,
    TranscriptSegment,
    Video,
    VideoChunk,
)
from lectra_core.discovery.url_validation import InvalidPlaylistUrlError, validate_playlist_url
from lectra_core.logging import get_logger
from lectra_core.worker import (
    CHUNK_PLAYLIST_JOB_TYPE,
    CHUNK_VIDEO_JOB_TYPE,
    DISCOVER_JOB_TYPE,
    EXTRACT_TRANSCRIPTS_JOB_TYPE,
    EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE,
    INDEX_PLAYLIST_JOB_TYPE,
    INDEX_VIDEO_JOB_TYPE,
)
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
    channel_name: Optional[str] = None
    video_count: int = 0
    status: str
    discovery_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_count: int = 0
    processing_count: int = 0
    failed_count: int = 0
    thumbnail_url: Optional[str] = None


class StageDetail(BaseModel):
    stage_name: str
    status: str  # PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED
    attempts: int = 0
    error_category: Optional[str] = None
    error_detail: Optional[str] = None
    completed_at: Optional[datetime] = None
    artifact_path: Optional[str] = None


class VideoResponse(BaseModel):
    id: str
    playlist_id: str
    youtube_id: str
    title: str
    url: str
    duration_seconds: Optional[float] = None
    position: int = 0
    status: str
    availability: Optional[str] = None
    discovery_error: Optional[str] = None
    transcript_segments_count: int = 0
    transcript_source: Optional[str] = None  # "generated" | "manual" | "whisper"
    language: Optional[str] = None
    chunks_count: int = 0
    indexed_vectors_count: int = 0
    thumbnail_url: Optional[str] = None
    stages: List[StageDetail] = []


class JobSummary(BaseModel):
    id: str
    status: str
    attempts: int
    error_summary: Optional[str] = None


class PlaylistStatusResponse(BaseModel):
    playlist_id: str
    youtube_id: str
    title: str
    status: str
    discovery_error: Optional[str] = None
    video_count: int = 0
    discovered_count: int = 0
    unavailable_count: int = 0
    transcripts_ready_count: int = 0
    needs_transcription_count: int = 0
    completed_count: int = 0
    processing_count: int = 0
    failed_count: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    total_vectors_indexed: int = 0
    total_transcript_segments: int = 0
    embedding_model: str = "google/embeddinggemma-2"
    latest_job: Optional[JobSummary] = None


class ActivityEventResponse(BaseModel):
    id: str
    timestamp: datetime
    playlist_id: str
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    stage: str
    event: str
    severity: str  # "info" | "warning" | "error" | "success"
    details: Optional[str] = None


class RetryResponse(BaseModel):
    success: bool
    job_id: str
    message: str


class VideoDeleteResponse(BaseModel):
    success: bool
    message: str
    video_id: str
    playlist_id: str


# --- Helpers ---


def _find_playlist(db: Session, identifier: str) -> Optional[Playlist]:
    """Find playlist by either internal UUID or YouTube ID."""
    return db.scalars(
        select(Playlist).where((Playlist.id == identifier) | (Playlist.youtube_id == identifier))
    ).first()


def _get_playlist_counts(db: Session, playlist_id: str) -> Dict[str, int]:
    """Efficiently compute video status counts and chunk totals for a playlist."""
    rows = db.execute(
        select(Video.status, func.count(Video.id))
        .where(Video.playlist_id == playlist_id)
        .group_by(Video.status)
    ).all()
    status_map = {status: count for status, count in rows}

    completed = status_map.get("INDEXED", 0)
    failed = (
        status_map.get("FAILED", 0)
        + status_map.get("SKIPPED_UNAVAILABLE", 0)
        + status_map.get("DISCOVERY_FAILED", 0)
    )
    processing = (
        status_map.get("IN_PROGRESS", 0)
        + status_map.get("TRANSCRIPT_READY", 0)
        + status_map.get("ENGLISH_READY", 0)
        + status_map.get("CHUNKED", 0)
    )

    total_chunks = (
        db.scalar(
            select(func.count(VideoChunk.id))
            .join(Video, VideoChunk.video_id == Video.id)
            .where(Video.playlist_id == playlist_id)
        )
        or 0
    )

    total_segs = (
        db.scalar(
            select(func.count(TranscriptSegment.id))
            .join(Video, TranscriptSegment.video_id == Video.id)
            .where(Video.playlist_id == playlist_id)
        )
        or 0
    )

    return {
        "completed": completed,
        "failed": failed,
        "processing": processing,
        "discovered": status_map.get("DISCOVERED", 0),
        "transcripts_ready": status_map.get("TRANSCRIPT_READY", 0),
        "needs_transcription": status_map.get("NEEDS_TRANSCRIPTION", 0),
        "unavailable": status_map.get("SKIPPED_UNAVAILABLE", 0),
        "total_chunks": total_chunks,
        "total_segments": total_segs,
    }


# --- Endpoints ---


@router.post("", response_model=PlaylistSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_playlist(
    payload: PlaylistSubmitRequest,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PlaylistSubmitResponse:
    """Submit a YouTube playlist URL for discovery and ingestion."""
    if settings.app_mode == "USER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Playlist ingestion is disabled in USER mode. In USER mode, Revision RAG "
            "operates as a revision assistant querying the central knowledge base.",
        )
    try:
        validated = validate_playlist_url(payload.url)
    except InvalidPlaylistUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

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

    playlist.status = "DISCOVERY_QUEUED"
    playlist.discovery_error = None

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
    """List all registered playlists with progress metrics."""
    playlists = db.scalars(select(Playlist).order_by(Playlist.created_at.desc())).all()
    results: List[PlaylistResponse] = []

    for p in playlists:
        counts = _get_playlist_counts(db, p.id)
        first_video = db.scalars(
            select(Video).where(Video.playlist_id == p.id).order_by(Video.position.asc()).limit(1)
        ).first()
        thumb = (
            f"https://i.ytimg.com/vi/{first_video.youtube_id}/hqdefault.jpg"
            if first_video
            else None
        )

        results.append(
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
                completed_count=counts["completed"],
                processing_count=counts["processing"],
                failed_count=counts["failed"],
                thumbnail_url=thumb,
            )
        )
    return results


@router.get("/{playlist_id}", response_model=PlaylistResponse)
def get_playlist(playlist_id: str, db: Session = Depends(get_db_session)) -> PlaylistResponse:
    """Get metadata and counts for a single playlist by internal UUID or YouTube ID."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )
    counts = _get_playlist_counts(db, playlist.id)
    first_video = db.scalars(
        select(Video)
        .where(Video.playlist_id == playlist.id)
        .order_by(Video.position.asc())
        .limit(1)
    ).first()
    thumb = (
        f"https://i.ytimg.com/vi/{first_video.youtube_id}/hqdefault.jpg" if first_video else None
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
        completed_count=counts["completed"],
        processing_count=counts["processing"],
        failed_count=counts["failed"],
        thumbnail_url=thumb,
    )


@router.get("/{playlist_id}/status", response_model=PlaylistStatusResponse)
def get_playlist_status(
    playlist_id: str, db: Session = Depends(get_db_session)
) -> PlaylistStatusResponse:
    """Get complete progress statistics and job status for a playlist."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    counts = _get_playlist_counts(db, playlist.id)

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
        discovered_count=counts["discovered"],
        unavailable_count=counts["unavailable"],
        transcripts_ready_count=counts["transcripts_ready"],
        needs_transcription_count=counts["needs_transcription"],
        completed_count=counts["completed"],
        processing_count=counts["processing"],
        failed_count=counts["failed"],
        total_chunks=counts["total_chunks"],
        total_embeddings=counts["total_chunks"] if counts["completed"] > 0 else 0,
        total_vectors_indexed=counts["total_chunks"] if counts["completed"] > 0 else 0,
        total_transcript_segments=counts["total_segments"],
        embedding_model="google/embeddinggemma-2",
        latest_job=latest_job,
    )


@router.get("/{playlist_id}/videos", response_model=List[VideoResponse])
def get_playlist_videos(
    playlist_id: str, db: Session = Depends(get_db_session)
) -> List[VideoResponse]:
    """Get all discovered videos for a playlist with stage checkpoints and metrics."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    videos = db.scalars(
        select(Video).where(Video.playlist_id == playlist.id).order_by(Video.position.asc())
    ).all()

    if not videos:
        return []

    video_ids = [v.id for v in videos]

    # Batch query processing stages
    all_stages = db.scalars(
        select(ProcessingStage)
        .where(ProcessingStage.video_id.in_(video_ids))
        .order_by(ProcessingStage.created_at.asc())
    ).all()
    stages_by_vid: Dict[str, List[StageDetail]] = {vid: [] for vid in video_ids}
    for st in all_stages:
        stages_by_vid[st.video_id].append(
            StageDetail(
                stage_name=st.stage_name,
                status=st.status,
                attempts=st.attempts,
                error_category=st.error_category,
                error_detail=st.error_detail,
                completed_at=st.completed_at,
                artifact_path=st.artifact_path,
            )
        )

    # Batch query chunks count
    chunk_counts_rows = db.execute(
        select(VideoChunk.video_id, func.count(VideoChunk.id))
        .where(VideoChunk.video_id.in_(video_ids))
        .group_by(VideoChunk.video_id)
    ).all()
    chunk_counts = {vid: cnt for vid, cnt in chunk_counts_rows}

    # Batch query transcript segments
    segment_rows = db.execute(
        select(
            TranscriptSegment.video_id,
            func.count(TranscriptSegment.id),
            func.min(TranscriptSegment.language),
            func.min(TranscriptSegment.source),
        )
        .where(TranscriptSegment.video_id.in_(video_ids))
        .group_by(TranscriptSegment.video_id)
    ).all()
    seg_info: Dict[str, Dict[str, Any]] = {
        vid: {"count": cnt, "language": lang, "source": src} for vid, cnt, lang, src in segment_rows
    }

    result: List[VideoResponse] = []
    for v in videos:
        c_count = int(chunk_counts.get(v.id, 0))
        s_data = seg_info.get(v.id, {})
        raw_cnt = s_data.get("count", 0)
        s_cnt = int(raw_cnt) if isinstance(raw_cnt, (int, float, str)) else 0
        s_src = str(s_data["source"]) if s_data.get("source") else None
        s_lang = str(s_data["language"]) if s_data.get("language") else None
        thumb = f"https://i.ytimg.com/vi/{v.youtube_id}/hqdefault.jpg"

        # Vectors indexed equals chunk count if video is INDEXED
        vectors_indexed = c_count if v.status == "INDEXED" else 0

        result.append(
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
                transcript_segments_count=s_cnt,
                transcript_source=s_src,
                language=s_lang,
                chunks_count=c_count,
                indexed_vectors_count=vectors_indexed,
                thumbnail_url=thumb,
                stages=stages_by_vid.get(v.id, []),
            )
        )

    return result


@router.get("/{playlist_id}/activity", response_model=List[ActivityEventResponse])
def get_playlist_activity(
    playlist_id: str,
    limit: int = 50,
    db: Session = Depends(get_db_session),
) -> List[ActivityEventResponse]:
    """Retrieve chronological activity log compiled from persisted jobs and processing stages."""
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    events: List[ActivityEventResponse] = []

    # 1. Playlist creation event
    events.append(
        ActivityEventResponse(
            id=f"pl-created-{playlist.id}",
            timestamp=playlist.created_at,
            playlist_id=playlist.id,
            stage="DISCOVERY",
            event=f'Playlist "{playlist.title}" submitted for discovery',
            severity="info",
            details=f"URL: {playlist.url}",
        )
    )

    # 2. Jobs associated with this playlist
    jobs = db.scalars(select(Job).order_by(Job.created_at.asc())).all()
    for j in jobs:
        payload = j.payload or {}
        is_match = (
            payload.get("playlist_url") == playlist.url or payload.get("playlist_id") == playlist.id
        )
        if is_match:
            sev = (
                "info"
                if j.status in ("QUEUED", "RUNNING")
                else ("success" if j.status == "COMPLETED" else "error")
            )
            events.append(
                ActivityEventResponse(
                    id=f"job-{j.id}",
                    timestamp=j.created_at,
                    playlist_id=playlist.id,
                    stage=j.job_type.upper(),
                    event=f"Background job '{j.job_type}' enqueued (status: {j.status})",
                    severity=sev,
                    details=j.error_summary,
                )
            )
            is_terminal = j.status in ("COMPLETED", "FAILED")
            if j.updated_at and j.updated_at != j.created_at and is_terminal:
                events.append(
                    ActivityEventResponse(
                        id=f"job-finish-{j.id}",
                        timestamp=j.updated_at,
                        playlist_id=playlist.id,
                        stage=j.job_type.upper(),
                        event=f"Job '{j.job_type}' finished with status {j.status}",
                        severity="success" if j.status == "COMPLETED" else "error",
                        details=j.error_summary,
                    )
                )

    # 3. Processing stage events
    stages_query = db.execute(
        select(ProcessingStage, Video)
        .join(Video, ProcessingStage.video_id == Video.id)
        .where(Video.playlist_id == playlist.id)
    ).all()

    for stage, vid in stages_query:
        ts = stage.completed_at or stage.updated_at or stage.created_at
        sev = (
            "success"
            if stage.status == "COMPLETED"
            else ("error" if stage.status == "FAILED" else "info")
        )
        stage_label = stage.stage_name.replace("_", " ").title()
        events.append(
            ActivityEventResponse(
                id=f"stage-{stage.id}",
                timestamp=ts,
                playlist_id=playlist.id,
                video_id=vid.id,
                video_title=vid.title,
                stage=stage.stage_name,
                event=f"{stage_label} {stage.status.lower()} for '{vid.title}'",
                severity=sev,
                details=stage.error_detail or stage.artifact_path,
            )
        )

    # Sort descending by timestamp
    events.sort(key=lambda x: x.timestamp, reverse=True)
    return events[:limit]


@router.post("/{playlist_id}/retry", response_model=RetryResponse)
def retry_playlist_ingestion(
    playlist_id: str,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> RetryResponse:
    """Retry ingestion for failed or incomplete videos in a playlist."""
    if settings.app_mode == "USER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Playlist ingestion is disabled in USER mode.",
        )
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    # If playlist discovery failed, re-enqueue discovery
    if playlist.status in ("DISCOVERY_FAILED", "DISCOVERY_QUEUED"):
        job = Job(
            job_type=DISCOVER_JOB_TYPE,
            status="QUEUED",
            payload={
                "playlist_url": playlist.url,
                "playlist_id": playlist.id,
                "youtube_id": playlist.youtube_id,
            },
        )
        playlist.status = "DISCOVERY_QUEUED"
        playlist.discovery_error = None
        db.add(job)
        db.commit()
        return RetryResponse(
            success=True,
            job_id=job.id,
            message="Discovery job re-enqueued successfully.",
        )

    # Determine what stage needs to be queued based on videos' status
    counts = _get_playlist_counts(db, playlist.id)
    if counts["discovered"] > 0 or counts["failed"] > 0:
        job_type = EXTRACT_TRANSCRIPTS_JOB_TYPE
        msg = "Transcript extraction job enqueued successfully."
    elif counts["transcripts_ready"] > 0:
        job_type = CHUNK_PLAYLIST_JOB_TYPE
        msg = "Chunking job enqueued successfully."
    elif counts["processing"] > 0 and counts["total_chunks"] > 0:
        job_type = INDEX_PLAYLIST_JOB_TYPE
        msg = "Indexing job enqueued successfully."
    else:
        job_type = EXTRACT_TRANSCRIPTS_JOB_TYPE
        msg = "Transcript extraction job enqueued successfully."

    job = Job(
        job_type=job_type,
        status="QUEUED",
        payload={
            "playlist_id": playlist.id,
            "youtube_id": playlist.youtube_id,
        },
    )
    db.add(job)
    db.commit()
    return RetryResponse(
        success=True,
        job_id=job.id,
        message=msg,
    )


@router.post("/videos/{video_id}/retry", response_model=RetryResponse)
def retry_video_ingestion(
    video_id: str,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> RetryResponse:
    """Retry ingestion for an individual failed video at its current failed stage."""
    if settings.app_mode == "USER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Video ingestion retry is disabled in USER mode.",
        )
    video = db.scalars(select(Video).where(Video.id == video_id)).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video '{video_id}' not found.",
        )

    # Determine failed or pending stage
    failed_stage = db.scalars(
        select(ProcessingStage)
        .where(ProcessingStage.video_id == video.id, ProcessingStage.status == "FAILED")
        .order_by(ProcessingStage.created_at.desc())
    ).first()

    if failed_stage:
        failed_stage.status = "PENDING"
        failed_stage.error_detail = None
        if failed_stage.stage_name == "TRANSCRIPT_ACQUISITION":
            job_type = EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE
        elif failed_stage.stage_name == "CHUNKING":
            job_type = CHUNK_VIDEO_JOB_TYPE
        else:
            job_type = INDEX_VIDEO_JOB_TYPE
    else:
        # Default to transcript extraction if not yet ready
        if video.status in ("DISCOVERED", "NEEDS_TRANSCRIPTION"):
            job_type = EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE
        elif video.status == "TRANSCRIPT_READY":
            job_type = CHUNK_VIDEO_JOB_TYPE
        else:
            job_type = INDEX_VIDEO_JOB_TYPE

    job = Job(
        job_type=job_type,
        status="QUEUED",
        payload={"video_id": video.id, "youtube_id": video.youtube_id},
    )
    db.add(job)
    db.commit()

    return RetryResponse(
        success=True,
        job_id=job.id,
        message=f"Re-enqueued '{job_type}' for video '{video.title}'.",
    )


@router.delete("/{playlist_id}/videos/{video_id}", response_model=VideoDeleteResponse)
def delete_playlist_video(
    playlist_id: str,
    video_id: str,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> VideoDeleteResponse:
    """Delete a video and its derived transcripts, chunks, embeddings, and artifacts."""
    if settings.app_mode == "USER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Video deletion is disabled in USER mode.",
        )
    playlist = _find_playlist(db, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Playlist '{playlist_id}' not found.",
        )

    video = db.scalars(
        select(Video).where(
            Video.id == video_id,
            Video.playlist_id == playlist.id,
        )
    ).first()

    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video '{video_id}' not found in playlist '{playlist_id}'.",
        )

    video_title = video.title
    youtube_id = video.youtube_id
    from lectra_core.config import get_settings

    settings = get_settings()

    # 1. Invalidate / cancel active and queued jobs for this video
    active_jobs = db.scalars(
        select(Job).where(
            Job.status.in_(["QUEUED", "RUNNING"]),
        )
    ).all()
    for j in active_jobs:
        payload = j.payload or {}
        if payload.get("video_id") == video.id:
            j.status = "CANCELLED"
            j.error_summary = "Video was deleted from playlist."

    # 2. Delete embeddings from Qdrant
    try:
        from lectra_core.vectorstore.qdrant import QdrantVectorStore

        vs = QdrantVectorStore(settings=settings)
        vs.delete_points_by_video_id(video.id)
        logger.info("Deleted Qdrant points for video", extra={"video_id": video.id})
    except Exception as exc:
        logger.warning(
            "Failed to delete Qdrant points during video removal",
            extra={"video_id": video.id, "error": str(exc)},
        )

    # 3. Delete local intermediate artifact files
    try:
        transcripts_dir = settings.artifacts_dir / "transcripts"
        if transcripts_dir.exists():
            for p in transcripts_dir.glob(f"{youtube_id}_*"):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

        temp_audio_dir = settings.temp_audio_dir
        if temp_audio_dir.exists():
            for p in temp_audio_dir.glob(f"*{youtube_id}*"):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning(
            "Error removing local artifact files during video deletion",
            extra={"video_id": video.id, "error": str(exc)},
        )

    # 4. Delete Video record from SQLite (cascades to stages, transcripts, chunks)
    db.delete(video)

    # 5. Reconcile playlist video count
    db.flush()
    new_video_count = (
        db.scalar(select(func.count(Video.id)).where(Video.playlist_id == playlist.id)) or 0
    )
    playlist.video_count = int(new_video_count)
    db.commit()

    logger.info(
        "Successfully deleted video from playlist",
        extra={"playlist_id": playlist.id, "video_id": video_id, "title": video_title},
    )

    return VideoDeleteResponse(
        success=True,
        message=f"Video '{video_title}' deleted successfully.",
        video_id=video_id,
        playlist_id=playlist.id,
    )
