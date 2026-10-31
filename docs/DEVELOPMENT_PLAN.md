# Revision RAG --- Development Plan

## Development approach

Build Revision RAG in small, verifiable phases. Each phase must have
working tests and a clear completion gate before the next phase begins.

Do not generate the entire application in one pass. Keep core processing
logic independent of Docker and the UI.

## Phase 0 --- Repository and development foundation

### Tasks

-   Create repository and agreed folder structure.
-   Establish Python backend environment and dependency management.
-   Establish frontend environment with Next.js and TypeScript.
-   Add `.gitignore`, `.env.example`, `AGENTS.md`, and documentation.
-   Add formatting, linting, and test tooling.
-   Define configuration loading and structured logging.
-   Add basic health-check entry points.
-   Decide supported Python and Node versions and record tested
    versions.

### Deliverables

-   Clean repository structure.
-   Reproducible local development setup.
-   Configuration validation.
-   Documentation for developers.

### Completion gate

-   Backend environment starts.
-   Frontend development server starts.
-   Configuration loads and invalid configuration produces a clear
    error.
-   Basic automated checks run successfully.
-   No secrets or generated data are tracked.

## Phase 1 --- Local infrastructure and application skeleton

### Tasks

-   Establish local host execution for frontend, backend, and worker.
-   Configure persistent host storage for SQLite, artifacts, and model
    cache under the configured data directory (`./data` by default).
-   Configure Qdrant Cloud connectivity via environment variables.
-   Add health checks and startup dependency handling.
-   Verify core Python modules remain runnable outside containers.
-   Document CPU-only startup; defer GPU acceleration until the CPU path
    works.

### Deliverables

-   Local application services start independently on the host.
-   Qdrant Cloud connectivity is configured and validated.
-   SQLite and artifact paths are persistent on the host.
-   Health endpoints work.

### Completion gate

-   A developer can start and stop backend, worker, and frontend
    individually without Docker.
-   Qdrant Cloud is reachable from the configured cluster URL.
-   Backend can connect to Qdrant and SQLite.
-   No service relies on container storage for important data.

## Phase 2 --- Playlist discovery and manifest

### Tasks

-   Accept and validate a playlist URL.
-   Discover playlist metadata with yt-dlp.
-   Store playlist and accessible video metadata in SQLite.
-   Use stable YouTube video IDs and separate internal database IDs
    where appropriate.
-   Reconcile repeated discovery without duplicates.
-   Record unavailable/private/deleted videos explicitly.
-   Track discovery status and errors.

### Deliverables

-   Playlist and video repositories.
-   Discovery service.
-   Durable manifest and status reporting.

### Completion gate

-   A test playlist can be discovered.
-   Re-running discovery does not duplicate records.
-   Inaccessible videos are recorded as exceptions.
-   The manifest survives application restart.

## Phase 3 --- Transcript acquisition

### Tasks

-   Inspect available subtitle tracks.
-   Prefer suitable existing captions.
-   Define what makes captions usable (nonempty text, valid timing,
    reasonable coverage).
-   Download audio only when captions are unavailable or unsuitable.
-   Add faster-whisper as local ASR fallback.
-   Preserve segment start/end times and source metadata.
-   Validate transcript output.
-   Persist transcript artifacts atomically.
-   Delete temporary audio only after transcript validation.
-   Add retries and per-video acquisition status.

### Deliverables

-   Caption acquisition module.
-   Audio-only download module.
-   ASR module.
-   Timestamped transcript schema and artifact writer.

### Completion gate

-   At least one caption-based video and one ASR-fallback video are
    processed.
-   No full video files are downloaded.
-   Transcript timestamps are validated.
-   Restarting does not repeat completed transcript acquisition.

## Phase 4 --- Language detection and English normalization

### Tasks

-   Detect transcript/segment language.
-   Preserve English segments.
-   Integrate Argos Translate for supported non-English-to-English
    language pairs.
-   Check language package availability at setup.
-   Preserve segment timestamps and source references.
-   Protect technical vocabulary and code identifiers where practical.
-   Record unsupported language and failed translation states.
-   Save original and English-aligned transcript artifacts.
-   Create a small Hindi-English technical translation evaluation set.

### Deliverables

-   Language detection and translation modules.
-   Translation artifact schema.
-   Translation validation and retry behavior.

### Completion gate

-   English transcript segments remain unchanged.
-   Supported Hindi segments translate to English.
-   Timestamps remain aligned.
-   Technical terms are checked against a manually reviewed test set.
-   Unsupported language cases are visible, not silently indexed.

## Phase 5 --- Chunking

### Tasks

-   Define chunk schema.
-   Implement sentence-aware chunking with configurable token target and
    overlap.
-   Keep chunks within video boundaries.
-   Map chunks to source transcript segments.
-   Derive start/end seconds from source segments.
-   Generate deterministic chunk IDs.
-   Persist chunk artifacts atomically.
-   Test short, long, empty, and boundary-case transcripts.

### Initial experimental defaults

-   300--500 tokens per chunk.
-   50--75 tokens overlap.
-   Sentence/semantic boundaries.
-   No cross-video chunks.

### Deliverables

-   Chunking module.
-   Chunk artifact files.
-   Chunk validation tests.

### Completion gate

-   Every chunk has nonempty English text, stable ID, video metadata,
    and valid source time range.
-   Reprocessing produces the same IDs for unchanged inputs.
-   No chunk crosses video boundaries.

## Phase 6 --- Embeddings and Qdrant indexing

### Tasks

