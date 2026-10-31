"""Unit tests for IngestionWorker discovery job execution and recovery."""

from unittest.mock import patch

from lectra_core.config import Settings
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.worker import DISCOVER_JOB_TYPE, IngestionWorker
from sqlalchemy import select

from .mock_provider import FakeProvider, make_entry


def test_worker_executes_discover_job(tmp_path):
    """Test that IngestionWorker claims and processes a discover_playlist job."""
    db_file = tmp_path / "worker_disc.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    # Queue a discovery job
    with next(get_db(settings)) as session:
        job = Job(
            job_type=DISCOVER_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_url": "https://www.youtube.com/playlist?list=PLtest1234567890"},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    entries = [
        make_entry(0, "vid_01", "Video 1", 200.0),
        make_entry(1, "vid_02", "Video 2", 300.0),
    ]
    fake_provider = FakeProvider(entries, title="Worker Test Playlist")

    with patch("lectra_core.worker.YtDlpProvider", return_value=fake_provider):
        worker = IngestionWorker(settings=settings)
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        completed_job = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert completed_job is not None
        assert completed_job.status == "COMPLETED"

        playlist = session.scalars(
            select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
        ).first()
        assert playlist is not None
        assert playlist.status == "DISCOVERY_COMPLETED"
        assert playlist.title == "Worker Test Playlist"

        videos = session.scalars(select(Video).where(Video.playlist_id == playlist.id)).all()
        assert len(videos) == 2


def test_worker_recovers_stale_discovery_job(tmp_path):
    """Test that worker recovers a crashed/stale RUNNING discovery job and re-runs it."""
    db_file = tmp_path / "worker_recover.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    # Insert a stale RUNNING job and a playlist left in DISCOVERY_RUNNING
    with next(get_db(settings)) as session:
        playlist = Playlist(
            youtube_id="PLtest1234567890",
            url="https://www.youtube.com/playlist?list=PLtest1234567890",
            title="Interrupted Playlist",
            status="DISCOVERY_RUNNING",
        )
        session.add(playlist)
        session.flush()

        job = Job(
            job_type=DISCOVER_JOB_TYPE,
            status="RUNNING",
            attempts=1,
            payload={"playlist_url": "https://www.youtube.com/playlist?list=PLtest1234567890"},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    entries = [make_entry(0, "rec_vid_1", "Recovered Vid", 400.0)]
    fake_provider = FakeProvider(entries, title="Interrupted Playlist")

    with patch("lectra_core.worker.YtDlpProvider", return_value=fake_provider):
        worker = IngestionWorker(settings=settings)
        # First check recovery
        with next(get_db(settings)) as session:
            count = worker.recover_stale_jobs(session)
            assert count == 1

        with next(get_db(settings)) as session:
            requeued_job = session.scalars(select(Job).where(Job.id == job_id)).first()
            assert requeued_job.status == "QUEUED"

            recovered_pl = session.scalars(
                select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
            ).first()
            assert recovered_pl.status == "DISCOVERY_QUEUED"

        # Now run worker to finish the recovered job
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        finished_job = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert finished_job.status == "COMPLETED"

        finished_pl = session.scalars(
            select(Playlist).where(Playlist.youtube_id == "PLtest1234567890")
        ).first()
        assert finished_pl.status == "DISCOVERY_COMPLETED"
