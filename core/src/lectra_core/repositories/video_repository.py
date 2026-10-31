"""Video repository: reconciliation helpers keyed by (playlist, stable YouTube video ID)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.db.models import Video

# Video statuses that downstream phases are or could be working on. Discovery
# reconciliation must never replace these with DISCOVERED or destroy progress.
_DOWNSTREAM_STATUSES = frozenset(
    {
        "TRANSCRIPT_READY",
        "NEEDS_TRANSCRIPTION",
        "ENGLISH_READY",
        "CHUNKED",
        "INDEXED",
    }
)


def get(playlist_db_id: str, youtube_id: str, session: Session) -> Optional[Video]:
    """Fetch one video of a playlist by its stable YouTube ID."""
    return session.scalars(
        select(Video).where(
            Video.playlist_id == playlist_db_id,
            Video.youtube_id == youtube_id,
        )
    ).first()


def apply_discovery(session: Session, video: Video, **fields) -> Video:
    """Update discovery-time fields on an existing video row.

    Position is only overwritten when the caller explicitly passes it
    (first occurrence wins for duplicates otherwise).
    """
    for field, value in fields.items():
        setattr(video, field, value)
    return video


def is_downstream_in_progress(video: Video) -> bool:
    """True when the video has progressed past discovery."""
    return video.status in _DOWNSTREAM_STATUSES


def get_eligible_for_transcription(session: Session, playlist_id: str) -> list[Video]:
    """Fetch discovered videos eligible for transcript extraction in order."""
    return list(
        session.scalars(
            select(Video)
            .where(
                Video.playlist_id == playlist_id,
                Video.status.in_(["DISCOVERED", "EXTRACTION_FAILED"]),
            )
            .order_by(Video.position.asc())
        ).all()
    )
