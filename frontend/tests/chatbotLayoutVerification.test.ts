import test from "node:test";
import assert from "node:assert/strict";
import { isValidCitation, findFirstValidCitation } from "../src/lib/citations.ts";
import { isValidChatMessage } from "../src/lib/chatStorage.ts";
import type { ChatMessage, CitationItem } from "../src/types/api";

test("Long user question test: wraps cleanly and retains validity", () => {
  const longText = "What is the detailed algorithmic strategy for solving the Fractional Knapsack problem using a greedy approach, and how does it differ from the 0/1 Knapsack dynamic programming solution when items cannot be broken into smaller fractions? ".repeat(5);
  
  const msg: ChatMessage = {
    id: "user-123",
    role: "user",
    content: longText,
    timestamp: new Date().toISOString(),
    playlist_id: "pl-test",
  };

  assert.equal(isValidChatMessage(msg), true);
  assert.equal(msg.content.length > 500, true);
});

test("Long assistant response with multiple citations test: maintains grounding structure", () => {
  const longAnswer = `The Fractional Knapsack problem employs a greedy strategy based on value-to-weight ratios [S1].
First, calculate the ratio for each item and sort items in descending order of their ratio.
Greedily select items with the highest density [S2].
When remaining capacity cannot accommodate the whole item, take the exact fraction required to fill the knapsack [S1].
The time complexity is dominated by the sorting step: O(N log N) [S2].`;

  const citations: CitationItem[] = [
    {
      source_id: "S1",
      video_title: "A Very Long Lecture Title About Greedy Algorithms, Fractional Knapsack, Sorting Strategies and Competitive Programming Examples in C++ and Python",
      youtube_id: "1bCwtgn3pd0",
      chunk_index: 0,
      start_seconds: 45.0,
      end_seconds: 180.0,
      youtube_url: "https://www.youtube.com/watch?v=1bCwtgn3pd0&t=45s",
      text: "In the fractional knapsack problem, we are allowed to break items into smaller pieces, so the optimal substructure property holds and greedy choice property guarantees global optimality. ".repeat(6),
    },
    {
      source_id: "S2",
      video_title: "Another Extremely Long Video Title That Tests Text Overflow In Desktop, Tablet, and Mobile Viewports Without Causing Horizontal Scrollbars",
      youtube_id: "pSVk-5WemQ0",
      chunk_index: 3,
      start_seconds: 240.0,
      end_seconds: 400.0,
      youtube_url: "https://www.youtube.com/watch?v=pSVk-5WemQ0&t=240s",
      text: "Sorting by value/weight ratio takes O(N log N) time, and then we greedily select items until capacity is exhausted. ".repeat(5),
    },
  ];

  const assistantMsg: ChatMessage = {
    id: "assistant-456",
    role: "assistant",
    content: longAnswer,
    status: "answered",
    citations: citations,
    timestamp: new Date().toISOString(),
    playlist_id: "pl-test",
  };

  assert.equal(isValidChatMessage(assistantMsg), true);
  assert.equal(assistantMsg.citations?.length, 2);

  const firstValid = findFirstValidCitation(citations);
  assert.ok(firstValid !== null);
  assert.equal(isValidCitation(firstValid), true);
  assert.equal(firstValid?.source_id, "S1");
  assert.equal(firstValid?.start_seconds, 45.0);

  // Validate that long excerpt length exceeds 800 chars
  assert.equal(citations[0].text!.length > 800, true);
  assert.equal(citations[0].video_title.length > 100, true);
});

test("Partially answered and Insufficient context statuses correctly represented", () => {
  const partialMsg: ChatMessage = {
    id: "assistant-partial",
    role: "assistant",
    content: "Only part of this topic is covered in your lectures [S1].",
    status: "partially_answered",
    citations: [
      {
        source_id: "S1",
        video_title: "Partial Topic Video",
        youtube_id: "yt_partial",
        chunk_index: 0,
        start_seconds: 10,
        end_seconds: 30,
        youtube_url: "https://youtube.com/watch?v=yt_partial&t=10s",
      },
    ],
    timestamp: new Date().toISOString(),
    playlist_id: null,
  };

  const abstainedMsg: ChatMessage = {
    id: "assistant-abstained",
    role: "assistant",
    content: "I do not have sufficient information from the lecture transcripts to answer this question.",
    status: "insufficient_context",
    citations: [],
    timestamp: new Date().toISOString(),
    playlist_id: null,
  };

  assert.equal(isValidChatMessage(partialMsg), true);
  assert.equal(isValidChatMessage(abstainedMsg), true);
  assert.equal(findFirstValidCitation(abstainedMsg.citations || []), null);
});
