# Revision RAG — Student Setup & Onboarding Guide

Revision RAG turns YouTube playlists into an interactive, grounded revision knowledge base with timestamped citations.

This version uses a **zero-cloud, local-first architecture**:
- **Prebuilt Knowledge Base**: Bundles 7,000 vectors and complete metadata across two curated playlists:
  1. **Strivers A2Z-DSA Course** (6,011 vectors across 313 indexed videos, 315 discovered, metadata count 316)
  2. **Generative AI using LangChain** (989 vectors, 20 videos)
- **Local Embedded Qdrant**: Runs embedded in Python directly from `data/qdrant/` (no Docker or cloud accounts).
- **Local SQLite Metadata**: Stored at `data/revision_rag.db`.
- **Grounded Answer Generation**: Uses your own **free Groq API key** for rapid LLM answer synthesis.

---

## What You Do NOT Need

- ❌ **NO Docker or Docker Compose**
- ❌ **NO Qdrant Cloud account or API keys**
- ❌ **NO hosted retrieval server or remote retrieval URL**
- ❌ **NO video downloads or Whisper transcription**
- ❌ **NO NVIDIA GPU required** (runs CPU-only on Linux, macOS, and Windows)

> **Note on Internet Access**: The application queries your local vector database on your computer. Internet access is only required for:
> 1. Downloading the 270M parameter `google/embeddinggemma-2` embedding model weights on the first run (cached locally afterward).
> 2. Calling the Groq API when generating answers to your revision questions.

---

## 1. Prerequisites

Ensure you have the following installed on your computer:

| Tool | Minimum Version | Installation Link |
| :--- | :--- | :--- |
| **Git** | Any recent version | [git-scm.com](https://git-scm.com/downloads) |
| **Python** | 3.12 or newer (64-bit) | [python.org](https://www.python.org/downloads/) |
| **uv** | 0.4+ | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **Node.js & npm** | Node 20 LTS+ / npm 10+ | [nodejs.org](https://nodejs.org/) |

### Installing `uv` (Fast Python Package Manager)

- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Verify your installations in a fresh terminal:
```bash
git --version
python3 --version  # or python --version
uv --version
node --version
npm --version
```

---

## 2. Automated One-Command Installation (Recommended)

### Linux & macOS

```bash
git clone https://github.com/your-username/revision-rag.git
cd revision-rag
./install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/your-username/revision-rag.git
cd revision-rag
.\install.ps1
```

The automated installer will:
1. Detect your operating system and CPU architecture.
2. Verify Python 3.12+ and Node.js 20+ installations.
3. Create the Python virtual environment (`.venv`).
4. Install all backend and frontend dependencies.
5. Create `.env` from template and prompt for your free Groq API key.
6. Verify the prebuilt knowledge-base assets (7,000 vectors) against their SHA-256 checksums.
7. Run complete preflight checks.

---

## 3. Launching Revision RAG

Once installation completes, launch the backend and frontend with:

### Linux & macOS
```bash
./start.sh
```

### Windows (PowerShell)
```powershell
.\start.ps1
```

Open your browser at:
👉 **[http://localhost:3000](http://localhost:3000)**

---

## 4. Manual Setup Alternative (Advanced Users)

If you prefer installing dependencies manually with `uv`:

```bash
uv sync
npm --prefix frontend install
cp .env.example .env
# Set GROQ_API_KEY in .env
uv run python run.py
```

```bash
uv run python run.py
```
*(Or simply `python run.py` if your active virtual environment is activated).*

### What happens on the first run:
1. **Asset Preflight**: Verifies the packaged knowledge base (`student_revision_rag.db`, `chunks_7000.jsonl.gz`, and `manifest.json`).
2. **SQLite Auto-Seed**: Automatically initializes `data/revision_rag.db` from `student_revision_rag.db`.
3. **Qdrant Auto-Import**: Decompresses and imports the 7,000 vector chunks into `data/qdrant/` (~20–30 seconds on CPU).
4. **Model Download**: On the first query, downloads the lightweight `google/embeddinggemma-2` text embedding model (~550 MB) and caches it locally.
5. **Services Startup**:
   - **Backend**: FastAPI running at `http://127.0.0.1:8000`
   - **Frontend**: Next.js running at `http://localhost:3000`

Once started, open your browser to:
👉 **[http://localhost:3000](http://localhost:3000)**

---

## 6. Using Revision RAG

1. Select your desired playlist from the top dropdown:
   - **Strivers A2Z-DSA Course** (Binary search, graphs, dynamic programming, trees, sorting)
   - **Generative AI using LangChain** (Prompts, models, memory, chains, RAG, agents)
2. Ask any revision question in the chat bar (e.g., *"How does binary search work on rotated sorted arrays?"* or *"What is PromptTemplate in LangChain?"*).
3. The response will cite exact lecture segments with **clickable YouTube timestamp links** (e.g. `[S1] 1470s - 1545s`) that jump directly to the timestamp in the video.

---

## 7. Stopping the Application

Press **`Ctrl+C`** in the terminal where `run.py` is running.

The runner intercepts the signal, gracefully terminates both FastAPI and Next.js, and releases local Qdrant directory locks cleanly.

---

## 8. Troubleshooting & FAQ

### Port 8000 or 3000 is already in use
If another application is using port 8000 or 3000, `run.py` will report the conflict cleanly. You can specify alternative ports:
```bash
uv run python run.py --backend-port 8080 --frontend-port 3001
```

### Hugging Face download timeout or network failure
On the first run, the embedding model weights are fetched from Hugging Face. If your connection drops:
- Ensure your internet connection is active.
- Re-run `uv run python run.py`. Hugging Face resumes partially downloaded files automatically.

### Incomplete or corrupted database recovery
If your local database file is accidentally corrupted:
- **To re-seed SQLite**: Delete `data/revision_rag.db` and re-run `run.py`.
- **To re-import Qdrant**: Run `uv run python scripts/load_knowledge_base.py --force`.

### Memory Requirements
Revision RAG is optimized for student machines:
- **RAM**: ~2–3 GB free system RAM is sufficient.
- **Disk Space**: ~1.5 GB total (code + 7,000 vectors + cached model weights).
