"""Unit tests for database session and SQLite models."""

from lectra_core.config import Settings
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db
from sqlalchemy import select


def test_init_db_and_job_crud(tmp_path):
    """Verify table creation, job insertion, querying and updating."""
    db_file = tmp_path / "test.db"
    settings = Settings(database_url=f"sqlite:///{db_file}")

    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    with next(get_db(settings)) as session:
        # Create a Job
        job = Job(job_type="discovery", payload={"url": "https://youtube.com/playlist?list=123"})
        session.add(job)
        session.commit()
        job_id = job.id

    with next(get_db(settings)) as session:
        queried = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert queried is not None
        assert queried.status == "QUEUED"
        assert queried.job_type == "discovery"
        assert queried.attempts == 0

        # Update status
        queried.status = "RUNNING"
        queried.attempts += 1
        session.commit()

    with next(get_db(settings)) as session:
        updated = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert updated is not None
        assert updated.status == "RUNNING"
        assert updated.attempts == 1


def test_playlist_and_video_models(tmp_path):
    """Verify playlist and video relationship persistence."""
    db_file = tmp_path / "test_models.db"
    settings = Settings(database_url=f"sqlite:///{db_file}")
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    with next(get_db(settings)) as session:
        playlist = Playlist(
            youtube_id="PL_TEST_1",
            url="https://youtube.com/playlist?list=PL_TEST_1",
            title="Test Playlist",
            video_count=1,
        )
        session.add(playlist)
        session.commit()

        video = Video(
            playlist_id=playlist.id,
            youtube_id="VID_TEST_1",
            title="Test Video 1",
            url="https://youtube.com/watch?v=VID_TEST_1",
            position=1,
        )
        session.add(video)
        session.commit()

    with next(get_db(settings)) as session:
        stmt = select(Playlist).where(Playlist.youtube_id == "PL_TEST_1")
        retrieved_playlist = session.scalars(stmt).first()
        assert retrieved_playlist is not None
        assert len(retrieved_playlist.videos) == 1
        assert retrieved_playlist.videos[0].youtube_id == "VID_TEST_1"
