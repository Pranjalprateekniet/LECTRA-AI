import test from "node:test";
import assert from "node:assert/strict";
import {
  SELECTED_PLAYLIST_STORAGE_KEY,
  DEFAULT_PLAYLIST_YOUTUBE_ID,
  loadSelectedPlaylistId,
  saveSelectedPlaylistId,
  clearSelectedPlaylistStorage,
  getDefaultPlaylistId,
  resolveActivePlaylistId,
} from "../src/lib/playlistStorage.ts";
import type { Playlist } from "../src/types/api";

// Simple in-memory LocalStorage mock for Node.js test environment
class MockLocalStorage {
  private store: Map<string, string> = new Map();
  public throwOnGet = false;
  public throwOnSet = false;
  public throwOnRemove = false;

  getItem(key: string): string | null {
    if (this.throwOnGet) throw new Error("Storage get access denied");
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    if (this.throwOnSet) throw new Error("Storage set quota exceeded");
    this.store.set(key, String(value));
  }

  removeItem(key: string): void {
    if (this.throwOnRemove) throw new Error("Storage remove access denied");
    this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }
}

const mockStorage = new MockLocalStorage();
(globalThis as unknown as { window: { localStorage: MockLocalStorage } }).window = {
  localStorage: mockStorage,
};

// Fixture playlists matching the actual database records
const samplePlaylists: Playlist[] = [
  {
    id: "2d9ff17e-c3fe-4bf9-8230-0718ecd1af8d",
    youtube_id: "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ",
    url: "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ",
    title: "Greedy Algorithms",
    channel_name: "take U forward",
    video_count: 16,
    status: "INDEXED",
    discovery_error: null,
    created_at: "2026-11-01T00:00:00.000Z",
    updated_at: "2026-11-01T00:00:00.000Z",
    completed_count: 16,
    processing_count: 0,
    failed_count: 0,
    thumbnail_url: null,
  },
  {
    id: "3820e00b-81b6-4f34-9e68-011ddc3d9f98",
    youtube_id: "PLgUwDviBIf0oF6QL8m22w1hIDC1vJ_BHz",
    url: "https://www.youtube.com/playlist?list=PLgUwDviBIf0oF6QL8m22w1hIDC1vJ_BHz",
    title: "Strivers A2Z-DSA Course | DSA Playlist | Placements",
    channel_name: "take U forward",
    video_count: 100,
    status: "INDEXED",
    discovery_error: null,
    created_at: "2026-11-01T00:00:00.000Z",
    updated_at: "2026-11-01T00:00:00.000Z",
    completed_count: 100,
    processing_count: 0,
    failed_count: 0,
    thumbnail_url: null,
  },
  {
    id: "0fd210e4-904f-4127-b539-130cb1497377",
    youtube_id: "PLKnIA16_RmvaTbihpo4MtzVm4XOQa0ER0",
    url: "https://www.youtube.com/playlist?list=PLKnIA16_RmvaTbihpo4MtzVm4XOQa0ER0",
    title: "Generative AI using LangChain",
    channel_name: "CampusX",
    video_count: 24,
    status: "INDEXED",
    discovery_error: null,
    created_at: "2026-11-01T00:00:00.000Z",
    updated_at: "2026-11-01T00:00:00.000Z",
    completed_count: 24,
    processing_count: 0,
    failed_count: 0,
    thumbnail_url: null,
  },
];

test("Scenario 1: Select Greedy Algorithms, verify saved and restored", () => {
  mockStorage.clear();
  const greedy = samplePlaylists[0];

  saveSelectedPlaylistId(greedy.id);
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), greedy.id);

  const loaded = loadSelectedPlaylistId();
  assert.equal(loaded, greedy.id);

  const activeId = resolveActivePlaylistId(samplePlaylists, loaded);
  assert.equal(activeId, greedy.id);
});

