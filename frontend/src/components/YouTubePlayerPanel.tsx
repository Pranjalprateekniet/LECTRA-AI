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
      <div className="h-full flex flex-col items-center justify-center p-8 text-center bg-slate-950/40 rounded-2xl border border-dashed border-slate-800">
        <div className="w-16 h-16 rounded-2xl bg-indigo-950/50 border border-indigo-800/40 flex items-center justify-center text-indigo-400 mb-4 shadow-inner">
          <VideoIcon className="w-8 h-8" />
        </div>
        <h3 className="text-base font-semibold text-slate-200">
          Embedded Lecture Video Player
        </h3>
        <p className="text-xs text-slate-400 max-w-sm mt-1.5 leading-relaxed">
          Ask a revision question on the left. Click any cited source card or timestamp badge
          to immediately jump this player to the exact video lecture timestamp.
        </p>
        <div className="mt-4 flex items-center gap-2 text-[11px] font-mono text-slate-500 bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800">
          <PlayIcon className="w-3.5 h-3.5 text-indigo-400" />
          <span>Interactive timestamp navigation enabled</span>
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
    <div className="flex flex-col h-full space-y-4">
      {/* Player Header Card */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded font-mono font-bold text-xs bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 shrink-0">
                [{selectedCitation.source_id}]
              </span>
              <h3
                className="text-sm font-semibold text-slate-100 truncate"
                title={selectedCitation.video_title}
              >
                {selectedCitation.video_title}
              </h3>
            </div>

            <div className="flex items-center gap-2.5 text-xs text-slate-400 font-mono mt-1.5 flex-wrap">
              <span className="flex items-center gap-1 text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded text-[11px]">
                <ClockIcon className="w-3 h-3" />
                <span>Timestamp: {startTimeStr} – {endTimeStr}</span>
              </span>
              <span className="text-slate-500">Chunk #{selectedCitation.chunk_index}</span>
            </div>
          </div>

          <a
            href={selectedCitation.youtube_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2.5 py-1.5 rounded-lg bg-rose-950/40 hover:bg-rose-900/40 border border-rose-800/50 text-rose-300 text-xs font-medium transition flex items-center gap-1.5 shrink-0"
            title="Open on YouTube website"
          >
            <PlayIcon className="w-3.5 h-3.5 text-rose-500" />
            <span className="hidden sm:inline">YouTube</span>
            <ExternalLinkIcon className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Video Embed Container (16:9 Aspect Ratio) */}
      <div className="relative w-full aspect-video bg-black rounded-2xl overflow-hidden border border-slate-800 shadow-lg">
        {iframeError ? (
          <div className="w-full h-full flex flex-col items-center justify-center p-6 text-center text-slate-400 text-xs space-y-3">
            <p>This YouTube video cannot be embedded due to content restriction.</p>
            <a
              href={selectedCitation.youtube_url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-medium flex items-center gap-2 transition"
            >
              <span>Watch on YouTube at {startTimeStr}</span>
              <ExternalLinkIcon className="w-4 h-4" />
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
      <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-xl p-4 overflow-y-auto space-y-2 text-xs">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 border-b border-slate-800/80 pb-2">
          <span className="font-semibold text-slate-300">Verified Transcript Excerpt</span>
          <span>YouTube ID: {selectedCitation.youtube_id}</span>
        </div>

        <blockquote className="border-l-2 border-indigo-500/80 pl-3 py-1.5 text-slate-200 font-sans italic text-xs leading-relaxed bg-slate-950/40 rounded-r-lg">
          {selectedCitation.text ? (
            <span>&ldquo;{selectedCitation.text}&rdquo;</span>
          ) : (
            <span className="text-slate-500">
              Lecture segment starting at timestamp {startTimeStr}. Click the video above to play.
            </span>
          )}
        </blockquote>
      </div>
    </div>
  );
}
