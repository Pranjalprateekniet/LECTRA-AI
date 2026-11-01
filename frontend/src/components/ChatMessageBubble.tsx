"use client";

import React, { useState } from "react";
import { ChatMessage, CitationItem } from "@/types/api";
import { SourceCard } from "./SourceCard";
import {
  AlertCircleIcon,
  BotIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  UserIcon,
} from "./Icons";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  selectedCitation: CitationItem | null;
  onSelectCitation?: (citation: CitationItem) => void;
}

function renderFormattedParagraph(
  text: string,
  citations: CitationItem[],
  selectedCitation: CitationItem | null,
  messageId: string,
  onSelectCitation?: (c: CitationItem) => void
) {
  // Regex to match citation tokens like [S1], [S2]
  const parts = text.split(/(\[S\d+\])/gi);

  return parts.map((part, i) => {
    const match = part.match(/\[(S\d+)\]/i);
    if (match) {
      const srcId = match[1].toUpperCase();
      const citation = citations.find((c) => c.source_id.toUpperCase() === srcId);
      if (citation) {
        const isSelected =
          Boolean(selectedCitation) &&
          selectedCitation?.source_id.toUpperCase() === srcId &&
          selectedCitation?.youtube_id === citation.youtube_id &&
          (selectedCitation?.message_id ? selectedCitation.message_id === messageId : true);

        return (
          <button
            key={i}
            type="button"
            onClick={() => onSelectCitation?.(citation)}
            className={`inline-flex items-center px-1.5 py-0.2 mx-0.5 rounded font-mono font-bold text-xs transition cursor-pointer select-none ${
              isSelected
                ? "bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400"
                : "bg-indigo-500/20 text-indigo-400 hover:bg-indigo-500/30 border border-indigo-500/30"
            }`}
            title={`Play ${citation.video_title} in lecture player`}
          >
            {part}
          </button>
        );
      }
    }
    return <span key={i}>{part}</span>;
  });
}

export function ChatMessageBubble({
  message,
  selectedCitation,
  onSelectCitation,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const [sourcesOpen, setSourcesOpen] = useState(true);

  if (isUser) {
    return (
      <div className="flex justify-end gap-3 max-w-3xl ml-auto">
        <div className="flex flex-col items-end">
          <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-md max-w-xl text-sm leading-relaxed">
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
          <span className="text-[11px] text-slate-500 font-mono mt-1 px-1">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-slate-300">
          <UserIcon className="w-4 h-4" />
        </div>
      </div>
    );
  }

  // Assistant Message
  const status = message.status || "answered";
  const citations = message.citations || [];
  const hasCitations = citations.length > 0;

  // Status Badge Config
  const getStatusBadge = () => {
    switch (status) {
      case "answered":
        return {
          icon: CheckCircleIcon,
          color: "text-emerald-400 bg-emerald-950/40 border-emerald-800/50",
          label: "Fully Grounded in Lecture Transcripts",
        };
      case "partially_answered":
        return {
          icon: AlertCircleIcon,
          color: "text-amber-400 bg-amber-950/40 border-amber-800/50",
          label: "Partially Supported (Missing Info Highlighted)",
        };
      case "insufficient_context":
        return {
          icon: AlertCircleIcon,
          color: "text-slate-400 bg-slate-900 border-slate-800",
          label: "Insufficient Lecture Context (Abstention)",
        };
    }
  };

  const badge = getStatusBadge();
  const StatusIcon = badge.icon;

  return (
    <div className="flex gap-3 max-w-4xl mr-auto">
      <div className="w-8 h-8 rounded-full bg-indigo-950 border border-indigo-700 flex items-center justify-center shrink-0 text-indigo-400 shadow-sm">
        <BotIcon className="w-4 h-4" />
      </div>

      <div className="flex-1 space-y-3">
        {/* Answer Bubble Card */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl rounded-tl-sm p-4 sm:p-5 shadow-sm space-y-4">
          {/* Header Status Bar */}
          <div className="flex items-center justify-between gap-2 flex-wrap pb-3 border-b border-slate-800/80">
            <span
              className={`inline-flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-full border ${badge.color}`}
            >
              <StatusIcon className="w-3.5 h-3.5 shrink-0" />
              <span>{badge.label}</span>
            </span>

            <span className="text-[11px] text-slate-500 font-mono">
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>

          {/* Answer Text Content with Clickable Citation Pills */}
          <div className="text-sm text-slate-200 leading-relaxed space-y-3">
            {message.content.split("\n\n").map((para, idx) => (
              <p key={idx} className="whitespace-pre-wrap break-words">
                {renderFormattedParagraph(
                  para,
                  citations,
                  selectedCitation,
                  message.id,
                  onSelectCitation
                )}
              </p>
            ))}
          </div>

          {/* Partially Answered Notice */}
          {status === "partially_answered" && (
            <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-900/50 text-xs text-amber-300/90 space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertCircleIcon className="w-4 h-4 text-amber-400" />
                <span>Partial Lecture Support</span>
              </div>
              <p className="text-[11px] text-slate-300">
                Part of your question was answered using verified lecture transcripts. Any aspects
                not covered above were omitted because they are not present in the indexed videos.
              </p>
            </div>
          )}

          {/* Insufficient Context Notice */}
          {status === "insufficient_context" && (
            <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-1">
              <div className="font-semibold text-slate-300 flex items-center gap-1.5">
                <ClockIcon className="w-4 h-4 text-slate-400" />
                <span>Strict Grounding Enforcement</span>
              </div>
              <p className="text-[11px]">
                Lectra strictly abstains from inventing answers when the indexed video transcripts
                do not contain relevant content for this question.
              </p>
            </div>
          )}

          {/* Supporting Sources Section */}
          {hasCitations && (
            <div className="pt-2 border-t border-slate-800/80 space-y-2">
              <div
                onClick={() => setSourcesOpen(!sourcesOpen)}
                className="flex items-center justify-between cursor-pointer select-none py-1 group"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-300 group-hover:text-indigo-400 transition">
                    Retrieved Supporting Sources ({citations.length})
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
                    Click to Play
                  </span>
                </div>

                <button
                  type="button"
                  className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 font-mono"
                >
                  <span>{sourcesOpen ? "Hide Sources" : "Show Sources"}</span>
                  {sourcesOpen ? (
                    <ChevronDownIcon className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRightIcon className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>

              {sourcesOpen && (
                <div className="space-y-2 pt-1">
                  {citations.map((c) => {
                    const isSelected =
                      Boolean(selectedCitation) &&
                      selectedCitation?.source_id === c.source_id &&
                      selectedCitation?.youtube_id === c.youtube_id &&
                      selectedCitation?.chunk_index === c.chunk_index &&
                      (selectedCitation?.message_id ? selectedCitation.message_id === message.id : true);

                    return (
                      <SourceCard
                        key={`${message.id}-${c.source_id}-${c.chunk_index}`}
                        citation={c}
                        isSelected={isSelected}
                        onSelect={onSelectCitation}
                        defaultExpanded={false}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
