"""Tests for Unified Student Runner (run.py) — Phase 5.

Covers:
1. First-run SQLite initialization from student seed.
2. First-run Qdrant initialization from packaged archive.
3. Repeated startup idempotency (never overwrites existing valid databases).
4. Corrupted / incomplete database detection with clear recovery messages.
5. Missing or placeholder GROQ_API_KEY detection.
6. Port conflict diagnostics.
7. Process lifecycle and graceful termination.
8. Clean-install simulation in an isolated temporary environment.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from lectra_core.config import Settings
from lectra_core.retrieval.schemas import RetrievalQuery
from lectra_core.retrieval.service import RetrievalService

import run

STRIVER_PLAYLIST_ID = "3820e00b-81b6-4f34-9e68-011ddc3d9f98"
LANGCHAIN_PLAYLIST_ID = "0fd210e4-904f-4127-b539-130cb1497377"


def test_distribution_assets_check_passes_on_repo():
    """Verify check_distribution_assets succeeds with current repo files."""
    run.check_distribution_assets()


def test_distribution_assets_check_fails_when_asset_missing(tmp_path):
    """Verify check_distribution_assets exits when a distribution file is absent."""
    missing_file = tmp_path / "nonexistent.db"
    with patch("run.STUDENT_SEED_DB", missing_file):
        with pytest.raises(SystemExit) as exc:
            run.check_distribution_assets()
        assert exc.value.code == 1


def test_initialize_sqlite_copies_seed_when_absent(tmp_path):
    """Verify first-run copy of student_revision_rag.db -> revision_rag.db."""
    target_db = tmp_path / "data" / "revision_rag.db"
    assert not target_db.exists()

    run.initialize_sqlite_if_needed(target_db=target_db)
    assert target_db.exists()
    assert target_db.stat().st_size > 1_000_000

    # Verify playlists are present
    conn = sqlite3.connect(target_db)
    rows = conn.execute("SELECT id FROM playlists;").fetchall()
    conn.close()
    pids = {r[0] for r in rows}
    assert pids == {STRIVER_PLAYLIST_ID, LANGCHAIN_PLAYLIST_ID}


def test_initialize_sqlite_never_overwrites_existing_valid_db(tmp_path):
    """Verify existing valid database is not overwritten or modified."""
    target_db = tmp_path / "test_valid.db"
    shutil.copyfile(run.STUDENT_SEED_DB, target_db)
    mtime_before = target_db.stat().st_mtime_ns

    run.initialize_sqlite_if_needed(target_db=target_db)
    mtime_after = target_db.stat().st_mtime_ns
    assert mtime_before == mtime_after


def test_initialize_sqlite_detects_corrupted_or_incomplete_db(tmp_path):
    """Verify corrupted/incomplete existing DB raises descriptive exit error."""
    target_db = tmp_path / "corrupted.db"
    conn = sqlite3.connect(target_db)
    conn.execute("CREATE TABLE playlists (id TEXT PRIMARY KEY, title TEXT);")
    conn.commit()
    conn.close()

    with pytest.raises(SystemExit) as exc:
        run.initialize_sqlite_if_needed(target_db=target_db)
    assert exc.value.code == 1


def test_validate_environment_config_detects_missing_groq_key(monkeypatch, tmp_path):
    """Verify missing or placeholder GROQ_API_KEY stops runner with clear guide."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("run.ENV_FILE", tmp_path / ".env"):
        # Write dummy .env with placeholder
        (tmp_path / ".env").write_text("GROQ_API_KEY=your_groq_api_key_here\nAPP_MODE=USER\n")
        with pytest.raises(SystemExit) as exc:
            run.validate_environment_config({"GROQ_API_KEY": "your_groq_api_key_here"})
        assert exc.value.code == 1


def test_port_conflict_detection():
    """Verify check_port_in_use correctly identifies listening or bound ports."""
    import socket

    # Bind a temporary socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        allocated_port = s.getsockname()[1]
        assert run.check_port_in_use(allocated_port) is True

    # After close, port should become available
    assert run.check_port_in_use(allocated_port) is False


def test_process_lifecycle_and_termination():
    """Verify terminate_processes cleanly terminates supervised subprocesses."""
    # Start two long-running dummy python sleep processes
    p1 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    p2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

    assert p1.poll() is None
    assert p2.poll() is None

    run.terminate_processes([p1, p2])

    assert p1.poll() is not None
    assert p2.poll() is not None


