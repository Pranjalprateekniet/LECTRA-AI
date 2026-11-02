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
      className={`border rounded-md overflow-hidden transition-colors text-left cursor-pointer group min-w-0 w-full ${
        isSelected
          ? "bg-[#181818] border-[#383838] ring-1 ring-[#383838]"
          : "bg-[#111111] border-[#292929] hover:border-[#383838] hover:bg-[#141414]"
      }`}
    >
      {/* Header bar */}
      <div className="p-2 sm:p-2.5 flex items-center justify-between gap-2 select-none min-w-0">
        <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
          {/* Source ID Pill (e.g. S1, S2) */}
          <span
            className={`px-1.5 py-0.5 rounded font-mono font-medium text-[10px] shrink-0 transition-colors ${
              isSelected
                ? "bg-[#F5F5F5] text-[#0A0A0A]"
                : "bg-[#181818] text-[#929292] border border-[#292929] group-hover:text-[#F5F5F5] group-hover:border-[#383838]"
            }`}
          >
            [{citation.source_id}]
          </span>

          {/* Video Title */}
          <span
            className={`text-xs font-medium truncate min-w-0 transition-colors ${
              isSelected ? "text-[#F5F5F5]" : "text-[#929292] group-hover:text-[#F5F5F5]"
            }`}
            title={citation.video_title}
          >
            {citation.video_title}
          </span>

          {isSelected && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-[#929292] bg-[#181818] border border-[#292929] px-1.5 py-0.2 rounded shrink-0">
              <PlayIcon className="w-2.5 h-2.5 text-[#F5F5F5]" />
              <span>Active</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Timestamp Range Pill */}
          <span className="text-[10px] font-mono text-[#929292] bg-[#181818] px-1.5 py-0.5 rounded border border-[#292929] whitespace-nowrap">
            {startTimeStr} - {endTimeStr}
          </span>

          {/* Direct YouTube Timestamp Link (opens in new tab) */}
          <a
            href={citation.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="p-1 rounded text-[#626262] hover:text-[#F5F5F5] hover:bg-[#202020] transition-colors"
            title={`Open directly on YouTube at ${startTimeStr}`}
          >
            <ExternalLinkIcon className="w-3.5 h-3.5" />
          </a>

          {/* Expand/Collapse Toggle Button */}
          <button
            type="button"
            onClick={handleToggleExpand}
            className="text-[#626262] hover:text-[#929292] transition-colors p-0.5"
            aria-label={isExpanded ? "Collapse transcript" : "Expand transcript"}
          >
            {isExpanded ? (
              <ChevronDownIcon className="w-3.5 h-3.5" />
            ) : (
              <ChevronRightIcon className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Collapsible Transcript Excerpt */}
      {isExpanded && (
        <div className="px-3 py-2 bg-[#0E0E0E] border-t border-[#292929] text-xs text-[#929292] space-y-1.5 min-w-0">
          <div className="flex items-center justify-between text-[10px] font-mono text-[#626262] min-w-0 flex-wrap gap-1">
            <span>Verified Transcript Chunk #{citation.chunk_index}</span>
            <span className="text-[#929292]">Play at {startTimeStr}</span>
          </div>

          <blockquote className="border-l-2 border-[#383838] pl-2.5 py-1 text-[#929292] italic text-xs leading-relaxed bg-[#111111] rounded-r break-words [overflow-wrap:anywhere]">
            {citation.text ? (
              <span>&ldquo;{citation.text}&rdquo;</span>
            ) : (
              <span className="text-[#626262]">
                Transcript segment text recorded at timestamp {startTimeStr} to {endTimeStr}.
              </span>
            )}
          </blockquote>
        </div>
      )}
    </div>
  );
}
