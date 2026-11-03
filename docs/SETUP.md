# Revision RAG — Setup & Onboarding Guide

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
- ❌ **NO video downloads or Whisper transcription for revision**
- ❌ **NO NVIDIA GPU required** (runs CPU-only on Linux, macOS, and Windows)
- ❌ **NO custom installation scripts** (`run.py` is the single application launcher)

> **Note on Internet Access**: The application queries your local vector database on your computer. Internet access is only required for:
> 1. Downloading the 270M parameter `google/embeddinggemma-2` embedding model weights on the first run (cached locally afterward).
> 2. Calling the Groq API when generating answers to your revision questions.

---

## 1. Prerequisites

Revision RAG is strictly locked to **Python 3.12.x**. Ensure you have the following installed on your computer:

| Tool | Required Version | Verification Command | Official Link |
| :--- | :--- | :--- | :--- |
| **Git** | Recent stable version | `git --version` | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **Python** | **3.12.x** (strictly locked) | `py -3.12 --version` or `python3.12 --version` | [python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/) |
| **Node.js & npm** | Node 20 LTS+ / npm 10+ | `node --version` / `npm --version` | [nodejs.org/en/download](https://nodejs.org/en/download) |

---

## 2. Standard Installation

### Step 1: Clone the repository

```bash
git clone https://github.com/Pranjalprateekniet/LECTRA-AI.git
cd LECTRA-AI
```

### Step 2: Create a Python 3.12 virtual environment

- **Windows**:
  ```powershell
  py -3.12 -m venv .venv
  ```
- **Linux & macOS**:
  ```bash
  python3.12 -m venv .venv
  ```

### Step 3: Activate the virtual environment

- **Windows (Command Prompt)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Linux & macOS**:
  ```bash
  source .venv/bin/activate
  ```

### Step 4: Install dependencies

With your virtual environment active:

```bash
# 1. Upgrade pip
python -m pip install --upgrade pip

# 2. Install third-party runtime dependencies
pip install -r requirements.txt

# 3. Install local core and backend packages in editable mode
pip install -e ./core
pip install -e ./backend

# 4. Install Next.js frontend dependencies via committed lockfile
npm ci --prefix frontend
```

#### Windows Alternative (without activating the virtual environment):
```powershell
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e ./core
.venv\Scripts\python.exe -m pip install -e ./backend
npm ci --prefix frontend
```

### Step 5: Configure `.env` and Groq API Key

Copy the `.env.example` template:

- **Windows CMD**: `copy .env.example .env`
- **Windows PowerShell**: `Copy-Item .env.example .env`
- **Linux & macOS**: `cp .env.example .env`

Edit `.env` and configure your free Groq API key:

```ini
GROQ_API_KEY=gsk_your_actual_key_here
```

Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys).

---

## 3. Launching Revision RAG

With the virtual environment activated:

```bash
python run.py
```

Or on Windows without environment activation:

```powershell
.venv\Scripts\python.exe run.py
```

### What happens during startup:
1. **Python Version Check**: Validates that the runtime interpreter is Python 3.12.x.
2. **Asset Preflight**: Verifies the packaged knowledge base (`student_revision_rag.db`, `chunks_7000.jsonl.gz`, and `manifest.json`).
3. **SQLite Auto-Seed**: Automatically initializes `data/revision_rag.db` from `student_revision_rag.db` if missing.
4. **Qdrant Auto-Import**: Decompresses and imports the 7,000 vector chunks into `data/qdrant/` if missing.
5. **Model Caching**: On the first query, downloads the lightweight `google/embeddinggemma-2` text embedding model (~540 MB) and caches it in `data/models/`.
6. **Services Startup**:
   - **Backend**: FastAPI running at `http://127.0.0.1:8000`
   - **Frontend**: Next.js running at `http://localhost:3000`

Once started, open your web browser at:
👉 **[http://localhost:3000](http://localhost:3000)**

---

## 4. Stopping the Application

Press **`Ctrl+C`** in the terminal running `run.py`.

The runner intercepts the interrupt signal, gracefully stops both FastAPI and Next.js, and releases local Qdrant directory locks cleanly.

---

## 5. Troubleshooting & FAQ

### Port 8000 or 3000 is already in use
If another application is using port 8000 or 3000, specify alternative ports:
```bash
python run.py --backend-port 8080 --frontend-port 3001
```

### Python version error
Revision RAG strictly requires Python 3.12.x. If you encounter:
```text
[ERROR] Unsupported Python version: 3.11.x / 3.13.x
```
Re-create your virtual environment explicitly with Python 3.12:
```bash
py -3.12 -m venv .venv       # Windows
python3.12 -m venv .venv     # Linux/macOS
```

### Initial embedding model download
On the first query, model weights are downloaded from Hugging Face. If your connection drops, simply re-run `python run.py`. Hugging Face automatically resumes partially downloaded files.

### Incomplete or corrupted database recovery
If local data is corrupted:
- **To re-seed SQLite**: Delete `data/revision_rag.db` and re-run `python run.py`.
- **To re-import Qdrant**: Run `python scripts/load_knowledge_base.py --force`.

### Memory Requirements
- **RAM**: ~2–3 GB free system RAM is sufficient.
- **Disk Space**: ~1.5 GB total (repository + 7,000 vectors + cached model weights).
