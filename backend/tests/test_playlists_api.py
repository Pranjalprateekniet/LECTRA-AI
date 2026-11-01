"""Tests for FastAPI playlists and jobs endpoints."""

import pytest
from fastapi.testclient import TestClient
from lectra_backend.main import create_app
from lectra_core.config import Settings
from lectra_core.db.models import Job, Playlist, Video
from lectra_core.db.session import get_db, get_engine, init_db


@pytest.fixture
def client(tmp_path):
    """TestClient fixture with isolated SQLite database."""
    db_file = tmp_path / "test_api.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file}",
        data_dir=tmp_path,
        environment="testing",
    )
    engine = get_engine(settings)
    init_db(engine=engine, settings=settings)

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        yield test_client, settings


def test_submit_playlist_invalid_url(client):
    tc, _ = client
    # Invalid scheme
    res1 = tc.post("/api/v1/playlists", json={"url": "not-a-youtube-url"})
    assert res1.status_code == 400
    assert "must start with http:// or https://" in res1.json()["detail"]

    # Non-YouTube domain
    res2 = tc.post(
        "/api/v1/playlists",
        json={"url": "https://vimeo.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"},
    )
    assert res2.status_code == 400
    assert "Not a YouTube URL" in res2.json()["detail"]


def test_submit_playlist_valid_enqueues_job(client):
    tc, settings = client
    url = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    response = tc.post("/api/v1/playlists", json={"url": url})
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert "playlist_id" in data
    assert data["youtube_id"] == "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    assert data["status"] == "DISCOVERY_QUEUED"

    # Verify job created in DB
    with next(get_db(settings)) as session:
        job = session.get(Job, data["job_id"])
        assert job is not None
        assert job.status == "QUEUED"
        assert job.job_type == "discover_playlist"


def test_submit_duplicate_playlist_returns_existing_job(client):
    tc, _ = client
    url = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
    res1 = tc.post("/api/v1/playlists", json={"url": url})
    assert res1.status_code == 202
    job_id_1 = res1.json()["job_id"]

    # Submit again while job is QUEUED
    res2 = tc.post("/api/v1/playlists", json={"url": url})
    assert res2.status_code == 202
    assert res2.json()["job_id"] == job_id_1
    assert "already queued" in res2.json()["message"]


