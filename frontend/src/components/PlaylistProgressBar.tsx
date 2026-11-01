"use client";

import React from "react";
import { PlaylistStatusResponse } from "@/types/api";

interface PlaylistProgressBarProps {
  status: PlaylistStatusResponse | null;
}

export function PlaylistProgressBar({ status }: PlaylistProgressBarProps) {
  if (!status || status.video_count === 0) return null;

  const total = status.video_count;
  const completed = status.completed_count;
  const processing = status.processing_count;
  const failed = status.failed_count + status.unavailable_count;
  const pending = Math.max(0, total - completed - processing - failed);

  const pctCompleted = Math.round((completed / total) * 100);
  const pctProcessing = Math.round((processing / total) * 100);
  const pctFailed = Math.round((failed / total) * 100);
  const pctPending = Math.max(0, 100 - pctCompleted - pctProcessing - pctFailed);

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">Ingestion Progress:</span>
          <span className="font-mono text-indigo-400">
            {completed} of {total} videos indexed
          </span>
          <span className="text-slate-500">({pctCompleted}%)</span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
            <span>{completed} Indexed</span>
          </span>
          {processing > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-indigo-500 inline-block animate-pulse"></span>
              <span>{processing} Running</span>
            </span>
          )}
          {failed > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-rose-500 inline-block"></span>
              <span>{failed} Failed/Skip</span>
            </span>
          )}
          {pending > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-slate-600 inline-block"></span>
              <span>{pending} Pending</span>
            </span>
          )}
        </div>
      </div>

      {/* Progress Bar Track */}
      <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden flex">
        {pctCompleted > 0 && (
          <div
            style={{ width: `${pctCompleted}%` }}
            className="bg-emerald-500 transition-all duration-500"
            title={`${completed} completed (${pctCompleted}%)`}
          />
        )}
        {pctProcessing > 0 && (
          <div
            style={{ width: `${pctProcessing}%` }}
            className="bg-indigo-500 transition-all duration-500 animate-pulse"
            title={`${processing} processing (${pctProcessing}%)`}
          />
        )}
        {pctFailed > 0 && (
          <div
            style={{ width: `${pctFailed}%` }}
            className="bg-rose-500 transition-all duration-500"
            title={`${failed} failed (${pctFailed}%)`}
          />
        )}
        {pctPending > 0 && (
          <div
            style={{ width: `${pctPending}%` }}
            className="bg-slate-700 transition-all duration-500"
            title={`${pending} pending (${pctPending}%)`}
          />
        )}
      </div>
    </div>
  );
}
