import type { ChatMessage, CitationItem } from "../types/api";
import { isValidCitation } from "./citations.ts";

export const CHAT_STORAGE_KEY = "lectra_chat_history_v1";
export const SELECTED_CITATION_STORAGE_KEY = "lectra_chat_selected_citation_v1";

/**
 * Validates whether an unknown value conforms to the ChatMessage interface.
 */
export function isValidChatMessage(item: unknown): item is ChatMessage {
  if (!item || typeof item !== "object") return false;
  const msg = item as Record<string, unknown>;

  if (typeof msg.id !== "string" || msg.id.trim() === "") return false;
  if (msg.role !== "user" && msg.role !== "assistant") return false;
  if (typeof msg.content !== "string") return false;
  if (typeof msg.timestamp !== "string") return false;

  if (msg.status !== undefined && typeof msg.status !== "string") return false;
  if (
    msg.playlist_id !== undefined &&
    msg.playlist_id !== null &&
    typeof msg.playlist_id !== "string"
  ) {
    return false;
  }

  if (msg.citations !== undefined) {
    if (!Array.isArray(msg.citations)) return false;
    for (const cit of msg.citations) {
      if (!cit || typeof cit !== "object") return false;
      const c = cit as Record<string, unknown>;
      if (typeof c.youtube_id !== "string" || typeof c.start_seconds !== "number") {
        return false;
      }
    }
  }

  return true;
}

/**
 * Load and validate chat history from localStorage safely.
 * Returns empty array if localStorage is unavailable, empty, or corrupted.
 */
export function loadChatHistory(): ChatMessage[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw || raw.trim() === "") return [];

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      console.warn("Invalid chat history in localStorage: expected array, got", typeof parsed);
      return [];
    }

    const validMessages: ChatMessage[] = [];
    for (const item of parsed) {
      if (isValidChatMessage(item)) {
        validMessages.push(item);
      } else {
        console.warn("Skipping malformed chat message in localStorage:", item);
      }
    }

    return validMessages;
  } catch (err) {
    console.warn("Failed to load chat history from localStorage:", err);
    return [];
  }
}

/**
 * Persist chat history to localStorage safely.
 */
export function saveChatHistory(messages: ChatMessage[]): void {
  if (typeof window === "undefined") return;

  try {
    if (!messages || messages.length === 0) {
      window.localStorage.removeItem(CHAT_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
  } catch (err) {
    console.error("Failed to save chat history to localStorage:", err);
  }
}

/**
 * Load and validate selected citation from localStorage safely.
 */
export function loadSelectedCitation(): CitationItem | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(SELECTED_CITATION_STORAGE_KEY);
    if (!raw || raw.trim() === "") return null;

    const parsed = JSON.parse(raw);
    if (isValidCitation(parsed)) {
      return parsed as CitationItem;
    }
    return null;
  } catch (err) {
    console.warn("Failed to load selected citation from localStorage:", err);
    return null;
  }
}

/**
 * Persist selected citation to localStorage safely.
 */
export function saveSelectedCitation(citation: CitationItem | null): void {
  if (typeof window === "undefined") return;

  try {
    if (!citation || !isValidCitation(citation)) {
      window.localStorage.removeItem(SELECTED_CITATION_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(SELECTED_CITATION_STORAGE_KEY, JSON.stringify(citation));
  } catch (err) {
    console.error("Failed to save selected citation to localStorage:", err);
  }
}

/**
 * Clear all chat-related keys from localStorage.
 */
export function clearChatStorage(): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
    window.localStorage.removeItem(SELECTED_CITATION_STORAGE_KEY);
  } catch (err) {
    console.error("Failed to clear chat storage from localStorage:", err);
  }
}
