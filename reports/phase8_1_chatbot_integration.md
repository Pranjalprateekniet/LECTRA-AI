# Phase 8.1 — Revision Chatbot Integration Report

**Date:** 2026-11-01
**Project:** Lectra (YouTube Revision RAG)
**Status:** Complete & Verified

---

## 1. Executive Summary

Phase 8.1 delivers the second primary tab of Lectra: the **Revision Chatbot**.

The Revision Chatbot provides an intuitive, conversational question-answering interface powered by the verified **Groq + GPT-OSS-120B** model, connected to the semantic retrieval engine (`google/embeddinggemma-2` 768d vectors and Qdrant Cloud).

Unlike generic AI chat interfaces that hallucinate or provide unverified explanations, Lectra enforces strict grounding rules:
1. Every assistant answer is supported by verified transcript chunks retrieved from the student's lectures.
2. Every cited source displays the original verbatim transcript text excerpt, start/end timestamps, and direct clickable YouTube timestamp links (`https://www.youtube.com/watch?v=...&t=...`).
3. If context is insufficient, the system abstains rather than inventing unsupported claims.
4. Users can scope their queries to a single indexed playlist or search across all indexed lectures.

---

## 2. API Audit Findings & Backend Enhancements

### 2.1 API Audit Summary (from [`reports/phase8_1_chatbot_audit.md`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase8_1_chatbot_audit.md))
- **`POST /api/v1/answers/generate`**: Accepted `GenerationRequest` with `query`, optional `playlist_id`, `video_id`, `youtube_id`, `top_k`, and `score_threshold`. Returned `AnswerResponse` with `status`, `answer`, and `citations`.
- **Gap Identified**: While the backend retrieval service (`SearchResultItem`) retained full transcript text, `CitationItem` did not expose `text`, `chunk_id`, or `playlist_id`. This would prevent the frontend from displaying original transcript excerpts without reconstructing them from the generated answer.
- **Conversational Context Audit**: `GenerationRequest` strictly enforces single-query input (`extra="forbid"`). The backend does not maintain server-side chat session state, ensuring clean embedding generation for dense vector search.

### 2.2 Minimal Backend Changes
To expose verified transcript excerpts without breaking any existing contracts:
1. **[`schemas.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/schemas.py)**:
   Added optional fields to `CitationItem`:
   ```python
   class CitationItem(BaseModel):
       source_id: str
       video_title: str
       youtube_id: str
       chunk_index: int
       start_seconds: float
       end_seconds: float
       youtube_url: str
       text: Optional[str] = Field(default=None, description="Original transcript chunk text excerpt")
       chunk_id: Optional[str] = Field(default=None, description="Unique chunk UUID")
       playlist_id: Optional[str] = Field(default=None, description="Playlist UUID")
   ```
2. **[`service.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/service.py)**:
   In `_synthesize_citations`, populated `text=chunk.text`, `chunk_id=chunk.chunk_id`, and `playlist_id=chunk.playlist_id` from the existing `source_map`.

---

## 3. Implemented Frontend Components

The chatbot interface is implemented using React 19, Next.js 16 (App Router), and Tailwind CSS v4 in [`frontend/src/components/`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/):

### 3.1 [`SourceCard.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/SourceCard.tsx)
- Displays individual supporting lecture sources below each assistant response.
- **Source Identifier**: e.g., `[S1]`, `[S2]`.
- **Video Title & Timestamp**: Formatted `MM:SS` start/end intervals (e.g. `07:19 - 08:48`).
- **Direct YouTube Link**: Clickable link opening the lecture directly at the chunk start timestamp.
- **Collapsible Transcript Excerpt**: Quoted excerpt displaying the exact verbatim chunk text returned by the backend.

### 3.2 [`ChatMessageBubble.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatMessageBubble.tsx)
- **User Bubble**: Styled right-aligned message container with timestamp.
- **Assistant Bubble**:
  - Distinct avatar and header with dynamic status badge:
    - `answered`: Green badge (*"Fully Grounded in Lecture Transcripts"*).
    - `partially_answered`: Amber badge (*"Partially Supported (Missing Info Highlighted)"*).
    - `insufficient_context`: Slate badge (*"Insufficient Lecture Context (Abstention)"*).
  - Clean paragraph-formatted answer.
  - Collapsible **Retrieved Supporting Sources** panel listing all cited chunks via `SourceCard`.
  - Grounding notices for partially answered or abstained queries.

### 3.3 [`ChatInterface.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatInterface.tsx)
- **Control Bar**:
  - Playlist Scope Selector: allows filtering answers to *"All Indexed Playlists"* or a specific playlist (e.g. Greedy Algorithms).
  - LLM Provider Pill: *"Groq GPT-OSS-120B"*.
  - Clear Conversation action with confirmation dialog.
- **Empty State**: Displays starter revision questions (N Meetings, Job Sequencing, Fractional Knapsack, and negative Dijkstra test).
- **Auto-scrolling Conversation History**: Automatically follows new questions and answers.
- **Generating Skeleton**: Pulsing animated bubble during retrieval and Groq generation.
- **Input Area**: Responsive auto-resizing textarea supporting `Enter` to submit and `Shift + Enter` for line breaks.

### 3.4 [`Header.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/Header.tsx) & [`page.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/app/page.tsx)
- Updated navigation tabs to seamlessly toggle between **Tab 1: Data Ingestion** and **Tab 2: Revision Chatbot**.
- Maintained active background polling for Tab 1 while enabling interactive conversation in Tab 2.

---

## 4. Grounded Citation & Transcript Source Handling

