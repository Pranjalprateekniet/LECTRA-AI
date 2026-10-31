"""Independently runnable background ingestion worker."""

import argparse
import signal
import sys
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from lectra_core.config import Settings, get_settings
from lectra_core.db.models import Job, Video
from lectra_core.db.session import get_db, init_db
from lectra_core.discovery.service import DiscoveryError, DiscoveryService
from lectra_core.discovery.ytdlp_client import YtDlpProvider
from lectra_core.logging import get_logger, setup_logging
from lectra_core.transcript.service import TranscriptService

logger = get_logger("lectra.worker")

DISCOVER_JOB_TYPE = "discover_playlist"
EXTRACT_TRANSCRIPTS_JOB_TYPE = "extract_transcripts"
EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE = "extract_video_transcript"
CHUNK_VIDEO_JOB_TYPE = "chunk_video"
CHUNK_PLAYLIST_JOB_TYPE = "chunk_playlist"


class IngestionWorker:
    """Worker process that polls SQLite for queued jobs and executes them."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.running = False

    def check_health(self) -> bool:
        """Verify database connectivity and directory accessibility."""
        try:
            self.settings.ensure_directories()
            with next(get_db(self.settings)) as session:
                session.execute(select(1))
            return True
        except Exception as e:
            logger.error("Worker health check failed", extra={"error": str(e)})
            return False

    def recover_stale_jobs(self, session: Session) -> int:
        """Requeue jobs left RUNNING by a prior worker crash.

        Discovery and transcript extraction are idempotent: re-running
        reconciles with already persisted SQLite state and artifacts.
        Returns the number of requeued jobs.
        """
        stale = session.scalars(select(Job).where(Job.status == "RUNNING")).all()
        for job in stale:
            job.status = "QUEUED"
            if job.job_type == DISCOVER_JOB_TYPE and job.payload:
                p_url = job.payload.get("playlist_url")
                if p_url:
                    try:
                        from lectra_core.discovery.url_validation import validate_playlist_url
                        from lectra_core.repositories import playlist_repository

                        p_info = validate_playlist_url(p_url)
                        playlist = playlist_repository.get_by_youtube_id(session, p_info.youtube_id)
                        if playlist and playlist.status == "DISCOVERY_RUNNING":
                            playlist.status = "DISCOVERY_QUEUED"
                    except Exception:
                        pass
            elif job.job_type == EXTRACT_TRANSCRIPTS_JOB_TYPE and job.payload:
                logger.warning(
                    "Requeued stale transcript extraction job",
                    extra={"job_id": job.id, "playlist_id": job.payload.get("playlist_id")},
                )
            logger.warning(
                "Requeued stale RUNNING job from a previous worker run",
                extra={"job_id": job.id, "job_type": job.job_type, "attempts": job.attempts},
            )
        if stale:
            session.commit()
        return len(stale)

    def claim_next_job(self, session: Session) -> Optional[Job]:
        """Atomically claim the next queued job."""
        stmt = (
            select(Job)
            .where(Job.status == "QUEUED")
            .order_by(Job.created_at.asc())
            .limit(1)
            .with_for_update()
        )
        job = session.scalars(stmt).first()
        if job:
            job.status = "RUNNING"
            job.attempts += 1
            session.commit()
            session.refresh(job)
            logger.info(
                "Claimed job",
                extra={"job_id": job.id, "job_type": job.job_type, "attempt": job.attempts},
            )
        return job

    def process_job(self, session: Session, job: Job) -> None:
        """Process a claimed job."""
        logger.info(
            "Processing job",
            extra={"job_id": job.id, "job_type": job.job_type},
        )
        if job.job_type == DISCOVER_JOB_TYPE:
            self._process_discover_job(session, job)
        elif job.job_type == EXTRACT_TRANSCRIPTS_JOB_TYPE:
            self._process_extract_transcripts_job(session, job)
        elif job.job_type == EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE:
            self._process_extract_video_transcript_job(session, job)
        elif job.job_type == CHUNK_VIDEO_JOB_TYPE:
            self._process_chunk_video_job(session, job)
        elif job.job_type == CHUNK_PLAYLIST_JOB_TYPE:
            self._process_chunk_playlist_job(session, job)
        elif job.job_type == "test_job":
            pass
        else:
            logger.warning(
                "Unknown job type left untouched; marking job as failed",
                extra={"job_id": job.id, "job_type": job.job_type},
            )
            job.status = "FAILED"
            job.error_summary = f"Unknown job type: {job.job_type}"
            session.commit()
            return
        job.status = "COMPLETED"
        session.commit()
        logger.info("Job completed successfully", extra={"job_id": job.id})

    def _process_discover_job(self, session: Session, job: Job) -> None:
        url = (job.payload or {}).get("playlist_url")
        if not url:
            raise DiscoveryError("Job payload is missing 'playlist_url'.")
        provider = YtDlpProvider(
            options={"socket_timeout": self.settings.discovery_socket_timeout_seconds}
        )
        result = DiscoveryService(provider=provider).discover(session, url)

        # Enqueue downstream transcript extraction job if not already active
        active_jobs = session.scalars(
            select(Job).where(
                Job.job_type == EXTRACT_TRANSCRIPTS_JOB_TYPE,
                Job.status.in_(["QUEUED", "RUNNING"]),
            )
        ).all()
        already_active = any(
            (j.payload or {}).get("playlist_id") == result.playlist_db_id for j in active_jobs
        )
        if not already_active:
            transcript_job = Job(
                job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
                status="QUEUED",
                max_retries=self.settings.worker_max_retries,
                payload={
                    "playlist_id": result.playlist_db_id,
                    "youtube_id": result.youtube_id,
                },
            )
            session.add(transcript_job)
            session.commit()
            logger.info(
                "Enqueued downstream transcript extraction job",
                extra={"job_id": transcript_job.id, "playlist_id": result.playlist_db_id},
            )

    def _process_extract_transcripts_job(self, session: Session, job: Job) -> None:
        payload = job.payload or {}
        playlist_id = payload.get("playlist_id")
        if not playlist_id:
            youtube_id = payload.get("youtube_id")
            if youtube_id:
                from lectra_core.repositories import playlist_repository

                pl = playlist_repository.get_by_youtube_id(session, youtube_id)
                if pl:
                    playlist_id = pl.id
        if not playlist_id:
            raise ValueError("Job payload is missing 'playlist_id'.")

        service = TranscriptService(settings=self.settings)
        result = service.extract_for_playlist(session, playlist_id)

        if result.failed > 0:
            raise RuntimeError(f"{result.failed} video(s) failed transcript extraction")

    def _process_extract_video_transcript_job(self, session: Session, job: Job) -> None:
        payload = job.payload or {}
        video_id = payload.get("video_id")
        if not video_id:
            raise ValueError("Job payload is missing 'video_id'.")
        video = session.get(Video, video_id)
        if not video:
            raise ValueError(f"Video '{video_id}' not found.")

        service = TranscriptService(settings=self.settings)
        summary = service.process_video(session, video)
        if summary.status == "EXTRACTION_FAILED":
            raise RuntimeError(f"Video transcript extraction failed: {summary.error_detail}")

    def _process_chunk_video_job(self, session: Session, job: Job) -> None:
        payload = job.payload or {}
        video_id = payload.get("video_id")
        if not video_id:
            raise ValueError("Job payload is missing 'video_id'.")
        video = session.get(Video, video_id)
        if not video:
            raise ValueError(f"Video '{video_id}' not found.")

        from lectra_core.chunking.service import ChunkingService

        service = ChunkingService(settings=self.settings)
        service.chunk_video(session, video)

    def _process_chunk_playlist_job(self, session: Session, job: Job) -> None:
        payload = job.payload or {}
        playlist_id = payload.get("playlist_id")
        if not playlist_id:
            raise ValueError("Job payload is missing 'playlist_id'.")

        from lectra_core.chunking.service import ChunkingService

        service = ChunkingService(settings=self.settings)
        videos = session.scalars(
            select(Video).where(
                Video.playlist_id == playlist_id,
                Video.status == "TRANSCRIPT_READY",
            )
        ).all()
        for v in videos:
            service.chunk_video(session, v)
            session.commit()

    def _handle_job_failure(self, session: Session, job: Job, exc: Exception) -> None:
        """Handle a failed job: retry if attempts < max_retries, else fail."""
        err_msg = str(exc)
        logger.error(
            "Job processing failed",
            extra={
                "job_id": job.id,
                "job_type": job.job_type,
                "attempt": job.attempts,
                "max_retries": job.max_retries,
                "error": err_msg,
            },
        )
        if job.attempts < job.max_retries:
            job.status = "QUEUED"
            job.error_summary = f"Attempt {job.attempts} failed: {err_msg[:400]}"
            logger.info("Job requeued for retry", extra={"job_id": job.id, "attempt": job.attempts})
        else:
            job.status = "FAILED"
            job.error_summary = err_msg[:500]
            logger.error("Job permanently marked FAILED", extra={"job_id": job.id})
        session.commit()

    def run_once(self) -> int:
        """Poll and execute one available job if present, then exit."""
        if not self.check_health():
            return 1

        with next(get_db(self.settings)) as session:
            self.recover_stale_jobs(session)

        with next(get_db(self.settings)) as session:
            job = self.claim_next_job(session)
            if job:
                try:
                    self.process_job(session, job)
                except Exception as e:
                    self._handle_job_failure(session, job, e)
                    return 1
        return 0

    def start(self) -> None:
        """Start the worker polling loop."""
        setup_logging(self.settings)
        logger.info(
            "Starting Lectra Worker",
            extra={
                "environment": self.settings.environment,
                "poll_interval": self.settings.worker_poll_interval_seconds,
                "concurrency": self.settings.worker_concurrency,
            },
        )

        init_db(settings=self.settings)

        if not self.check_health():
            logger.critical("Worker failed initial health check. Aborting startup.")
            sys.exit(1)

        with next(get_db(self.settings)) as session:
            recovered = self.recover_stale_jobs(session)
            if recovered:
                logger.info(
                    "Recovered jobs from a previous worker run",
                    extra={"requeued_jobs": recovered},
                )

        self.running = True

        def _handle_exit(sig, frame):
            logger.info("Termination signal received. Shutting down worker gracefully...")
            self.running = False

        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

        logger.info("Worker is ready and waiting for jobs.")
        try:
            while self.running:
                try:
                    with next(get_db(self.settings)) as session:
                        job = self.claim_next_job(session)
                        if job:
                            try:
                                self.process_job(session, job)
                            except Exception as e:
                                self._handle_job_failure(session, job, e)
                except Exception as e:
                    logger.error("Unexpected error in worker loop", extra={"error": str(e)})

                time.sleep(self.settings.worker_poll_interval_seconds)
        finally:
            from lectra_core.transcript.whisper_transcriber import WhisperModelManager

            WhisperModelManager.get_instance().unload_model()
            logger.info("Lectra Worker stopped.")


def main() -> None:
    """CLI entrypoint for standalone worker."""
    parser = argparse.ArgumentParser(description="Lectra Ingestion Worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()

    worker = IngestionWorker()
    if args.once:
        setup_logging(worker.settings)
        init_db(settings=worker.settings)
        exit_code = worker.run_once()
        sys.exit(exit_code)
    else:
        worker.start()


if __name__ == "__main__":
    main()
