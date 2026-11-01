# Phase 8.2 — Split-Screen Revision Chatbot with Embedded YouTube Player

**Date:** 2026-11-01
**Project:** Lectra (YouTube Revision RAG)
**Status:** Complete & Verified

---

## 1. Executive Summary

Phase 8.2 enhances the Lectra Revision Chatbot with a **two-panel split-screen interface** featuring an embedded official YouTube lecture player directly alongside the conversational revision interface.

Previously, clicking a cited source opened an external browser tab to YouTube. Now, students can query their lecture material on the left and immediately watch the exact verified lecture video segment on the right at the precise starting timestamp without ever leaving the revision workspace.

The existing backend RAG generation pipeline, Groq GPT-OSS-120B integration, Qdrant Cloud vector index, and the Phase 8 Data Ingestion Dashboard are 100% preserved.

---

## 2. Layout & Architectural Design

### 2.1 Two-Panel Split Screen

The layout is implemented in [`frontend/src/components/ChatInterface.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatInterface.tsx) within an overarching full-height container (`h-[calc(100vh-125px)] min-h-[640px]`):

1. **Left Panel: Chat Interface (54% desktop width)**:
   - Houses the scrollable conversation history (`overflow-y-auto`).
   - Renders user message bubbles and assistant response cards with status badges (`answered`, `partially_answered`, `insufficient_context`).
   - Renders inline interactive citation pills (e.g. `[S1]`, `[S2]`) directly inside the answer text.
   - Renders expandable source cards showing chunk duration, video title, and verbatim transcript excerpts.
   - Anchors a **fixed message input bar** at the bottom so students can type follow-ups while browsing conversation history.

2. **Right Panel: Embedded YouTube Lecture Player (46% desktop width)**:
   - Implemented in [`frontend/src/components/YouTubePlayerPanel.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/YouTubePlayerPanel.tsx).
   - Features an official YouTube iframe player in a responsive 16:9 aspect ratio container (`aspect-video`).
   - Displays the active video's title, chunk index, formatted timestamp interval (`MM:SS – MM:SS`), and a direct link to YouTube.
   - Below the video player, renders an active **Verified Transcript Excerpt** panel displaying the exact text corresponding to the playing segment.
   - Provides a clean standby state when no source is selected yet.

---

## 3. Interactive Source Selection Mechanism

### 3.1 Interaction Flow
1. When an assistant response arrives, all cited sources are indexed as `[S1]`, `[S2]`, etc.
2. If the player has no active video, the first citation of the response is loaded as a sensible default.
3. Clicking either an **inline citation pill** (`[S1]`) or a **source card** in the sources list:
   - Sets `selectedCitation` in central React state.
   - Highlights the source card with an active border (`border-indigo-500`), subtle glow (`ring-1 ring-indigo-500/50`), and an animated `▶ Playing` pill.
   - Dynamically reloads the YouTube iframe embed URL:
     ```
     https://www.youtube.com/embed/{youtube_id}?start={int(start_seconds)}&autoplay=1&rel=0
     ```
   - Uses `key={`${selectedCitation.youtube_id}-${startSec}`}` so that selecting a different chunk from the same video forces the iframe to immediately seek to the new start timestamp.
4. When the user asks a subsequent question, the player retains its currently playing video and timestamp until another citation is explicitly selected.

---

## 4. YouTube Player Implementation & Fallbacks

- **Embed URL Construction**: Formats the verified 11-character `youtube_id` with `start={int(start_seconds)}&autoplay=1&rel=0`.
- **Content Restriction Fallback**: If YouTube restricts iframe embedding for a particular network or account, an error boundary card renders a direct *"Watch on YouTube at MM:SS"* button linking to `selectedCitation.youtube_url`.
- **Zero Hallucination Guarantee**: Video IDs and timestamps are exclusively populated from SQLite and Qdrant retrieval records (`CitationItem`).

---

## 5. Responsive Behavior

| Screen Size | Layout | Behavior |
|---|---|---|
| **Desktop (`lg` / $\ge 1024\text{px}$)** | Split Screen (54% Chat / 46% Player) | Side-by-side simultaneous revision and lecture playback. |
| **Tablet / Mobile ($< 1024\text{px}$)** | Adaptive Tab Switcher | Clean segment toggle (`Chat` vs. `Lecture Video`). Selecting a source card automatically switches to the player tab so mobile students see the video immediately. The chat input remains permanently pinned at the bottom. |

