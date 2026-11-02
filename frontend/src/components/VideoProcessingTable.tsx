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
    <div className="bg-[#111111] border border-[#292929] rounded-xl overflow-hidden shadow-xs min-w-0">
      {/* Controls Bar */}
      <div className="p-3 sm:p-3.5 border-b border-[#292929] flex flex-col sm:flex-row gap-2.5 items-stretch sm:items-center justify-between min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <h3 className="font-medium text-xs sm:text-sm text-[#F5F5F5] truncate">Video Ingestion Pipeline</h3>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#181818] text-[#626262] font-mono border border-[#292929] shrink-0">
            {filteredVideos.length} of {videos.length} videos
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {/* Search Input */}
          <div className="relative flex-1 sm:w-60 min-w-0">
            <SearchIcon className="w-3.5 h-3.5 text-[#626262] absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title or ID..."
              className="w-full pl-7 pr-2.5 py-1 rounded-md bg-[#181818] border border-[#292929] text-xs text-[#F5F5F5] placeholder-[#626262] focus:outline-none focus:border-[#444]"
            />
          </div>

          {/* Status Filter Buttons */}
          <div className="flex items-center gap-0.5 bg-[#181818] p-0.5 rounded-md border border-[#292929] text-xs shrink-0">
            {["ALL", "INDEXED", "PROCESSING", "FAILED"].map((cat) => (
              <button
                key={cat}
                onClick={() => setStatusFilter(cat)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  statusFilter === cat
                    ? "bg-[#202020] text-[#F5F5F5] border border-[#292929]"
                    : "text-[#929292] hover:text-[#F5F5F5]"
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
        <div className="p-8 text-center text-[#929292] text-xs animate-pulse font-mono min-w-0">
          Loading video processing statuses...
        </div>
      ) : filteredVideos.length === 0 ? (
        <div className="p-8 text-center text-[#626262] text-xs font-mono min-w-0">
          No videos match the current search / filter criteria.
        </div>
      ) : (
        <div className="divide-y divide-[#292929] overflow-x-auto min-w-0">
          {filteredVideos.map((video) => {
            const isExpanded = expandedVideoId === video.id;
            const isIndexed = video.status === "INDEXED";
            const isFailed = video.status === "FAILED" || video.status === "SKIPPED_UNAVAILABLE";

            return (
              <div
                key={video.id}
                className={`transition-colors ${
                  isExpanded ? "bg-[#141414]" : "hover:bg-[#141414]"
                }`}
              >
                {/* Main Video Row */}
                <div
                  onClick={() => toggleExpand(video.id)}
                  className="p-3 sm:p-3.5 cursor-pointer flex flex-col lg:flex-row lg:items-center justify-between gap-3 min-w-0"
                >
                  {/* Left: Position, Title, Metadata */}
                  <div className="flex items-start gap-2.5 min-w-0 lg:w-1/3">
                    <button
                      type="button"
                      className="mt-0.5 text-[#626262] hover:text-[#F5F5F5] transition-colors shrink-0"
                      aria-label={isExpanded ? "Collapse video details" : "Expand video details"}
                    >
                      {isExpanded ? (
                        <ChevronDownIcon className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRightIcon className="w-3.5 h-3.5" />
                      )}
                    </button>

                    <span className="font-mono text-xs text-[#626262] mt-0.5 shrink-0">
                      #{video.position}
                    </span>

                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                        <a
                          href={video.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="font-medium text-xs sm:text-sm text-[#F5F5F5] hover:underline transition-colors flex items-center gap-1 min-w-0"
                        >
                          <span className="truncate">{video.title}</span>
                          <ExternalLinkIcon className="w-3 h-3 text-[#626262] shrink-0" />
                        </a>
                      </div>

                      <div className="flex items-center gap-2 text-[11px] text-[#626262] font-mono mt-0.5 flex-wrap">
                        <span>{video.youtube_id}</span>
                        <span>•</span>
                        <span>{formatDuration(video.duration_seconds)}</span>
                        {video.transcript_source && (
                          <>
                            <span>•</span>
                            <span className="text-[#929292] capitalize">
                              {video.transcript_source} captions
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Center: 6-Stage Pipeline Indicators */}
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5 lg:w-7/12 min-w-0">
                    {/* Stage 1: Discovery */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        1. Discovery
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono text-emerald-500">
                        <CheckCircleIcon className="w-3 h-3" />
                        <span>Ready</span>
                      </div>
                    </div>

                    {/* Stage 2: Transcript */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        2. Transcript
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono">
                        {video.transcript_segments_count > 0 ? (
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircleIcon className="w-3 h-3" />
                            <span>{video.transcript_segments_count} segs</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-500 flex items-center gap-1">
                            <AlertCircleIcon className="w-3 h-3" />
                            <span>None</span>
                          </span>
                        ) : (
                          <span className="text-[#626262] flex items-center gap-1">
                            <ClockIcon className="w-3 h-3" />
                            <span>Pending</span>
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Stage 3: Translation */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        3. Translation
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono">
                        {video.language === "en" || video.transcript_segments_count > 0 ? (
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircleIcon className="w-3 h-3" />
                            <span>EN Ready</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-500">Failed</span>
                        ) : (
                          <span className="text-[#626262]">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 4: Chunking */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        4. Chunking
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono">
                        {video.chunks_count > 0 ? (
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircleIcon className="w-3 h-3" />
                            <span>{video.chunks_count} chunks</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-500">Failed</span>
                        ) : (
                          <span className="text-[#626262]">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 5: Embedding */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        5. Embedding
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono">
                        {video.indexed_vectors_count > 0 ? (
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircleIcon className="w-3 h-3" />
                            <span>{video.indexed_vectors_count}/{video.chunks_count}</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-500">Failed</span>
                        ) : (
                          <span className="text-[#626262]">Pending</span>
                        )}
                      </div>
                    </div>

                    {/* Stage 6: Indexing */}
                    <div className="bg-[#181818] border border-[#292929] rounded-md p-1.5 text-center min-w-0">
                      <div className="text-[9px] uppercase font-medium text-[#626262] truncate">
                        6. Indexing
                      </div>
                      <div className="mt-0.5 flex items-center justify-center gap-1 text-[11px] font-mono">
                        {isIndexed ? (
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircleIcon className="w-3 h-3" />
                            <span>Indexed</span>
                          </span>
                        ) : isFailed ? (
                          <span className="text-rose-500 flex items-center gap-1">
                            <AlertCircleIcon className="w-3 h-3" />
                            <span>Failed</span>
                          </span>
                        ) : (
                          <span className="text-[#F5F5F5] flex items-center gap-1 animate-pulse">
                            <ClockIcon className="w-3 h-3" />
                            <span>Running</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-1 lg:w-1/12 justify-end shrink-0">
                    {isFailed && (
                      <button
                        onClick={(e) => handleRetry(e, video.id)}
                        disabled={retryingId === video.id}
                        className="px-2 py-0.5 rounded bg-[#181818] hover:bg-[#202020] border border-[#292929] text-[#F5F5F5] text-xs font-mono flex items-center gap-1 transition-colors"
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
                        className="p-1.5 rounded text-[#626262] hover:text-rose-400 hover:bg-[#181818] border border-transparent hover:border-[#292929] transition-colors"
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
                  <div className="px-4 sm:px-6 py-3 bg-[#0E0E0E] border-t border-[#292929] text-xs space-y-2.5 min-w-0">
                    <div className="flex items-center justify-between text-[#626262] font-mono text-[11px] min-w-0 flex-wrap gap-1">
                      <span>Video ID: {video.id}</span>
                      <span>Qdrant: revision_chunks (768d Gemma 2)</span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2 min-w-0">
                      {video.stages && video.stages.length > 0 ? (
                        video.stages.map((stage) => {
                          const isStageDone = stage.status === "COMPLETED";
                          const isStageErr = stage.status === "FAILED";

                          return (
                            <div
                              key={stage.stage_name}
                              className={`p-2.5 rounded-md border font-mono min-w-0 ${
                                isStageDone
                                  ? "bg-[#141414] border-[#292929] text-[#929292]"
                                  : isStageErr
                                  ? "bg-[#141414] border-rose-900/40 text-rose-300"
                                  : "bg-[#141414] border-[#292929] text-[#626262]"
                              }`}
                            >
                              <div className="flex items-center justify-between min-w-0">
                                <span className="font-medium text-[#F5F5F5] uppercase text-[10px] truncate">
                                  {stage.stage_name}
                                </span>
                                <span
                                  className={`text-[9px] px-1 py-0.2 rounded border ${
                                    isStageDone
                                      ? "bg-[#181818] text-emerald-500 border-[#292929]"
                                      : isStageErr
                                      ? "bg-[#181818] text-rose-500 border-rose-900/40"
                                      : "bg-[#181818] text-[#626262] border-[#292929]"
                                  }`}
                                >
                                  {stage.status}
                                </span>
                              </div>

                              <div className="mt-1.5 space-y-0.5 text-[10px] text-[#626262]">
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
                        <div className="col-span-4 text-[#626262] italic text-xs">
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
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => {
            if (!isDeleting) setConfirmDeleteVideo(null);
          }}
        >
          <div
            className="bg-[#181818] border border-[#292929] rounded-xl max-w-md w-full p-5 shadow-xl space-y-3.5 min-w-0"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-md bg-[#202020] border border-[#292929] flex items-center justify-center text-[#F5F5F5] shrink-0">
                <TrashIcon className="w-4 h-4 text-rose-400" />
              </div>
              <div className="min-w-0">
                <h3 id="delete-dialog-title" className="text-sm font-semibold text-[#F5F5F5]">
                  Delete Video from Playlist
                </h3>
                <p className="text-xs text-[#929292]">
                  This action cannot be undone.
                </p>
              </div>
            </div>

            <div className="p-2.5 bg-[#111111] rounded-md border border-[#292929] space-y-0.5 min-w-0">
              <div className="text-xs font-medium text-[#F5F5F5] line-clamp-2">
                &ldquo;{confirmDeleteVideo.title}&rdquo;
              </div>
              <div className="text-[10px] font-mono text-[#626262] flex items-center gap-2">
                <span>ID: {confirmDeleteVideo.youtube_id}</span>
                <span>•</span>
                <span>Position #{confirmDeleteVideo.position}</span>
              </div>
            </div>

            <p className="text-xs text-[#929292] leading-relaxed">
              Are you sure you want to delete this video? This will permanently remove its transcript segments,
              chunk boundaries, local artifact files, and vector embeddings from Qdrant.
            </p>

            {deleteError && (
              <div className="p-2.5 bg-[#111111] border border-rose-900/50 rounded-md text-rose-300 text-xs flex items-center gap-2">
                <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setConfirmDeleteVideo(null)}
                disabled={isDeleting}
                className="px-3 py-1.5 rounded-md text-xs font-medium text-[#929292] hover:text-[#F5F5F5] hover:bg-[#202020] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="px-3 py-1.5 rounded-md text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white transition-colors flex items-center gap-1.5 disabled:opacity-50"
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
