#!/usr/bin/env python3
"""Revision RAG — Unified Student Setup & Application Runner.

Provides a single-command cross-platform entry point for students:
1. Validates required distribution assets.
2. Auto-initializes local SQLite database from seed if missing.
3. Auto-imports local persistent Qdrant database if missing.
4. Verifies database integrity, point counts, and playlists.
5. Validates user environment configuration (GROQ_API_KEY).
6. Performs non-destructive port conflict checks.
7. Supervises FastAPI backend and Next.js frontend with live logs.
8. Provides graceful Ctrl+C shutdown without orphaned processes.
"""

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent

# Distribution asset paths
DATA_DIR = PROJECT_ROOT / "data"
KB_DIR = DATA_DIR / "knowledge_base"
STUDENT_SEED_DB = KB_DIR / "student_revision_rag.db"
ARCHIVE_FILE = KB_DIR / "chunks_7000.jsonl.gz"
MANIFEST_FILE = KB_DIR / "manifest.json"

# Local runtime asset paths
RUNTIME_SQLITE_DB = DATA_DIR / "revision_rag.db"
RUNTIME_QDRANT_DIR = DATA_DIR / "qdrant"
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

# Expected entity identities
EXPECTED_PLAYLIST_IDS = {
    "3820e00b-81b6-4f34-9e68-011ddc3d9f98": "Strivers A2Z-DSA Course",
    "0fd210e4-904f-4127-b539-130cb1497377": "Generative AI using LangChain",
}
EXPECTED_QDRANT_POINTS = 7000
EXPECTED_TOTAL_POINTS = 7000
EXPECTED_COLLECTION = "revision_chunks"


# --------------------------------------------------------------------------
# Console UI helpers
# --------------------------------------------------------------------------


def log_step(msg: str) -> None:
    print(f"\033[1;34m[SETUP]\033[0m {msg}")


def log_success(msg: str) -> None:
    print(f"\033[1;32m[SUCCESS]\033[0m {msg}")


def log_warn(msg: str) -> None:
    print(f"\033[1;33m[WARNING]\033[0m {msg}", file=sys.stderr)


def log_err(msg: str) -> None:
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr)


# --------------------------------------------------------------------------
# Preflight Verification & Auto-Initialization
# --------------------------------------------------------------------------


def check_python_version() -> None:
    """Enforce that Revision RAG runs exclusively under Python 3.12.x."""
    major = sys.version_info[0]
    minor = sys.version_info[1]
    micro = sys.version_info[2]
    if major != 3 or minor != 12:
        log_err(
            f"Unsupported Python version: {major}.{minor}.{micro}.\n"
            f"Revision RAG is strictly locked to Python 3.12.x (received {major}.{minor}.{micro}).\n"
            f"Current interpreter: {sys.executable}\n\n"
            f"Please run Revision RAG using a Python 3.12 virtual environment:\n"
            f"  - Windows:       py -3.12 -m venv .venv && .venv\\Scripts\\activate\n"
            f"  - Linux/macOS:   python3.12 -m venv .venv && source .venv/bin/activate\n"
        )
        sys.exit(1)


def check_distribution_assets() -> None:
    """Ensure all required prebuilt distribution assets exist."""
    required = [
        (STUDENT_SEED_DB, "Student seed database"),
        (ARCHIVE_FILE, "Knowledge base vector archive (chunks_7000.jsonl.gz)"),
        (MANIFEST_FILE, "Knowledge base manifest (manifest.json)"),
    ]
    missing = []
    for path, desc in required:
        if not path.exists():
            missing.append(f"  - {desc} at {path}")

    if missing:
        log_err("Required distribution assets are missing from the repository:")
        for item in missing:
            print(item, file=sys.stderr)
        log_err("Please verify your git clone or restore assets from the repository.")
        sys.exit(1)


def load_env_vars() -> Dict[str, str]:
    """Load key-value pairs from .env if present."""
    env: Dict[str, str] = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip().strip("'\"")
    return env


def validate_environment_config(env_vars: Dict[str, str]) -> None:
    """Validate student environment variables, particularly GROQ_API_KEY."""
    if not ENV_FILE.exists():
        log_warn(f".env file not found at {ENV_FILE}")
        if ENV_EXAMPLE.exists():
            log_step("Creating .env from .env.example...")
            shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
            log_success("Created .env file. Please edit it to add your GROQ_API_KEY.")
        else:
            log_err(f"Neither .env nor .env.example found. Please create {ENV_FILE}.")
            sys.exit(1)

    # Re-read env after potential copy
    active_env = load_env_vars()
    groq_key = os.environ.get("GROQ_API_KEY") or active_env.get("GROQ_API_KEY")

    if not groq_key or groq_key in ("your_groq_api_key_here", "your_groq_api_key"):
        log_err("GROQ_API_KEY is not configured in .env.")
        print("\nRevision RAG uses Groq exclusively for local grounded answer generation.")
        print("1. Obtain a free API key at: https://console.groq.com/keys")
        print("2. Set your key in .env:")
        print("   GROQ_API_KEY=gsk_your_actual_groq_key\n")
        sys.exit(1)


