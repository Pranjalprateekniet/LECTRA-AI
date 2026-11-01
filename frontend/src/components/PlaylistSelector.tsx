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
      <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-6 text-center text-slate-400 text-sm animate-pulse">
        Loading ingested playlists...
      </div>
    );
  }

  if (playlists.length === 0) {
    return (
      <div className="bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-8 text-center">
        <VideoIcon className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <h3 className="text-sm font-medium text-slate-300">No playlists ingested yet</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
          Submit a YouTube playlist URL above to begin discovery and ingestion.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Ingested Playlists ({playlists.length})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {playlists.map((pl) => {
          const isSelected = pl.id === selectedId;
          const isFullyIndexed = pl.completed_count === pl.video_count && pl.video_count > 0;
          const hasFailed = pl.failed_count > 0;
          const isProcessing = pl.processing_count > 0 || pl.status.includes("RUNNING");

          return (
            <div
              key={pl.id}
              onClick={() => onSelect(pl.id)}
              className={`cursor-pointer rounded-xl p-4 border transition-all text-left relative overflow-hidden group ${
                isSelected
                  ? "bg-slate-900 border-indigo-500 shadow-md shadow-indigo-950/40 ring-1 ring-indigo-500/50"
                  : "bg-slate-900/50 border-slate-800 hover:border-slate-700 hover:bg-slate-900/80"
              }`}
            >
              {/* Active Indicator Strip */}
              {isSelected && (
                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 to-violet-500" />
              )}

              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-sm text-slate-100 truncate group-hover:text-indigo-300 transition">
                      {pl.title || "Untitled Playlist"}
                    </h3>
                  </div>
                  <p className="text-xs text-slate-400 truncate mt-0.5">
                    {pl.channel_name || "Unknown Channel"}
                  </p>
                </div>

                <a
                  href={pl.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-slate-500 hover:text-slate-300 p-1 rounded transition"
                  title="Open on YouTube"
                >
                  <ExternalLinkIcon className="w-3.5 h-3.5" />
                </a>
              </div>

              {/* Status and counts */}
              <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5 font-mono text-slate-300">
                  <span className="font-semibold text-slate-100">{pl.video_count}</span>
                  <span className="text-slate-500">videos</span>
                </div>

                <div className="flex items-center gap-2 font-mono">
                  {isFullyIndexed && (
                    <span className="inline-flex items-center gap-1 text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded text-[11px]">
                      <CheckCircleIcon className="w-3 h-3" />
                      <span>{pl.completed_count}/{pl.video_count} Ready</span>
                    </span>
                  )}

                  {!isFullyIndexed && isProcessing && (
                    <span className="inline-flex items-center gap-1 text-indigo-400 bg-indigo-950/40 border border-indigo-800/40 px-2 py-0.5 rounded text-[11px] animate-pulse">
                      <ClockIcon className="w-3 h-3" />
                      <span>{pl.processing_count} Active</span>
                    </span>
                  )}

                  {hasFailed && (
                    <span className="inline-flex items-center gap-1 text-rose-400 bg-rose-950/40 border border-rose-800/40 px-2 py-0.5 rounded text-[11px]">
                      <AlertCircleIcon className="w-3 h-3" />
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
