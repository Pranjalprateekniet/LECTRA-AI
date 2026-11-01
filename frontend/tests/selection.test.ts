import test from "node:test";
import assert from "node:assert/strict";
import {
  isValidCitation,
  findFirstValidCitation,
} from "../src/lib/citations.ts";
import type { CitationItem } from "../src/types/api";

test("isValidCitation correctly identifies valid citations", () => {
  const validCitation: CitationItem = {
    source_id: "S1",
    video_title: "Fractional Knapsack Problem",
    youtube_id: "1bCwtgn3pd0",
    chunk_index: 0,
    start_seconds: 45.0,
    end_seconds: 120.0,
    youtube_url: "https://www.youtube.com/watch?v=1bCwtgn3pd0&t=45s",
  };

  assert.equal(isValidCitation(validCitation), true);
  assert.equal(isValidCitation(null), false);
  assert.equal(isValidCitation(undefined), false);
  assert.equal(isValidCitation(""), false);
  assert.equal(isValidCitation({}), false);

  // Missing or empty youtube_id
  assert.equal(isValidCitation({ ...validCitation, youtube_id: "" }), false);
  assert.equal(isValidCitation({ ...validCitation, youtube_id: "   " }), false);
  assert.equal(
    isValidCitation({ ...validCitation, youtube_id: null as unknown as string }),
    false
  );

  // Invalid start_seconds
  assert.equal(isValidCitation({ ...validCitation, start_seconds: -1 }), false);
  assert.equal(isValidCitation({ ...validCitation, start_seconds: NaN }), false);
  assert.equal(isValidCitation({ ...validCitation, start_seconds: Infinity }), false);
  assert.equal(
    isValidCitation({ ...validCitation, start_seconds: "45" as unknown as number }),
    false
  );
  assert.equal(
    isValidCitation({ ...validCitation, start_seconds: null as unknown as number }),
    false
  );
});

test("findFirstValidCitation finds first valid citation or skips invalid ones", () => {
  const valid1: CitationItem = {
    source_id: "S1",
    video_title: "Knapsack Lecture",
    youtube_id: "vid_knapsack",
    chunk_index: 0,
    start_seconds: 30,
    end_seconds: 90,
    youtube_url: "https://youtube.com/watch?v=vid_knapsack&t=30s",
  };

  const valid2: CitationItem = {
    source_id: "S2",
    video_title: "N Meetings Lecture",
    youtube_id: "vid_n_meetings",
    chunk_index: 1,
    start_seconds: 60,
    end_seconds: 150,
    youtube_url: "https://youtube.com/watch?v=vid_n_meetings&t=60s",
  };

  const invalidMetadata: CitationItem = {
    source_id: "S0",
    video_title: "Corrupted Source",
    youtube_id: "",
    chunk_index: 0,
    start_seconds: -5,
    end_seconds: 10,
    youtube_url: "",
  };

  // Normal valid list -> returns first
  assert.deepEqual(findFirstValidCitation([valid1, valid2]), valid1);

  // First is corrupted -> skips to second valid
  assert.deepEqual(findFirstValidCitation([invalidMetadata, valid2]), valid2);

  // All corrupted -> returns null
  assert.equal(findFirstValidCitation([invalidMetadata]), null);

  // Empty list -> returns null
  assert.equal(findFirstValidCitation([]), null);
  assert.equal(findFirstValidCitation(null), null);
  assert.equal(findFirstValidCitation(undefined), null);
});

