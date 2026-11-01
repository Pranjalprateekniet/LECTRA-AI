# Phase 8.1 — Revision Chatbot API & Architecture Audit

**Date:** 2026-11-01
**Project:** Lectra (YouTube Revision RAG)
**Objective:** Mandatory API audit of backend generation, retrieval, citation, and conversation capabilities before frontend implementation.

---

## 1. Existing Backend Endpoints & Capabilities

### 1.1 `POST /api/v1/answers/generate`
- **Location:** [`backend/src/lectra_backend/api/v1/answers.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/backend/src/lectra_backend/api/v1/answers.py)
- **Service:** `GenerationService` in [`core/src/lectra_core/generation/service.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/service.py)
- **Request Contract (`GenerationRequest`):**
  ```python
  class GenerationRequest(BaseModel):
      model_config = ConfigDict(extra="forbid")
      query: str
      top_k: Optional[int] = None
      score_threshold: Optional[float] = None
      playlist_id: Optional[str] = None
      video_id: Optional[str] = None
      youtube_id: Optional[str] = None
  ```
- **Response Contract (`AnswerResponse`):**
  ```python
  class AnswerResponse(BaseModel):
      model_config = ConfigDict(extra="ignore")
      status: Literal["answered", "partially_answered", "insufficient_context"]
      answer: str
      citations: List[CitationItem]
  ```

### 1.2 `POST /api/v1/retrieval/search`
- **Location:** [`backend/src/lectra_backend/api/v1/retrieval.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/backend/src/lectra_backend/api/v1/retrieval.py)
- **Service:** `RetrievalService` in [`core/src/lectra_core/retrieval/service.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/retrieval/service.py)
- **Response Contract (`SearchResponse`):**
  - Returns `results: List[SearchResultItem]`, where each item includes:
    - `chunk_id: str`
    - `video_id: str`
    - `youtube_id: str`
    - `playlist_id: str`
    - `video_title: str`
    - `chunk_index: int`
    - `text: str` (the full original transcript chunk text)
    - `start_seconds: float`
    - `end_seconds: float`
    - `duration_seconds: float`
    - `similarity_score: float`
    - `youtube_url: str`

---

## 2. Capability Audit Matrix

| Required Capability | Status in Current Backend | Field / Source | Gap & Remedy |
|---|---|---|---|
| **Generated Answer** | **Supported** | `AnswerResponse.answer: str` | Matches requirement. |
| **Answer Status** | **Supported** | `AnswerResponse.status` (`answered`, `partially_answered`, `insufficient_context`) | Matches requirement. |
| **Citation IDs** | **Supported** | `CitationItem.source_id: str` (`"S1"`, `"S2"`, etc.) | Matches requirement. |
| **Source Video Titles** | **Supported** | `CitationItem.video_title: str` | Matches requirement. |
| **YouTube Video IDs** | **Supported** | `CitationItem.youtube_id: str` | Matches requirement. |
| **Chunk Start/End Timestamps** | **Supported** | `CitationItem.start_seconds`, `end_seconds` | Matches requirement. |
| **Original Transcript Chunk Text** | **Missing from CitationItem** | Available in `SearchResultItem.text`, but dropped in `_synthesize_citations` | **Requires smallest enhancement:** Add `text: Optional[str] = None` to `CitationItem` and populate from `SearchResultItem.text`. |
| **Citation YouTube URLs** | **Supported** | `CitationItem.youtube_url: str` | Constructed with deterministic timestamp `&t={int(start)}`. |
| **Playlist Association** | **Partially Supported** | Supported as filter in `GenerationRequest.playlist_id`; missing from `CitationItem.playlist_id` | Add `playlist_id: Optional[str] = None` to `CitationItem`. |
| **Multi-turn Conversational Context** | **Not Supported** | Single query input only (`query: str`); `extra="forbid"` | Documented constraint. Maintain session history in frontend UI; do not send unvalidated conversation history to Groq. |

---

## 3. Identified Gaps & Smallest Required Backend Changes

### Gap 1: Transcript Chunk Text Not Exposed in `CitationItem`
**Problem:**
In [`core/src/lectra_core/generation/schemas.py`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/core/src/lectra_core/generation/schemas.py), `CitationItem` contains metadata (title, youtube_id, start/end seconds, youtube_url), but lacks the chunk's text. In Section 5 of the prompt, the assistant response must display its supporting transcript chunks with the original transcript excerpt directly under the answer.

