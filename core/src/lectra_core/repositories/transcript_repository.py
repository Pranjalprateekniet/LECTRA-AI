"""Transcript repository: database operations for timestamped transcript segments."""

from typing import Any, List, Sequence, Union

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lectra_core.db.models import TranscriptSegment
from lectra_core.transcript.models import TranscriptSegmentData

TranscriptSegmentInput = TranscriptSegmentData


def save_segments(
    session: Session,
    video_id: str,
    segments: Sequence[Union[TranscriptSegmentData, Any]],
) -> List[TranscriptSegment]:
    """Persist transcript segments for a video idempotently.

    Existing segments for the video are removed first within the transaction
    so that retries never leave duplicate records or broken ordering.
    """
    session.execute(delete(TranscriptSegment).where(TranscriptSegment.video_id == video_id))

    records = [
        TranscriptSegment(
            video_id=video_id,
            segment_index=seg.segment_index,
            start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds,
            duration_seconds=seg.duration_seconds,
            text=seg.text,
            language=seg.language,
            source=seg.source,
        )
        for seg in segments
    ]
    session.add_all(records)
    session.flush()
    return records


def get_by_video_id(session: Session, video_id: str) -> List[TranscriptSegment]:
    """Fetch all transcript segments for a video ordered by segment index."""
    return list(
        session.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.video_id == video_id)
            .order_by(TranscriptSegment.segment_index.asc())
        ).all()
    )


def has_transcripts(session: Session, video_id: str) -> bool:
    """Check if any transcript segments exist for the given video."""
    count = session.scalar(
        select(func.count(TranscriptSegment.id)).where(TranscriptSegment.video_id == video_id)
    )
    return bool(count and count > 0)


def delete_by_video_id(session: Session, video_id: str) -> int:
    """Delete all transcript segments for a video. Returns count of deleted rows."""
    result = session.execute(
        delete(TranscriptSegment).where(TranscriptSegment.video_id == video_id)
    )
    return int(getattr(result, "rowcount", 0) or 0)
