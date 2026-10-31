"""Unit tests for standalone worker."""

from lectra_core.config import Settings
from lectra_core.db.models import Job
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.worker import IngestionWorker
from sqlalchemy import select


def test_worker_health_check(tmp_path):
    """Verify worker health check succeeds when database is available."""
    db_file = tmp_path / "worker_health.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    worker = IngestionWorker(settings=settings)
    assert worker.check_health() is True


def test_worker_run_once(tmp_path):
    """Verify worker --once claims and completes a queued job."""
    db_file = tmp_path / "worker_run.db"
    settings = Settings(database_url=f"sqlite:///{db_file}", data_dir=tmp_path)
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    # Insert a queued job
    with next(get_db(settings)) as session:
        job = Job(job_type="test_job", status="QUEUED")
        session.add(job)
        session.commit()
        job_id = job.id

    worker = IngestionWorker(settings=settings)
    exit_code = worker.run_once()
    assert exit_code == 0

    # Verify job completed
    with next(get_db(settings)) as session:
        completed_job = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert completed_job is not None
        assert completed_job.status == "COMPLETED"
        assert completed_job.attempts == 1
