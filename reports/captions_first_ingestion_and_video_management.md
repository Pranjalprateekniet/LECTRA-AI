# Captions-First Ingestion and Playlist Video Management Report

## 1. Executive Summary

This release completes the captions-first ingestion pipeline, offline Argos translation integration, fixed 75-second / 5-second overlap chunking, and individual video deletion with complete database, vector store, artifact, and worker race safety.

Automatic execution of Whisper during ingestion is completely disabled, preventing CPU overload and system crashes. The system strictly prefers existing captions, prioritizes English auto-generated captions, supports translating non-English caption tracks (such as Hindi) offline into English, and provides robust video removal capabilities on both backend and frontend.

---

## 2. Key Changes & Architecture

### 2.1 Captions-First Priority & Track Selection
- **Module**: `core/src/lectra_core/transcript/ytdlp_extractor.py` (`select_best_track`)
- **Priority Order**:
  1. English auto-generated captions (`automatic_captions` matching `'en'` or prefix `'en-'`).
  2. English manual captions (`subtitles` matching `'en'`).
  3. Hindi manual captions (`hi`).
  4. Hindi auto-generated captions (`hi`).
  5. Other manual caption tracks.
  6. Other auto-generated caption tracks.
- **Auto-translated skip**: Tracks with YouTube machine translation (`tlang=`) are skipped to preserve pristine source transcripts.

### 2.2 Offline Argos Translate Integration
- **Module**: `core/src/lectra_core/translation/service.py` (`TranslationService`)
- **Offline Configuration**:
  - Sets `ARGOS_PACKAGES_DIR` to `data/models/argos-packages`.
  - Configures writable `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`.
  - Monkeys-patches Stanza sentence boundary detection with `download_method=DownloadMethod.REUSE_RESOURCES` to ensure zero external network calls.
- **Segment Translation**:
  - `translate_segments`: Preserves sequence ordering, segment index, `start_seconds`, and `end_seconds`.
  - Converts text to English while maintaining timestamp alignment.
  - If language is unsupported, raises `UnsupportedLanguageError` and records failure as `UNSUPPORTED_LANGUAGE`. Untranslated text is never silently indexed.

### 2.3 Whisper Decoupling & Failure Recording
- **Module**: `core/src/lectra_core/transcript/service.py` (`TranscriptService`)
- `TranscriptService` does not instantiate `FasterWhisperTranscriber` by default.
- When captions are unavailable (`CaptionsUnavailableError`), the video is marked `NEEDS_TRANSCRIPTION` with `discovery_error="CAPTIONS_UNAVAILABLE"` and the stage is set to `SKIPPED` with `error_category="CAPTIONS_UNAVAILABLE"`.
- Whisper is not automatically run and audio is never downloaded during normal ingestion.

### 2.4 Fixed 75-Second / 5-Second Overlap Chunking
- **Module**: `core/src/lectra_core/chunking/service.py` (`ChunkingService`)
- Fixed sliding window:
  - Duration: 75.0 seconds
  - Overlap: 5.0 seconds
  - Stride: 70.0 seconds
- Window progression:
  - Chunk 1: 0.0s to 75.0s
  - Chunk 2: 70.0s to 145.0s
  - Chunk 3: 140.0s to 215.0s
  - Final partial chunk: covers up to video end time.
- Empty windows are omitted. Deterministic UUID5 chunk identifiers are preserved.

### 2.5 Playlist Video Deletion (Backend & Frontend)
- **Backend Endpoint**: `DELETE /api/v1/playlists/{playlist_id}/videos/{video_id}`
  - Validates video belongs to playlist.
  - Cascading SQLite deletion of video metadata, processing stages, transcript segments, and chunks.
  - Deletes point vectors in Qdrant via `QdrantVectorStore.delete_points_by_video_id`.
  - Deletes local artifacts: `data/artifacts/transcripts/{youtube_id}_*` and temporary audio.
  - Cancels queued or running background jobs for the video (`Job.status = "CANCELLED"`).
  - Recalculates and updates playlist `video_count`.
- **Worker Race Safety**:
  - In `core/src/lectra_core/worker.py`, video jobs check if the video was deleted before executing; if deleted, the job safely exits without failing or resurrecting records.
  - In `TranscriptService`, `ChunkingService`, and `IndexingService`, database existence of `Video` is verified prior to persisting transcripts, chunks, or upserting points to Qdrant.
- **Frontend UI**:
  - Added delete button with `TrashIcon` to each video in `VideoProcessingTable.tsx`.
  - Confirmation modal displaying video title, YouTube ID, and warning.
  - Optimistic deletion in `page.tsx` updating video counts and progress metrics with automatic error rollback if API fails.

---

## 3. Verification & Test Results

### 3.1 Unit and Integration Tests
- **Frontend Test Suite**:
  ```bash
  npm --prefix frontend test
  ```
  Result: 4 passed, 0 failed.
- **Frontend Production Build**:
  ```bash
  npm --prefix frontend run build
  ```
  Result: Compiled successfully with zero TypeScript or lint errors.
- **Core Test Suite**:
  ```bash
  pytest core/tests/ -k "not real_playlist"
  ```
  Result: 151 passed, 0 failed, 3 deselected (live YouTube integration tests).
- **Backend Test Suite**:
  ```bash
  pytest backend/tests/
  ```
  Result: 24 passed, 0 failed.
- **Newly Added Feature Tests**:
  ```bash
  pytest core/tests/test_captions_first_and_translation.py backend/tests/test_video_deletion.py
  ```
  Result: 9 passed, 0 failed.
- **Code Linter**:
  ```bash
  ruff check core/ backend/
  ```
  Result: All checks passed.
