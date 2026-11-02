"use client";

import React, { useState } from "react";
import { CitationItem } from "@/types/api";
import {
  ExternalLinkIcon,
  PlayIcon,
  VideoIcon,
  ClockIcon,
} from "./Icons";

interface YouTubePlayerPanelProps {
  selectedCitation: CitationItem | null;
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

export function YouTubePlayerPanel({ selectedCitation }: YouTubePlayerPanelProps) {
  const [failedCitationKey, setFailedCitationKey] = useState<string | null>(null);

  if (!selectedCitation) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center bg-[#111111] rounded-lg border border-dashed border-[#292929] min-w-0">
        <div className="w-10 h-10 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center text-[#929292] mb-3">
          <VideoIcon className="w-5 h-5" />
        </div>
        <h3 className="text-sm font-semibold text-[#F5F5F5]">
          Lecture Video Player
        </h3>
        <p className="text-xs text-[#929292] max-w-xs mt-1 leading-relaxed">
          Ask a revision question on the left. Click any cited source or timestamp
          to jump this player to the exact video timestamp.
        </p>
        <div className="mt-3 flex items-center gap-1.5 text-[11px] font-mono text-[#626262] bg-[#181818] px-2.5 py-1 rounded-md border border-[#292929]">
          <PlayIcon className="w-3 h-3 text-[#929292]" />
          <span>Interactive timestamp navigation</span>
        </div>
      </div>
    );
  }

  const startSec = Math.floor(selectedCitation.start_seconds);
  const startTimeStr = formatTime(selectedCitation.start_seconds);
  const endTimeStr = formatTime(selectedCitation.end_seconds);
  const currentKey = `${selectedCitation.youtube_id}-${startSec}-${selectedCitation.source_id}-${selectedCitation.chunk_index}`;
  const iframeError = failedCitationKey === currentKey;

  // Construct official YouTube iframe embed URL with start timestamp and autoplay
  const embedUrl = `https://www.youtube.com/embed/${selectedCitation.youtube_id}?start=${startSec}&autoplay=1&rel=0`;

  return (
    <div className="flex flex-col h-full space-y-3 min-w-0">
      {/* Player Header Card */}
      <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 sm:p-3 min-w-0">
        <div className="flex items-start justify-between gap-2.5 min-w-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="px-1.5 py-0.5 rounded font-mono font-medium text-[10px] bg-[#202020] text-[#F5F5F5] border border-[#292929] shrink-0">
                [{selectedCitation.source_id}]
              </span>
              <h3
                className="text-xs sm:text-sm font-medium text-[#F5F5F5] truncate min-w-0"
                title={selectedCitation.video_title}
              >
                {selectedCitation.video_title}
              </h3>
            </div>

            <div className="flex items-center gap-2 text-[11px] text-[#929292] font-mono mt-1.5 flex-wrap min-w-0">
              <span className="flex items-center gap-1 text-[#929292] bg-[#111111] border border-[#292929] px-2 py-0.5 rounded">
                <ClockIcon className="w-3 h-3 text-[#626262]" />
                <span>{startTimeStr} – {endTimeStr}</span>
              </span>
              <span className="text-[#626262]">Chunk #{selectedCitation.chunk_index}</span>
            </div>
          </div>

          <a
            href={selectedCitation.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 rounded-md bg-[#202020] hover:bg-[#292929] border border-[#292929] text-[#F5F5F5] text-xs font-medium transition-colors flex items-center gap-1.5 shrink-0"
            title="Open on YouTube website"
          >
            <PlayIcon className="w-3 h-3 text-[#F5F5F5]" />
            <span className="hidden sm:inline">YouTube</span>
            <ExternalLinkIcon className="w-3 h-3 text-[#929292]" />
          </a>
        </div>
      </div>

      {/* Video Embed Container (16:9 Aspect Ratio) */}
      <div className="relative w-full aspect-video bg-black rounded-lg overflow-hidden border border-[#292929] shrink-0">
        {iframeError ? (
          <div className="w-full h-full flex flex-col items-center justify-center p-6 text-center text-[#929292] text-xs space-y-3">
            <p>This YouTube video cannot be embedded due to platform restrictions.</p>
            <a
              href={selectedCitation.youtube_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-md bg-[#202020] hover:bg-[#292929] border border-[#292929] text-[#F5F5F5] font-medium flex items-center gap-1.5 transition-colors"
            >
              <span>Watch on YouTube at {startTimeStr}</span>
              <ExternalLinkIcon className="w-3.5 h-3.5 text-[#929292]" />
            </a>
          </div>
        ) : (
          <iframe
            key={currentKey}
            src={embedUrl}
            title={selectedCitation.video_title}
            className="w-full h-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            onError={() => setFailedCitationKey(currentKey)}
          />
        )}
      </div>

      {/* Transcript Excerpt Card */}
      <div className="flex-1 bg-[#181818] border border-[#292929] rounded-lg p-3 overflow-y-auto space-y-2 text-xs min-w-0">
        <div className="flex items-center justify-between text-[10px] font-mono text-[#626262] border-b border-[#292929] pb-1.5 min-w-0 flex-wrap gap-1">
          <span className="font-medium text-[#929292]">Verified Transcript Excerpt</span>
          <span className="truncate">ID: {selectedCitation.youtube_id}</span>
        </div>

        <blockquote className="border-l-2 border-[#383838] pl-2.5 py-1 text-[#F5F5F5] font-sans italic text-xs leading-relaxed bg-[#111111] rounded-r break-words [overflow-wrap:anywhere]">
          {selectedCitation.text ? (
            <span>&ldquo;{selectedCitation.text}&rdquo;</span>
          ) : (
            <span className="text-[#626262]">
              Lecture segment starting at timestamp {startTimeStr}. Click video above to play.
            </span>
          )}
        </blockquote>
      </div>
    </div>
  );
}