---

## 6. End-to-End Verification Matrix

The 12-point test verification was executed against the running backend with the 5-video Greedy Algorithms playlist:

| # | Test Scenario | Verified Behavior | Status |
|---|---|---|:---:|
| 1 | **Question & Answer Flow** | Asked *"What is the greedy choice in N meetings in one room and how are meetings sorted?"* -> Returned `answered` with 2 citations. | **Passed** |
| 2 | **Source Card Expansion** | Expanded source cards -> Displayed verbatim transcript text, chunk index, and timestamp ranges. | **Passed** |
| 3 | **First Source Selection** | Clicked `[S2]` -> Embed loaded `https://www.youtube.com/embed/II6ziNnub1Q?start=174&autoplay=1&rel=0`. Card marked active with `Playing` badge. | **Passed** |
| 4 | **Video Title & Metadata** | Title *"N meetings In One Room | Greedy Algorithm"* and timestamp `02:54 – 04:22` displayed above player. | **Passed** |
| 5 | **Timestamp Precision** | Verified `start=174` corresponds to $174.08\text{s}$ start timestamp. | **Passed** |
| 6 | **Second Source Selection** | Clicked `[S5]` from same response -> Embed immediately reloaded to `https://www.youtube.com/embed/II6ziNnub1Q?start=261&autoplay=1&rel=0`. | **Passed** |
| 7 | **Timestamp Seeking** | Verified iframe dynamic key forced seek to second timestamp ($261.6\text{s}$). | **Passed** |
| 8 | **Multi-Turn Persistence** | Asked follow-up query (*"What is the Fractional Knapsack problem?"*) -> Player retained `[S5]` video selection while new question was answered. | **Passed** |
| 9 | **Partially Answered Flow** | Tested Knapsack comparison query -> Returned `partially_answered` with 4 citations; source selection worked seamlessly. | **Passed** |
| 10 | **Insufficient Context Flow** | Tested negative query (Dijkstra) -> Returned `insufficient_context` with 0 citations; player retained existing video state without disruption. | **Passed** |
| 11 | **Responsive Switcher** | Mobile toggle (`Chat` / `Lecture Video`) switched panels cleanly; chat input remained pinned at bottom. | **Passed** |
| 12 | **Data Ingestion Tab Integrity** | Switched back to Tab 1 -> All 6 pipeline stages, statistics dashboard, and activity log fully functional. | **Passed** |

---

## 7. Build, Linting & Type Checks

| Check | Tool | Result | Details |
|---|---|---|---|
| **Frontend Production Build** | Next.js 16.4.3 (Turbopack) | **Passed** | 0 warnings, 0 errors, static pages built in 512ms. |
| **Backend Unit & Generation Tests** | Pytest 9.2.0 | **40 / 40 Passed** | All 40 tests passed in 5.41s. |
| **Python Linter** | Ruff 0.9.x | **Passed** | 0 errors across `backend/` and `core/`. |
| **Python Type Checker** | Mypy 1.15.x | **Passed** | 0 errors across 54 source files. |

---

## 8. Files Changed / Added

- **Added**:
  - [`frontend/src/components/YouTubePlayerPanel.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/YouTubePlayerPanel.tsx): Embedded YouTube iframe player with title, timestamp badge, transcript excerpt, and standby state.
- **Enhanced**:
  - [`frontend/src/components/ChatInterface.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatInterface.tsx): Implemented split-screen 54%/46% desktop layout, mobile view switcher, fixed bottom input, and active citation state management.
  - [`frontend/src/components/ChatMessageBubble.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/ChatMessageBubble.tsx): Added clickable inline citation tokens (`[S1]`, `[S2]`) inside answer prose and passed selection handler down to source cards.
  - [`frontend/src/components/SourceCard.tsx`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/frontend/src/components/SourceCard.tsx): Added `isSelected` active styling, `onSelect` callback, and `Playing` status indicator.
- **Report**:
  - [`reports/phase8_2_split_screen_chatbot.md`](file:///mnt/data/AI%20ML/PROJECTS/YOUTUBE%20REVISION%20RAG/reports/phase8_2_split_screen_chatbot.md): This report.