def initialize_sqlite_if_needed(target_db: Path = RUNTIME_SQLITE_DB) -> None:
    """Copy prebuilt student database if runtime database is missing."""
    if not target_db.exists():
        log_step(f"Runtime database {target_db.name} not found. Initializing from student seed...")
        target_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(STUDENT_SEED_DB, target_db)
        log_success(f"Initialized {target_db.name} from {STUDENT_SEED_DB.name}")
    else:
        # Validate existing database has expected playlists
        conn = sqlite3.connect(target_db)
        try:
            cur = conn.cursor()
            rows = cur.execute("SELECT id, title FROM playlists;").fetchall()
            found_ids = {r[0] for r in rows}
            missing_ids = set(EXPECTED_PLAYLIST_IDS.keys()) - found_ids
            if missing_ids:
                log_err(f"Existing database at {target_db} is incomplete (missing playlists: {missing_ids}).")
                print("To restore the clean prebuilt database, run:")
                print(f"  rm {target_db} && python run.py")
                sys.exit(1)
        except Exception as exc:
            log_err(f"Existing database at {target_db} is invalid or corrupted: {exc}")
            print(f"To restore the clean prebuilt database, delete {target_db} and re-run run.py.")
            sys.exit(1)
        finally:
            conn.close()


def initialize_qdrant_if_needed(target_dir: Path = RUNTIME_QDRANT_DIR) -> None:
    """Import local Qdrant collection from packaged archive if missing."""
    needs_import = False

    if not target_dir.exists():
        needs_import = True
    else:
        # Check if collection exists and has points
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(path=str(target_dir))
            try:
                if not client.collection_exists(EXPECTED_COLLECTION):
                    needs_import = True
                else:
                    info = client.get_collection(EXPECTED_COLLECTION)
                    if info.points_count != EXPECTED_TOTAL_POINTS:
                        log_err(
                            f"Local Qdrant collection '{EXPECTED_COLLECTION}' has {info.points_count} points "
                            f"(expected {EXPECTED_TOTAL_POINTS})."
                        )
                        print("To re-import the complete knowledge base, run:")
                        print("  python scripts/load_knowledge_base.py --force")
                        sys.exit(1)
            finally:
                client.close()
        except SystemExit:
            raise
        except Exception as exc:
            log_warn(f"Could not inspect local Qdrant database: {exc}")
            needs_import = True

    if needs_import:
        log_step("Initializing local persistent Qdrant database from packaged knowledge base archive...")
        importer_script = PROJECT_ROOT / "scripts" / "load_knowledge_base.py"
        if not importer_script.exists():
            log_err(f"Importer script not found at {importer_script}")
            sys.exit(1)

        cmd = [
            sys.executable,
            str(importer_script),
            "--archive",
            str(ARCHIVE_FILE),
            "--manifest",
            str(MANIFEST_FILE),
            "--destination",
            str(target_dir),
            "--force",
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            log_err("Failed to import knowledge base into local Qdrant.")
            sys.exit(1)
        log_success("Local Qdrant database initialized successfully (7,000 vectors).")


def check_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is currently listening or bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def verify_ports_available(backend_port: int, frontend_port: int) -> None:
    """Ensure ports 8000 and 3000 are not occupied before launching."""
    conflicts = []
    if check_port_in_use(backend_port):
        conflicts.append(
            f"Backend port {backend_port} is already in use by another process.\n"
            f"  -> Please stop the process using port {backend_port} or run with --backend-port <port>."
        )
    if check_port_in_use(frontend_port):
        conflicts.append(
            f"Frontend port {frontend_port} is already in use by another process.\n"
            f"  -> Please stop the process using port {frontend_port} or run with --frontend-port <port>."
        )

    if conflicts:
        log_err("Port conflict detected:")
        for msg in conflicts:
            print(f"  {msg}", file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------
# Process Execution & Stream Piping
# --------------------------------------------------------------------------


def stream_process_output(pipe, prefix: str, color_code: str) -> None:
    """Read lines from process stdout/stderr and print with prefix."""
    try:
        for line in iter(pipe.readline, ""):
            if line:
                clean_line = line.rstrip("\r\n")
                print(f"{color_code}[{prefix}]\033[0m {clean_line}")
    except (ValueError, OSError):
        pass


def terminate_processes(processes: List[subprocess.Popen]) -> None:
    """Cross-platform graceful process termination."""
    for proc in processes:
        if proc.poll() is None:
            try:
                if sys.platform == "win32":
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGINT)
            except Exception:
                pass

    # Wait up to 4 seconds for clean exit
    start_time = time.time()
    for proc in processes:
        while proc.poll() is None and time.time() - start_time < 4.0:
            time.sleep(0.1)

    # Force kill any stubborn processes
    for proc in processes:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


def run_services(
    backend_port: int = 8000,
    frontend_port: int = 3000,
) -> None:
    """Launch and supervise FastAPI backend and Next.js frontend."""
    frontend_dir = PROJECT_ROOT / "frontend"
    node_modules = frontend_dir / "node_modules"

    if not node_modules.exists():
        log_warn("Frontend dependencies (node_modules) are not installed.")
        print("Installing frontend packages via npm ci...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        npm_res = subprocess.run([npm_cmd, "ci"], cwd=str(frontend_dir))
        if npm_res.returncode != 0:
            log_err("npm ci failed in frontend/ directory.")
            print("Please run manually: npm ci --prefix frontend")
            sys.exit(1)

    npm_bin = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or "npm"

    # Start Backend
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "lectra_backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(backend_port),
    ]

    # Start Frontend
    frontend_cmd = [
        npm_bin,
        "run",
        "dev",
        "--",
        "-p",
        str(frontend_port),
    ]

    print("=" * 65)
    print("  Revision RAG — Local Revision Assistant")
    print("=" * 65)
    print(f"  Backend:  http://127.0.0.1:{backend_port}  (FastAPI + Local Qdrant)")
    print(f"  Frontend: http://localhost:{frontend_port}  (Next.js UI)")
    print("=" * 65)
    print("Press Ctrl+C to stop all services.\n")

    env_vars = load_env_vars()
    env_copy = os.environ.copy()
    env_copy["PYTHONUNBUFFERED"] = "1"
    env_copy["APP_MODE"] = os.environ.get("APP_MODE") or env_vars.get("APP_MODE") or "USER"
    env_copy["NEXT_PUBLIC_API_URL"] = f"http://127.0.0.1:{backend_port}"

    processes: List[subprocess.Popen] = []

    try:
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(PROJECT_ROOT),
            env=env_copy,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append(backend_proc)

        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=str(frontend_dir),
            env=env_copy,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append(frontend_proc)

        # Start output reading threads
        t_be = threading.Thread(
            target=stream_process_output,
            args=(backend_proc.stdout, "backend", "\033[36m"),
            daemon=True,
        )
        t_fe = threading.Thread(
            target=stream_process_output,
            args=(frontend_proc.stdout, "frontend", "\033[35m"),
            daemon=True,
        )
        t_be.start()
        t_fe.start()

        # Supervision loop
        while True:
            time.sleep(0.5)
            if backend_proc.poll() is not None:
                log_err(f"Backend process exited unexpectedly (code {backend_proc.returncode}).")
                break
            if frontend_proc.poll() is not None:
                log_err(f"Frontend process exited unexpectedly (code {frontend_proc.returncode}).")
                break

    except KeyboardInterrupt:
        print("\n")
        log_step("Shutting down Revision RAG services...")

    finally:
        terminate_processes(processes)
        log_success("All services stopped cleanly.")


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------


def main() -> None:
    # Step 0: Enforce Python 3.12.x version lock before any application operations
    check_python_version()

    parser = argparse.ArgumentParser(
        description="Unified local-first runner for Revision RAG."
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=8000,
        help="Port for FastAPI backend (default: 8000)",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=3000,
        help="Port for Next.js frontend (default: 3000)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Perform asset, database, and configuration preflight checks without launching servers",
    )

    args = parser.parse_args()

    # Step 1: Validate packaged repository assets
    check_distribution_assets()

    # Step 2: Auto-initialize SQLite database if absent
    initialize_sqlite_if_needed()

    # Step 3: Auto-initialize Qdrant collection if absent
    initialize_qdrant_if_needed()

    # Step 4: Validate environment configuration (GROQ_API_KEY)
    env_vars = load_env_vars()
    validate_environment_config(env_vars)

    if args.check_only:
        log_success("Preflight checks passed: Distribution assets, SQLite DB, Qdrant DB, and configuration verified.")
        sys.exit(0)

    # Step 5: Verify ports are available
    verify_ports_available(args.backend_port, args.frontend_port)

    # Step 6: Launch and supervise processes
    run_services(backend_port=args.backend_port, frontend_port=args.frontend_port)


if __name__ == "__main__":
    main()

