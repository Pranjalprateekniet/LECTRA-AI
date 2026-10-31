# Revision RAG --- Architecture

## 1. Product summary

Revision RAG is an open-source, self-hosted application that ingests one
YouTube playlist and turns its spoken content into a searchable revision
assistant.

The user supplies a playlist URL. The application discovers accessible
videos, retrieves suitable captions or downloads audio-only for local
transcription, translates supported non-English transcript content into
English, creates timestamp-preserving chunks, embeds English text, and
stores vectors and metadata in Qdrant (cloud or local).

At query time, the user asks a question. The system retrieves relevant
passages, sends grounded context to a configured LLM provider, and
returns an answer with source video titles and clickable timestamps.

## 2. Product principles

-   Local-first: transcripts, processing state, and vector data remain
    on the user's machine by default.
-   Self-hosted: the user runs the application locally on the host
    machine using the documented development setup (Python virtual
    environment, uv, Node.js). Docker is not required.
-   Resumable: each video and processing stage is independently
    checkpointed.
-   Source-grounded: every source link comes from stored metadata
    associated with retrieved evidence.
-   Hardware-inclusive: CPU-only operation is supported; NVIDIA
    acceleration is optional.
-   Modular: core processing code can run and be tested without Docker.
-   Provider-aware: external LLM credentials are supplied by the user;
    secrets never enter the frontend bundle or Git.

## 3. First-release scope

### Included

-   One playlist per knowledge base.
-   Playlist metadata discovery.
-   Caption-first transcript acquisition.
-   Audio-only download when captions are unavailable or unsuitable.
-   Local ASR fallback using faster-whisper.
-   Translation of supported non-English transcripts into English.
-   Timestamp-preserving transcript processing and chunking.
-   English-only embeddings and Qdrant indexing.
-   SQLite checkpoints and resumable ingestion.
-   Semantic retrieval and LLM-grounded answers.
-   FastAPI backend, background ingestion worker, and Next.js frontend.
-   Local host deployment with persistent host storage under `./data`.
-   CPU baseline and optional GPU acceleration.

### Excluded from the first release

-   Full video downloading or video understanding.
-   Multiple playlists in one combined knowledge base (design should not
    prevent adding it later).
-   PDF, website, and document ingestion.
-   Fine-tuning or training an LLM.
-   Mandatory local LLM inference.
-   Accounts, multi-user hosting, cloud synchronization, and hosted SaaS
    operation.
-   Advanced learning analytics, flashcards, and automatic study plans.

## 4. High-level system

``` text
                         USER
                          |
                          v
                 Next.js Web Interface
                          |
                          v
                    FastAPI Backend
                     /          \
                    /            \
             SQLite State     Job Queue
                                  |
                                  v
                           Ingestion Worker
                                  |
             +--------------------+--------------------+
             |                    |                    |
             v                    v                    v
       YouTube/yt-dlp       Local Model Runtime    Local Artifacts
       metadata/captions    faster-whisper         transcripts/chunks
       audio-only fallback  Argos Translate
                            MiniLM embeddings
                                  |
                                  v
                             Local Qdrant
                                  |
                                  v
                         Retrieval Service
                                  |
                                  v
                         LLM Provider Adapter
                                  |
                                  v
                         Structured Answer
                                  |
                                  v
                         Next.js Web Interface
```

The job queue may initially be implemented using SQLite-backed jobs or
another lightweight local mechanism. The architecture must define job
claiming, locking, retries, and recovery before concurrent workers are
introduced. Do not add Redis solely by default.

## 5. Runtime services

### 5.1 Frontend --- Next.js

Responsibilities: - Playlist submission and validation feedback. -
First-run configuration experience. - Ingestion progress and per-video
status. - Pause/resume/retry controls where supported. - Revision
search/chat interface. - Source cards with title, time range, and
YouTube timestamp links.

The frontend must never receive the Groq API key or other provider
secrets.

### 5.2 Backend --- FastAPI

Responsibilities: - Validate requests and configuration. - Create and
manage playlist/ingestion jobs. - Expose status and retry operations. -
Coordinate query embedding, retrieval, and answer generation. - Return
structured responses and source metadata.

Long-running ingestion must not run inside a long-lived HTTP request.
The API enqueues work and returns a job identifier.

### 5.3 Ingestion worker --- Python

Responsibilities: - Claim queued work safely. - Execute the per-video
processing state machine. - Persist intermediate artifacts. - Update
SQLite checkpoints. - Retry transient failures and expose permanent
failures. - Reconcile SQLite state with Qdrant after interruptions.

The worker uses the same core Python modules as tests and development
scripts.

### 5.4 Qdrant

Responsibilities: - Store vectors and payloads. - Provide similarity
search and metadata filtering. - Persist data in Qdrant Cloud (default)
or a configured local directory.

Qdrant Cloud is the default for the first release. Credentials are
loaded from environment variables and never committed to Git.

