import type { Playlist } from "../types/api";

export const SELECTED_PLAYLIST_STORAGE_KEY = "lectra_selected_playlist_id_v1";
export const DEFAULT_PLAYLIST_YOUTUBE_ID = "PLgUwDviBIf0oF6QL8m22w1hIDC1vJ_BHz";

/**
 * Load the previously selected playlist ID from localStorage safely.
 * Returns null if localStorage is unavailable, empty, or inaccessible.
 */
export function loadSelectedPlaylistId(): string | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.localStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY);
    if (!raw || raw.trim() === "") return null;
    return raw.trim();
  } catch (err) {
    console.warn("Failed to load selected playlist ID from localStorage:", err);
    return null;
  }
}

/**
 * Persist the selected playlist ID to localStorage safely.
 * If id is null, undefined, or empty, removes the saved selection key.
 */
export function saveSelectedPlaylistId(id: string | null | undefined): void {
  if (typeof window === "undefined") return;

  try {
    if (!id || id.trim() === "") {
      window.localStorage.removeItem(SELECTED_PLAYLIST_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(SELECTED_PLAYLIST_STORAGE_KEY, id.trim());
  } catch (err) {
    console.warn("Failed to save selected playlist ID to localStorage:", err);
  }
}

/**
 * Clear the saved playlist selection from localStorage safely.
 */
export function clearSelectedPlaylistStorage(): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.removeItem(SELECTED_PLAYLIST_STORAGE_KEY);
  } catch (err) {
    console.warn("Failed to clear selected playlist storage from localStorage:", err);
  }
}

/**
 * Get the default playlist ID from a list of playlists.
 * Prefers the canonical Strivers A2Z playlist (PLgUwDviBIf0oF6QL8m22w1hIDC1vJ_BHz).
 * If not found, falls back to the first available playlist.
 * Returns null if the list is empty.
 */
export function getDefaultPlaylistId(playlists: Playlist[]): string | null {
  if (!playlists || playlists.length === 0) return null;
  const preferred = playlists.find((p) => p.youtube_id === DEFAULT_PLAYLIST_YOUTUBE_ID);
  return preferred ? preferred.id : playlists[0].id;
}

/**
 * Pure function to resolve the active playlist selection:
 * 1. If savedId matches an available playlist (by database id or youtube_id), return that playlist's database id.
 * 2. If savedId is missing, deleted, or invalid, fall back to the default playlist.
 * 3. Never writes to localStorage (maintains read-only resolution purity).
 */
export function resolveActivePlaylistId(
  playlists: Playlist[],
  savedId: string | null | undefined
): string | null {
  if (!playlists || playlists.length === 0) return null;

  if (savedId && savedId.trim() !== "") {
    const trimmed = savedId.trim();
    const match = playlists.find((p) => p.id === trimmed || p.youtube_id === trimmed);
    if (match) {
      return match.id;
    }
  }

  return getDefaultPlaylistId(playlists);
}

