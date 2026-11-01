# Ingestion Pipeline Fix: Transcript-to-Chunking Transition

## 1. Executive Summary

The ingestion pipeline previously stopped progressing after the `TRANSCRIPT_ACQUISITION` stage. While discovery, transcript acquisition, and translation functioned as expected, downstream jobs (`chunk_playlist`, `chunk_video`, `index_playlist`, and `index_video`) were defined but never enqueued upon completion of preceding stages.

This fix establishes durable, idempotent automatic stage transitions:
```
DiscoveryService -> extract_transcripts -> chunk_playlist -> index_playlist
```
and at the individual video level:
```
extract_video_transcript -> chunk_video -> index_video
```

---

## 2. Root Cause Analysis

Tracing the execution path through [`core/src/lectra_core/worker.py`](file:///mnt/data/AI ML/PROJECTS/YOUTUBE REVISION RAG/core/src/lectra_core/worker.py) and [`backend/src/lectra_backend/api/v1/playlists.py`](file:///mnt/data/AI ML/PROJECTS/YOUTUBE REVISION RAG/backend/src/lectra_backend/api/v1/playlists.py) revealed the following gaps:

1. **Missing Stage Chaining in Worker Handlers**:
   - `_process_extract_transcripts_job`: Extracted transcripts for eligible videos in a playlist, but never enqueued `CHUNK_PLAYLIST_JOB_TYPE`.
   - `_process_chunk_playlist_job`: Chunked `TRANSCRIPT_READY` videos, but never enqueued `INDEX_PLAYLIST_JOB_TYPE`.
   - `_process_extract_video_transcript_job`: Processed a single video to `TRANSCRIPT_READY`, but never enqueued `CHUNK_VIDEO_JOB_TYPE`.
   - `_process_chunk_video_job`: Processed a single video to `CHUNKED`, but never enqueued `INDEX_VIDEO_JOB_TYPE`.
2. **Coarse Playlist Retry Logic**:
   - `retry_playlist_ingestion` in `playlists.py` previously only enqueued `EXTRACT_TRANSCRIPTS_JOB_TYPE`, ignoring whether all transcripts were already acquired.
3. **Partial Failure Vulnerability**:
   - In playlist chunking and indexing loops, an unhandled exception on a single video previously could abort processing for subsequent videos in the batch.

---

## 3. Implementation Details

### A. Worker Stage Transitions (`core/src/lectra_core/worker.py`)
- **`_process_extract_transcripts_job`**:
  - After transcript extraction, checks for any videos with status `TRANSCRIPT_READY`.
  - If found and no active chunk job exists, enqueues `Job(job_type=CHUNK_PLAYLIST_JOB_TYPE, status="QUEUED", ...)`.
  - Commits the downstream job before evaluating partial extraction errors, ensuring eligible videos continue forward even if some videos failed extraction.
- **`_process_chunk_playlist_job`**:
  - Wrapped each video in a `try/except` block to ensure an issue with one video's cues logs the error, marks that video's `ProcessingStage` as `FAILED`, and continues chunking remaining videos.
  - After processing, checks for videos with status `CHUNKED`. If present, automatically enqueues `Job(job_type=INDEX_PLAYLIST_JOB_TYPE, status="QUEUED", ...)`.
- **`_process_extract_video_transcript_job`**:
  - Upon reaching `TRANSCRIPT_READY`, automatically enqueues `Job(job_type=CHUNK_VIDEO_JOB_TYPE, status="QUEUED", ...)`.
- **`_process_chunk_video_job`**:
  - Upon reaching `CHUNKED`, automatically enqueues `Job(job_type=INDEX_VIDEO_JOB_TYPE, status="QUEUED", ...)`.
- **`_process_index_playlist_job`**:
  - Wrapped each video indexing step to record individual errors on `ProcessingStage` without dropping preceding or subsequent video completions.

### B. Intelligent API Retry Routing (`backend/src/lectra_backend/api/v1/playlists.py`)
- Updated `retry_playlist_ingestion` to inspect playlist video status counts:
  - If pending/failed transcripts: enqueues `EXTRACT_TRANSCRIPTS_JOB_TYPE`.
  - Else if `transcripts_ready > 0`: enqueues `CHUNK_PLAYLIST_JOB_TYPE`.
  - Else if `processing > 0 and total_chunks > 0`: enqueues `INDEX_PLAYLIST_JOB_TYPE`.
  - Because each stage automatically chains into the next, any re-triggered job carries through to full indexing.

---

## 4. Verification and Data Integrity

### Test Suite Execution
- **`core/tests/test_pipeline_chaining.py`** (7 unit and integration tests):
  - `test_extract_transcripts_chains_to_chunk_playlist` — **PASS**
  - `test_chunk_playlist_chains_to_index_playlist` — **PASS**
  - `test_video_level_chaining_extract_chunk_index` — **PASS**
  - `test_chaining_does_not_duplicate_existing_active_jobs` — **PASS**
  - `test_failed_video_during_chunking_does_not_abort_playlist` — **PASS**
  - `test_deleted_video_is_safely_skipped_in_chain` — **PASS**
  - `test_re_running_chunk_playlist_is_idempotent` — **PASS**
- **Full Core Suite (`pytest core/tests/ -k "not real_playlist"`)**: **158 passed**, 3 deselected, 0 failed.
- **Backend API Suite (`pytest backend/tests/`)**: **24 passed**, 0 failed.
- **Ruff Linter (`ruff check core/ backend/`)**: **All checks passed**.
- **Frontend Test Suite (`npm --prefix frontend test`)**: **4 passed**, 0 failed.
- **Frontend Build (`npm --prefix frontend run build`)**: **Success** (Turbopack production build).

### Live Verification on LangChain Playlist (`0fd210e4-904f-4127-b539-130cb1497377`)
The 5 videos that were previously stuck at `TRANSCRIPT_READY` with 0 chunks were processed through the chained pipeline:
1. **Video 0** (*GenAI Roadmap for Beginners*): 43 chunks generated, 43 vectors indexed.
2. **Video 1** (*Generative AI using LangChain*): 14 chunks generated, 14 vectors indexed.
3. **Video 2** (*Introduction to LangChain*): 33 chunks generated, 33 vectors indexed.
4. **Video 3** (*LangChain Components*): 46 chunks generated, 46 vectors indexed.
5. **Video 4** (*LangChain Models*): 88 chunks generated, 88 vectors indexed.
- **Total Chunks in SQLite**: 224 chunks across all 5 videos.
- **Total Points in Qdrant Cloud**: 224 points retrieved and verified (`768-dimensional`, cosine metric).
- **Processing Stages**: All 5 videos reached `INDEXING: COMPLETED` with video status `INDEXED`.