### 5.5 SQLite

Responsibilities: - Store playlist and video records. - Store per-stage
processing states and attempts. - Store job state, error summaries, and
timestamps. - Store application configuration metadata that is not
secret.

SQLite is the source of truth for ingestion state, not a substitute for
Qdrant.

## 6. Per-video ingestion state machine

Recommended successful states:

``` text
DISCOVERED
    |
    v
TRANSCRIPT_READY
    |
    v
ENGLISH_READY
    |
    v
CHUNKED
    |
    v
INDEXED
```

A video may also have explicit terminal or recoverable states such as: -
`SKIPPED_UNAVAILABLE` - `UNSUPPORTED_LANGUAGE` - `FAILED_RETRYABLE` -
`FAILED_PERMANENT` - `NEEDS_REVIEW`

Store the failed stage, error category, sanitized error detail, attempt
count, and retry eligibility. Do not collapse every failure into one
state that loses recovery information.

A stage is complete only after its output is persisted and validated. On
startup, the worker reconciles its state with artifacts and Qdrant
before scheduling unfinished work.

## 7. Stage contracts

### Stage A --- Playlist discovery

Input: playlist URL.

Process: - Validate the URL and discover accessible playlist metadata
with yt-dlp. - Record playlist ID and stable video IDs. - Store title,
URL, duration, playlist position, and availability. - Reconcile with
existing records on repeat discovery.

Output: durable playlist/video manifest in SQLite.

### Stage B --- Transcript acquisition

Input: one discovered video.

Process: 1. Check for suitable captions. 2. Prefer available caption
tracks. 3. If captions are missing or unsuitable, download audio only.
4. Transcribe locally using faster-whisper. 5. Normalize segment
representation and validate timestamps. 6. Persist raw timestamped
transcript. 7. Delete temporary audio only after validation and
persistence.

Output: timestamped source-language transcript segments and acquisition
metadata.

Do not download full video files. Do not bypass access restrictions.

### Stage C --- Language normalization and translation

Input: timestamped transcript segments.

Process: - Detect language at transcript or segment level as needed. -
Preserve English text unchanged. - Translate supported non-English
content into English using the configured local translation engine
(Argos Translate in the initial implementation). - Preserve source
segment IDs and time boundaries. - Protect technical terms, code
identifiers, package names, and API names where practical. - Record
unsupported language or translation failures explicitly.

Output: English segments aligned to source timestamps, plus retained
original transcript artifacts.

Translation quality must be evaluated on Hindi-English technical speech
before scaling to a full playlist. Argos language-pair availability must
be checked during setup; the application must not silently assume every
language package is installed.

### Stage D --- Chunking

Input: English timestamped segments.

Initial experimental settings: - Target chunk size: approximately
300--500 tokens. - Overlap: approximately 50--75 tokens. - Prefer
sentence and semantic boundaries. - Never cross video boundaries.

These values are configuration defaults to be evaluated, not immutable
rules.

Output: chunk records with stable IDs, English text, video ID, title,
URL, start/end seconds, and source segment references.

### Stage E --- Embedding and indexing

Input: validated English chunks.

Process: - Use `sentence-transformers` with `all-MiniLM-L6-v2`
initially. - Use identical model and preprocessing for document and
query embeddings. - Confirm the model's vector dimension at
initialization rather than hard-coding assumptions in multiple places. -
Upsert points to Qdrant using deterministic IDs. - Verify expected
points before updating SQLite to `INDEXED`.

Qdrant payload fields: - `chunk_id` - `playlist_id` - `video_id` -
`video_title` - `video_url` - `start_seconds` - `end_seconds` -
`english_text` - `transcript_language` - `embedding_model` -
`pipeline_version`

The first release indexes English text only. Original-language
transcripts remain local artifacts.

## 8. Persistence and recovery

### Storage responsibilities

  Data                              Store
  --------------------------------- -------------------------------------
  Playlist/video metadata           SQLite
  Job and checkpoint state          SQLite
  Raw transcript segments           Local artifact files
  English transcript segments       Local artifact files
  Chunk records                     Local artifact files
  Vectors and searchable payloads   Qdrant
  Temporary audio                   Temporary local directory
  Model cache                       Configurable persistent model cache

### Recovery rules

-   Network failure during discovery/download: retry outstanding
    operations; retain completed records and files.
-   Interrupted audio download: resume where supported, otherwise
    restart only that video.
-   ASR interruption: reuse persisted transcript output if validated;
    otherwise redo the incomplete video transcription.
-   Translation failure: retry only failed segments where the
    translation artifact format allows it.
-   Chunking failure: rebuild chunks from saved English transcript.
-   Embedding failure: regenerate only missing embeddings.
-   Qdrant unavailable: retain chunk artifacts and retry indexing later.
-   Qdrant write succeeds but SQLite update fails: inspect deterministic
    point IDs and reconcile before retrying.
