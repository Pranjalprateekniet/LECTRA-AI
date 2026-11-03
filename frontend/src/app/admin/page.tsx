"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityEventResponse,
  HealthData,
  Playlist,
  PlaylistStatusResponse,
  VideoResponse,
} from "@/types/api";
import { api } from "@/lib/api";
import { Header } from "@/components/Header";
import { PlaylistSubmitForm } from "@/components/PlaylistSubmitForm";
import { PlaylistSelector } from "@/components/PlaylistSelector";
import { StatisticsDashboard } from "@/components/StatisticsDashboard";
import { PlaylistProgressBar } from "@/components/PlaylistProgressBar";
import { VideoProcessingTable } from "@/components/VideoProcessingTable";
import { ActivityLog } from "@/components/ActivityLog";
import { VectorIndexStatus } from "@/components/VectorIndexStatus";
import { AlertCircleIcon, CheckCircleIcon } from "@/components/Icons";
import {
  loadSelectedPlaylistId,
  resolveActivePlaylistId,
  saveSelectedPlaylistId,
} from "@/lib/playlistStorage";

export default function AdminPage() {
  // Backend Health
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Playlists
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | null>(null);
  const [playlistsLoading, setPlaylistsLoading] = useState(true);

  // Selected Playlist Details
  const [status, setStatus] = useState<PlaylistStatusResponse | null>(null);
  const [videos, setVideos] = useState<VideoResponse[]>([]);
  const [activity, setActivity] = useState<ActivityEventResponse[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);

  // Submission & Actions
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Polling State
  const [isPolling, setIsPolling] = useState(false);
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Fetch Backend Health
  const checkHealth = useCallback(async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch {
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // 2. Fetch All Playlists
  const loadPlaylists = useCallback(async () => {
    try {
      const data = await api.getPlaylists();
      setPlaylists(data);
      if (data.length > 0) {
        setSelectedPlaylistId((prev) => {
          if (prev && data.some((p) => p.id === prev)) return prev;
          const savedId = loadSelectedPlaylistId();
          return resolveActivePlaylistId(data, savedId);
        });
      }
    } catch (err: unknown) {
      console.error("Failed to load playlists:", err);
    } finally {
      setPlaylistsLoading(false);
    }
  }, []);

  // 3. Fetch Selected Playlist Details
  const loadPlaylistDetails = useCallback(async (playlistId: string) => {
    try {
      const [st, vids, act] = await Promise.all([
        api.getPlaylistStatus(playlistId),
        api.getPlaylistVideos(playlistId),
        api.getPlaylistActivity(playlistId, 40),
      ]);
      setStatus(st);
      setVideos(vids);
      setActivity(act);
    } catch (err: unknown) {
      console.error("Failed to load playlist details:", err);
    } finally {
      setDetailsLoading(false);
    }
  }, []);

  // Initial Load
  useEffect(() => {
    checkHealth();
    loadPlaylists();
  }, [checkHealth, loadPlaylists]);

  // Load details when selected playlist changes
  useEffect(() => {
    if (!selectedPlaylistId) return;
    setDetailsLoading(true);
    loadPlaylistDetails(selectedPlaylistId);
  }, [selectedPlaylistId, loadPlaylistDetails]);

  // Determine whether active polling is required
  const isPipelineActive = useCallback((): boolean => {
    if (!status && videos.length === 0) return false;

    if (status?.status === "DISCOVERY_RUNNING" || status?.status === "IN_PROGRESS") {
      return true;
    }

    if (
      status?.latest_job &&
      (status.latest_job.status === "RUNNING" || status.latest_job.status === "QUEUED")
    ) {
      return true;
    }

    return videos.some(
      (v) =>
        v.status === "IN_PROGRESS" ||
        v.status === "DISCOVERED" ||
        v.status === "TRANSCRIPT_READY" ||
        v.status === "CHUNKED"
    );
  }, [status, videos]);

  // Polling Effect
  useEffect(() => {
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }

    if (!selectedPlaylistId) {
      setIsPolling(false);
      return;
    }

    const active = isPipelineActive();
    setIsPolling(active);

    if (active) {
      pollingTimerRef.current = setInterval(() => {
        loadPlaylistDetails(selectedPlaylistId);
      }, 3000);
    }

    return () => {
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
      }
    };
  }, [selectedPlaylistId, isPipelineActive, loadPlaylistDetails]);

  // Manual Refresh Handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([
        checkHealth(),
        loadPlaylists(),
        selectedPlaylistId ? loadPlaylistDetails(selectedPlaylistId) : Promise.resolve(),
      ]);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Submit Playlist Handler
  const handlePlaylistSubmit = async (url: string) => {
    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      const res = await api.submitPlaylist(url);
      setSubmitSuccess(`Playlist accepted. Job ID: ${res.job_id}. Ingestion pipeline initiated.`);
      await loadPlaylists();
      setSelectedPlaylistId(res.playlist_id);
      saveSelectedPlaylistId(res.playlist_id);
      await loadPlaylistDetails(res.playlist_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit playlist";
      setSubmitError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Retry Video Handler
  const handleRetryVideo = async (videoId: string) => {
    try {
      await api.retryVideo(videoId);
      if (selectedPlaylistId) {
        await loadPlaylistDetails(selectedPlaylistId);
      }
    } catch (err: unknown) {
      console.error("Retry failed:", err);
    }
  };

  // Delete Video Handler with Optimistic UI updates
  const handleDeleteVideo = async (videoId: string) => {
    if (!selectedPlaylistId) return;

    const previousVideos = [...videos];
    const previousStatus = status ? { ...status } : null;
    const targetVideo = videos.find((v) => v.id === videoId);

    setVideos((prev) => prev.filter((v) => v.id !== videoId));
    if (status && targetVideo) {
      const isCompleted = targetVideo.status === "INDEXED";
      const isFailed =
        targetVideo.status === "FAILED" || targetVideo.status === "SKIPPED_UNAVAILABLE";
      const isProcessing =
        targetVideo.status === "IN_PROGRESS" ||
        targetVideo.status === "DISCOVERED" ||
        targetVideo.status === "TRANSCRIPT_READY" ||
        targetVideo.status === "CHUNKED";

      setStatus({
        ...status,
        video_count: Math.max(0, status.video_count - 1),
        completed_count: isCompleted
          ? Math.max(0, status.completed_count - 1)
          : status.completed_count,
        failed_count: isFailed ? Math.max(0, status.failed_count - 1) : status.failed_count,
        processing_count: isProcessing
          ? Math.max(0, status.processing_count - 1)
          : status.processing_count,
      });
    }

    try {
      await api.deleteVideo(selectedPlaylistId, videoId);
      await Promise.all([loadPlaylistDetails(selectedPlaylistId), loadPlaylists()]);
    } catch (err: unknown) {
      setVideos(previousVideos);
      if (previousStatus) setStatus(previousStatus);
      throw err;
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F5F5] flex flex-col font-sans selection:bg-[#4a4a4a] selection:text-white w-full max-w-full overflow-x-hidden">
      {/* Admin Header */}
      <Header
        health={health}
        healthLoading={healthLoading}
        isPolling={isPolling}
        isRefreshing={isRefreshing}
        onRefresh={handleManualRefresh}
        isAdmin={true}
      />

      {/* Main Admin Dashboard Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 lg:px-8 py-3.5 sm:py-5 min-w-0 overflow-x-hidden space-y-6">
        {/* Section 1: Playlist Management */}
        <section aria-labelledby="section-playlist-management" className="space-y-3 min-w-0">
          <div className="flex items-center justify-between border-b border-[#292929] pb-2 min-w-0">
            <h2
              id="section-playlist-management"
              className="text-xs uppercase font-mono font-semibold tracking-wider text-[#929292]"
            >
              1. Playlist Management
            </h2>
            <span className="text-[10px] text-[#626262] font-mono">
              {playlists.length} registered
            </span>
          </div>

          <PlaylistSubmitForm
            onSubmit={handlePlaylistSubmit}
            isSubmitting={isSubmitting}
          />

          {/* Submission Alerts */}
          {submitSuccess && (
            <div className="flex items-center gap-2 text-xs text-[#F5F5F5] bg-[#181818] border border-[#292929] px-3.5 py-2.5 rounded-lg animate-fade-in">
              <CheckCircleIcon className="w-4 h-4 shrink-0 text-emerald-400" />
              <span className="flex-1">{submitSuccess}</span>
              <button
                onClick={() => setSubmitSuccess(null)}
                className="text-[#626262] hover:text-[#F5F5F5] text-xs ml-2"
              >
                ✕
              </button>
            </div>
          )}

          {submitError && (
            <div className="flex items-center gap-2 text-xs text-[#F5F5F5] bg-[#181818] border border-[#292929] px-3.5 py-2.5 rounded-lg animate-fade-in">
              <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
              <span className="flex-1">{submitError}</span>
              <button
                onClick={() => setSubmitError(null)}
                className="text-[#626262] hover:text-[#F5F5F5] text-xs ml-2"
              >
                ✕
              </button>
            </div>
          )}

          <PlaylistSelector
            playlists={playlists}
            selectedId={selectedPlaylistId}
            onSelect={(id) => {
              setSelectedPlaylistId(id);
              saveSelectedPlaylistId(id);
            }}
            isLoading={playlistsLoading}
          />
        </section>

        {/* Section 2: Ingestion Dashboard */}
        {selectedPlaylistId && (
          <section aria-labelledby="section-ingestion-dashboard" className="space-y-3 min-w-0">
            <div className="flex items-center justify-between border-b border-[#292929] pb-2 min-w-0">
              <h2
                id="section-ingestion-dashboard"
                className="text-xs uppercase font-mono font-semibold tracking-wider text-[#929292]"
              >
                2. Ingestion Dashboard
              </h2>
              <div className="flex items-center gap-2 text-[10px] font-mono text-[#626262]">
                {status?.latest_job && (
                  <span>Job: {status.latest_job.id.slice(0, 8)} ({status.latest_job.status})</span>
                )}
                {isPolling && (
                  <span className="flex items-center gap-1 text-emerald-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span>Live Sync</span>
                  </span>
                )}
              </div>
            </div>

            {/* Pipeline Status Summary Card */}
            <div className="bg-[#111111] border border-[#292929] rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 min-w-0 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-medium text-[#F5F5F5]">Pipeline State:</span>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-[#181818] border border-[#292929] text-[#F5F5F5]">
                  {status?.status || "UNKNOWN"}
                </span>
                {status?.discovery_error && (
                  <span className="text-rose-400 text-[11px] truncate max-w-sm">
                    {status.discovery_error}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3 text-[11px] font-mono text-[#626262]">
                <span>Discovered: {status?.discovered_count ?? 0}</span>
                <span>•</span>
                <span>Ready: {status?.transcripts_ready_count ?? 0}</span>
                <span>•</span>
                <span>Needs ASR: {status?.needs_transcription_count ?? 0}</span>
              </div>
            </div>

            {/* Progress Breakdown Bar */}
            <PlaylistProgressBar status={status} />
          </section>
        )}

        {/* Section 3: Video Processing Statistics */}
        {selectedPlaylistId && (
          <section aria-labelledby="section-video-stats" className="space-y-3 min-w-0">
            <div className="flex items-center justify-between border-b border-[#292929] pb-2 min-w-0">
              <h2
                id="section-video-stats"
                className="text-xs uppercase font-mono font-semibold tracking-wider text-[#929292]"
              >
                3. Video Processing Statistics & Pipeline
              </h2>
              <span className="text-[10px] text-[#626262] font-mono">
                {videos.length} videos tracked
              </span>
            </div>

            {/* 7 Metric Cards */}
            <StatisticsDashboard status={status} loading={detailsLoading} />

            {/* 6-Stage Video Pipeline Table with Retry & Delete */}
            <VideoProcessingTable
              videos={videos}
              loading={detailsLoading}
              onRetryVideo={handleRetryVideo}
              onDeleteVideo={handleDeleteVideo}
            />
          </section>
        )}

        {/* Section 4: Ingestion Logs */}
        {selectedPlaylistId && (
          <section aria-labelledby="section-ingestion-logs" className="space-y-3 min-w-0">
            <div className="flex items-center justify-between border-b border-[#292929] pb-2 min-w-0">
              <h2
                id="section-ingestion-logs"
                className="text-xs uppercase font-mono font-semibold tracking-wider text-[#929292]"
              >
                4. Ingestion Logs & Activity Events
              </h2>
              <span className="text-[10px] text-[#626262] font-mono">
                Recent 40 events
              </span>
            </div>

            <ActivityLog events={activity} loading={detailsLoading} />
          </section>
        )}

        {/* Section 5: Vector Index Status */}
        {selectedPlaylistId && (
          <section aria-labelledby="section-vector-index" className="space-y-3 min-w-0">
            <div className="flex items-center justify-between border-b border-[#292929] pb-2 min-w-0">
              <h2
                id="section-vector-index"
                className="text-xs uppercase font-mono font-semibold tracking-wider text-[#929292]"
              >
                5. Vector Index Status
              </h2>
              <span className="text-[10px] text-[#626262] font-mono">
                Qdrant Storage
              </span>
            </div>

            <VectorIndexStatus
              status={status}
              health={health}
              loading={detailsLoading}
            />
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#292929] bg-[#0A0A0A] py-3 text-center text-xs text-[#626262] font-mono">
        Lectra Admin — Ingestion & Vector Index Management Interface • Unauthenticated Route (Development Mode)
      </footer>
    </div>
  );
}