test("Scenario 2: Select LangChain, verify saved and restored", () => {
  mockStorage.clear();
  const langchain = samplePlaylists[2];

  saveSelectedPlaylistId(langchain.id);
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), langchain.id);

  const loaded = loadSelectedPlaylistId();
  assert.equal(loaded, langchain.id);

  const activeId = resolveActivePlaylistId(samplePlaylists, loaded);
  assert.equal(activeId, langchain.id);
});

test("Scenario 3: Select Striver's A2Z, verify saved and restored", () => {
  mockStorage.clear();
  const strivers = samplePlaylists[1];

  saveSelectedPlaylistId(strivers.id);
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), strivers.id);

  const loaded = loadSelectedPlaylistId();
  assert.equal(loaded, strivers.id);

  const activeId = resolveActivePlaylistId(samplePlaylists, loaded);
  assert.equal(activeId, strivers.id);
});

test("Scenario 4: Clear saved selection, verify fallback to default playlist (Strivers A2Z)", () => {
  mockStorage.clear();
  // Set LangChain first
  saveSelectedPlaylistId(samplePlaylists[2].id);
  assert.equal(loadSelectedPlaylistId(), samplePlaylists[2].id);

  // Clear selection
  clearSelectedPlaylistStorage();
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), null);
  assert.equal(loadSelectedPlaylistId(), null);

  // Fallback to default
  const activeId = resolveActivePlaylistId(samplePlaylists, loadSelectedPlaylistId());
  assert.equal(activeId, samplePlaylists[1].id); // Strivers A2Z default
});

test("Scenario 5: Save playlist ID that no longer exists (deleted), verify graceful fallback", () => {
  mockStorage.clear();
  const deletedPlaylistId = "deleted-playlist-uuid-9999";

  saveSelectedPlaylistId(deletedPlaylistId);
  const loaded = loadSelectedPlaylistId();
  assert.equal(loaded, deletedPlaylistId);

  // Resolving against existing playlists should fall back to default
  const activeId = resolveActivePlaylistId(samplePlaylists, loaded);
  assert.equal(activeId, samplePlaylists[1].id); // Strivers A2Z default
  // Verify localStorage still holds the original value (not silently overridden during resolution)
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), deletedPlaylistId);
});

test("Requirement 8: resolveActivePlaylistId is pure and never saves default to storage prematurely", () => {
  mockStorage.clear();
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), null);

  const activeId = resolveActivePlaylistId(samplePlaylists, null);
  assert.equal(activeId, samplePlaylists[1].id);

  // localStorage must remain empty until user explicitly saves
  assert.equal(mockStorage.getItem(SELECTED_PLAYLIST_STORAGE_KEY), null);
});

test("Handles matching by YouTube ID as well as database ID", () => {
  const activeId = resolveActivePlaylistId(samplePlaylists, "PLKnIA16_RmvaTbihpo4MtzVm4XOQa0ER0");
  assert.equal(activeId, samplePlaylists[2].id);
});

test("Handles empty playlist array gracefully", () => {
  assert.equal(getDefaultPlaylistId([]), null);
  assert.equal(resolveActivePlaylistId([], "any-id"), null);
  assert.equal(resolveActivePlaylistId([], null), null);
});

test("Handles missing default (Greedy) by falling back to first playlist", () => {
  const withoutGreedy = [samplePlaylists[1], samplePlaylists[2]];
  assert.equal(getDefaultPlaylistId(withoutGreedy), samplePlaylists[1].id);
  assert.equal(resolveActivePlaylistId(withoutGreedy, "unknown-id"), samplePlaylists[1].id);
});

test("Safe error handling when localStorage throws exceptions", () => {
  mockStorage.throwOnGet = true;
  mockStorage.throwOnSet = true;
  mockStorage.throwOnRemove = true;

  // Should not throw, should return null or log warning
  assert.equal(loadSelectedPlaylistId(), null);
  assert.doesNotThrow(() => saveSelectedPlaylistId("some-id"));
  assert.doesNotThrow(() => clearSelectedPlaylistStorage());

  mockStorage.throwOnGet = false;
  mockStorage.throwOnSet = false;
  mockStorage.throwOnRemove = false;
});

