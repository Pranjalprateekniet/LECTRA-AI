"""Unit tests for IngestionWorker transcript extraction, retry, and recovery."""

from unittest.mock import patch

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.repositories import transcript_repository
from lectra_core.transcript.models import (
    CaptionsUnavailableError,
    NonEnglishAudioError,
    TranscriptExtractionError,
)
from lectra_core.worker import (
    EXTRACT_TRANSCRIPTS_JOB_TYPE,
    IngestionWorker,
)
from sqlalchemy import select

from .mock_extractor import (
    SAMPLE_JSON3_ENGLISH,
    FakeSubtitleExtractor,
    FakeWhisperTranscriber,
)


@pytest.fixture
def worker_env(tmp_path):
    db_file = tmp_path / "worker_transcripts.db"
    artifacts_dir = tmp_path / "artifacts"
    temp_audio_dir = tmp_path / "temp_audio"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=artifacts_dir,
        temp_audio_dir=temp_audio_dir,
        worker_max_retries=2,
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    fake_extractor = FakeSubtitleExtractor()
    fake_transcriber = FakeWhisperTranscriber()
    return settings, fake_extractor, fake_transcriber


def test_worker_executes_extract_transcripts_job(worker_env):
    settings, extractor, transcriber = worker_env

    # Seed playlist and 2 videos
    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_worker_test",
            url="https://www.youtube.com/playlist?list=PL_worker_test",
            title="Worker Transcript Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_w1",
            title="Video 1",
            url="https://www.youtube.com/watch?v=vid_w1",
            position=0,
            status="DISCOVERED",
        )
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_w2",
            title="Video 2",
            url="https://www.youtube.com/watch?v=vid_w2",
            position=1,
            status="DISCOVERED",
        )
        session.add_all([v1, v2])

        # Add extract_transcripts job
        job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="QUEUED",
            max_retries=2,
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    # Configure extractor: v1 has subtitles, v2 has none
    extractor.set_response(
        "https://www.youtube.com/watch?v=vid_w1",
        SAMPLE_JSON3_ENGLISH,
        format_name="json3",
        language="en",
        source="manual",
    )
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_w2",
        CaptionsUnavailableError("Captions disabled"),
    )
    transcriber.set_error(
        "https://www.youtube.com/watch?v=vid_w2",
        NonEnglishAudioError("hi", 0.95),
    )

    with (
        patch("lectra_core.transcript.service.YtDlpSubtitleExtractor", return_value=extractor),
        patch("lectra_core.transcript.service.FasterWhisperTranscriber", return_value=transcriber),
    ):
        worker = IngestionWorker(settings=settings)
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        completed_job = session.scalars(select(Job).where(Job.id == job_id)).first()
        assert completed_job is not None
        assert completed_job.status == "COMPLETED"

        v1 = session.scalars(select(Video).where(Video.youtube_id == "vid_w1")).first()
        assert v1.status == "TRANSCRIPT_READY"
        assert transcript_repository.has_transcripts(session, v1.id) is True

        v2 = session.scalars(select(Video).where(Video.youtube_id == "vid_w2")).first()
        assert v2.status == "NEEDS_TRANSCRIPTION"


def test_worker_retry_behavior_on_transient_failure(worker_env):
    settings, extractor, transcriber = worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_retry_test",
            url="https://www.youtube.com/playlist?list=PL_retry_test",
            title="Retry Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_retry_01",
            title="Retry Video",
            url="https://www.youtube.com/watch?v=vid_retry_01",
            position=0,
            status="DISCOVERED",
        )
        session.add(v1)

        job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="QUEUED",
            max_retries=2,
            attempts=0,
            payload={"playlist_id": pl.id},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    # Configure extractor to fail with transient error
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_retry_01",
        TranscriptExtractionError("Transient network failure"),
    )

    with (
        patch("lectra_core.transcript.service.YtDlpSubtitleExtractor", return_value=extractor),
        patch("lectra_core.transcript.service.FasterWhisperTranscriber", return_value=transcriber),
    ):
        worker = IngestionWorker(settings=settings)

        # Attempt 1: should fail and be requeued (attempts=1 < max_retries=2)
        exit_code = worker.run_once()
        assert exit_code == 1

        with next(get_db(settings)) as session:
            j1 = session.get(Job, job_id)
            assert j1.status == "QUEUED"
            assert j1.attempts == 1
            assert "Attempt 1 failed" in (j1.error_summary or "")

        # Attempt 2: second run (attempts=2 == max_retries=2) -> permanently FAILED
        exit_code_2 = worker.run_once()
        assert exit_code_2 == 1

        with next(get_db(settings)) as session:
            j2 = session.get(Job, job_id)
            assert j2.status == "FAILED"
            assert j2.attempts == 2


