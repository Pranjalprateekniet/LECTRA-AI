"use client";

import React, { useState } from "react";
import { VideoResponse } from "@/types/api";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  ExternalLinkIcon,
  RefreshCwIcon,
  SearchIcon,
  TrashIcon,
} from "./Icons";

interface VideoProcessingTableProps {
  videos: VideoResponse[];
  loading: boolean;
  onRetryVideo: (videoId: string) => Promise<void>;
  onDeleteVideo?: (videoId: string) => Promise<void>;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const h = Math.floor(m / 60);
  if (h > 0) {
    const remM = m % 60;
    return `${h}h ${remM < 10 ? "0" : ""}${remM}m`;
  }
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export function VideoProcessingTable({
  videos,
  loading,
  onRetryVideo,
  onDeleteVideo,
}: VideoProcessingTableProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [expandedVideoId, setExpandedVideoId] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [confirmDeleteVideo, setConfirmDeleteVideo] = useState<VideoResponse | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedVideoId(expandedVideoId === id ? null : id);
  };

  const handleRetry = async (e: React.MouseEvent, videoId: string) => {
    e.stopPropagation();
    try {
      setRetryingId(videoId);
      await onRetryVideo(videoId);
    } finally {
      setRetryingId(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!confirmDeleteVideo || !onDeleteVideo) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await onDeleteVideo(confirmDeleteVideo.id);
      setConfirmDeleteVideo(null);
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete video");
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredVideos = videos.filter((video) => {
    const matchesSearch =
      video.title.toLowerCase().includes(search.toLowerCase()) ||
      video.youtube_id.toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;

    if (statusFilter === "INDEXED") {
      return video.status === "INDEXED";
    }
    if (statusFilter === "PROCESSING") {
      return (
        video.status === "IN_PROGRESS" ||
        video.status === "DISCOVERED" ||
        video.status === "TRANSCRIPT_READY" ||
        video.status === "CHUNKED"
      );
    }
    if (statusFilter === "FAILED") {
      return (
        video.status === "FAILED" ||
        video.status === "SKIPPED_UNAVAILABLE" ||
        video.discovery_error !== null
      );
    }
    return true;
  });

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
      {/* Controls Bar */}
      <div className="p-4 border-b border-slate-800 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-sm text-slate-100">Video Ingestion Pipeline</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
            {filteredVideos.length} of {videos.length} videos
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Search Input */}
          <div className="relative flex-1 sm:w-64">
            <SearchIcon className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title or ID..."
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Status Filter Buttons */}
          <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-lg border border-slate-800 text-xs">
            {["ALL", "INDEXED", "PROCESSING", "FAILED"].map((cat) => (
              <button
                key={cat}
                onClick={() => setStatusFilter(cat)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition ${
                  statusFilter === cat
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                }`}
              >
                {cat.charAt(0) + cat.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Video Table */}
      {loading && videos.length === 0 ? (
        <div className="p-12 text-center text-slate-400 text-sm animate-pulse">
          Loading video processing statuses...
        </div>
      ) : filteredVideos.length === 0 ? (
        <div className="p-12 text-center text-slate-500 text-sm">
          No videos match the current search / filter criteria.
        </div>
      ) : (
        <div className="divide-y divide-slate-800/80 overflow-x-auto">
          {filteredVideos.map((video) => {
            const isExpanded = expandedVideoId === video.id;
            const isIndexed = video.status === "INDEXED";
            const isFailed = video.status === "FAILED" || video.status === "SKIPPED_UNAVAILABLE";
            const isProcessing =
              video.status === "IN_PROGRESS" ||
              video.status === "DISCOVERED" ||
              video.status === "TRANSCRIPT_READY" ||
              video.status === "CHUNKED";

            return (
              <div
                key={video.id}
                className={`transition-colors ${
                  isExpanded ? "bg-slate-850/50" : "hover:bg-slate-800/30"
                }`}
              >
                {/* Main Video Row */}
                <div
                  onClick={() => toggleExpand(video.id)}
                  className="p-4 cursor-pointer flex flex-col lg:flex-row lg:items-center justify-between gap-4"
                >
                  {/* Left: Position, Title, Metadata */}
                  <div className="flex items-start gap-3 min-w-0 lg:w-1/3">
                    <button
                      type="button"
                      className="mt-0.5 text-slate-500 hover:text-slate-300 transition"
                      aria-label={isExpanded ? "Collapse video details" : "Expand video details"}
                    >
                      {isExpanded ? (
                        <ChevronDownIcon className="w-4 h-4" />
                      ) : (
                        <ChevronRightIcon className="w-4 h-4" />
                      )}
                    </button>

                    <span className="font-mono text-xs text-slate-500 mt-0.5 shrink-0">
                      #{video.position}
                    </span>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <a
                          href={video.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-sm text-slate-100 hover:text-indigo-400 transition flex items-center gap-1"
                        >
                          <span className="truncate">{video.title}</span>
                          <ExternalLinkIcon className="w-3 h-3 text-slate-500 shrink-0" />
                        </a>
                      </div>

                      <div className="flex items-center gap-3 text-xs text-slate-400 font-mono mt-1">
                        <span>{video.youtube_id}</span>
                        <span>•</span>
                        <span>{formatDuration(video.duration_seconds)}</span>
                        {video.transcript_source && (
                          <>
                            <span>•</span>
                            <span className="text-slate-300 capitalize">
                              {video.transcript_source} captions
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Center: 6-Stage Pipeline Indicators */}
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 lg:w-7/12">
                    {/* Stage 1: Discovery */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        1. Discovery
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono text-emerald-400">
                        <CheckCircleIcon className="w-3.5 h-3.5" />
                        <span>Ready</span>
                      </div>
                    </div>

                    {/* Stage 2: Transcript */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        2. Transcript
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono">
                        {video.transcript_segments_count > 0 ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircleIcon className="w-3.5 h-3.5" />
                            <span>{video.transcript_segments_count} segs</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-400 flex items-center gap-1">
                            <AlertCircleIcon className="w-3.5 h-3.5" />
                            <span>None</span>
                          </span>
                        ) : (
                          <span className="text-slate-400 flex items-center gap-1">
                            <ClockIcon className="w-3.5 h-3.5" />
                            <span>Pending</span>
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Stage 3: Translation */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        3. Translation
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono">
                        {video.language === "en" || video.transcript_segments_count > 0 ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircleIcon className="w-3.5 h-3.5" />
                            <span>EN Ready</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-400">Failed</span>
                        ) : (
                          <span className="text-slate-500">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 4: Chunking */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        4. Chunking
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono">
                        {video.chunks_count > 0 ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircleIcon className="w-3.5 h-3.5" />
                            <span>{video.chunks_count} chunks</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-400">Failed</span>
                        ) : (
                          <span className="text-slate-500">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 5: Embedding */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        5. Embedding
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono">
                        {video.indexed_vectors_count > 0 ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircleIcon className="w-3.5 h-3.5" />
                            <span>{video.indexed_vectors_count}/{video.chunks_count}</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-400">Failed</span>
                        ) : (
                          <span className="text-slate-500">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 6: Indexing */}
                    <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2 text-center">
                      <div className="text-[10px] uppercase font-semibold text-slate-400">
                        6. Indexing
                      </div>
                      <div className="mt-1 flex items-center justify-center gap-1 text-xs font-mono">
                        {isIndexed ? (
                          <span className="text-emerald-400 flex items-center gap-1">
                            <CheckCircleIcon className="w-3.5 h-3.5" />
                            <span>Indexed</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-400 flex items-center gap-1">
                            <AlertCircleIcon className="w-3.5 h-3.5" />
                            <span>Failed</span>
                          </span>
                        ) : (
                          <span className="text-indigo-400 flex items-center gap-1 animate-pulse">
                            <ClockIcon className="w-3.5 h-3.5" />
                            <span>Running</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-1.5 lg:w-1/12 justify-end">
                    {isFailed && (
                      <button
                        onClick={(e) => handleRetry(e, video.id)}
                        disabled={retryingId === video.id}
                        className="px-2 py-1 rounded bg-rose-950/50 hover:bg-rose-900/50 border border-rose-800/60 text-rose-300 text-xs font-mono flex items-center gap-1 transition"
                        title="Retry processing this video"
                      >
                        <RefreshCwIcon
                          className={`w-3 h-3 ${retryingId === video.id ? "animate-spin" : ""}`}
                        />
                        <span>Retry</span>
                      </button>
                    )}

                    {onDeleteVideo && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteError(null);
                          setConfirmDeleteVideo(video);
                        }}
                        className="p-1.5 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-950/40 border border-transparent hover:border-rose-900/50 transition"
                        title="Delete video from playlist"
                        aria-label={`Delete video ${video.title}`}
                      >
                        <TrashIcon className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded Stage Details Panel */}
                {isExpanded && (
                  <div className="px-6 py-4 bg-slate-950/60 border-t border-slate-800/80 text-xs space-y-3">
                    <div className="flex items-center justify-between text-slate-400 font-mono text-[11px]">
                      <span>Video ID: {video.id}</span>
                      <span>Qdrant Collection: revision_chunks (768d Gemma 2)</span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                      {video.stages && video.stages.length > 0 ? (
                        video.stages.map((stage) => {
                          const isStageDone = stage.status === "COMPLETED";
                          const isStageErr = stage.status === "FAILED";

                          return (
                            <div
                              key={stage.stage_name}
                              className={`p-3 rounded-lg border font-mono ${
                                isStageDone
                                  ? "bg-slate-900 border-emerald-900/40 text-slate-300"
                                  : isStageErr
                                  ? "bg-rose-950/20 border-rose-900/50 text-rose-300"
                                  : "bg-slate-900 border-slate-800 text-slate-400"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-slate-200 uppercase text-[10px]">
                                  {stage.stage_name}
                                </span>
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded ${
                                    isStageDone
                                      ? "bg-emerald-950 text-emerald-400"
                                      : isStageErr
                                      ? "bg-rose-950 text-rose-400"
                                      : "bg-slate-800 text-slate-400"
                                  }`}
                                >
                                  {stage.status}
                                </span>
                              </div>

                              <div className="mt-2 space-y-1 text-[11px] text-slate-400">
                                <div>Attempts: {stage.attempts}</div>
                                {stage.completed_at && (
                                  <div className="truncate">
                                    Done: {new Date(stage.completed_at).toLocaleTimeString()}
                                  </div>
                                )}
                                {stage.error_detail && (
                                  <div className="text-rose-400 text-[10px] mt-1 break-words">
                                    {stage.error_detail}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="col-span-4 text-slate-500 italic">
                          No intermediate stage checkpoint records recorded for this video.
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Confirmation Dialog Modal */}
      {confirmDeleteVideo && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150"
          onClick={() => {
            if (!isDeleting) setConfirmDeleteVideo(null);
          }}
        >
          <div
            className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 shrink-0">
                <TrashIcon className="w-5 h-5" />
              </div>
              <div>
                <h3 id="delete-dialog-title" className="text-sm font-semibold text-slate-100">
                  Delete Video from Playlist
                </h3>
                <p className="text-xs text-slate-400">
                  This action cannot be undone.
                </p>
              </div>
            </div>

            <div className="p-3 bg-slate-950/80 rounded-xl border border-slate-800 space-y-1">
              <div className="text-xs font-medium text-slate-200 line-clamp-2">
                &ldquo;{confirmDeleteVideo.title}&rdquo;
              </div>
              <div className="text-[11px] font-mono text-slate-500 flex items-center gap-2">
                <span>ID: {confirmDeleteVideo.youtube_id}</span>
                <span>•</span>
                <span>Position #{confirmDeleteVideo.position}</span>
              </div>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Are you sure you want to delete this video? This will permanently remove its transcript segments,
              chunk boundaries, local artifact files, and vector embeddings from Qdrant.
            </p>

            {deleteError && (
              <div className="p-3 bg-rose-950/40 border border-rose-800/60 rounded-lg text-rose-300 text-xs flex items-center gap-2">
                <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setConfirmDeleteVideo(null)}
                disabled={isDeleting}
                className="px-4 py-2 rounded-xl text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1.5 shadow-lg shadow-rose-900/30 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <RefreshCwIcon className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <TrashIcon className="w-3.5 h-3.5" />
                    <span>Confirm Delete</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
