"use client";

import React from "react";
import { Playlist } from "@/types/api";
import { CheckCircleIcon, ClockIcon, AlertCircleIcon, VideoIcon, ExternalLinkIcon } from "./Icons";

interface PlaylistSelectorProps {
  playlists: Playlist[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading: boolean;
}

export function PlaylistSelector({
  playlists,
  selectedId,
  onSelect,
  isLoading,
}: PlaylistSelectorProps) {
  if (isLoading && playlists.length === 0) {
    return (
      <div className="bg-[#111111] border border-[#292929] rounded-xl p-6 text-center text-[#929292] text-xs font-mono animate-pulse min-w-0">
        Loading ingested playlists...
      </div>
    );
  }

  if (playlists.length === 0) {
    return (
      <div className="bg-[#111111] border border-dashed border-[#292929] rounded-xl p-6 text-center min-w-0">
        <VideoIcon className="w-6 h-6 text-[#626262] mx-auto mb-2" />
        <h3 className="text-xs font-medium text-[#F5F5F5]">No playlists ingested yet</h3>
        <p className="text-[11px] text-[#929292] mt-1 max-w-sm mx-auto">
          Submit a YouTube playlist URL above to begin discovery and ingestion.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5 min-w-0">
      <div className="flex items-center justify-between min-w-0">
        <span className="text-[11px] font-medium uppercase tracking-wider text-[#929292]">
          Ingested Playlists ({playlists.length})
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 min-w-0">
        {playlists.map((pl) => {
          const isSelected = pl.id === selectedId;
          const isFullyIndexed = pl.completed_count === pl.video_count && pl.video_count > 0;
          const hasFailed = pl.failed_count > 0;
          const isProcessing = pl.processing_count > 0 || pl.status.includes("RUNNING");

          return (
            <div
              key={pl.id}
              onClick={() => onSelect(pl.id)}
              className={`cursor-pointer rounded-lg p-3 sm:p-3.5 border transition-colors text-left relative overflow-hidden group min-w-0 ${
                isSelected
                  ? "bg-[#181818] border-[#383838] ring-1 ring-[#383838]"
                  : "bg-[#111111] border-[#292929] hover:border-[#383838] hover:bg-[#141414]"
              }`}
            >
              <div className="flex items-start justify-between gap-2 min-w-0">
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-xs sm:text-sm text-[#F5F5F5] truncate transition-colors">
                    {pl.title || "Untitled Playlist"}
                  </h3>
                  <p className="text-[11px] text-[#929292] truncate mt-0.5">
                    {pl.channel_name || "Unknown Channel"}
                  </p>
                </div>

                <a
                  href={pl.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-[#626262] hover:text-[#F5F5F5] p-1 rounded transition-colors shrink-0"
                  title="Open on YouTube"
                >
                  <ExternalLinkIcon className="w-3.5 h-3.5" />
                </a>
              </div>

              {/* Status and counts */}
              <div className="mt-2.5 pt-2 border-t border-[#292929] flex items-center justify-between text-xs min-w-0">
                <div className="flex items-center gap-1 font-mono text-xs">
                  <span className="font-semibold text-[#F5F5F5]">{pl.video_count}</span>
                  <span className="text-[#626262]">videos</span>
                </div>

                <div className="flex items-center gap-1.5 font-mono text-[11px] shrink-0">
                  {isFullyIndexed && (
                    <span className="inline-flex items-center gap-1 text-[#929292] bg-[#181818] border border-[#292929] px-1.5 py-0.2 rounded">
                      <CheckCircleIcon className="w-3 h-3 text-emerald-500" />
                      <span>{pl.completed_count}/{pl.video_count} Ready</span>
                    </span>
                  )}

                  {!isFullyIndexed && isProcessing && (
                    <span className="inline-flex items-center gap-1 text-[#929292] bg-[#181818] border border-[#292929] px-1.5 py-0.2 rounded animate-pulse">
                      <ClockIcon className="w-3 h-3 text-[#F5F5F5]" />
                      <span>{pl.processing_count} Active</span>
                    </span>
                  )}

                  {hasFailed && (
                    <span className="inline-flex items-center gap-1 text-[#929292] bg-[#181818] border border-[#292929] px-1.5 py-0.2 rounded">
                      <AlertCircleIcon className="w-3 h-3 text-rose-500" />
                      <span>{pl.failed_count} Failed</span>
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
