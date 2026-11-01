import test from "node:test";
import assert from "node:assert/strict";
import {
  CHAT_STORAGE_KEY,
  SELECTED_CITATION_STORAGE_KEY,
  isValidChatMessage,
  loadChatHistory,
  saveChatHistory,
  loadSelectedCitation,
  saveSelectedCitation,
  clearChatStorage,
} from "../src/lib/chatStorage.ts";
import { findFirstValidCitation } from "../src/lib/citations.ts";
import type { ChatMessage, CitationItem } from "../src/types/api";

// Simple in-memory LocalStorage mock for Node.js test environment
class MockLocalStorage {
  private store: Map<string, string> = new Map();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }
}

const mockStorage = new MockLocalStorage();
// Set up globalThis.window.localStorage
(globalThis as unknown as { window: { localStorage: MockLocalStorage } }).window = {
  localStorage: mockStorage,
};

test("isValidChatMessage correctly identifies valid and invalid chat messages", () => {
  const validUserMsg: ChatMessage = {
    id: "user-1",
    role: "user",
    content: "What is Fractional Knapsack?",
    timestamp: "2026-11-02T00:00:00.000Z",
    playlist_id: "pl-1",
  };

  const validAssistantMsg: ChatMessage = {
    id: "assistant-2",
    role: "assistant",
    content: "Fractional Knapsack is a greedy algorithm...",
    status: "answered",
    citations: [
      {
        source_id: "S1",
        video_title: "Fractional Knapsack Lecture",
        youtube_id: "vid_123",
        chunk_index: 0,
        start_seconds: 45,
        end_seconds: 120,
        youtube_url: "https://www.youtube.com/watch?v=vid_123&t=45s",
      },
    ],
    timestamp: "2026-11-02T00:00:05.000Z",
    playlist_id: "pl-1",
  };

  assert.equal(isValidChatMessage(validUserMsg), true);
  assert.equal(isValidChatMessage(validAssistantMsg), true);

  // Invalid cases
  assert.equal(isValidChatMessage(null), false);
  assert.equal(isValidChatMessage(undefined), false);
  assert.equal(isValidChatMessage("string"), false);
  assert.equal(isValidChatMessage({}), false);
  assert.equal(isValidChatMessage({ ...validUserMsg, id: "" }), false);
  assert.equal(isValidChatMessage({ ...validUserMsg, role: "moderator" }), false);
  assert.equal(isValidChatMessage({ ...validUserMsg, content: 123 }), false);
  assert.equal(isValidChatMessage({ ...validUserMsg, timestamp: null }), false);
  assert.equal(isValidChatMessage({ ...validAssistantMsg, citations: "invalid" }), false);
  assert.equal(
    isValidChatMessage({
      ...validAssistantMsg,
      citations: [{ youtube_id: "", start_seconds: "invalid" }],
    }),
    false
  );
});

test("saveChatHistory and loadChatHistory preserve messages and citations in exact order", () => {
  mockStorage.clear();

  const msg1: ChatMessage = {
    id: "user-101",
    role: "user",
    content: "Explain Dijkstra algorithm",
    timestamp: "2026-11-02T00:01:00.000Z",
  };

  const msg2: ChatMessage = {
    id: "assistant-102",
    role: "assistant",
    content: "Dijkstra is used for single-source shortest paths.",
    status: "answered",
    citations: [
      {
        source_id: "S1",
        video_title: "Graph Theory Lecture 5",
        youtube_id: "yt_graph_5",
        chunk_index: 2,
        start_seconds: 110,
        end_seconds: 185,
        youtube_url: "https://youtube.com/watch?v=yt_graph_5&t=110s",
        message_id: "assistant-102",
      },
    ],
    timestamp: "2026-11-02T00:01:03.000Z",
  };

  saveChatHistory([msg1, msg2]);

  const loaded = loadChatHistory();
  assert.equal(loaded.length, 2);
  assert.deepEqual(loaded[0], msg1);
  assert.deepEqual(loaded[1], msg2);
  assert.equal(loaded[1].citations?.length, 1);
  assert.equal(loaded[1].citations[0].youtube_id, "yt_graph_5");
  assert.equal(loaded[1].citations[0].start_seconds, 110);
});

test("loadChatHistory handles empty and malformed localStorage data safely", () => {
  mockStorage.clear();

  // 1. Empty storage returns empty array
  assert.deepEqual(loadChatHistory(), []);

  // 2. Corrupted JSON syntax -> safely returns []
  mockStorage.setItem(CHAT_STORAGE_KEY, "{ broken json syntax !!!");
  assert.deepEqual(loadChatHistory(), []);

  // 3. Valid JSON but not an array -> safely returns []
  mockStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify({ message: "not an array" }));
  assert.deepEqual(loadChatHistory(), []);

  mockStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(12345));
  assert.deepEqual(loadChatHistory(), []);

  mockStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify("a string"));
  assert.deepEqual(loadChatHistory(), []);

  // 4. Array containing valid and invalid items -> filters out invalid items cleanly
  const mixed = [
    { id: "user-1", role: "user", content: "Good message", timestamp: "2026-11-02T00:00:00Z" },
    { bad: "data", invalid: true },
    null,
    42,
  ];
  mockStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(mixed));
  const restored = loadChatHistory();
  assert.equal(restored.length, 1);
  assert.equal(restored[0].id, "user-1");
});

