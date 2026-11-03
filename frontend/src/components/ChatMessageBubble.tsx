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
            className={`inline-flex items-center px-1.5 py-0.2 mx-0.5 rounded font-mono font-medium text-[11px] transition-colors cursor-pointer select-none ${
              isSelected
                ? "bg-[#F5F5F5] text-[#0A0A0A] border border-[#F5F5F5] shadow-xs"
                : "bg-[#202020] text-[#929292] hover:text-[#F5F5F5] hover:bg-[#292929] border border-[#292929]"
            }`}
            title={`Play ${citation.video_title} in lecture player`}
          >
            {part}
          </button>
        );
      }
    }
    return <span key={i} className="select-text cursor-text">{part}</span>;
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
      <div className="flex justify-end gap-2 max-w-[85%] sm:max-w-[78%] ml-auto min-w-0 select-text">
        <div className="flex flex-col items-end min-w-0 select-text">
          <div className="bg-[#202020] text-[#F5F5F5] border border-[#292929] rounded-lg px-3 py-2 text-xs sm:text-sm leading-relaxed min-w-0 break-words [overflow-wrap:anywhere] select-text cursor-text selection:bg-[#4a4a4a] selection:text-white">
            <p className="whitespace-pre-wrap select-text cursor-text">{message.content}</p>
          </div>
          <span className="text-[10px] text-[#626262] font-mono mt-0.5 px-0.5 select-none">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        <div className="w-6 h-6 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center shrink-0 text-[#929292] mt-0.5 select-none">
          <UserIcon className="w-3.5 h-3.5" />
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
          dotColor: "bg-emerald-500",
          label: "Fully Grounded in Transcripts",
        };
      case "partially_answered":
        return {
          icon: AlertCircleIcon,
          dotColor: "bg-amber-400",
          label: "Partially Supported",
        };
      case "insufficient_context":
        return {
          icon: ClockIcon,
          dotColor: "bg-[#626262]",
          label: "Insufficient Context (Abstained)",
        };
    }
  };

  const badge = getStatusBadge();

  return (
    <div className="flex gap-2.5 max-w-[96%] sm:max-w-[92%] mr-auto min-w-0 w-full select-text">
      <div className="w-6 h-6 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center shrink-0 text-[#929292] mt-0.5 select-none">
        <BotIcon className="w-3.5 h-3.5" />
      </div>

      <div className="flex-1 space-y-2 min-w-0 select-text">
        {/* Answer Bubble Card */}
        <div className="bg-[#181818] border border-[#292929] rounded-lg p-3 sm:p-3.5 space-y-2.5 min-w-0 select-text">
          {/* Header Status Bar */}
          <div className="flex items-center justify-between gap-2 flex-wrap pb-2 border-b border-[#292929] min-w-0 select-none">
            <span className="inline-flex items-center gap-1.5 text-[11px] font-mono px-2 py-0.5 rounded border border-[#292929] bg-[#111111] text-[#929292]">
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${badge.dotColor}`} />
              <span className="truncate">{badge.label}</span>
            </span>

            <span className="text-[10px] text-[#626262] font-mono">
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>

          {/* Answer Text Content with Clickable Citation Pills */}
          <div className="text-xs sm:text-sm text-[#F5F5F5] leading-relaxed space-y-2 min-w-0 break-words [overflow-wrap:anywhere] select-text cursor-text selection:bg-[#4a4a4a] selection:text-white">
            {message.content.split("\n\n").map((para, idx) => (
              <p key={idx} className="whitespace-pre-wrap select-text cursor-text">
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
            <div className="p-2 rounded-md bg-[#111111] border border-[#292929] text-[11px] text-[#929292] space-y-0.5 min-w-0 select-text">
              <div className="font-medium text-[#F5F5F5] flex items-center gap-1.5 select-none">
                <AlertCircleIcon className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span>Partial Lecture Support</span>
              </div>
              <p className="text-[10px] text-[#929292] leading-relaxed select-text cursor-text">
                Part of this answer is verified from lecture transcripts. Aspects not covered above were omitted because they are not present in indexed videos.
              </p>
            </div>
          )}

          {/* Insufficient Context Notice */}
          {status === "insufficient_context" && (
            <div className="p-2 rounded-md bg-[#111111] border border-[#292929] text-[11px] text-[#929292] space-y-0.5 min-w-0 select-text">
              <div className="font-medium text-[#F5F5F5] flex items-center gap-1.5 select-none">
                <ClockIcon className="w-3.5 h-3.5 text-[#626262] shrink-0" />
                <span>Grounding Enforcement</span>
              </div>
              <p className="text-[10px] text-[#929292] leading-relaxed select-text cursor-text">
                Lectra strictly abstains from inventing answers when the indexed video transcripts do not contain relevant content.
              </p>
            </div>
          )}

          {/* Supporting Sources Section */}
          {hasCitations && (
            <div className="pt-1.5 border-t border-[#292929] space-y-1.5 min-w-0">
              <div
                onClick={() => setSourcesOpen(!sourcesOpen)}
                className="flex items-center justify-between cursor-pointer select-none py-0.5 group min-w-0"
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="text-xs font-medium text-[#929292] group-hover:text-[#F5F5F5] transition-colors truncate">
                    Sources ({citations.length})
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#111111] border border-[#292929] text-[#626262] font-mono shrink-0">
                    Click to Play
                  </span>
                </div>

                <button
                  type="button"
                  className="text-[11px] text-[#626262] hover:text-[#929292] flex items-center gap-0.5 font-mono transition-colors shrink-0"
                >
                  <span>{sourcesOpen ? "Hide" : "Show"}</span>
                  {sourcesOpen ? (
                    <ChevronDownIcon className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRightIcon className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>

              {sourcesOpen && (
                <div className="space-y-1.5 pt-0.5 min-w-0">
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
