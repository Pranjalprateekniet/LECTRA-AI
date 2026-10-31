"""Chunk repository: database operations for derived video chunks."""

from dataclasses import dataclass
from typing import Any, List, Sequence, Union

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lectra_core.db.models import VideoChunk


@dataclass
class ChunkData:
    """In-memory data representation for a derived video chunk."""

    id: str
    video_id: str
    chunk_index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    text: str
    token_count: int
    source_segment_start_index: int
    source_segment_end_index: int


def save_chunks(
    session: Session,
    video_id: str,
    chunks: Sequence[Union[ChunkData, VideoChunk, Any]],
) -> List[VideoChunk]:
    """Persist video chunks idempotently.

    Existing chunks for the video are removed first within the transaction
    so that retries or recalculations never leave duplicate records.
    """
    session.execute(delete(VideoChunk).where(VideoChunk.video_id == video_id))

    records = [
        VideoChunk(
            id=c.id,
            video_id=video_id,
            chunk_index=c.chunk_index,
            start_seconds=c.start_seconds,
            end_seconds=c.end_seconds,
            duration_seconds=c.duration_seconds,
            text=c.text,
            token_count=c.token_count,
            source_segment_start_index=c.source_segment_start_index,
            source_segment_end_index=c.source_segment_end_index,
        )
        for c in chunks
    ]
    session.add_all(records)
    session.flush()
    return records


def get_by_video_id(session: Session, video_id: str) -> List[VideoChunk]:
    """Fetch all chunks for a video ordered by chunk index."""
    return list(
        session.scalars(
            select(VideoChunk)
            .where(VideoChunk.video_id == video_id)
            .order_by(VideoChunk.chunk_index.asc())
        ).all()
    )


def has_chunks(session: Session, video_id: str) -> bool:
    """Check if any chunks exist for the given video."""
    count = session.scalar(
        select(func.count(VideoChunk.id)).where(VideoChunk.video_id == video_id)
    )
    return bool(count and count > 0)


def delete_by_video_id(session: Session, video_id: str) -> int:
    """Delete all chunks for a video. Returns count of deleted rows."""
    result = session.execute(
        delete(VideoChunk).where(VideoChunk.video_id == video_id)
    )
    return int(getattr(result, "rowcount", 0) or 0)

