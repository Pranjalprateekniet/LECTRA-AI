# AGENTS.md --- Revision RAG

## Project purpose

Revision RAG is an open-source, self-hosted application that turns a
YouTube playlist into a searchable revision knowledge base. A user
should be able to clone the repository, install the prerequisites,
configure an LLM provider, submit a playlist URL, wait for ingestion,
and ask questions with answers linked to the original video timestamps.

The first release supports one playlist per knowledge base. It preserves
source timestamps, translates supported transcript content into English,
indexes English chunks only, and uses local Qdrant for vector storage.

## Non-negotiable product requirements

1.  Do not download full video files. Prefer available captions. If
    usable captions are unavailable, download audio only for
    transcription.
2.  Do not assume every playlist video is accessible or has captions.
    Record unavailable, private, deleted, age-restricted, or otherwise
    unprocessable videos as explicit exceptions.
3.  Preserve source segment timestamps from transcript acquisition
    through translation, chunking, indexing, retrieval, and answer
    rendering.
4.  Translate supported non-English transcript content into English.
    Keep English content unchanged. The first release indexes English
    text only.
5.  Retain original timestamped transcripts locally where practical so
    translation and chunking can be repeated without downloading or
    transcribing again.
6.  Ingestion must be resumable after network failures, process crashes,
    and machine restarts.
7.  SQLite is the source of truth for ingestion job state and
    application metadata. Local artifacts are the source of truth for
    intermediate transcript and chunk data. Qdrant is the searchable
    vector index.
8.  Use deterministic IDs for videos and chunks. Qdrant writes must be
    safe to retry.
9.  Never mark a stage complete until its output has been persisted and
    validated.
10. Do not fabricate explanations, video titles, timestamps, or
    citations. If retrieval evidence is insufficient, say so.
11. Keep core Python processing modules independent of Docker. Docker
    Compose packages and orchestrates the application; it must not be
    required to unit-test core logic.
12. CPU-only operation must be supported. NVIDIA GPU acceleration is
    optional.
13. Never commit API keys, local databases, downloaded audio,
    transcripts, model files, vector data, or other user-generated data.
14. Respect applicable platform terms, copyright, privacy, and
    content-access restrictions. Do not bypass access controls.

## Development workflow

-   Implement the project phase by phase according to
    `docs/DEVELOPMENT_PLAN.md`.
-   Read `docs/ARCHITECTURE.md` before making structural decisions.
-   Do not implement later phases prematurely unless explicitly
    requested.
-   Before adding a dependency, explain why it is needed and check
    whether an existing dependency already provides the capability.
-   Prefer small, testable modules with explicit input and output
    contracts.
-   Add unit tests for processing logic and integration tests for
    database/vector-store behavior.
-   Run relevant tests, linting, and type checks after changes. Report
    exactly what was run and whether it passed.
-   Do not claim a feature is complete merely because code was
    generated.
-   Update architecture and development documentation when an approved
    design decision changes.
-   Keep configuration centralized and validate it at application
    startup.
-   Use structured logging. Do not log secrets or entire private
    transcripts unnecessarily.
-   Handle external API failures, rate limits, timeouts, retries, and
    cancellation explicitly.
-   Avoid silent fallbacks. Record which transcript source, ASR model,
    translation path, embedding model, and LLM provider were used.

## Data and processing rules

### Playlist discovery

-   Store playlist identity and each accessible video's stable YouTube
    ID, title, URL, duration, playlist position, and discovery status.
-   Re-running discovery must update or reconcile existing records
    rather than create duplicates.
-   Do not assume playlist position is a permanent identifier.

### Transcript acquisition

-   Prefer suitable manually created or auto-generated captions.
-   Use audio-only download plus local ASR only when captions are
    unavailable or unsuitable.
-   Validate transcript text and timestamps before marking the
    transcript stage complete.
-   Keep temporary audio until the transcript has been persisted and
    validated; then it may be deleted according to configuration.

### Translation

-   Preserve each source segment's start and end times.
-   Keep English text unchanged.
-   Translate supported languages into English.
-   Preserve technical terms, code identifiers, library names, API
    names, and proper nouns where appropriate.
-   Record unsupported languages and translation failures explicitly;
    never silently index untranslated text as English.
-   Translation output must remain traceable to its source segment(s).

### Chunking and embeddings

-   Chunk within a video boundary; never combine content from different
    videos in one chunk.
-   Prefer sentence/semantic boundaries over arbitrary character
    slicing.
-   Store start and end times covering the source segments represented
    by the chunk.
-   Use the same embedding model and preprocessing for document chunks
    and user queries.
-   Record embedding model name and version/configuration with index
    metadata.

### Qdrant

-   Use a named collection with an explicitly configured vector
    dimension and distance metric.
-   Store English chunk text and source metadata in payloads.
-   Use deterministic point IDs and idempotent upserts.
-   Verify writes before advancing the corresponding SQLite state.
-   Implement reconciliation for the case where Qdrant succeeds but the
    SQLite checkpoint update fails.

### Answer generation

-   Provide the LLM only with retrieved evidence and required source
    metadata.
-   Instruct it to distinguish evidence from general explanation and to
    abstain when evidence is insufficient.
-   Construct YouTube timestamp URLs from stored video IDs and start
    seconds in application code, not by asking the LLM to invent links.
-   Return structured sources separately from generated prose.
-   Validate that every displayed source refers to a retrieved chunk.

## Security and privacy

-   Read secrets from environment variables or local secret
    configuration; never hard-code them.
-   Keep `.env`, local data, logs containing sensitive content, and
    model caches out of Git.
-   Do not expose Qdrant or internal worker interfaces publicly by
    default.
-   Bind the local application to localhost by default unless the user
    explicitly configures remote access.
-   Validate playlist URLs and API inputs.
-   Do not execute downloaded content as code.

## Compatibility

-   Target supported Linux, Windows (via WSL2 where needed), and macOS
    usage where dependencies permit. Docker is not required.
-   Document platform-specific limitations honestly.
-   CPU-only is the baseline. GPU support is an optional acceleration
    path and must not be required for installation.
-   Pin or constrain dependencies and document tested versions.

## Definition of done for a change

A change is done only when: 1. Its behavior matches the approved phase
and architecture. 2. Inputs, outputs, and failure behavior are
documented where relevant. 3. Tests cover normal behavior and important
failure cases. 4. No secrets or generated user data are included. 5.
Relevant checks have been run and their results reported. 6.
Documentation is updated if setup, behavior, or architecture changed.
