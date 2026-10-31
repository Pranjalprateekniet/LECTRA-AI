# Revision RAG (LECTRA)

Revision RAG is an open-source, self-hosted application that turns a YouTube playlist into a searchable revision knowledge base. It ingests video transcripts (preferring existing captions, falling back to audio-only transcription), translates supported non-English content to English while preserving timestamps, chunks and indexes content into Qdrant Cloud vector storage, and answers revision questions with grounded citations and clickable YouTube timestamp links.

Lectra runs directly on the host machine using the project Python virtual environment (`.venv`) and uv for dependency management, plus a local Node.js installation for the frontend. Docker is not required.

This repository is currently at **Phase 2 (YouTube Playlist Discovery)**.

---

## Architecture Overview

Revision RAG is structured as a modular monorepo:

- **`core/` (`lectra-core`)**: The independent core processing module:
  - Centralized Pydantic Settings configuration (`lectra_core.config`).
  - Structured JSON and console logging with automatic secret masking (`lectra_core.logging`).
  - SQLAlchemy models and SQLite connection management with WAL mode (`lectra_core.db`).
  - Alembic database migration environment and version tracking (`core/alembic`).
  - Standalone background ingestion worker (`lectra_core.worker` / CLI `lectra-worker`).
- **`backend/` (`lectra-backend`)**: Lightweight FastAPI service:
  - Health checks (`GET /api/v1/health`) and application endpoints.
  - CORS middleware configured for the local frontend.
  - Startup runner (`lectra-server`).
- **`frontend/`**: Next.js 16 (App Router) interface styled with Tailwind CSS v4:
  - Reverse proxy rewrites routing `/api/*` to the FastAPI backend.
  - Real-time health inspection dashboard.
- **Worker**: Standalone ingestion worker run from `lectra_core.worker`, independently of FastAPI.
- **Vector Database**: **Qdrant Cloud** (free tier cluster) accessed securely over HTTPS.
- **Persistent Storage**: Host directory `./data` (SQLite database, original/translated transcripts, chunk artifacts, and model cache) persists across restarts.

---

## Prerequisites

Ensure the following tools are installed on your host machine:

| Tool | Tested Version | Notes |
| :--- | :--- | :--- |
| **Linux / OS** | Ubuntu / Linux x86_64 | CPU-only default, GPU optional |
| **Python** | 3.12.13 | Project virtual environment at `.venv` |
| **uv** | 0.11+ | Python packaging & dependency management |
| **Node.js** | 22.23+ | Frontend runtime |
| **npm** | 10.9+ | Frontend package manager |
| **FFmpeg & FFprobe** | 7.1+ / git-master | Audio extraction & transcription fallback |

---

## Local Development Quickstart

Lectra runs on the host machine. Each service (backend, worker, frontend) is started independently — no Docker is required.

### 1. Configure Environment Variables

Copy the example environment configuration to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and fill in your Qdrant Cloud cluster URL, Qdrant API key, and Groq API key:

```ini
QDRANT_URL=https://your-cluster-url.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
GROQ_API_KEY=your_groq_api_key
```

> **Security Note:** Provider secrets (`QDRANT_API_KEY`, `GROQ_API_KEY`) are backend-only. The frontend never receives these credentials. Never commit `.env` to version control.

### 2. Install Dependencies

Install backend/core packages into the project virtual environment with uv, and install frontend dependencies:

```bash
make install
```

This uses the existing Python environment at `.venv` and `uv`.

### 3. Run Database Migrations

```bash
make migrate
```

### 4. Run Services Individually

Open one terminal per service:

```bash
# Terminal 1: FastAPI Backend (port 8000)
make run-backend

# Terminal 2: Ingestion Worker Daemon
make run-worker

# Terminal 3: Next.js Frontend (port 3000)
make run-frontend
```

Access the services:
- **Frontend Dashboard**: `http://localhost:3000`
- **Backend Health Check**: `http://localhost:8000/api/v1/health`
- **Backend OpenAPI Docs**: `http://localhost:8000/docs`

### Discovery API Endpoints (Phase 2)

- `POST /api/v1/playlists` - Submit a playlist URL for discovery (validates URL and enqueues job)
- `GET /api/v1/playlists` - List all registered playlists
- `GET /api/v1/playlists/{playlist_id}` - Get playlist metadata by UUID or YouTube ID
- `GET /api/v1/playlists/{playlist_id}/status` - Get discovery progress and video counts
- `GET /api/v1/playlists/{playlist_id}/videos` - List all discovered videos in original position order
- `GET /api/v1/jobs/{job_id}` - Check status of background jobs

Stop each service with `Ctrl+C` in its terminal.

---

## Persistent Storage Architecture

All persistent application data is stored under the configured host data directory (`./data` by default, or `DATA_DIR` from `.env`):

- **SQLite Database**: `./data/revision_rag.db`
- **Transcript Artifacts**: `./data/artifacts/`
- **Temporary Audio**: `./data/temp_audio/`
- **Model Cache**: `./data/models/`

Data persists across service restarts and host reboots. The `data/` directory, `.venv`, `node_modules`, and `.env` are excluded from version control via `.gitignore`.

---

---

## Testing & Quality Assurance

Run automated unit and integration tests (which execute completely independent of Docker):

```bash
make test
```

Run code formatting and linting:

```bash
# Run lint checks (Ruff for Python, ESLint for Next.js)
make lint

# Automatically format Python code
make format
```

Clean temporary caches and bytecode:

```bash
make clean
```

---

## Troubleshooting

### Qdrant Connection Issues

Revision RAG uses Qdrant Cloud. Verify that:
1. `QDRANT_URL` in `.env` starts with `https://` and includes the cluster hostname.
2. `QDRANT_API_KEY` is set and valid.
3. Your host has outbound HTTPS access to Qdrant Cloud.

---

## Security & Repository Guidelines

- **Zero Secret Exposure**: Never commit `.env` or credentials. Secrets are excluded via `.gitignore` and never passed into frontend client assets.
- **CPU Baseline**: All defaults run on standard x86_64 CPUs. GPU acceleration (`EXECUTION_DEVICE=cuda`) is optional.
- **Deterministic Checkpoints**: Stage progression in subsequent phases requires validated persistent artifacts before SQLite checkpoints advance.
