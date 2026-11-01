"""Integration and unit tests for automatic pipeline chaining in IngestionWorker.

Tests the full transition:
TranscriptService -> Job Scheduling -> Worker Dispatch -> ChunkingService -> IndexingService
"""

from unittest.mock import MagicMock, patch

import pytest
from lectra_core.config import Settings
from lectra_core.db.models import (
    Job,
    Playlist,
    ProcessingStage,
    TranscriptSegment,
    Video,
    VideoChunk,
)
from lectra_core.db.session import get_db, get_engine, init_db
from lectra_core.vectorstore.service import IndexingResult
from lectra_core.worker import (
    CHUNK_PLAYLIST_JOB_TYPE,
    CHUNK_VIDEO_JOB_TYPE,
    EXTRACT_TRANSCRIPTS_JOB_TYPE,
    EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE,
    INDEX_PLAYLIST_JOB_TYPE,
    INDEX_VIDEO_JOB_TYPE,
    IngestionWorker,
)
from sqlalchemy import select


@pytest.fixture
def test_worker_env(tmp_path):
    db_file = tmp_path / "test_chaining.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=tmp_path / "artifacts",
        temp_audio_dir=tmp_path / "temp_audio",
        worker_max_retries=2,
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)
    return settings


def test_extract_transcripts_chains_to_chunk_playlist(test_worker_env):
    """When extract_transcripts finishes with TRANSCRIPT_READY videos, chunk_playlist is queued."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_1",
            url="https://www.youtube.com/playlist?list=PL_chain_test_1",
            title="Chain Test 1",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c1",
            title="Video C1",
            url="https://www.youtube.com/watch?v=vid_c1",
            position=0,
            status="DISCOVERED",
        )
        session.add(v1)

        job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(job)
        session.commit()
        pl_id = pl.id

    worker = IngestionWorker(settings=settings)

    # Mock TranscriptService to mark v1 as TRANSCRIPT_READY and commit
    def fake_extract_for_playlist(session, playlist_id):
        video = session.scalars(select(Video).where(Video.playlist_id == playlist_id)).first()
        video.status = "TRANSCRIPT_READY"
        session.commit()
        res = MagicMock()
        res.failed = 0
        res.transcripts_ready = 1
        return res

    with patch("lectra_core.worker.TranscriptService") as MockService:
        instance = MockService.return_value
        instance.extract_for_playlist.side_effect = fake_extract_for_playlist

        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        # Initial job completed
        extract_job = session.scalars(
            select(Job).where(Job.job_type == EXTRACT_TRANSCRIPTS_JOB_TYPE)
        ).first()
        assert extract_job.status == "COMPLETED"

        # Downstream chunking job was enqueued
        chunk_job = session.scalars(
            select(Job).where(Job.job_type == CHUNK_PLAYLIST_JOB_TYPE)
        ).first()
        assert chunk_job is not None
        assert chunk_job.status == "QUEUED"
        assert chunk_job.payload.get("playlist_id") == pl_id


def test_chunk_playlist_chains_to_index_playlist(test_worker_env):
    """When chunk_playlist processes TRANSCRIPT_READY videos, it enqueues index_playlist."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_2",
            url="https://www.youtube.com/playlist?list=PL_chain_test_2",
            title="Chain Test 2",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c2",
            title="Video C2",
            url="https://www.youtube.com/watch?v=vid_c2",
            position=0,
            status="TRANSCRIPT_READY",
        )
        session.add(v1)
        session.flush()

        seg1 = TranscriptSegment(
            video_id=v1.id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=30.0,
            duration_seconds=30.0,
            text="Hello world this is test part one.",
            language="en",
            source="manual",
        )
        seg2 = TranscriptSegment(
            video_id=v1.id,
            segment_index=1,
            start_seconds=30.0,
            end_seconds=70.0,
            duration_seconds=40.0,
            text="And here is part two of the speech.",
            language="en",
            source="manual",
        )
        session.add_all([seg1, seg2])

        chunk_job = Job(
            job_type=CHUNK_PLAYLIST_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(chunk_job)
        session.commit()
        pl_id = pl.id
        v1_id = v1.id

    worker = IngestionWorker(settings=settings)
    exit_code = worker.run_once()
    assert exit_code == 0

    with next(get_db(settings)) as session:
        # Check chunk job completed
        c_job = session.scalars(select(Job).where(Job.job_type == CHUNK_PLAYLIST_JOB_TYPE)).first()
        assert c_job.status == "COMPLETED"

        # Check video was chunked
        v = session.get(Video, v1_id)
        assert v.status == "CHUNKED"

        # Check chunks were saved in DB
        chunks = session.scalars(select(VideoChunk).where(VideoChunk.video_id == v1_id)).all()
        assert len(chunks) > 0

        # Check downstream index job was enqueued
        index_job = session.scalars(
            select(Job).where(Job.job_type == INDEX_PLAYLIST_JOB_TYPE)
        ).first()
        assert index_job is not None
        assert index_job.status == "QUEUED"
        assert index_job.payload.get("playlist_id") == pl_id


def test_video_level_chaining_extract_chunk_index(test_worker_env):
    """Test individual video job chaining: extract -> chunk -> index."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_3",
            url="https://www.youtube.com/playlist?list=PL_chain_test_3",
            title="Chain Test 3",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c3",
            title="Video C3",
            url="https://www.youtube.com/watch?v=vid_c3",
            position=0,
            status="DISCOVERED",
        )
        session.add(v1)
        session.flush()
        v1_id = v1.id

        job = Job(
            job_type=EXTRACT_VIDEO_TRANSCRIPT_JOB_TYPE,
            status="QUEUED",
            payload={"video_id": v1.id, "youtube_id": v1.youtube_id},
        )
        session.add(job)
        session.commit()

    worker = IngestionWorker(settings=settings)

    # Step 1: Run extract_video_transcript (mocked to create segments and mark TRANSCRIPT_READY)
    def fake_process_video(session, video):
        video.status = "TRANSCRIPT_READY"
        seg = TranscriptSegment(
            video_id=video.id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=40.0,
            duration_seconds=40.0,
            text="Single video test transcript.",
            language="en",
            source="manual",
        )
        session.add(seg)
        session.commit()
        summary = MagicMock()
        summary.status = "TRANSCRIPT_READY"
        return summary

    with patch("lectra_core.worker.TranscriptService") as MockService:
        instance = MockService.return_value
        instance.process_video.side_effect = fake_process_video
        exit_code = worker.run_once()
        assert exit_code == 0

    with next(get_db(settings)) as session:
        chunk_v_job = session.scalars(
            select(Job).where(Job.job_type == CHUNK_VIDEO_JOB_TYPE)
        ).first()
        assert chunk_v_job is not None
        assert chunk_v_job.status == "QUEUED"

    # Step 2: Run chunk_video
    exit_code = worker.run_once()
    assert exit_code == 0

    with next(get_db(settings)) as session:
        v = session.get(Video, v1_id)
        assert v.status == "CHUNKED"

        index_v_job = session.scalars(
            select(Job).where(Job.job_type == INDEX_VIDEO_JOB_TYPE)
        ).first()
        assert index_v_job is not None
        assert index_v_job.status == "QUEUED"


def test_chaining_does_not_duplicate_existing_active_jobs(test_worker_env):
    """If a downstream job is already active, duplicate jobs must not be created."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_4",
            url="https://www.youtube.com/playlist?list=PL_chain_test_4",
            title="Chain Test 4",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c4",
            title="Video C4",
            url="https://www.youtube.com/watch?v=vid_c4",
            position=0,
            status="TRANSCRIPT_READY",
        )
        session.add(v1)

        # Already an existing active chunk_playlist job
        existing_chunk_job = Job(
            job_type=CHUNK_PLAYLIST_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(existing_chunk_job)

        extract_job = Job(
            job_type=EXTRACT_TRANSCRIPTS_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(extract_job)
        session.flush()
        extract_job_id = extract_job.id
        session.commit()

    worker = IngestionWorker(settings=settings)

    with patch("lectra_core.worker.TranscriptService") as MockService:
        instance = MockService.return_value
        res = MagicMock()
        res.failed = 0
        instance.extract_for_playlist.return_value = res

        with next(get_db(settings)) as session:
            job = session.get(Job, extract_job_id)
            job.status = "RUNNING"
            session.commit()
            worker.process_job(session, job)

    with next(get_db(settings)) as session:
        chunk_jobs = session.scalars(
            select(Job).where(Job.job_type == CHUNK_PLAYLIST_JOB_TYPE)
        ).all()
        # Exactly 1, no duplicate created
        assert len(chunk_jobs) == 1


def test_failed_video_during_chunking_does_not_abort_playlist(test_worker_env):
    """If one video raises an error during chunking, others still proceed and index is queued."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_5",
            url="https://www.youtube.com/playlist?list=PL_chain_test_5",
            title="Chain Test 5",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_bad",
            title="Bad Video",
            url="https://www.youtube.com/watch?v=vid_bad",
            position=0,
            status="TRANSCRIPT_READY",
        )
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_good",
            title="Good Video",
            url="https://www.youtube.com/watch?v=vid_good",
            position=1,
            status="TRANSCRIPT_READY",
        )
        session.add_all([v1, v2])
        session.flush()

        seg = TranscriptSegment(
            video_id=v2.id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=50.0,
            duration_seconds=50.0,
            text="Good video segments here.",
            language="en",
            source="manual",
        )
        session.add(seg)

        chunk_job = Job(
            job_type=CHUNK_PLAYLIST_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(chunk_job)
        session.commit()
        v1_id = v1.id
        v2_id = v2.id

    worker = IngestionWorker(settings=settings)

    from lectra_core.chunking.service import ChunkingService
    original_chunk_video = ChunkingService.chunk_video

    def buggy_chunk_video(self, session, video):
        if video.id == v1_id:
            raise RuntimeError("Corrupted audio sync error")
        return original_chunk_video(self, session, video)

    with patch.object(ChunkingService, "chunk_video", buggy_chunk_video):
        exit_code = worker.run_once()
        # chunk_playlist records 1 error so exit_code reflects failure/retry
        assert exit_code == 1

    with next(get_db(settings)) as session:
        # v2 should still have been successfully chunked!
        v2 = session.get(Video, v2_id)
        assert v2.status == "CHUNKED"

        # Downstream index_playlist job should still have been enqueued for v2!
        index_job = session.scalars(
            select(Job).where(Job.job_type == INDEX_PLAYLIST_JOB_TYPE)
        ).first()
        assert index_job is not None
        assert index_job.status == "QUEUED"

        # v1 stage should be marked FAILED
        stage = session.scalars(
            select(ProcessingStage).where(
                ProcessingStage.video_id == v1_id,
                ProcessingStage.stage_name == "CHUNKING"
            )
        ).first()
        assert stage is not None
        assert stage.status == "FAILED"
        assert "Corrupted audio sync error" in stage.error_detail


def test_deleted_video_is_safely_skipped_in_chain(test_worker_env):
    """If a video is deleted before chunking or indexing, the worker skips it safely."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_6",
            url="https://www.youtube.com/playlist?list=PL_chain_test_6",
            title="Chain Test 6",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c6",
            title="Video C6",
            url="https://www.youtube.com/watch?v=vid_c6",
            position=0,
            status="TRANSCRIPT_READY",
        )
        session.add(v1)
        session.flush()

        # Enqueue chunk_video for a non-existent / deleted video ID
        job = Job(
            job_type=CHUNK_VIDEO_JOB_TYPE,
            status="QUEUED",
            payload={"video_id": "non_existent_uuid", "youtube_id": "deleted_vid"},
        )
        session.add(job)
        session.commit()

    worker = IngestionWorker(settings=settings)
    exit_code = worker.run_once()
    assert exit_code == 0

    with next(get_db(settings)) as session:
        j = session.scalars(select(Job).where(Job.job_type == CHUNK_VIDEO_JOB_TYPE)).first()
        assert j.status == "COMPLETED"


def test_re_running_chunk_playlist_is_idempotent(test_worker_env):
    """Re-running chunk_playlist on already chunked videos produces no duplicates."""
    settings = test_worker_env

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_chain_test_7",
            url="https://www.youtube.com/playlist?list=PL_chain_test_7",
            title="Chain Test 7",
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_c7",
            title="Video C7",
            url="https://www.youtube.com/watch?v=vid_c7",
            position=0,
            status="TRANSCRIPT_READY",
        )
        session.add(v1)
        session.flush()

        seg = TranscriptSegment(
            video_id=v1.id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=40.0,
            duration_seconds=40.0,
            text="Idempotency test speech text.",
            language="en",
            source="manual",
        )
        session.add(seg)

        job1 = Job(
            job_type=CHUNK_PLAYLIST_JOB_TYPE,
            status="QUEUED",
            payload={"playlist_id": pl.id, "youtube_id": pl.youtube_id},
        )
        session.add(job1)
        session.commit()
        v1_id = v1.id
        pl_id = pl.id

    worker = IngestionWorker(settings=settings)

    with patch("lectra_core.vectorstore.service.IndexingService.index_video") as mock_index:
        mock_index.return_value = IndexingResult(
            video_id=v1_id,
            youtube_id="vid_c7",
            chunks_indexed=1,
            status="COMPLETED",
            verified_points=1,
        )

        # First run: chunks the video and enqueues index_playlist
        exit_code1 = worker.run_once()
        assert exit_code1 == 0

        with next(get_db(settings)) as session:
            chunks_1 = session.scalars(select(VideoChunk).where(VideoChunk.video_id == v1_id)).all()
            count_1 = len(chunks_1)
            assert count_1 > 0

            # Now enqueue another chunk_playlist job to verify re-running does not duplicate
            job2 = Job(
                job_type=CHUNK_PLAYLIST_JOB_TYPE,
                status="QUEUED",
                payload={"playlist_id": pl_id, "youtube_id": "PL_chain_test_7"},
            )
            session.add(job2)
            session.commit()

        # Run index_playlist (enqueued by first job)
        exit_code_idx = worker.run_once()
        assert exit_code_idx == 0

        # Run second chunk_playlist job: does not re-chunk or duplicate chunks
        exit_code2 = worker.run_once()
        assert exit_code2 == 0

        with next(get_db(settings)) as session:
            chunks_2 = session.scalars(select(VideoChunk).where(VideoChunk.video_id == v1_id)).all()
            assert len(chunks_2) == count_1