def test_worker_recovers_stale_transcript_job_without_duplicates(worker_env):
    settings, extractor, transcriber = worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_crash_test",
            url="https://www.youtube.com/playlist?list=PL_crash_test",
            title="Crash Recovery Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        # v1 already completed before crash
        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c1",
            title="Video 1",
            url="https://www.youtube.com/watch?v=vid_c1",
            position=0,
            status="TRANSCRIPT_READY",
        )
        # v2 was not processed yet when crash occurred
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c2",
            title="Video 2",
            url="https://www.youtube.com/watch?v=vid_c2",
            position=1,
            status="DISCOVERED",
        )
        session.add_all([v1, v2])
        session.flush()

        v1_id = v1.id
        v2_id = v2.id

        # Pre-seed v1 transcript segments
        transcript_repository.save_segments(
            session,
            v1_id,
            [
                transcript_repository.TranscriptSegmentInput(
                    segment_index=0,
                    start_seconds=0.0,
                    end_seconds=3.0,
                    duration_seconds=3.0,
                    text="Pre-existing segment",
                    language="en",
                    source="manual",
                )
            ],
        )

        # Job was left in RUNNING status by worker crash
        stale_job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="RUNNING",
            attempts=1,
            payload={"playlist_id": pl.id},
        )
        session.add(stale_job)
        session.commit()
        job_id = stale_job.id

    # Configure extractor for v2
    extractor.set_response(
        "https://www.youtube.com/watch?v=vid_c2",
        SAMPLE_JSON3_ENGLISH,
        format_name="json3",
        language="en",
        source="manual",
    )

    with (
        patch("lectra_core.transcript.service.YtDlpSubtitleExtractor", return_value=extractor),
        patch("lectra_core.transcript.service.FasterWhisperTranscriber", return_value=transcriber),
    ):
        worker = IngestionWorker(settings=settings)

        # Recovery should requeue the stale job
        with next(get_db(settings)) as session:
            count = worker.recover_stale_jobs(session)
            assert count == 1
            requeued_job = session.get(Job, job_id)
            assert requeued_job.status == "QUEUED"

        # Running worker processes the job
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        done_job = session.get(Job, job_id)
        assert done_job.status == "COMPLETED"

        # Verify v1 was not duplicated and still has 1 segment
        v1_segs = transcript_repository.get_by_video_id(session, v1_id)
        assert len(v1_segs) == 1
        assert v1_segs[0].text == "Pre-existing segment"

        # Verify v2 was successfully extracted
        v2_segs = transcript_repository.get_by_video_id(session, v2_id)
        assert len(v2_segs) == 3


def test_worker_whisper_fallback_succeeds_for_uncaptioned_video(worker_env):
    settings, extractor, transcriber = worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_whisper_worker_test",
            url="https://www.youtube.com/playlist?list=PL_whisper_worker_test",
            title="Whisper Worker Playlist",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_whisper_fallback",
            title="Needs Whisper Video",
            url="https://www.youtube.com/watch?v=vid_whisper_fallback",
            position=0,
            status="DISCOVERED",
        )
        session.add(v1)

        job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="QUEUED",
            max_retries=2,
            payload={"playlist_id": pl.id},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    # Configure extractor to report captions unavailable
    extractor.set_error(
        "https://www.youtube.com/watch?v=vid_whisper_fallback",
        CaptionsUnavailableError("No subtitles available"),
    )
    # Configure transcriber to succeed with default mock Whisper segments

    with (
        patch("lectra_core.transcript.service.YtDlpSubtitleExtractor", return_value=extractor),
        patch("lectra_core.transcript.service.FasterWhisperTranscriber", return_value=transcriber),
    ):
        worker = IngestionWorker(settings=settings)
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        job = session.get(Job, job_id)
        assert job.status == "COMPLETED"

        video = session.scalars(
            select(Video).where(Video.youtube_id == "vid_whisper_fallback")
        ).first()
        assert video.status == "NEEDS_TRANSCRIPTION"
        assert video.discovery_error == "CAPTIONS_UNAVAILABLE"