def test_get_playlists_and_details(client):
    tc, settings = client
    # Seed a playlist and videos
    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PLtest1234567890",
            url="https://www.youtube.com/playlist?list=PLtest1234567890",
            title="Seeded Playlist",
            channel_name="Seeded Channel",
            video_count=2,
            status="DISCOVERY_COMPLETED",
        )
        session.add(pl)
        session.flush()

        v1 = Video(
            playlist_id=pl.id,
            youtube_id="vid_1",
            title="Video One",
            url="https://www.youtube.com/watch?v=vid_1",
            duration_seconds=300.0,
            position=0,
            status="DISCOVERED",
            availability="public",
        )
        v2 = Video(
            playlist_id=pl.id,
            youtube_id="vid_2",
            title="Video Two",
            url="https://www.youtube.com/watch?v=vid_2",
            duration_seconds=400.0,
            position=1,
            status="SKIPPED_UNAVAILABLE",
            availability="PRIVATE",
            discovery_error="Private video",
        )
        session.add_all([v1, v2])
        session.commit()
        pl_id = pl.id

    # Test list playlists
    list_res = tc.get("/api/v1/playlists")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["title"] == "Seeded Playlist"

    # Test get by DB UUID
    detail_res = tc.get(f"/api/v1/playlists/{pl_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["title"] == "Seeded Playlist"

    # Test get by YouTube ID
    yt_detail_res = tc.get("/api/v1/playlists/PLtest1234567890")
    assert yt_detail_res.status_code == 200
    assert yt_detail_res.json()["id"] == pl_id

    # Test get status
    status_res = tc.get(f"/api/v1/playlists/{pl_id}/status")
    assert status_res.status_code == 200
    s_data = status_res.json()
    assert s_data["status"] == "DISCOVERY_COMPLETED"
    assert s_data["video_count"] == 2
    assert s_data["discovered_count"] == 1
    assert s_data["unavailable_count"] == 1

    # Test get videos
    videos_res = tc.get(f"/api/v1/playlists/{pl_id}/videos")
    assert videos_res.status_code == 200
    v_data = videos_res.json()
    assert len(v_data) == 2
    assert v_data[0]["position"] == 0
    assert v_data[0]["youtube_id"] == "vid_1"
    assert v_data[1]["position"] == 1
    assert v_data[1]["status"] == "SKIPPED_UNAVAILABLE"


def test_get_job_status(client):
    tc, settings = client
    with next(get_db(settings)) as session:
        job = Job(
            job_type="discover_playlist",
            status="RUNNING",
            attempts=1,
            payload={"playlist_url": "https://www.youtube.com/playlist?list=PLtest"},
        )
        session.add(job)
        session.commit()
        job_id = job.id

    res = tc.get(f"/api/v1/jobs/{job_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == job_id
    assert data["status"] == "RUNNING"
    assert data["attempts"] == 1


def test_get_nonexistent_playlist_and_job(client):
    tc, _ = client
    assert tc.get("/api/v1/playlists/does-not-exist").status_code == 404
    assert tc.get("/api/v1/jobs/does-not-exist").status_code == 404


def test_playlist_activity_and_video_details(client):
    tc, settings = client
    from lectra_core.db.models import ProcessingStage, VideoChunk

    with next(get_db(settings)) as session:
        pl = Playlist(
            youtube_id="PL_act_test",
            url="https://www.youtube.com/playlist?list=PL_act_test",
            title="Activity Test Playlist",
            status="DISCOVERY_COMPLETED",
            video_count=1,
        )
        session.add(pl)
        session.flush()

        v = Video(
            playlist_id=pl.id,
            youtube_id="vid_act_1",
            title="Video 1",
            url="https://www.youtube.com/watch?v=vid_act_1",
            status="INDEXED",
            position=0,
        )
        session.add(v)
        session.flush()

        stage = ProcessingStage(
            video_id=v.id,
            stage_name="TRANSCRIPT_ACQUISITION",
            status="COMPLETED",
            attempts=1,
        )
        session.add(stage)

        chunk = VideoChunk(
            id="chk_act_1",
            video_id=v.id,
            chunk_index=0,
            start_seconds=0.0,
            end_seconds=10.0,
            duration_seconds=10.0,
            text="Test chunk",
            token_count=5,
            source_segment_start_index=0,
            source_segment_end_index=0,
        )
        session.add(chunk)
        session.commit()
        pl_id = pl.id
        vid_id = v.id

    # 1. Activity log check
    act_res = tc.get(f"/api/v1/playlists/{pl_id}/activity")
    assert act_res.status_code == 200
    events = act_res.json()
    assert len(events) >= 2  # creation + stage
    assert any("TRANSCRIPT_ACQUISITION" in e["stage"] for e in events)

    # 2. Video details check
    vid_res = tc.get(f"/api/v1/playlists/{pl_id}/videos")
    assert vid_res.status_code == 200
    v_data = vid_res.json()
    assert len(v_data) == 1
    assert v_data[0]["chunks_count"] == 1
    assert v_data[0]["indexed_vectors_count"] == 1
    assert len(v_data[0]["stages"]) == 1
    assert v_data[0]["stages"][0]["stage_name"] == "TRANSCRIPT_ACQUISITION"

    # 3. Retry playlist check
    retry_pl_res = tc.post(f"/api/v1/playlists/{pl_id}/retry")
    assert retry_pl_res.status_code == 200
    assert retry_pl_res.json()["success"] is True

    # 4. Retry video check
    retry_v_res = tc.post(f"/api/v1/playlists/videos/{vid_id}/retry")
    assert retry_v_res.status_code == 200
    assert retry_v_res.json()["success"] is True
