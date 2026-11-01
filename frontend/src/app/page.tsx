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
import { ChatInterface } from "@/components/ChatInterface";
import { AlertCircleIcon, CheckCircleIcon } from "@/components/Icons";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"ingestion" | "qa">("ingestion");

  // Backend Health
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Playlists
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | null>(null);
  const [playlistsLoading, setPlaylistsLoading] = useState(true);

  // Selected Playlist Data
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
          // Prefer Greedy Algorithms playlist if found
          const greedy = data.find((p) => p.youtube_id === "PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ");
          return greedy ? greedy.id : data[0].id;
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

  // When selected playlist changes, load details
  useEffect(() => {
    if (!selectedPlaylistId) return;
    setDetailsLoading(true);
    loadPlaylistDetails(selectedPlaylistId);
  }, [selectedPlaylistId, loadPlaylistDetails]);

  // Determine whether active polling is required
  const isPipelineActive = useCallback((): boolean => {
    if (!status && videos.length === 0) return false;

    // Check playlist level status
    if (status?.status === "DISCOVERY_RUNNING" || status?.status === "IN_PROGRESS") {
      return true;
    }

    // Check latest job status
    if (status?.latest_job && (status.latest_job.status === "RUNNING" || status.latest_job.status === "QUEUED")) {
      return true;
    }

    // Check if any video is non-terminal
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
      setSubmitSuccess(`Playlist accepted! Job ID: ${res.job_id}. Ingestion pipeline initiated.`);
      await loadPlaylists();
      setSelectedPlaylistId(res.playlist_id);
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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Header */}
      <Header
        health={health}
        healthLoading={healthLoading}
        isPolling={isPolling}
        isRefreshing={isRefreshing}
        onRefresh={handleManualRefresh}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Tab 2: Revision Chatbot */}
        {activeTab === "qa" ? (
          <ChatInterface
            playlists={playlists}
            defaultPlaylistId={selectedPlaylistId}
          />
        ) : (
          <>
            {/* Top Row: Playlist Submission Form */}
            <PlaylistSubmitForm
              onSubmit={handlePlaylistSubmit}
              isSubmitting={isSubmitting}
            />

            {/* Submission Alerts */}
            {submitSuccess && (
              <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 px-4 py-3 rounded-xl animate-fade-in">
                <CheckCircleIcon className="w-4 h-4 shrink-0 text-emerald-400" />
                <span className="flex-1">{submitSuccess}</span>
                <button
                  onClick={() => setSubmitSuccess(null)}
                  className="text-slate-400 hover:text-slate-200 text-xs ml-2"
                >
                  ✕
                </button>
              </div>
            )}

            {submitError && (
              <div className="flex items-center gap-2 text-xs text-rose-400 bg-rose-950/40 border border-rose-800/50 px-4 py-3 rounded-xl animate-fade-in">
                <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
                <span className="flex-1">{submitError}</span>
                <button
                  onClick={() => setSubmitError(null)}
                  className="text-slate-400 hover:text-slate-200 text-xs ml-2"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Playlists Selector */}
            <PlaylistSelector
              playlists={playlists}
              selectedId={selectedPlaylistId}
              onSelect={(id) => setSelectedPlaylistId(id)}
              isLoading={playlistsLoading}
            />

            {/* Selected Playlist Status & Metrics */}
            {selectedPlaylistId && (
              <div className="space-y-6 pt-2">
                {/* 7 Metric Cards */}
                <StatisticsDashboard status={status} loading={detailsLoading} />

                {/* Progress Breakdown Bar */}
                <PlaylistProgressBar status={status} />

                {/* 6-Stage Video Pipeline Table */}
                <VideoProcessingTable
                  videos={videos}
                  loading={detailsLoading}
                  onRetryVideo={handleRetryVideo}
                />

                {/* Persisted Chronological Activity Log */}
                <ActivityLog events={activity} loading={detailsLoading} />
              </div>
            )}
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-xs text-slate-500 font-mono">
        Lectra — YouTube Revision RAG Engine • EmbeddingGemma 2 (768d) • Qdrant Cloud • Groq GPT-OSS-120B
      </footer>
    </div>
  );
}
