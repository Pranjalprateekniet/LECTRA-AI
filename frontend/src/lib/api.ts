/**
 * Centralized, strongly typed API client for Lectra Frontend.
 */

import {
  ActivityEventResponse,
  AnswerResponse,
  GenerationRequest,
  HealthData,
  Playlist,
  PlaylistStatusResponse,
  PlaylistSubmitResponse,
  RetryResponse,
  VideoResponse,
} from "@/types/api";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;
  details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    let jsonDetails: unknown = null;
    try {
      jsonDetails = await res.json();
      if (typeof jsonDetails === "object" && jsonDetails !== null && "detail" in jsonDetails) {
        errorDetail = String((jsonDetails as { detail: unknown }).detail);
      }
    } catch {
      // not JSON
    }
    throw new ApiError(errorDetail, res.status, jsonDetails);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** Check backend health status */
  async getHealth(): Promise<HealthData> {
    const res = await fetch(`${BASE_URL}/api/v1/health`, { cache: "no-store" });
    return handleResponse<HealthData>(res);
  },

  /** List all registered playlists */
  async getPlaylists(): Promise<Playlist[]> {
    const res = await fetch(`${BASE_URL}/api/v1/playlists`, { cache: "no-store" });
    return handleResponse<Playlist[]>(res);
  },

  /** Get single playlist metadata */
  async getPlaylist(id: string): Promise<Playlist> {
    const res = await fetch(`${BASE_URL}/api/v1/playlists/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    return handleResponse<Playlist>(res);
  },

  /** Get playlist status & statistics */
  async getPlaylistStatus(id: string): Promise<PlaylistStatusResponse> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/${encodeURIComponent(id)}/status`,
      { cache: "no-store" }
    );
    return handleResponse<PlaylistStatusResponse>(res);
  },

  /** Get playlist videos with stage progress */
  async getPlaylistVideos(id: string): Promise<VideoResponse[]> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/${encodeURIComponent(id)}/videos`,
      { cache: "no-store" }
    );
    return handleResponse<VideoResponse[]>(res);
  },

  /** Get playlist chronological activity log */
  async getPlaylistActivity(id: string, limit = 50): Promise<ActivityEventResponse[]> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/${encodeURIComponent(id)}/activity?limit=${limit}`,
      { cache: "no-store" }
    );
    return handleResponse<ActivityEventResponse[]>(res);
  },

  /** Submit YouTube playlist URL for discovery */
  async submitPlaylist(url: string): Promise<PlaylistSubmitResponse> {
    const res = await fetch(`${BASE_URL}/api/v1/playlists`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    return handleResponse<PlaylistSubmitResponse>(res);
  },

  /** Retry ingestion for incomplete/failed videos in a playlist */
  async retryPlaylist(id: string): Promise<RetryResponse> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/${encodeURIComponent(id)}/retry`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }
    );
    return handleResponse<RetryResponse>(res);
  },

  /** Retry ingestion for a specific failed video */
  async retryVideo(videoId: string): Promise<RetryResponse> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/videos/${encodeURIComponent(videoId)}/retry`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }
    );
    return handleResponse<RetryResponse>(res);
  },

  /** Delete a video and all associated artifacts, chunks, and vector points */
  async deleteVideo(
    playlistId: string,
    videoId: string
  ): Promise<{ success: boolean; message: string; video_id: string; playlist_id: string }> {
    const res = await fetch(
      `${BASE_URL}/api/v1/playlists/${encodeURIComponent(playlistId)}/videos/${encodeURIComponent(videoId)}`,
      {
        method: "DELETE",
      }
    );
    return handleResponse<{ success: boolean; message: string; video_id: string; playlist_id: string }>(res);
  },

  /** Generate grounded RAG answer with timestamped YouTube citations */
  async generateAnswer(request: GenerationRequest): Promise<AnswerResponse> {
    const res = await fetch(`${BASE_URL}/api/v1/answers/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return handleResponse<AnswerResponse>(res);
  },
};