**Evidence from Code:**
In `GenerationService.generate_answer`:
```python
context_res = self.context_builder.build_context(...)
# context_res.source_map has Dict[str, SearchResultItem] with full chunk.text
validated_citations = self._synthesize_citations(
    raw_citations=raw_answer.citations,
    answer_text=raw_answer.answer,
    source_map=context_res.source_map,
)
```
In `_synthesize_citations`:
```python
chunk = source_map[src_id]
citations.append(
    CitationItem(
        source_id=src_id,
        video_title=chunk.video_title,
        youtube_id=chunk.youtube_id,
        chunk_index=chunk.chunk_index,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        youtube_url=chunk.youtube_url,
        # chunk.text was omitted here
    )
)
```

**Proposed Minimal Change:**
1. In `core/src/lectra_core/generation/schemas.py`:
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
2. In `core/src/lectra_core/generation/service.py`:
   Pass `text=chunk.text`, `chunk_id=chunk.chunk_id`, and `playlist_id=chunk.playlist_id` into `CitationItem`.
3. This is 100% backward-compatible: all default values are `None`, existing tests continue to pass without changes, and the frontend gets instant access to original transcript excerpts without reconstructing them.

---

## 4. Multi-Turn Conversational Context Audit

### Backend State:
- `GenerationRequest` strictly enforces `extra="forbid"` and has only `query: str`.
- `GenerationService` injects only `[{"role": "system", ...}, {"role": "user", ...}]` into Groq `generate_chat_completion`.
- The embedding model `google/embeddinggemma-2` embeds single query strings for cosine retrieval against Qdrant. Passing full multi-turn chat history into a dense retrieval embedding model dilutes cosine similarity scores and violates the strict grounding constraints established in Phases 5-7.

### Frontend Implementation Strategy:
- The chat UI maintains a full conversational message list in browser session state (`messages: ChatMessage[]`).
- Follow-up questions are submitted as standalone queries or contextual questions to the backend.
- The UI transparently presents the chat history like a conventional AI chatbot while clearly adhering to backend grounding rules without pretending the backend maintains server-side sessions.
- Future enhancement recommendation: A lightweight query contextualization/reformulation step (e.g. rewriting follow-up pronoun queries using prior turn context) can be added to the backend in a future phase.

---

## 5. Frontend Chatbot Architecture Plan

### 5.1 Tab Switching
In [`frontend/src/app/page.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/app/page.tsx):
- Tab 1: **Data Ingestion Dashboard** (Phase 8)
- Tab 2: **Revision Chatbot** (Phase 8.1 — replacing placeholder banner)

### 5.2 Chatbot Components
1. **`ChatInterface.tsx`**:
   - Central message timeline with auto-scrolling to newest message.
   - User message bubbles with distinct styling.
   - Assistant message bubbles with status badge (`Answered`, `Partially Answered`, `Insufficient Context`).
   - Grounded Answer text formatted with readable markdown.
   - Retrieved Transcript Sources panel below each assistant message:
     - Collapsible card for each cited chunk (`[S1]`, `[S2]`).
     - Video title with YouTube external link and timestamp badge (`12:34 - 14:15`).
     - Verified original transcript excerpt quoted inside formatted card.
     - Direct "Watch on YouTube at mm:ss" button.
   - Input bar with textarea, character counter, send button, Enter/Shift+Enter support, and disabled state while waiting for response.
   - "Clear Conversation" button with confirmation.
   - Quick example prompt chips (e.g., *"How do you solve N meetings in one room?"*, *"What is the time complexity of Job Sequencing?"*, *"How does Fractional Knapsack differ from 0/1 Knapsack?"*).

2. **Playlist Scope Selector**:
   - Dropdown or pill selector allowing the student to filter retrieval:
     - "All Indexed Playlists" (`playlist_id: null`)
     - Selected playlist (e.g., "Greedy Algorithms" `playlist_id: "2d9ff17e-..."`).

3. **Status Indicators**:
   - `answered`: Green badge, full explanation with citations.
   - `partially_answered`: Amber badge, clear highlighting of supported points vs missing lecture content.
   - `insufficient_context`: Slate/rose badge, backend abstention message without fabricating hallucinations.
