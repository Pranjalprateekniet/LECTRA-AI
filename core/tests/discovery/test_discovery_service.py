"""Unit tests for DiscoveryService with FakeProvider."""

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.discovery.service import DiscoveryError, DiscoveryService
from sqlalchemy import select

from .mock_provider import FakeProvider, make_entry


@pytest.fixture
def test_db_session(tmp_path):
    """Fixture providing a temporary SQLite session."""
    db_file = tmp_path / "test_discovery.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)
    with next(get_db(settings)) as session:
        yield session


def test_discovery_normal_flow(test_db_session):
    """Test standard playlist discovery with 3 available videos."""
    entries = [
        make_entry(0, "video_id_001", "Binary Search Intro", 600.0),
        make_entry(1, "video_id_002", "Binary Search Edge Cases", 750.0),
        make_entry(2, "video_id_003", "Search in Rotated Array", 900.0),
    ]
    provider = FakeProvider(entries, title="Algorithms 101")
    service = DiscoveryService(provider=provider)

    result = service.discover(
        test_db_session,
        "https://www.youtube.com/playlist?list=PLtest1234567890",
    )

    assert result.distinct_videos == 3
    assert result.discovered == 3
    assert result.unavailable == 0
    assert result.duplicate_entries == 0

    # Verify playlist persisted in DB
    playlist = test_db_session.scalars(
        select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
    ).first()
    assert playlist is not None
    assert playlist.title == "Algorithms 101"
    assert playlist.status == "DISCOVERY_COMPLETED"
    assert playlist.video_count == 3

    # Verify videos in DB with exact ordering and metadata
    videos = test_db_session.scalars(
        select(Video).where(Video.playlist_id == playlist.id).order_by(Video.position.asc())
    ).all()
    assert len(videos) == 3
    assert [v.youtube_id for v in videos] == ["video_id_001", "video_id_002", "video_id_003"]
    assert [v.position for v in videos] == [0, 1, 2]
    assert [v.duration_seconds for v in videos] == [600.0, 750.0, 900.0]
    assert [v.status for v in videos] == ["DISCOVERED", "DISCOVERED", "DISCOVERED"]
    assert [v.availability for v in videos] == ["public", "public", "public"]


def test_discovery_handles_unavailable_videos(test_db_session):
    """Test that unavailable, private, and removed videos do not terminate discovery."""
    entries = [
        make_entry(0, "vid_normal_1", "Normal 1", 300.0),
        make_entry(1, "vid_private_2", "Private Video", 400.0),
        make_entry(2, "vid_removed_3", "Removed Video", 500.0),
        make_entry(3, "vid_normal_4", "Normal 4", 600.0),
    ]
    provider = FakeProvider(entries)
    # Simulate errors on specific videos
    provider.video_failures["https://www.youtube.com/watch?v=vid_private_2"] = (
        "This video is private."
    )
    provider.video_failures["https://www.youtube.com/watch?v=vid_removed_3"] = (
        "Video unavailable: This video has been removed by the uploader."
    )

    service = DiscoveryService(provider=provider)
    result = service.discover(
        test_db_session,
        "https://www.youtube.com/playlist?list=PLtest1234567890",
    )

    assert result.distinct_videos == 4
    assert result.discovered == 2
    assert result.unavailable == 2
    assert "vid_private_2" in result.unavailable_ids
    assert "vid_removed_3" in result.unavailable_ids

    playlist = test_db_session.scalars(
        select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
    ).first()
    assert playlist.status == "DISCOVERY_COMPLETED"

    # Verify per-video status and error classification
    v_priv = test_db_session.scalars(
        select(Video).where(Video.youtube_id == "vid_private_2")
    ).first()
    assert v_priv.status == "SKIPPED_UNAVAILABLE"
    assert v_priv.availability == "PRIVATE"
    assert "This video is private." in v_priv.discovery_error

    v_rem = test_db_session.scalars(
        select(Video).where(Video.youtube_id == "vid_removed_3")
    ).first()
    assert v_rem.status == "SKIPPED_UNAVAILABLE"
    assert v_rem.availability == "REMOVED"
    assert "removed by the uploader" in v_rem.discovery_error

    v_norm = test_db_session.scalars(
        select(Video).where(Video.youtube_id == "vid_normal_4")
    ).first()
    assert v_norm.status == "DISCOVERED"


def test_discovery_repeated_submission_idempotency(test_db_session):
    """Test that submitting the same playlist repeatedly updates records without duplicates."""
    entries = [
        make_entry(0, "video_rep_1", "Video 1", 300.0),
        make_entry(1, "video_rep_2", "Video 2", 400.0),
    ]
    provider = FakeProvider(entries, title="Original Title")
    service = DiscoveryService(provider=provider)

    res1 = service.discover(
        test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890"
    )
    assert res1.discovered == 2

    # Re-run discovery with updated title
    provider.playlist_title = "Updated Title"
    res2 = service.discover(
        test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890"
    )
    assert res2.discovered == 0  # no new videos inserted
    assert res2.distinct_videos == 2

    playlists = test_db_session.scalars(select(Playlist)).all()
    assert len(playlists) == 1
    assert playlists[0].title == "Updated Title"

    videos = test_db_session.scalars(select(Video)).all()
    assert len(videos) == 2


def test_discovery_in_playlist_duplicates(test_db_session):
    """Test that duplicate video IDs within the same playlist are deduplicated (first wins)."""
    entries = [
        make_entry(0, "dup_video_1", "Duplicate Video First", 300.0),
        make_entry(1, "other_video", "Other Video", 400.0),
        make_entry(2, "dup_video_1", "Duplicate Video Second", 300.0),
    ]
    provider = FakeProvider(entries)
    service = DiscoveryService(provider=provider)

    result = service.discover(
        test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890"
    )
    assert result.entries_seen == 3
    assert result.distinct_videos == 2
    assert result.duplicate_entries == 1

    videos = test_db_session.scalars(select(Video).order_by(Video.position.asc())).all()
    assert len(videos) == 2
    assert videos[0].youtube_id == "dup_video_1"
    assert videos[0].position == 0
    assert videos[0].title == "Duplicate Video First"


def test_discovery_preserves_downstream_status(test_db_session):
    """Test that discovery reconciliation never overwrites downstream processing states."""
    entries = [make_entry(0, "processed_video", "Processed Video", 500.0)]
    provider = FakeProvider(entries)
    service = DiscoveryService(provider=provider)

    # First discovery
    service.discover(test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890")
    video = test_db_session.scalars(
        select(Video).where(Video.youtube_id == "processed_video")
    ).first()
    assert video.status == "DISCOVERED"

    # Simulate downstream advancement to INDEXED
    video.status = "INDEXED"
    test_db_session.commit()

    # Re-run discovery
    service.discover(test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890")
    test_db_session.refresh(video)
    assert video.status == "INDEXED"  # preserved!


def test_discovery_playlist_failure(test_db_session):
    """Test that playlist-level failure marks playlist as DISCOVERY_FAILED."""
    provider = FakeProvider([])
    provider.playlist_error = RuntimeError("Playlist is private or does not exist.")
    service = DiscoveryService(provider=provider)

    with pytest.raises(DiscoveryError):
        service.discover(test_db_session, "https://www.youtube.com/playlist?list=PLtest1234567890")

    playlist = test_db_session.scalars(
        select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
    ).first()
    assert playlist is not None
    assert playlist.status == "DISCOVERY_FAILED"
    assert "Playlist is private or does not exist." in playlist.discovery_error
