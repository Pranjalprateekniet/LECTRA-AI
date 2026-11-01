"""Comprehensive tests for Video Deletion API and worker race safety."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from lectra_backend.main import app
from lectra_core.config import Settings
from lectra_core.db.models import (
    Job,
    Playlist,
    ProcessingStage,
    TranscriptSegment,
    Video,
    VideoChunk,
)
from lectra_core.db.session import get_engine, init_db
from lectra_core.worker import IngestionWorker
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture
def delete_test_env(tmp_path):
    """Set up temporary database and artifacts for video deletion tests."""
    db_file = tmp_path / "test_delete.db"
    artifacts_dir = tmp_path / "artifacts"
    transcripts_dir = artifacts_dir / "transcripts"
    temp_audio_dir = tmp_path / "temp_audio"

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    temp_audio_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        artifacts_dir=artifacts_dir,
        temp_audio_dir=temp_audio_dir,
        model_cache_dir=tmp_path / "models",
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    with Session(engine) as session:
        pl = Playlist(
            id="pl_del_test",
            youtube_id="PL_DELETE_TEST",
            url="https://www.youtube.com/playlist?list=PL_DELETE_TEST",
            title="Delete Test Playlist",
            video_count=2,
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            id="vid_to_delete",
            playlist_id=pl.id,
            youtube_id="YT_DEL_123",
            title="Video To Delete",
            url="https://www.youtube.com/watch?v=YT_DEL_123",
            position=0,
            status="INDEXED",
        )
        v2 = Video(
            id="vid_to_keep",
            playlist_id=pl.id,
            youtube_id="YT_KEEP_456",
            title="Video To Keep",
            url="https://www.youtube.com/watch?v=YT_KEEP_456",
            position=1,
            status="INDEXED",
        )
        session.add_all([v1, v2])
        session.flush()

        # Add processing stages
        stage1 = ProcessingStage(
            video_id=v1.id,
            stage_name="TRANSCRIPT_ACQUISITION",
            status="COMPLETED",
        )
        stage2 = ProcessingStage(
            video_id=v1.id,
            stage_name="CHUNKING",
            status="COMPLETED",
        )
        stage3 = ProcessingStage(
            video_id=v1.id,
            stage_name="INDEXING",
            status="COMPLETED",
        )
        session.add_all([stage1, stage2, stage3])

        # Add transcript segments
        seg = TranscriptSegment(
            video_id=v1.id,
            segment_index=0,
            start_seconds=0.0,
            end_seconds=10.0,
            duration_seconds=10.0,
            text="Delete me text",
            language="en",
            source="generated",
        )
        session.add(seg)

        # Add chunks
        chunk = VideoChunk(
            id="chunk_del_1",
            video_id=v1.id,
            chunk_index=0,
            start_seconds=0.0,
            end_seconds=75.0,
            duration_seconds=75.0,
            text="Delete me chunk",
            token_count=10,
            source_segment_start_index=0,
            source_segment_end_index=0,
        )
        session.add(chunk)

        # Add active/queued background job
        job = Job(
            job_type="index_video",
            status="QUEUED",
            payload={"video_id": v1.id, "youtube_id": v1.youtube_id},
        )
        session.add(job)

        session.commit()

        # Create dummy artifact files
        raw_artifact = transcripts_dir / f"{v1.youtube_id}_raw.json"
        raw_artifact.write_text('{"dummy": "data"}', encoding="utf-8")

        temp_audio = temp_audio_dir / f"{v1.youtube_id}.m4a"
        temp_audio.write_bytes(b"dummy audio")

        yield session, settings, engine


def test_delete_video_api_success(delete_test_env):
    """Test DELETE /api/v1/playlists/{playlist_id}/videos/{video_id} completely removes records."""
    session, settings, engine = delete_test_env
    from lectra_backend.dependencies import get_db_session

    app.dependency_overrides[get_db_session] = lambda: session
    client = TestClient(app)

    try:
        with (
            patch("lectra_core.config.get_settings", return_value=settings),
            patch(
                "lectra_core.vectorstore.qdrant.QdrantVectorStore.delete_points_by_video_id"
            ) as mock_del_qdrant,
        ):
            res = client.delete("/api/v1/playlists/pl_del_test/videos/vid_to_delete")

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["video_id"] == "vid_to_delete"
        assert data["playlist_id"] == "pl_del_test"

        # 1. Qdrant deletion was called
        mock_del_qdrant.assert_called_once_with("vid_to_delete")

        # 2. Database records deleted (cascading)
        assert session.get(Video, "vid_to_delete") is None
        stages = session.scalars(
            select(ProcessingStage).where(ProcessingStage.video_id == "vid_to_delete")
        ).all()
        assert len(stages) == 0
        segs = session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.video_id == "vid_to_delete")
        ).all()
        assert len(segs) == 0
        chunks = session.scalars(
            select(VideoChunk).where(VideoChunk.video_id == "vid_to_delete")
        ).all()
        assert len(chunks) == 0

        # 3. Remaining video is preserved
        assert session.get(Video, "vid_to_keep") is not None

        # 4. Playlist count was updated to 1
        pl = session.get(Playlist, "pl_del_test")
        assert pl.video_count == 1

        # 5. Background jobs cancelled
        jobs = session.scalars(select(Job)).all()
        cancelled = [j for j in jobs if (j.payload or {}).get("video_id") == "vid_to_delete"]
        assert len(cancelled) == 1
        assert cancelled[0].status == "CANCELLED"

        # 6. Artifact files removed
        raw_artifact = settings.artifacts_dir / "transcripts" / "YT_DEL_123_raw.json"
        assert not raw_artifact.exists()
        temp_audio = settings.temp_audio_dir / "YT_DEL_123.m4a"
        assert not temp_audio.exists()
    finally:
        app.dependency_overrides.clear()


def test_delete_video_not_found(delete_test_env):
    """Verify 404 is returned when video or playlist is missing."""
    session, settings, engine = delete_test_env
    from lectra_backend.dependencies import get_db_session

    app.dependency_overrides[get_db_session] = lambda: session
    client = TestClient(app)

    try:
        with patch("lectra_core.config.get_settings", return_value=settings):
            res = client.delete("/api/v1/playlists/pl_del_test/videos/non_existent_vid")
            assert res.status_code == 404

            res2 = client.delete("/api/v1/playlists/non_existent_pl/videos/vid_to_delete")
            assert res2.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_worker_race_safety_on_deleted_video(delete_test_env):
    """Verify worker handles a video that is deleted before or during job execution."""
    session, settings, engine = delete_test_env

    # Clear any previous queued jobs
    for j in session.scalars(select(Job)).all():
        session.delete(j)
    session.commit()

    # Enqueue a chunk_video job for a non-existent/deleted video
    job = Job(
        job_type="chunk_video",
        status="QUEUED",
        payload={"video_id": "already_deleted_vid"},
    )
    session.add(job)
    session.commit()
    job_id = job.id

    def fake_get_db(s=None):
        yield session

    with patch("lectra_core.worker.get_db", side_effect=fake_get_db):
        worker = IngestionWorker(settings=settings)
        # Should not raise exception or crash
        exit_code = worker.run_once()
        assert exit_code == 0

    job_rec = session.get(Job, job_id)
    assert job_rec.status == "COMPLETED"