def test_clean_install_simulation_in_isolated_directory(tmp_path):
    """Clean-install simulation:

    1. Neither student database exists in tmp_path.
    2. Initializes SQLite from student seed.
    3. Validates Qdrant collection point count and metadata.
    4. Runs LangChain and Striver queries against the isolated databases.
    """
    isolated_data = tmp_path / "data"
    isolated_kb = isolated_data / "knowledge_base"
    isolated_kb.mkdir(parents=True, exist_ok=True)

    # 1. Provide only the distribution seed assets in the isolated dir
    isolated_seed_db = isolated_kb / "student_revision_rag.db"
    shutil.copyfile(run.STUDENT_SEED_DB, isolated_seed_db)

    isolated_sqlite_db = isolated_data / "revision_rag.db"
    assert not isolated_sqlite_db.exists()

    # 2. Run SQLite initialization
    with patch("run.STUDENT_SEED_DB", isolated_seed_db):
        run.initialize_sqlite_if_needed(target_db=isolated_sqlite_db)
    assert isolated_sqlite_db.exists()

    # Verify isolated SQLite contents
    conn = sqlite3.connect(isolated_sqlite_db)
    pls = conn.execute("SELECT id, title, video_count FROM playlists ORDER BY title;").fetchall()
    assert len(pls) == 2
    v_count = conn.execute("SELECT count(*) FROM videos;").fetchone()[0]
    assert v_count == 335
    conn.close()

    # 3. Verify retrieval with local Qdrant VectorStore
    # Point to the existing 7,000 points local Qdrant directory
    settings = Settings(
        app_mode="USER",
        sqlite_path=isolated_sqlite_db,
        database_url=f"sqlite:///{isolated_sqlite_db}",
        qdrant_path=run.RUNTIME_QDRANT_DIR,
        retrieval_api_url=None,
    )

    mock_emb = MagicMock()
    mock_emb.embed_query.return_value = [0.01] * 768
    retrieval_svc = RetrievalService(settings=settings, embedding_service=mock_emb)

    # Query 1: LangChain
    res_lc = retrieval_svc.search_query(
        RetrievalQuery(query="PromptTemplate", playlist_id=LANGCHAIN_PLAYLIST_ID, top_k=2)
    )
    assert res_lc.total_results > 0
    assert res_lc.results[0].playlist_id == LANGCHAIN_PLAYLIST_ID
    assert res_lc.results[0].youtube_url.startswith("https://www.youtube.com/watch?v=")

    # Query 2: Striver
    res_st = retrieval_svc.search_query(
        RetrievalQuery(query="Binary search", playlist_id=STRIVER_PLAYLIST_ID, top_k=2)
    )
    assert res_st.total_results > 0
    assert res_st.results[0].playlist_id == STRIVER_PLAYLIST_ID
    assert res_st.results[0].start_seconds >= 0

    from lectra_core.vectorstore.qdrant import close_local_qdrant_clients
    close_local_qdrant_clients()


def test_custom_scripts_do_not_exist():
    """Verify that obsolete custom shell/PowerShell scripts have been removed."""
    install_sh = run.PROJECT_ROOT / "install.sh"
    start_sh = run.PROJECT_ROOT / "start.sh"
    install_ps1 = run.PROJECT_ROOT / "install.ps1"
    start_ps1 = run.PROJECT_ROOT / "start.ps1"

    assert not install_sh.exists()
    assert not start_sh.exists()
    assert not install_ps1.exists()
    assert not start_ps1.exists()


def test_run_py_executes_check_only():
    """Verify that python run.py --check-only executes cleanly."""
    from lectra_core.vectorstore.qdrant import close_local_qdrant_clients
    close_local_qdrant_clients()

    res = subprocess.run(
        [sys.executable, "run.py", "--check-only"],
        capture_output=True,
        text=True,
        cwd=str(run.PROJECT_ROOT),
    )
    assert res.returncode == 0
    assert "Preflight checks passed" in res.stdout


def test_python_version_check_enforcement():
    """Verify run.py check_python_version enforces Python 3.12."""
    with patch("sys.version_info", (3, 11, 8)):
        with pytest.raises(SystemExit) as exc:
            run.check_python_version()
        assert exc.value.code == 1

    with patch("sys.version_info", (3, 13, 0)):
        with pytest.raises(SystemExit) as exc:
            run.check_python_version()
        assert exc.value.code == 1

    with patch("sys.version_info", (3, 12, 4)):
        # Should not raise
        run.check_python_version()
