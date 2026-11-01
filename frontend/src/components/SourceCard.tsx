"use client";

import React, { useState } from "react";
import { CitationItem } from "@/types/api";
import { ChevronDownIcon, ChevronRightIcon, ExternalLinkIcon, PlayIcon } from "./Icons";

interface SourceCardProps {
  citation: CitationItem;
  defaultExpanded?: boolean;
  isSelected?: boolean;
  onSelect?: (citation: CitationItem) => void;
}

function formatTime(seconds: number): string {
  const totalSecs = Math.floor(seconds);
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  const h = Math.floor(m / 60);
  if (h > 0) {
    const remM = m % 60;
    return `${h}:${remM < 10 ? "0" : ""}${remM}:${s < 10 ? "0" : ""}${s}`;
  }
  return `${m}:${s < 10 ? "0" : ""}${s}`;
}

export function SourceCard({
  citation,
  defaultExpanded = false,
  isSelected = false,
  onSelect,
}: SourceCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const startTimeStr = formatTime(citation.start_seconds);
  const endTimeStr = formatTime(citation.end_seconds);

  const handleCardClick = () => {
    if (onSelect) {
      onSelect(citation);
    }
  };

  const handleToggleExpand = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  return (
    <div
      onClick={handleCardClick}
      className={`border rounded-xl overflow-hidden transition-all text-left cursor-pointer group ${
        isSelected
          ? "bg-slate-900 border-indigo-500 shadow-md ring-1 ring-indigo-500/50"
          : "bg-slate-950/80 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60"
      }`}
    >
      {/* Header bar */}
      <div className="p-3 flex items-center justify-between gap-3 select-none">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Source ID Pill (e.g. S1, S2) */}
          <span
            className={`px-2 py-0.5 rounded font-mono font-bold text-xs shrink-0 transition ${
              isSelected
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 group-hover:bg-indigo-500/30"
            }`}
          >
            [{citation.source_id}]
          </span>

          {/* Video Title */}
          <span
            className={`text-xs font-medium truncate transition ${
              isSelected ? "text-indigo-200" : "text-slate-200 group-hover:text-slate-100"
            }`}
            title={citation.video_title}
          >
            {citation.video_title}
          </span>

          {isSelected && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-indigo-400 bg-indigo-950/60 border border-indigo-800/40 px-1.5 py-0.2 rounded shrink-0 animate-pulse">
              <PlayIcon className="w-2.5 h-2.5 text-indigo-400" />
              <span>Playing</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Timestamp Range Pill */}
          <span className="text-[11px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
            {startTimeStr} - {endTimeStr}
          </span>

          {/* Direct YouTube Timestamp Link (opens in new tab) */}
          <a
            href={citation.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
            title={`Open directly on YouTube at ${startTimeStr}`}
          >
            <ExternalLinkIcon className="w-3.5 h-3.5" />
          </a>

          {/* Expand/Collapse Toggle Button */}
          <button
            type="button"
            onClick={handleToggleExpand}
            className="text-slate-500 hover:text-slate-300 transition p-0.5"
            aria-label={isExpanded ? "Collapse transcript" : "Expand transcript"}
          >
            {isExpanded ? (
              <ChevronDownIcon className="w-4 h-4" />
            ) : (
              <ChevronRightIcon className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Collapsible Transcript Excerpt */}
      {isExpanded && (
        <div className="px-4 py-3 bg-slate-900/40 border-t border-slate-800/80 text-xs text-slate-300 space-y-2">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-500">
            <span>Verified Transcript Chunk #{citation.chunk_index}</span>
            <span className="text-indigo-400">Click card to play at {startTimeStr}</span>
          </div>

          <blockquote className="border-l-2 border-indigo-500/60 pl-3 py-1 text-slate-300 font-sans italic text-xs leading-relaxed bg-slate-950/40 rounded-r-lg">
            {citation.text ? (
              <span>&ldquo;{citation.text}&rdquo;</span>
            ) : (
              <span className="text-slate-500">
                Transcript segment text recorded at timestamp {startTimeStr} to {endTimeStr}.
              </span>
            )}
          </blockquote>
        </div>
      )}
    </div>
  );
}