Every assistant answer is linked to verified lecture timestamps:
1. `GenerationService` injects citation tokens (`[S1]`, `[S2]`, etc.) into the context.
2. The LLM cites these sources in its JSON response.
3. The backend validates every cited token against `source_map`, extracting start/end seconds and chunk text from the SQLite/Qdrant record.
4. The frontend renders clickable pills and source cards that navigate to:
   ```
   https://www.youtube.com/watch?v={youtube_id}&t={int(start_seconds)}
   ```
5. Original transcript chunk text is rendered directly from `citation.text` — never reconstructed or fabricated in the frontend.

---

## 5. Conversational Context Implementation

- **Session History in UI**: The chat interface maintains the conversation state in browser session memory.
- **Single-Turn Grounding Integrity**: As audited in Phase 8.1, dense retrieval models perform best on focused queries. Individual student questions are sent with their active playlist filter.
- **Limitation Documented**: The backend does not maintain server-side conversation state. Follow-up questions (e.g. *"What about its space complexity?"*) are sent directly to the generation service.

---

## 6. End-to-End Live Test Results

The 10-point test suite was executed against the running backend with the 5-video Greedy playlist:

| # | Test Scenario | Query | Status | Citations | Verified Result |
|---|---|---|---|:---:|---|
| 1 | **Conceptual** | *"What is the greedy choice in N meetings in one room?"* | `answered` | 2 (`[S3]`, `[S4]`) | Selects meeting finishing earliest. 1,282 and 1,315 char excerpts verified. |
| 2 | **Algorithm Steps** | *"Explain the steps to solve the Job Sequencing problem."* | `answered` | 3 (`[S1]`, `[S4]`, `[S5]`) | Explains greedy slot allocation by latest deadline. Verified verbatim excerpts. |
| 3 | **Complexity** | *"What is the time complexity of the Fractional Knapsack algorithm and why?"* | `answered` | 1 (`[S3]`) | Returns $O(n \log n)$ due to value-per-weight sorting. Verified excerpt at $t=524\text{s}$. |
| 4 | **Partially Supported** | *"Explain the difference between Fractional Knapsack and 0/1 Knapsack according to the lecture."* | `insufficient_context` | 0 | Correctly abstains because 0/1 Knapsack is not covered in the Greedy dataset. |
| 5 | **Unsupported (Negative)** | *"How does Dijkstra algorithm find shortest paths in a graph?"* | `insufficient_context` | 0 | Correctly abstains with 0 citations; no hallucinations. |
| 6 | **Multiple Citations** | N Meetings and Job Sequencing queries | `answered` | 2–3 citations | Each citation contains `source_id`, `video_title`, `youtube_url`, and `text`. |
| 7 | **YouTube Links** | All positive queries | Verified | N/A | Formats URL with timestamp parameter: `&t=174`, `&t=518`, etc. |
| 8 | **Playlist Filtering** | Query with non-existent playlist UUID | `insufficient_context` | 0 | Vector search cleanly scopes to playlist; zero chunks retrieved from other sources. |
| 9 | **Input Validation** | Empty or whitespace-only query | HTTP 422 | N/A | Unprocessable Entity returned; client validation also prevents submission. |
| 10 | **Chat Lifecycle** | Send, load, display, clear conversation | Verified | N/A | UI state manages timeline smoothly; auto-scrolls to bottom. |

---

## 7. Build, Linting & Type Checks

| Check | Tool | Result |
|---|---|---|
| **Frontend Production Build** | Next.js 16.4.3 (Turbopack) | **Passed** (0 warnings, 0 errors, static pages built in 537ms) |
| **Backend Unit & Generation Tests** | Pytest 9.2.0 | **40 / 40 Passed** (in 5.97s) |
| **Python Linter** | Ruff 0.9.x | **Passed** (0 errors) |
| **Python Type Checker** | Mypy 1.15.x | **Passed** (0 errors across 54 source files) |

---

## 8. Files Changed / Added

- **Backend / Core**:
  - [`core/src/lectra_core/generation/schemas.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/schemas.py): Added `text`, `chunk_id`, and `playlist_id` to `CitationItem`.
  - [`core/src/lectra_core/generation/service.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/service.py): Populated transcript text and IDs in `_synthesize_citations`.
- **Frontend**:
  - [`frontend/src/types/api.ts`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/types/api.ts): Added `AnswerResponse`, `CitationItem`, `GenerationRequest`, `ChatMessage`.
  - [`frontend/src/lib/api.ts`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/lib/api.ts): Added `generateAnswer` API method.
  - [`frontend/src/components/SourceCard.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/SourceCard.tsx): New component for collapsible transcript chunk sources with YouTube navigation.
  - [`frontend/src/components/ChatMessageBubble.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatMessageBubble.tsx): New component for user/assistant messages with status pills and source lists.
  - [`frontend/src/components/ChatInterface.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatInterface.tsx): New conversational interface with playlist selector, starter chips, input bar, and clear history.
  - [`frontend/src/components/Header.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/Header.tsx): Activated Tab 2 navigation button.
  - [`frontend/src/components/Icons.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/Icons.tsx): Added `SendIcon`, `UserIcon`, `BotIcon`, `TrashIcon`, `BookOpenIcon`.
  - [`frontend/src/app/page.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/app/page.tsx): Integrated `ChatInterface` into Tab 2.
- **Reports**:
  - [`reports/phase8_1_chatbot_audit.md`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase8_1_chatbot_audit.md): Complete backend API audit.
  - [`reports/phase8_1_chatbot_integration.md`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase8_1_chatbot_integration.md): This report.