test("saveSelectedCitation and loadSelectedCitation persist citation state", () => {
  mockStorage.clear();

  const citation: CitationItem = {
    source_id: "S1",
    video_title: "Knapsack Lecture",
    youtube_id: "yt_knapsack",
    chunk_index: 0,
    start_seconds: 30,
    end_seconds: 90,
    youtube_url: "https://youtube.com/watch?v=yt_knapsack&t=30s",
  };

  // Initially null
  assert.equal(loadSelectedCitation(), null);

  // Save and restore
  saveSelectedCitation(citation);
  const loaded = loadSelectedCitation();
  assert.deepEqual(loaded, citation);

  // Saving null or invalid citation removes from storage
  saveSelectedCitation(null);
  assert.equal(loadSelectedCitation(), null);

  // Corrupted citation in storage -> returns null
  mockStorage.setItem(SELECTED_CITATION_STORAGE_KEY, "{ bad json");
  assert.equal(loadSelectedCitation(), null);
});

test("clearChatStorage clears all stored chat data", () => {
  mockStorage.clear();

  saveChatHistory([
    { id: "u-1", role: "user", content: "Hello", timestamp: "2026-11-02T00:00:00Z" },
  ]);
  saveSelectedCitation({
    source_id: "S1",
    video_title: "Test",
    youtube_id: "yt_test",
    chunk_index: 0,
    start_seconds: 10,
    end_seconds: 20,
    youtube_url: "https://youtube.com/watch?v=yt_test&t=10s",
  });

  assert.equal(loadChatHistory().length, 1);
  assert.ok(loadSelectedCitation() !== null);

  // Clear
  clearChatStorage();

  assert.deepEqual(loadChatHistory(), []);
  assert.equal(loadSelectedCitation(), null);
});

test("Simulated Tab Switching & Component Unmount Sequence: Full conversation restored", () => {
  mockStorage.clear();

  // --- Session 1: User asks question on Chatbot tab ---
  let messages: ChatMessage[] = [];
  let selectedCitation: CitationItem | null = null;

  // User sends "What is Greedy approach?"
  const userMsg1: ChatMessage = {
    id: `user-${Date.now()}-1`,
    role: "user",
    content: "What is Greedy approach?",
    timestamp: new Date().toISOString(),
  };
  messages.push(userMsg1);
  saveChatHistory(messages);

  // Assistant responds with citations from Greedy video
  const assistantMsg1: ChatMessage = {
    id: `assistant-${Date.now()}-2`,
    role: "assistant",
    content: "A greedy algorithm builds a solution piece by piece...",
    status: "answered",
    citations: [
      {
        source_id: "S1",
        video_title: "Greedy Algorithms Introduction",
        youtube_id: "yt_greedy_intro",
        chunk_index: 0,
        start_seconds: 15,
        end_seconds: 80,
        youtube_url: "https://www.youtube.com/watch?v=yt_greedy_intro&t=15s",
        message_id: "assistant-msg-1",
      },
    ],
    timestamp: new Date().toISOString(),
  };
  messages.push(assistantMsg1);
  selectedCitation = findFirstValidCitation(assistantMsg1.citations!);
  saveChatHistory(messages);
  saveSelectedCitation(selectedCitation);

  assert.equal(messages.length, 2);
  assert.equal(selectedCitation?.youtube_id, "yt_greedy_intro");

  // --- Step 2: User switches to Data Ingestion tab ---
  // Chatbot component gets unmounted! Local component variables are discarded.
  messages = [];
  selectedCitation = null;

  // --- Step 3: User returns to Revision Chatbot tab ---
  // Chatbot component remounts and hydrates from localStorage:
  const restoredMessages = loadChatHistory();
  const restoredCitation =
    loadSelectedCitation() ||
    (restoredMessages.length > 0 &&
      restoredMessages[restoredMessages.length - 1].role === "assistant" &&
      restoredMessages[restoredMessages.length - 1].citations
        ? findFirstValidCitation(
            restoredMessages[restoredMessages.length - 1].citations!
          )
        : null);

  // Verify all messages and citations are restored in original order
  assert.equal(restoredMessages.length, 2);
  assert.equal(restoredMessages[0].role, "user");
  assert.equal(restoredMessages[0].content, "What is Greedy approach?");
  assert.equal(restoredMessages[1].role, "assistant");
  assert.equal(restoredMessages[1].citations?.length, 1);
  assert.equal(restoredMessages[1].citations![0].youtube_id, "yt_greedy_intro");
  assert.equal(restoredCitation?.youtube_id, "yt_greedy_intro");
  assert.equal(restoredCitation?.start_seconds, 15);

  // --- Step 4: User sends a follow-up question after restoration ---
  const userMsg2: ChatMessage = {
    id: `user-${Date.now()}-3`,
    role: "user",
    content: "Can you give an example of Greedy?",
    timestamp: new Date().toISOString(),
  };
  const updatedMessages = [...restoredMessages, userMsg2];
  saveChatHistory(updatedMessages);

  // Verify history contains 3 messages without duplicates
  const finalLoaded = loadChatHistory();
  assert.equal(finalLoaded.length, 3);
  assert.equal(finalLoaded[0].content, "What is Greedy approach?");
  assert.equal(finalLoaded[2].content, "Can you give an example of Greedy?");

  // --- Step 5: User explicitly clears chat ---
  clearChatStorage();
  assert.deepEqual(loadChatHistory(), []);
  assert.equal(loadSelectedCitation(), null);
});
