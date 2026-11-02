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
    <div className="bg-[#111111] border border-[#292929] rounded-lg p-3 space-y-2 min-w-0">
      <div className="flex flex-wrap items-center justify-between text-xs gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium text-[#F5F5F5] text-xs">Progress:</span>
          <span className="font-mono text-[#F5F5F5] text-xs">
            {completed} of {total} videos indexed
          </span>
          <span className="text-[#626262] text-xs font-mono">({pctCompleted}%)</span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-mono text-[#929292] shrink-0">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block"></span>
            <span>{completed} Indexed</span>
          </span>
          {processing > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#F5F5F5] inline-block animate-pulse"></span>
              <span>{processing} Running</span>
            </span>
          )}
          {failed > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 inline-block"></span>
              <span>{failed} Failed</span>
            </span>
          )}
          {pending > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#383838] inline-block"></span>
              <span>{pending} Pending</span>
            </span>
          )}
        </div>
      </div>

      {/* Progress Bar Track */}
      <div className="w-full h-1.5 bg-[#181818] rounded-full overflow-hidden flex min-w-0 border border-[#292929]">
        {pctCompleted > 0 && (
          <div
            style={{ width: `${pctCompleted}%` }}
            className="bg-[#F5F5F5] transition-all duration-300"
            title={`${completed} completed (${pctCompleted}%)`}
          />
        )}
        {pctProcessing > 0 && (
          <div
            style={{ width: `${pctProcessing}%` }}
            className="bg-[#626262] transition-all duration-300 animate-pulse"
            title={`${processing} processing (${pctProcessing}%)`}
          />
        )}
        {pctFailed > 0 && (
          <div
            style={{ width: `${pctFailed}%` }}
            className="bg-rose-500 transition-all duration-300"
            title={`${failed} failed (${pctFailed}%)`}
          />
        )}
        {pctPending > 0 && (
          <div
            style={{ width: `${pctPending}%` }}
            className="bg-[#202020] transition-all duration-300"
            title={`${pending} pending (${pctPending}%)`}
          />
        )}
      </div>
    </div>
  );
}