-   Integrate sentence-transformers and `all-MiniLM-L6-v2`.
-   Load the model lazily and persist model cache.
-   Determine vector dimension from the loaded model.
-   Create and validate Qdrant collection configuration.
-   Define payload schema and deterministic point IDs.
-   Generate embeddings in bounded batches.
-   Upsert points idempotently.
-   Verify Qdrant writes before advancing SQLite state.
-   Add reconciliation for partial writes and restarts.
-   Add retrieval smoke tests.

### Deliverables

-   Embedding service.
-   Qdrant repository/index manager.
-   Collection initialization and migration strategy.
-   Indexing checkpoint logic.

### Completion gate

-   English chunks are searchable.
-   Payload metadata is correct.
-   Repeated indexing does not duplicate points.
-   Simulated interruption between Qdrant write and SQLite update is
    recoverable.

## Phase 7 --- Retrieval engine and evaluation

### Tasks

-   Embed user queries using the same model and preprocessing.
-   Search Qdrant with configurable top-k.
-   Support playlist filtering.
-   Return structured evidence objects, not plain text alone.
-   Create manually verified question/evidence evaluation set.
-   Measure Recall@K and correct-source retrieval.
-   Tune chunk size, overlap, and top-k using evaluation.
-   Add keyword/hybrid retrieval only if baseline tests justify it.
-   Add reranking only if it improves measured results.

### Deliverables

-   Retrieval service.
-   Evidence result schema.
-   Evaluation dataset and baseline report.

### Completion gate

-   Known questions retrieve the expected source passages at an
    acceptable measured rate.
-   Missing-topic questions can return no reliable evidence.
-   Source metadata survives retrieval intact.

## Phase 8 --- LLM generation and provider abstraction

### Tasks

-   Define an LLM provider interface.
-   Implement Groq provider using user-supplied credentials.
-   Configure GPT-OSS-120B where available to the user's account.
-   Build prompts using retrieved evidence.
-   Return structured answer and sources separately.
-   Require abstention when evidence is insufficient.
-   Construct timestamp URLs in application code.
-   Handle timeouts, rate limits, malformed responses, and provider
    errors.
-   Add tests for hallucinated or unsupported citations.

### Deliverables

-   Provider adapter.
-   Grounded answer service.
-   Structured response schema.
-   Error handling and tests.

### Completion gate

-   Answers are grounded in retrieved evidence.
-   The LLM cannot introduce unverified video titles or timestamps into
    source objects.
-   Missing evidence is handled honestly.
-   API keys remain backend-only.

## Phase 9 --- FastAPI and job orchestration

### Tasks

-   Expose playlist creation/discovery and ingestion operations.
-   Add job IDs and status endpoints.
-   Implement safe job claiming and worker locking.
-   Add pause/resume/cancel semantics if supported by the worker design.
-   Add retry endpoints for failed videos.
-   Expose health and diagnostic status.
-   Ensure HTTP requests enqueue long-running work instead of executing
    it synchronously.
-   Test concurrent requests and worker restarts.

### Deliverables

-   Versioned API.
-   Worker orchestration.
-   Job/status reporting.
-   API documentation.

### Completion gate

-   Ingestion can be started and monitored through APIs.
-   Worker restarts do not lose job state.
-   Duplicate requests do not create duplicate jobs or index points
    unintentionally.

## Phase 10 --- Frontend application

### Tasks

-   Build first-run configuration flow.
-   Build playlist submission screen.
-   Build ingestion progress dashboard.
-   Display per-video states and failures.
-   Add retry/resume controls.
-   Build revision search/chat interface.
-   Display answer and source cards.
-   Add clickable timestamp links.
-   Display useful loading, empty, and error states.
-   Keep provider secrets out of browser code.

### Deliverables

-   Functional Next.js application.
-   API integration.
-   Usable ingestion and revision workflows.

### Completion gate

-   A user can configure the application, submit a playlist, monitor
    ingestion, and ask a question without using command-line scripts for
    normal operation.

## Phase 11 --- Cross-platform packaging and open-source release

### Tasks

-   Finalize local host installation and startup (Python virtual
    environment, uv, Node.js).
-   Document optional NVIDIA acceleration separately.
-   Test on supported Linux, Windows (WSL2), and macOS environments as
    practical.
-   Add installation and troubleshooting guides.
-   Add license, contribution guide, security policy, and issue
    templates.
-   Add GitHub Actions for tests, linting, and builds.
-   Verify persistent data and backup/delete behavior.
-   Review dependency licences and YouTube access/copyright guidance.
-   Prepare a release checklist.

### Deliverables

-   Reproducible local installation without Docker.
-   Complete README and documentation.
-   CI checks.
-   Open-source v1.0 release.

### Completion gate

A new user can clone the repository, configure the required provider
credentials, start the application, submit a playlist, allow ingestion
to complete, and ask revision questions with working source timestamps.

## Recommended milestone grouping

  -----------------------------------------------------------------------
  Milestone               Phases                  Result
  ----------------------- ----------------------- -----------------------
  M1 --- Foundation       0--2                    Running local stack and
                                                  playlist manifest

  M2 --- Content pipeline 3--5                    Timestamped English
                                                  chunks

  M3 --- Searchable       6--7                    Local Qdrant and
  knowledge base                                  evaluated retrieval

  M4 --- Answering        8--10                   Grounded chat and
  application                                     frontend

  M5 --- Open-source      11                      Installable, documented
  release                                         application
  -----------------------------------------------------------------------

## Working rules

-   Work on one phase at a time.
-   Do not proceed until the current phase's completion gate passes.
-   Keep a short phase status in this document or a dedicated progress
    document.
-   Record architectural changes in `ARCHITECTURE.md`.
-   Test recovery behavior, not only the happy path.
-   Prefer measured evaluation over assumptions about retrieval quality
    or performance.