-   Process restart: perform reconciliation, then enqueue incomplete
    work.

Use atomic file writes (write temporary file, validate, then rename) for
important artifacts. Avoid marking a stage complete before the artifact
is safely committed.

## 9. Query-time architecture

Input: user's natural-language question.

Process: 1. Validate the question and selected knowledge base. 2. Embed
the query using the same MiniLM model. 3. Retrieve top candidate chunks
from Qdrant. 4. Optionally apply keyword/hybrid retrieval and reranking
after evaluation demonstrates a need. 5. Apply evidence selection and
context limits. 6. Call the configured LLM provider through a provider
adapter. 7. Validate the structured answer and source references. 8.
Construct YouTube timestamp links in application code using the stored
video ID and `start_seconds`.

The LLM must not invent titles, URLs, or timestamps. The answer should
abstain or ask for clarification when the retrieved evidence is
insufficient.

### LLM provider

Initial default: Groq-hosted GPT-OSS-120B, subject to current provider
availability, API limits, and user-supplied credentials.

Keep provider integration behind an interface so additional
OpenAI-compatible or local providers can be added later. Never expose
provider credentials to the browser.

## 10. Suggested API surface

These routes are proposals and may be refined during implementation:

  ------------------------------------------------------------------------------------------
  Method                  Route                                      Purpose
  ----------------------- ------------------------------------------ -----------------------
  POST                    `/api/v1/playlists`                        Register/discover a
                                                                     playlist

  GET                     `/api/v1/playlists/{playlist_id}`          Playlist details

  GET                     `/api/v1/playlists/{playlist_id}/status`   Ingestion progress

  GET                     `/api/v1/playlists/{playlist_id}/videos`   Video statuses

  POST                    `/api/v1/playlists/{playlist_id}/ingest`   Start/resume ingestion

  POST                    `/api/v1/videos/{video_id}/retry`          Retry a failed video

  POST                    `/api/v1/chat`                             Ask a revision question

  GET                     `/api/v1/health`                           Application health
  ------------------------------------------------------------------------------------------

Long-running jobs return a job identifier and are polled or streamed for
progress. API design must distinguish playlist IDs, video IDs, and job
IDs.

## 11. Local execution and distribution

Lectra runs directly on the host machine using the project Python
virtual environment (`.venv`) and uv for dependency management, plus a
local Node.js installation for the frontend. Docker is not required and
is not part of the installation path.

Services: - `frontend` (Next.js, port 3000) - `backend` (FastAPI, port
8000) - `worker` (standalone ingestion worker from `lectra_core.worker`)

Qdrant Cloud is the default vector database.

SQLite and local artifacts use a clearly documented host data directory
(`./data` by default, configurable via `DATA_DIR`). Model caches also
persist to avoid repeated downloads.

The core engine runs and is tested outside Docker by default.

Default network posture: - Frontend exposed on localhost. - Backend
exposed only as needed by the frontend/local user. - No public binding
by default.

CPU-only is the baseline. GPU acceleration is optional and must be
documented separately because NVIDIA driver and toolkit configuration
varies by operating system.

## 12. Configuration

Provide `.env.example` with non-secret defaults and placeholders. At
minimum, configuration should cover: - LLM provider and API key. - LLM
model name. - Qdrant URL, collection name, and API key. - SQLite path. - Artifact and
temporary-audio paths. - Model cache path. - Embedding model. - Whisper
model/device/compute type. - Translation language/package
configuration. - Worker concurrency and retry policy. - Logging level
and local host/port settings.

Validate configuration at startup and explain missing or invalid
settings clearly. Never put secrets in frontend build-time variables.

## 13. Observability

Expose: - Total discovered videos. - Videos in each processing state. -
Current video and stage. - Retry count and failed-job summaries. -
Transcript acquisition method. - Translation language and status. -
Indexed chunk count. - Last successful checkpoint. - Worker and Qdrant
health.

Logs should be structured and useful for diagnosis without leaking API
keys or unnecessarily printing transcript contents.

## 14. Evaluation

Create a small manually verified evaluation set before scaling
ingestion. Include: - Exact technical terms. - Paraphrased questions. -
Questions answered across multiple chunks. - Topics mentioned in
multiple videos. - Questions absent from the playlist.

Measure: - Transcript usability and timestamp validity. - Translation
quality on technical Hindi-English content. - Retrieval Recall@K /
correct-source retrieval. - Timestamp accuracy. - Answer faithfulness
and citation correctness. - Ingestion time and resource consumption.

Do not claim accuracy based only on a successful demo.

## 15. Future extension points

Keep the design open to: - Multiple playlists and separate knowledge
bases. - PDF and document ingestion. - Additional ASR and translation
providers. - Multilingual embeddings. - Hybrid search and rerankers. -
Additional LLM providers. - Saved topics, revision notes, and
flashcards.

Do not implement these in v1 unless explicitly brought into scope.
