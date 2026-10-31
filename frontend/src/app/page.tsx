"use client";

import { useCallback, useEffect, useState } from "react";

interface HealthData {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  database: string;
  execution_device: string;
  components?: {
    api: string;
    database: string;
    qdrant_configured: boolean;
  };
}

interface Playlist {
  id: string;
  youtube_id: string;
  url: string;
  title: string;
  channel_name: string | null;
  video_count: int;
  status: string;
  discovery_error: string | null;
  created_at: string;
  updated_at: string;
}

type int = number;

interface VideoItem {
  id: string;
  playlist_id: string;
  youtube_id: string;
  title: string;
  url: string;
  duration_seconds: number | null;
  position: number;
  status: string;
  availability: string | null;
  discovery_error: string | null;
}

interface PlaylistStatus {
  playlist_id: string;
  youtube_id: string;
  title: string;
  status: string;
  discovery_error: string | null;
  video_count: number;
  discovered_count: number;
  unavailable_count: number;
  latest_job: {
    id: string;
    status: string;
    attempts: number;
    error_summary: string | null;
  } | null;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

const DEFAULT_TEST_PLAYLIST =
  "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ";

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);

  const [playlistUrl, setPlaylistUrl] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | null>(null);
  const [playlistStatus, setPlaylistStatus] = useState<PlaylistStatus | null>(null);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loadingVideos, setLoadingVideos] = useState<boolean>(false);

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  // Load status and videos for a playlist
  const refreshPlaylistDetails = useCallback(
    async (plId: string) => {
      try {
        const [statusRes, videosRes] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/playlists/${plId}/status`),
          fetch(`${apiBaseUrl}/api/v1/playlists/${plId}/videos`),
        ]);

        if (statusRes.ok) {
          const sData: PlaylistStatus = await statusRes.json();
          setPlaylistStatus(sData);
        }
        if (videosRes.ok) {
          const vData: VideoItem[] = await videosRes.json();
          setVideos(vData);
        }
      } catch {
        // ignore
      } finally {
        setLoadingVideos(false);
      }
    },
    [apiBaseUrl]
  );

  // Initial load
  useEffect(() => {
    let ignore = false;

    async function initialize() {
      try {
        const [hRes, pRes] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/health`),
          fetch(`${apiBaseUrl}/api/v1/playlists`),
        ]);

        if (!ignore && hRes.ok) {
          const hData: HealthData = await hRes.json();
          setHealth(hData);
        }
        if (!ignore && pRes.ok) {
          const pData: Playlist[] = await pRes.json();
          setPlaylists(pData);
          if (pData.length > 0) {
            setSelectedPlaylistId(pData[0].id);
          }
        }
      } catch {
        // ignore
      } finally {
        if (!ignore) {
          setHealthLoading(false);
        }
      }
    }

    initialize();
    return () => {
      ignore = true;
    };
  }, [apiBaseUrl]);

  // Load details whenever selected playlist changes
  useEffect(() => {
    if (!selectedPlaylistId) return;
    let ignore = false;

    async function loadDetails() {
      try {
        const [statusRes, videosRes] = await Promise.all([
          fetch(`${apiBaseUrl}/api/v1/playlists/${selectedPlaylistId}/status`),
          fetch(`${apiBaseUrl}/api/v1/playlists/${selectedPlaylistId}/videos`),
        ]);

        if (!ignore && statusRes.ok) {
          const sData: PlaylistStatus = await statusRes.json();
          setPlaylistStatus(sData);
        }
        if (!ignore && videosRes.ok) {
          const vData: VideoItem[] = await videosRes.json();
          setVideos(vData);
        }
      } catch {
        // ignore
      } finally {
        if (!ignore) {
          setLoadingVideos(false);
        }
      }
    }

    loadDetails();
    return () => {
      ignore = true;
    };
  }, [selectedPlaylistId, apiBaseUrl]);

  const refreshPlaylists = useCallback(async () => {
    try {
      const res = await fetch(`${apiBaseUrl}/api/v1/playlists`);
      if (res.ok) {
        const data: Playlist[] = await res.json();
        setPlaylists(data);
      }
    } catch {
      // ignore
    }
  }, [apiBaseUrl]);

  // Polling while discovery job is active
  useEffect(() => {
    if (!selectedPlaylistId) return;

    const isActive =
      playlistStatus?.status === "DISCOVERY_QUEUED" ||
      playlistStatus?.status === "DISCOVERY_RUNNING";

    if (!isActive) return;

    const interval = setInterval(() => {
      refreshPlaylistDetails(selectedPlaylistId);
      refreshPlaylists();
    }, 2500);

    return () => clearInterval(interval);
  }, [selectedPlaylistId, playlistStatus?.status, refreshPlaylistDetails, refreshPlaylists]);

  // Submit Playlist
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!playlistUrl.trim()) return;

    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      const res = await fetch(`${apiBaseUrl}/api/v1/playlists`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: playlistUrl.trim() }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to submit playlist.");
      }

      setSubmitSuccess(data.message || "Playlist discovery job submitted!");
      setSelectedPlaylistId(data.playlist_id);
      refreshPlaylists();
      refreshPlaylistDetails(data.playlist_id);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Error submitting playlist.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center font-black text-white shadow-lg shadow-indigo-500/20 text-base">
            L
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Lectra <span className="text-xs font-normal text-slate-400">/ Revision RAG</span>
            </h1>
            <p className="text-xs text-slate-400">
              YouTube Playlist Revision Knowledge Base
            </p>
          </div>
        </div>
        <div className="flex items-center space-x-3 text-xs">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            Phase 2: Playlist Discovery
          </span>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60">
            <span
              className={`w-2 h-2 rounded-full ${
                health?.status === "ok" ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
              }`}
            />
            <span className="text-slate-300">
              {healthLoading ? "Checking..." : health?.status === "ok" ? "Backend Online" : "Backend Offline"}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-5xl w-full mx-auto p-6 md:p-8 space-y-6">
        {/* Playlist Discovery Submission Form */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-sm">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-white">
              Discover YouTube Playlist
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Submit a public or unlisted YouTube playlist URL to extract video metadata, titles, durations, and original positions.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                placeholder="https://www.youtube.com/playlist?list=..."
                value={playlistUrl}
                onChange={(e) => setPlaylistUrl(e.target.value)}
                className="flex-1 px-3.5 py-2.5 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
                disabled={submitting}
              />
              <button
                type="submit"
                disabled={submitting || !playlistUrl.trim()}
                className="px-5 py-2.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition-colors cursor-pointer flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Enqueuing...
                  </>
                ) : (
                  "Discover Playlist"
                )}
              </button>
            </div>

            <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
              <span>Need a sample playlist?</span>
              <button
                type="button"
                onClick={() => setPlaylistUrl(DEFAULT_TEST_PLAYLIST)}
                className="text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
              >
                Load Test Playlist (Greedy Algorithms)
              </button>
            </div>
          </form>

          {submitError && (
            <div className="mt-4 p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs">
              <strong>Error:</strong> {submitError}
            </div>
          )}

          {submitSuccess && (
            <div className="mt-4 p-3.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40 text-emerald-300 text-xs">
              ✓ {submitSuccess}
            </div>
          )}
        </section>

        {/* Playlists Selector (if multiple exist) */}
        {playlists.length > 1 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
            <span className="text-slate-400">Playlists:</span>
            {playlists.map((pl) => (
              <button
                key={pl.id}
                onClick={() => setSelectedPlaylistId(pl.id)}
                className={`px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
                  selectedPlaylistId === pl.id
                    ? "bg-indigo-600/20 border-indigo-500 text-indigo-300"
                    : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                {pl.title}
              </button>
            ))}
          </div>
        )}

        {/* Active Discovery Status Card */}
        {playlistStatus && (
          <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-6 shadow-sm space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800/80 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-white">
                    {playlistStatus.title || "Loading Title..."}
                  </h3>
                  <a
                    href={`https://www.youtube.com/playlist?list=${playlistStatus.youtube_id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-indigo-400 hover:underline"
                  >
                    ↗ YouTube
                  </a>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  ID: <code className="text-slate-300">{playlistStatus.youtube_id}</code>
                </p>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${
                    playlistStatus.status === "DISCOVERY_COMPLETED"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                      : playlistStatus.status === "DISCOVERY_RUNNING"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse"
                      : playlistStatus.status === "DISCOVERY_FAILED"
                      ? "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                      : "bg-slate-700/30 text-slate-400 border border-slate-700/50"
                  }`}
                >
                  {playlistStatus.status}
                </span>

                <button
                  onClick={() => selectedPlaylistId && refreshPlaylistDetails(selectedPlaylistId)}
                  className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg transition-colors cursor-pointer"
                >
                  Refresh
                </button>
              </div>
            </div>

            {playlistStatus.discovery_error && (
              <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 text-xs">
                <strong>Discovery Error:</strong> {playlistStatus.discovery_error}
              </div>
            )}

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <div className="text-xs text-slate-400">Total Declared</div>
                <div className="text-xl font-bold text-white mt-1">
                  {playlistStatus.video_count}
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <div className="text-xs text-slate-400">Discovered Accessible</div>
                <div className="text-xl font-bold text-emerald-400 mt-1">
                  {playlistStatus.discovered_count}
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <div className="text-xs text-slate-400">Unavailable / Exceptions</div>
                <div className="text-xl font-bold text-amber-400 mt-1">
                  {playlistStatus.unavailable_count}
                </div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-800/40 border border-slate-800">
                <div className="text-xs text-slate-400">Worker Status</div>
                <div className="text-xs font-semibold text-slate-200 mt-2 truncate">
                  {playlistStatus.latest_job
                    ? `Job #${playlistStatus.latest_job.id.slice(0, 8)} (${playlistStatus.latest_job.status})`
                    : "No active job"}
                </div>
              </div>
            </div>

            {/* Videos Table */}
            <div className="mt-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-slate-200">
                  Discovered Video Manifest ({videos.length})
                </h4>
                {playlistStatus.status === "DISCOVERY_RUNNING" && (
                  <span className="text-xs text-amber-400 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                    Discovery in progress...
                  </span>
                )}
              </div>

              {loadingVideos ? (
                <div className="py-8 text-center text-slate-400 text-xs">
                  Loading video manifest...
                </div>
              ) : videos.length === 0 ? (
                <div className="py-8 text-center text-slate-500 text-xs bg-slate-950/40 rounded-lg border border-slate-800">
                  {playlistStatus.status === "DISCOVERY_QUEUED"
                    ? "Job is queued in SQLite. Start the worker (make run-worker) to begin discovery."
                    : "No videos discovered yet."}
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-xs text-slate-300">
                    <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                      <tr>
                        <th className="py-2.5 px-3 w-12 text-center">#</th>
                        <th className="py-2.5 px-3">Video Title</th>
                        <th className="py-2.5 px-3 w-24">Duration</th>
                        <th className="py-2.5 px-3 w-32">Status</th>
                        <th className="py-2.5 px-3 w-28">Availability</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                      {videos.map((v) => (
                        <tr key={v.id} className="hover:bg-slate-800/30 transition-colors">
                          <td className="py-2.5 px-3 text-center font-mono text-slate-500">
                            {v.position + 1}
                          </td>
                          <td className="py-2.5 px-3">
                            <a
                              href={v.url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-medium text-slate-100 hover:text-indigo-400 hover:underline transition-colors line-clamp-1"
                            >
                              {v.title}
                            </a>
                            {v.discovery_error && (
                              <p className="text-[10px] text-rose-400 mt-0.5 truncate">
                                Error: {v.discovery_error}
                              </p>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-mono text-slate-400">
                            {formatDuration(v.duration_seconds)}
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${
                                v.status === "DISCOVERED"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              }`}
                            >
                              {v.status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400 capitalize">
                            {v.availability || "Unknown"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      <footer className="border-t border-slate-800 px-6 py-4 text-center text-xs text-slate-500">
        Lectra Revision RAG • Phase 2 YouTube Playlist Discovery • Self-Hosted & Local-First
      </footer>
    </div>
  );
}