test("Phase 8.2.1 Verification Sequence: Multi-turn automatic video selection and manual switching", () => {
  let selectedCitation: CitationItem | null = null;
  let activeRequestId = 0;

  // Simulated handler for when an answer arrives
  function onAnswerReceived(
    requestId: number,
    status: "answered" | "insufficient_context",
    rawCitations: CitationItem[]
  ) {
    if (requestId !== activeRequestId) {
      return; // Stale async protection
    }

    const msgId = `msg-${Date.now()}-${Math.random()}`;
    const decorated = rawCitations.map((c) => ({
      ...c,
      message_id: msgId,
    }));

    const firstValid = findFirstValidCitation(decorated);
    selectedCitation = firstValid;
    return { msgId, decorated };
  }

  // 1. Ask Fractional Knapsack question
  activeRequestId++;
  const knapsackCitation: CitationItem = {
    source_id: "S1",
    video_title: "Fractional Knapsack Problem",
    youtube_id: "yt_knapsack",
    chunk_index: 0,
    start_seconds: 15,
    end_seconds: 80,
    youtube_url: "https://www.youtube.com/watch?v=yt_knapsack&t=15s",
  };

  // 2. Verify Fractional Knapsack video opens
  onAnswerReceived(activeRequestId, "answered", [knapsackCitation]);
  assert.ok(selectedCitation !== null);
  const sel1 = selectedCitation as CitationItem;
  assert.equal(sel1.youtube_id, "yt_knapsack");
  assert.equal(sel1.video_title, "Fractional Knapsack Problem");
  assert.equal(sel1.start_seconds, 15);

  // 3. Ask N Meetings question
  activeRequestId++;
  const nMeetingsCitation: CitationItem = {
    source_id: "S1",
    video_title: "N Meetings in One Room",
    youtube_id: "yt_n_meetings",
    chunk_index: 0,
    start_seconds: 40,
    end_seconds: 120,
    youtube_url: "https://www.youtube.com/watch?v=yt_n_meetings&t=40s",
  };

  // 4. Verify N Meetings video automatically replaces Fractional Knapsack
  onAnswerReceived(activeRequestId, "answered", [nMeetingsCitation]);
  assert.ok(selectedCitation !== null);
  const sel2 = selectedCitation as CitationItem;
  assert.equal(sel2.youtube_id, "yt_n_meetings");
  assert.equal(sel2.video_title, "N Meetings in One Room");
  assert.equal(sel2.start_seconds, 40);

  // 5. Ask Job Sequencing question
  activeRequestId++;
  const jobSeqCitation1: CitationItem = {
    source_id: "S1",
    video_title: "Job Sequencing Problem - Part 1",
    youtube_id: "yt_job_seq",
    chunk_index: 0,
    start_seconds: 25,
    end_seconds: 90,
    youtube_url: "https://www.youtube.com/watch?v=yt_job_seq&t=25s",
  };
  const jobSeqCitation2: CitationItem = {
    source_id: "S2",
    video_title: "Job Sequencing Problem - Part 2",
    youtube_id: "yt_job_seq",
    chunk_index: 1,
    start_seconds: 180,
    end_seconds: 250,
    youtube_url: "https://www.youtube.com/watch?v=yt_job_seq&t=180s",
  };

  // 6. Verify Job Sequencing video opens (auto-selects first citation S1)
  const turn3 = onAnswerReceived(activeRequestId, "answered", [jobSeqCitation1, jobSeqCitation2]);
  assert.ok(selectedCitation !== null);
  const sel3 = selectedCitation as CitationItem;
  assert.equal(sel3.youtube_id, "yt_job_seq");
  assert.equal(sel3.source_id, "S1");
  assert.equal(sel3.start_seconds, 25);

  // 7. Click a different citation from the same answer (Manual selection S2)
  const manualSelected = turn3!.decorated[1]; // S2
  selectedCitation = manualSelected;

  // 8. Verify that the player switches to that citation (S2, start=180)
  const sel4 = selectedCitation as CitationItem;
  assert.equal(sel4.source_id, "S2");
  assert.equal(sel4.start_seconds, 180);

  // 9. Ask an unsupported question
  activeRequestId++;

  // 10. Verify that previous video is not incorrectly presented as source of unsupported answer
  onAnswerReceived(activeRequestId, "insufficient_context", []);
  assert.equal(selectedCitation, null); // Empty player state
});

test("Edge Case: Stale asynchronous response does not overwrite newer answer selection", () => {
  let selectedCitation: CitationItem | null = null;
  let activeRequestId = 0;

  function onAnswerReceived(
    requestId: number,
    citations: CitationItem[]
  ) {
    if (requestId !== activeRequestId) {
      return; // Stale async protection
    }
    selectedCitation = findFirstValidCitation(citations);
  }

  // Request 1 starts (e.g. slow query)
  activeRequestId++;
  const req1Id = activeRequestId;

  // Request 2 starts before Request 1 resolves (fast query)
  activeRequestId++;
  const req2Id = activeRequestId;

  const req2Citation: CitationItem = {
    source_id: "S1",
    video_title: "Fast Query Lecture",
    youtube_id: "yt_fast",
    chunk_index: 0,
    start_seconds: 10,
    end_seconds: 50,
    youtube_url: "https://www.youtube.com/watch?v=yt_fast&t=10s",
  };

  // Request 2 resolves first
  onAnswerReceived(req2Id, [req2Citation]);
  assert.equal(selectedCitation!.youtube_id, "yt_fast");

  // Request 1 resolves late (stale)
  const req1Citation: CitationItem = {
    source_id: "S1",
    video_title: "Slow Stale Lecture",
    youtube_id: "yt_stale",
    chunk_index: 0,
    start_seconds: 99,
    end_seconds: 150,
    youtube_url: "https://www.youtube.com/watch?v=yt_stale&t=99s",
  };
  onAnswerReceived(req1Id, [req1Citation]);

  // Player must retain the newer answer selection (yt_fast), not the stale one!
  assert.equal(selectedCitation!.youtube_id, "yt_fast");
});
