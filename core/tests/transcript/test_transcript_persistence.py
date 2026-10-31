"""Unit tests for transcript segments persistence and database relationships."""

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, TranscriptSegment, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import TranscriptSegmentData
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_segments.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PLpersistence123",
            url="https://www.youtube.com/playlist?list=PLpersistence123",
            title="Persistence Test Playlist",
        )
        session.add(pl)
        session.flush()

        video = Video(
            playlist_id=pl.id,
            youtube_id="vid_pers_01",
            title="Video Persistence",
            url="https://www.youtube.com/watch?v=vid_pers_01",
            position=0,
            status="DISCOVERED",
        )
        session.add(video)
        session.commit()
        video_id = video.id

    with next(get_db(settings)) as session:
        yield session, video_id, settings


def test_transcript_segments_save_and_retrieve(db_session):
    session, video_id, _ = db_session

    segments_data = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=3.2,
            duration_seconds=3.2,
            text="First sentence.",
            language="en",
            source="manual",
        ),
        TranscriptSegmentData(
            segment_index=1,
            start_seconds=3.2,
            end_seconds=7.0,
            duration_seconds=3.8,
            text="Second sentence.",
            language="en",
            source="manual",
        ),
    ]

    saved = transcript_repository.save_segments(session, video_id, segments_data)
    session.commit()
    assert len(saved) == 2

    retrieved = transcript_repository.get_by_video_id(session, video_id)
    assert len(retrieved) == 2
    assert retrieved[0].segment_index == 0
    assert retrieved[0].text == "First sentence."
    assert retrieved[0].start_seconds == 0.0
    assert retrieved[0].end_seconds == 3.2
    assert retrieved[0].duration_seconds == 3.2
    assert retrieved[0].language == "en"
    assert retrieved[0].source == "manual"

    assert retrieved[1].segment_index == 1
    assert retrieved[1].text == "Second sentence."


def test_save_segments_idempotent_replacement(db_session):
    session, video_id, _ = db_session

    first_batch = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=2.0,
            duration_seconds=2.0,
            text="Old text",
            language="en",
            source="manual",
        )
    ]
    transcript_repository.save_segments(session, video_id, first_batch)
    session.commit()
    assert transcript_repository.has_transcripts(session, video_id) is True

    # Reprocess with updated text
    second_batch = [
        TranscriptSegmentData(
            segment_index=0,
            start_seconds=0.0,
            end_seconds=2.5,
            duration_seconds=2.5,
            text="New text",
            language="en",
            source="manual",
        ),
        TranscriptSegmentData(
            segment_index=1,
            start_seconds=2.5,
            end_seconds=5.0,
            duration_seconds=2.5,
            text="New second sentence",
            language="en",
            source="manual",
        ),
    ]
    transcript_repository.save_segments(session, video_id, second_batch)
    session.commit()

    retrieved = transcript_repository.get_by_video_id(session, video_id)
    assert len(retrieved) == 2
    assert retrieved[0].text == "New text"
    assert retrieved[1].text == "New second sentence"


def test_unique_constraint_prevents_duplicate_segment_index(db_session):
    session, video_id, _ = db_session

    seg1 = TranscriptSegment(
        video_id=video_id,
        segment_index=0,
        start_seconds=0.0,
        end_seconds=2.0,
        duration_seconds=2.0,
        text="A",
        language="en",
        source="manual",
    )
    seg2 = TranscriptSegment(
        video_id=video_id,
        segment_index=0,  # Duplicate index!
        start_seconds=2.0,
        end_seconds=4.0,
        duration_seconds=2.0,
        text="B",
        language="en",
        source="manual",
    )
    session.add(seg1)
    session.add(seg2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_cascade_delete_removes_segments_when_video_deleted(db_session):
    session, video_id, _ = db_session

    seg = TranscriptSegment(
        video_id=video_id,
        segment_index=0,
        start_seconds=0.0,
        end_seconds=2.0,
        duration_seconds=2.0,
        text="Sample text",
        language="en",
        source="manual",
    )
    session.add(seg)
    session.commit()
    assert transcript_repository.has_transcripts(session, video_id) is True

    # Delete video
    video = session.get(Video, video_id)
    session.delete(video)
    session.commit()

    # Segments should be cascade-deleted
    assert transcript_repository.has_transcripts(session, video_id) is False
