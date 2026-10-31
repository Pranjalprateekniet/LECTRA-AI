"""Real yt-dlp integration test using the specified test playlist.

Playlist: https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ
Channel: take U forward
Title: Greedy Algorithms
Number of videos: 5
"""

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.discovery.service import DiscoveryService
from lectra_core.discovery.ytdlp_client import YtDlpProvider
from lectra_core.worker import DISCOVER_JOB_TYPE, IngestionWorker
from sqlalchemy import select

TEST_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
EXPECTED_YOUTUBE_ID = "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
EXPECTED_VIDEO_IDS = [
    "II6ziNnub1Q",
    "dxVcMDI7vyI",
    "LjPx4wQaRIs",
    "F_DDzYnxO14",
    "mVg9CfJvayM",
]


@pytest.fixture
def test_env(tmp_path):
    """Isolated environment fixture for real playlist integration."""
    db_file = tmp_path / "integration_test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        discovery_socket_timeout_seconds=15,
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)
    return settings


@pytest.mark.integration
def test_real_playlist_discovery_and_idempotency(test_env):
    """Verify discovery with real yt-dlp provider against the supplied test playlist."""
    settings = test_env
    provider = YtDlpProvider(options={"socket_timeout": 15})
    service = DiscoveryService(provider=provider)

    # 1. First run discovery
    with next(get_db(settings)) as session:
        result = service.discover(session, TEST_PLAYLIST_URL)

    # Verify DiscoveryResult
    assert result.youtube_id == EXPECTED_YOUTUBE_ID
    assert result.title == "Greedy Algorithms"
    assert result.entries_seen == 5
    assert result.distinct_videos == 5
    assert result.discovered == 5
    assert result.unavailable == 0
    assert result.duplicate_entries == 0

    # Verify SQLite Persistence
    with next(get_db(settings)) as session:
        playlist = session.scalars(
            select(Playlist).where(Playlist.youtube_id == EXPECTED_YOUTUBE_ID)
        ).first()
        assert playlist is not None
        assert playlist.title == "Greedy Algorithms"
        assert playlist.channel_name == "take U forward"
        assert playlist.video_count == 5
        assert playlist.status == "DISCOVERY_COMPLETED"
        assert playlist.discovery_error is None

        videos = session.scalars(
            select(Video).where(Video.playlist_id == playlist.id).order_by(Video.position.asc())
        ).all()
        assert len(videos) == 5

        # Verify IDs, ordering, durations and statuses
        for i, (video, expected_id) in enumerate(zip(videos, EXPECTED_VIDEO_IDS)):
            assert video.youtube_id == expected_id
            assert video.position == i
            assert video.status == "DISCOVERED"
            assert video.availability == "public"
            assert video.duration_seconds is not None and video.duration_seconds > 0
            assert len(video.title) > 0

    # 2. Repeated Submission (Idempotency)
    with next(get_db(settings)) as session:
        res2 = service.discover(session, TEST_PLAYLIST_URL)

    assert res2.distinct_videos == 5
    assert res2.discovered == 0  # Reconciled without creating duplicates
    assert res2.duplicate_entries == 0

    with next(get_db(settings)) as session:
        all_playlists = session.scalars(select(Playlist)).all()
        assert len(all_playlists) == 1
        all_videos = session.scalars(select(Video)).all()
        assert len(all_videos) == 5


@pytest.mark.integration
def test_real_playlist_worker_execution(test_env):
    """Verify that IngestionWorker processes the real playlist job from queue."""
    settings = test_env

    # Queue job
    with next(get_db(settings)) as session:
        job = Job(
            job_type=DISCOVER_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_url": TEST_PLAYLIST_URL},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    worker = IngestionWorker(settings=settings)
    exit_code = worker.run_once()
    assert exit_code == 0

    with next(get_db(settings)) as session:
        job = session.get(Job, job_id)
        assert job.status == "COMPLETED"
        assert job.attempts == 1

        playlist = session.scalars(
            select(Playlist).where(Playlist.youtube_id == EXPECTED_YOUTUBE_ID)
        ).first()
        assert playlist is not None
        assert playlist.status == "DISCOVERY_COMPLETED"
        assert playlist.video_count == 5
