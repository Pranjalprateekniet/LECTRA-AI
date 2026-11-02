# Revision RAG

Revision RAG is an open-source revision knowledge base that turns YouTube playlists into searchable revision assistants with grounded answers and clickable timestamp citations.

This version features a **zero-hosting-cost, local-first distribution architecture**:
- **Pre-Indexed Knowledge Base**: Distributed with 7,000 vectors across **Strivers A2Z-DSA Course** and **Generative AI using LangChain**.
- **Embedded Local Qdrant**: Operates embedded on disk at `data/qdrant` without Docker, cloud vector accounts, or remote retrieval servers.
- **Compact Seed Database**: Seeded from `data/knowledge_base/student_revision_rag.db`.
- **Private BYO-Key LLM Generation**: Uses your own free Groq API key (`openai/gpt-oss-120b`) for ultra-fast grounded answer generation.

---

## Quickstart (Student Setup)

### 1. Prerequisites
- **Git**
- **Python 3.12+**
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh` or via PowerShell)
- **Node.js 20+ & npm**
- A free **Groq API key** from [console.groq.com/keys](https://console.groq.com/keys)

*(No Docker, no cloud accounts, and no GPU required!)*

### 2. Install & Configure

```bash
# 1. Clone repository
git clone https://github.com/your-username/revision-rag.git
cd revision-rag

# 2. Install Python and frontend dependencies
uv sync
npm --prefix frontend install

# 3. Create .env from template
cp .env.example .env
```

Open `.env` and set your Groq key:
```ini
APP_MODE=USER
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

### 3. Run Application

```bash
uv run python run.py
```

The runner automatically:
1. Validates distribution assets.
2. Auto-initializes local SQLite (`data/revision_rag.db`).
3. Auto-imports the 7,000 vectors into local Qdrant (`data/qdrant/`) on first run.
4. Starts the FastAPI backend (`http://127.0.0.1:8000`) and Next.js UI (`http://localhost:3000`).

Open your browser to: **[http://localhost:3000](http://localhost:3000)**

---

## Pre-Indexed Playlists

1. **Strivers A2Z-DSA Course | DSA Playlist | Placements**
   - **ID**: `3820e00b-81b6-4f34-9e68-011ddc3d9f98`
   - **Vectors**: 6,011 chunks (313 indexed videos from 315 discovered, metadata count 316)
   - **Topics**: Binary Search, Dynamic Programming, Graphs, Trees, Recursion, Arrays, Sorting.

2. **Generative AI using LangChain**
   - **ID**: `0fd210e4-904f-4127-b539-130cb1497377`
   - **Vectors**: 989 chunks (20 indexed videos)
   - **Topics**: Prompts, Models, Output Parsers, Memory, Chains, LCEL, Retrieval-Augmented Generation, Agents.

---

## Architecture Overview

```mermaid
flowchart LR
    User[Student Browser] -->|UI / Question| NextJS[Next.js Frontend :3000]
    NextJS -->|/api/v1/query| FastAPI[FastAPI Backend :8000]
    FastAPI -->|768d Vector Query| LocalQdrant[(Local Qdrant data/qdrant)]
    FastAPI -->|Playlist & Video Metadata| SQLite[(SQLite data/revision_rag.db)]
    LocalQdrant -->|Retrieved Chunks + Timestamps| FastAPI
    FastAPI -->|Prompt + Context| GroqAPI[Groq API Cloud]
    GroqAPI -->|Grounded Prose| FastAPI
    FastAPI -->|Answer + Clickable YouTube URLs| NextJS
```

---

## Application Modes

- **`APP_MODE=USER` (Default)**:
  - Connects to local persistent Qdrant at `data/qdrant/`.
  - Ingestion and video retry endpoints are disabled (HTTP 403) to protect the prebuilt knowledge base.
  - Requires only `GROQ_API_KEY`.
- **`APP_MODE=DEVELOPER`**:
  - Unlocks local discovery, audio downloading, Whisper speech-to-text fallback, and Qdrant ingestion.
  - Can connect to Qdrant Cloud or a local Qdrant server for new playlist ingestion.

---

## Repository Structure

```
├── run.py                          # Unified cross-platform runner
├── data/
│   ├── knowledge_base/             # Prebuilt distribution assets
│   │   ├── chunks_7000.jsonl.gz    # 7,000 vectors + payloads (29.9 MB gzip)
│   │   ├── manifest.json           # SHA-256 integrity manifest
│   │   └── student_revision_rag.db # Clean SQLite seed (11 MB)
│   ├── qdrant/                     # Local embedded vector database
│   └── revision_rag.db             # Local SQLite database
├── core/                           # lectra-core: vectorstore, retrieval, generation
├── backend/                        # lectra-backend: FastAPI REST API
├── frontend/                       # Next.js 16 App Router UI with Tailwind CSS
├── scripts/
│   ├── load_knowledge_base.py      # Qdrant local importer
│   ├── export_knowledge_base.py    # Qdrant export tool
│   └── create_student_database.py  # SQLite seed generator
└── docs/
    └── SETUP.md                    # Detailed onboarding guide
```

---

## Testing

Run the full test suite with:

```bash
uv run pytest tests/ backend/tests/ -v
```

---

## License

MIT License.
