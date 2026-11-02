"""Tests for student SQLite seed database generation and integrity (Phase 4).

Verifies that data/knowledge_base/student_revision_rag.db:
1. Contains all required tables, constraints, and indexes.
2. Preserves exact playlist and video UUIDs for Strivers A2Z and LangChain.
3. Successfully passes foreign-key and database integrity checks.
4. Excludes the ~70 MB raw transcript segments table.
5. Successfully serves all FastAPI USER-mode playlist and health endpoints.
"""

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from lectra_backend.main import create_app
from lectra_core.config import Settings

STUDENT_DB_PATH = Path("data/knowledge_base/student_revision_rag.db")
DEVELOPER_DB_PATH = Path("data/revision_rag.db")

STRIVER_PLAYLIST_ID = "3820e00b-81b6-4f34-9e68-011ddc3d9f98"
LANGCHAIN_PLAYLIST_ID = "0fd210e4-904f-4127-b539-130cb1497377"


def test_student_database_exists_and_is_compact():
    """Verify student database artifact exists and is significantly smaller than developer DB."""
    assert STUDENT_DB_PATH.exists(), f"Student DB missing at {STUDENT_DB_PATH}"
    student_size = STUDENT_DB_PATH.stat().st_size
    dev_size = DEVELOPER_DB_PATH.stat().st_size

    # Must be between 5 MB and 15 MB (around 11 MB), >80% smaller than 81.5 MB dev DB
    assert 5 * 1024 * 1024 < student_size < 15 * 1024 * 1024
    assert student_size < dev_size * 0.2


def test_student_database_integrity_and_foreign_keys():
    """Verify database passes SQLite integrity and foreign key checks without error."""
    conn = sqlite3.connect(STUDENT_DB_PATH)
    cur = conn.cursor()

    integrity_res = cur.execute("PRAGMA integrity_check;").fetchall()
    assert integrity_res == [("ok",)], f"Integrity check failed: {integrity_res}"

    fk_errors = cur.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_errors == [], f"Foreign key errors: {fk_errors}"
    conn.close()


def test_student_database_schema_and_tables():
    """Verify all 7 expected application tables exist."""
    conn = sqlite3.connect(STUDENT_DB_PATH)
    cur = conn.cursor()

    tables = sorted([
        r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        ).fetchall()
    ])
    expected_tables = [
        "alembic_version",
        "jobs",
        "playlists",
        "processing_stages",
        "transcript_segments",
        "video_chunks",
        "videos",
    ]
    assert tables == expected_tables

    # Check transcript_segments is empty (excluded to save ~70 MB)
    seg_count = cur.execute("SELECT count(*) FROM transcript_segments;").fetchone()[0]
    assert seg_count == 0, f"Expected 0 transcript segments, got {seg_count}"

    # Check video_chunks has 7,000 chunks
    chunk_count = cur.execute("SELECT count(*) FROM video_chunks;").fetchone()[0]
    assert chunk_count == 7000, f"Expected 7000 video chunks, got {chunk_count}"

    conn.close()


def test_student_database_records_match_developer_db():
    """Verify playlist and video records match original developer database 100%."""
    dev_conn = sqlite3.connect(DEVELOPER_DB_PATH)
    student_conn = sqlite3.connect(STUDENT_DB_PATH)

    # 1. Playlists
    dev_pls = dict(dev_conn.execute("SELECT id, title FROM playlists;").fetchall())
    student_pls = dict(student_conn.execute("SELECT id, title FROM playlists;").fetchall())
    assert set(student_pls.keys()) == {STRIVER_PLAYLIST_ID, LANGCHAIN_PLAYLIST_ID}
    assert student_pls == dev_pls

    # 2. Videos count and IDs
    dev_vids = set(r[0] for r in dev_conn.execute("SELECT id FROM videos;").fetchall())
    student_vids = set(r[0] for r in student_conn.execute("SELECT id FROM videos;").fetchall())
    assert student_vids == dev_vids
    assert len(student_vids) == 335

    # 3. Check individual playlist video breakdown
    striver_vids = student_conn.execute(
        "SELECT count(*) FROM videos WHERE playlist_id = ?", (STRIVER_PLAYLIST_ID,)
    ).fetchone()[0]
    assert striver_vids == 315

    langchain_vids = student_conn.execute(
        "SELECT count(*) FROM videos WHERE playlist_id = ?", (LANGCHAIN_PLAYLIST_ID,)
    ).fetchone()[0]
    assert langchain_vids == 20

    dev_conn.close()
    student_conn.close()


def test_fastapi_endpoints_with_student_database():
    """Verify FastAPI backend serves all USER-mode playlist endpoints with student DB."""
    settings = Settings(
        app_mode="USER",
        sqlite_path=STUDENT_DB_PATH,
        database_url=f"sqlite:///{STUDENT_DB_PATH}",
        retrieval_api_url=None,
    )
    app = create_app(settings=settings)
    client = TestClient(app)

    # 1. Health
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["database"] == "connected"

    # 2. List playlists
    res_pls = client.get("/api/v1/playlists")
    assert res_pls.status_code == 200
    pls = res_pls.json()
    assert len(pls) == 2
    pl_ids = {p["id"] for p in pls}
    assert pl_ids == {STRIVER_PLAYLIST_ID, LANGCHAIN_PLAYLIST_ID}

    # Verify thumbnails and completed counts
    for p in pls:
        assert p["completed_count"] > 0
        assert p["thumbnail_url"].startswith("https://i.ytimg.com/vi/")

    # 3. Individual playlist endpoints
    for pid in [STRIVER_PLAYLIST_ID, LANGCHAIN_PLAYLIST_ID]:
        res_single = client.get(f"/api/v1/playlists/{pid}")
        assert res_single.status_code == 200
        assert res_single.json()["id"] == pid

        res_status = client.get(f"/api/v1/playlists/{pid}/status")
        assert res_status.status_code == 200
        st = res_status.json()
        assert st["total_chunks"] in (6011, 989)
        assert st["status"] == "DISCOVERY_COMPLETED"

        res_vids = client.get(f"/api/v1/playlists/{pid}/videos")
        assert res_vids.status_code == 200
        vids = res_vids.json()
        assert len(vids) in (315, 20)
        assert all(v["playlist_id"] == pid for v in vids)

    # 4. Ingestion blocked with 403 in USER mode
    res_sub = client.post(
        "/api/v1/playlists",
        json={"url": "https://www.youtube.com/playlist?list=PLgUwDviBIf0oF6QL8m22w1hIDC1vJ_BHz"},
    )
    assert res_sub.status_code == 403
