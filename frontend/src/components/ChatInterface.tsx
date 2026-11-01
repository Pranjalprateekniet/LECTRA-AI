"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChatMessage, CitationItem, Playlist } from "@/types/api";
import { api } from "@/lib/api";
import { findFirstValidCitation, isValidCitation } from "@/lib/citations";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { YouTubePlayerPanel } from "./YouTubePlayerPanel";
import {
  AlertCircleIcon,
  BotIcon,
  PlayIcon,
  RefreshCwIcon,
  SendIcon,
  SparklesIcon,
  TrashIcon,
} from "./Icons";

interface ChatInterfaceProps {
  playlists: Playlist[];
  defaultPlaylistId: string | null;
}

const STARTER_QUESTIONS = [
  {
    title: "N Meetings in One Room",
    query: "How do you select the maximum number of non-overlapping meetings?",
  },
  {
    title: "Job Sequencing Problem",
    query: "What is the greedy strategy and time complexity for Job Sequencing?",
  },
  {
    title: "Fractional Knapsack",
    query: "How does the Fractional Knapsack algorithm work and what is its time complexity?",
  },
  {
    title: "Unsupported Topic Test",
    query: "How does Dijkstra's algorithm find shortest paths in a graph?",
  },
];

export { isValidCitation, findFirstValidCitation };

let messageSeq = 0;
function generateMessageId(prefix: "user" | "assistant"): string {
  messageSeq += 1;
  return `${prefix}-${messageSeq}`;
}

export function ChatInterface({ playlists, defaultPlaylistId }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | "ALL">(
    defaultPlaylistId || "ALL"
  );
  const [prevDefaultId, setPrevDefaultId] = useState(defaultPlaylistId);
  if (defaultPlaylistId !== prevDefaultId) {
    setPrevDefaultId(defaultPlaylistId);
    if (selectedPlaylistId === "ALL" && defaultPlaylistId) {
      setSelectedPlaylistId(defaultPlaylistId);
    }
  }

  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  // Active Video Player Selection
  const [selectedCitation, setSelectedCitation] = useState<CitationItem | null>(null);

  // Mobile View Switcher ("chat" | "player")
  const [mobileTab, setMobileTab] = useState<"chat" | "player">("chat");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeRequestIdRef = useRef<number>(0);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSelectCitation = (citation: CitationItem) => {
    setSelectedCitation(citation);
    // On mobile, auto-switch to player tab so the user sees the video immediately
    if (window.innerWidth < 1024) {
      setMobileTab("player");
    }
  };

  const handleSend = async (queryText?: string) => {
    const q = (queryText !== undefined ? queryText : inputQuery).trim();
    if (!q || isLoading) return;

    setErrorBanner(null);
    setInputQuery("");

    // Create user message
    const userMsg: ChatMessage = {
      id: generateMessageId("user"),
      role: "user",
      content: q,
      timestamp: new Date().toISOString(),
      playlist_id: selectedPlaylistId === "ALL" ? null : selectedPlaylistId,
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);
    const currentRequestId = ++activeRequestIdRef.current;

    try {
      const response = await api.generateAnswer({
        query: q,
        playlist_id: selectedPlaylistId === "ALL" ? null : selectedPlaylistId,
      });

      // Prevent stale asynchronous responses from updating state
      if (currentRequestId !== activeRequestIdRef.current) {
        return;
      }

      const assistantMsgId = generateMessageId("assistant");
      const decoratedCitations: CitationItem[] = (response.citations || []).map((c) => ({
        ...c,
        message_id: assistantMsgId,
      }));

      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: response.answer,
        status: response.status,
        citations: decoratedCitations,
        timestamp: new Date().toISOString(),
        playlist_id: selectedPlaylistId === "ALL" ? null : selectedPlaylistId,
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Automatic video selection after every new answer:
      // Read citations associated with this specific answer, find the first valid
      // citation containing a YouTube video ID and timestamp, and select it.
      // If no valid citation exists (e.g. insufficient_context), clear selection to show empty player state.
      const firstValid = findFirstValidCitation(decoratedCitations);
      setSelectedCitation(firstValid);
    } catch (err: unknown) {
      if (currentRequestId !== activeRequestIdRef.current) {
        return;
      }
      const errDetail = err instanceof Error ? err.message : "Failed to generate answer";
      setErrorBanner(errDetail);
    } finally {
      if (currentRequestId === activeRequestIdRef.current) {
        setIsLoading(false);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClearHistory = () => {
    if (messages.length === 0) return;
    if (window.confirm("Are you sure you want to clear the conversation history?")) {
      activeRequestIdRef.current += 1;
      setMessages([]);
      setSelectedCitation(null);
      setErrorBanner(null);
      setIsLoading(false);
    }
  };

  const activePlaylist = playlists.find((p) => p.id === selectedPlaylistId);

  return (
    <div className="flex flex-col h-[calc(100vh-125px)] min-h-[640px] bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
      {/* Top Filter & Control Bar */}
      <div className="px-4 sm:px-6 py-3 border-b border-slate-800 bg-slate-950/80 flex flex-wrap items-center justify-between gap-3">
        {/* Left: Playlist Scope Selector */}
        <div className="flex items-center gap-2.5">
          <label
            htmlFor="playlist-scope-select"
            className="text-xs font-semibold text-slate-400 uppercase tracking-wider"
          >
            Scope:
          </label>
          <div className="relative">
            <select
              id="playlist-scope-select"
              value={selectedPlaylistId}
              onChange={(e) => setSelectedPlaylistId(e.target.value)}
              className="text-xs bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-indigo-500 font-medium"
            >
              <option value="ALL">All Indexed Playlists</option>
              {playlists.map((pl) => (
                <option key={pl.id} value={pl.id}>
                  {pl.title || "Untitled Playlist"} ({pl.video_count} videos)
                </option>
              ))}
            </select>
          </div>

          {activePlaylist && (
            <span className="hidden xl:inline text-[11px] text-slate-500 font-mono">
              Filtered to {activePlaylist.video_count} videos
            </span>
          )}
        </div>

        {/* Center: Mobile View Toggle (hidden on desktop lg) */}
        <div className="flex lg:hidden items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 text-xs">
          <button
            onClick={() => setMobileTab("chat")}
            className={`px-3 py-1 rounded-md font-medium transition ${
              mobileTab === "chat"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileTab("player")}
            className={`px-3 py-1 rounded-md font-medium transition flex items-center gap-1.5 ${
              mobileTab === "player"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <PlayIcon className="w-3 h-3 text-rose-500" />
            <span>Lecture Video</span>
            {selectedCitation && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            )}
          </button>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={handleClearHistory}
              className="text-xs text-slate-400 hover:text-rose-400 px-2.5 py-1.5 rounded-lg border border-slate-800 hover:border-rose-900/50 hover:bg-rose-950/30 transition flex items-center gap-1.5 font-mono"
              title="Clear all messages"
            >
              <TrashIcon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Clear History</span>
            </button>
          )}

          <div className="flex items-center gap-1.5 text-[11px] font-mono text-indigo-400 bg-indigo-950/40 px-2.5 py-1 rounded-md border border-indigo-800/40">
            <SparklesIcon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Groq GPT-OSS-120B</span>
          </div>
        </div>
      </div>

      {/* Main Split-Screen Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANEL: Chat Interface (54% on desktop) */}
        <div
          className={`w-full lg:w-[54%] flex flex-col h-full border-r border-slate-800/80 bg-slate-950/30 ${
            mobileTab === "chat" ? "flex" : "hidden lg:flex"
          }`}
        >
          {/* Scrollable Conversation History */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
            {/* Empty State */}
            {messages.length === 0 && (
              <div className="max-w-xl mx-auto py-8 text-center space-y-6">
                <div className="w-12 h-12 rounded-2xl bg-indigo-950/80 border border-indigo-800/60 flex items-center justify-center mx-auto text-indigo-400 shadow-lg shadow-indigo-950/50">
                  <BotIcon className="w-6 h-6" />
                </div>

                <div className="space-y-1">
                  <h3 className="text-base font-bold text-slate-100">
                    Lectra Revision Chatbot
                  </h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                    Ask questions about your lectures. Verified answers cite exact video timestamps.
                    Click any citation to load the video in the split-screen player.
                  </p>
                </div>

                {/* Quick Starter Chips */}
                <div className="space-y-2">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    Example revision queries
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                    {STARTER_QUESTIONS.map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSend(item.query)}
                        className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 hover:border-indigo-500/60 hover:bg-slate-900/60 transition group text-left"
                      >
                        <div className="text-xs font-semibold text-slate-300 group-hover:text-indigo-400 transition">
                          {item.title}
                        </div>
                        <div className="text-[11px] text-slate-500 truncate mt-0.5">
                          {item.query}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Message List */}
            {messages.map((msg) => (
              <ChatMessageBubble
                key={msg.id}
                message={msg}
                selectedCitation={selectedCitation}
                onSelectCitation={handleSelectCitation}
              />
            ))}

            {/* Generating Indicator Bubble */}
            {isLoading && (
              <div className="flex gap-3 max-w-2xl mr-auto animate-fade-in">
                <div className="w-8 h-8 rounded-full bg-indigo-950 border border-indigo-700 flex items-center justify-center shrink-0 text-indigo-400">
                  <BotIcon className="w-4 h-4" />
                </div>
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl rounded-tl-sm p-4 space-y-2 text-xs text-slate-400 font-mono flex items-center gap-3">
                  <RefreshCwIcon className="w-4 h-4 animate-spin text-indigo-400" />
                  <span>Retrieving lecture context and generating grounded answer...</span>
                </div>
              </div>
            )}

            {/* Error Banner */}
            {errorBanner && (
              <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300">
                <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
                <span className="flex-1">{errorBanner}</span>
                <button
                  onClick={() => setErrorBanner(null)}
                  className="text-slate-400 hover:text-slate-200 text-xs font-mono ml-2"
                >
                  ✕
                </button>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Fixed Bottom Message Input Bar */}
          <div className="p-3 sm:p-4 border-t border-slate-800 bg-slate-950/90">
            <div className="flex gap-2 items-end">
              <div className="relative flex-1">
                <textarea
                  ref={textareaRef}
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about your revision lectures..."
                  rows={2}
                  disabled={isLoading}
                  className="w-full resize-none px-4 py-2.5 rounded-xl bg-slate-900/90 border border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-slate-100 text-xs sm:text-sm placeholder-slate-500 outline-none transition disabled:opacity-60"
                />
              </div>

              <button
                onClick={() => handleSend()}
                disabled={isLoading || !inputQuery.trim()}
                className="px-4 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-xs sm:text-sm transition shadow-sm flex items-center justify-center gap-1.5 shrink-0"
                title="Send query (Enter)"
              >
                {isLoading ? (
                  <RefreshCwIcon className="w-4 h-4 animate-spin" />
                ) : (
                  <SendIcon className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Send</span>
              </button>
            </div>
            <p className="text-[10px] text-slate-500 text-center mt-1.5 font-mono">
              Press <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">Enter</kbd> to send, <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">Shift + Enter</kbd> for new line
            </p>
          </div>
        </div>

        {/* RIGHT PANEL: Embedded YouTube Lecture Player (46% on desktop) */}
        <div
          className={`w-full lg:w-[46%] h-full p-4 sm:p-5 overflow-y-auto bg-slate-950/60 ${
            mobileTab === "player" ? "flex flex-col" : "hidden lg:flex lg:flex-col"
          }`}
        >
          <YouTubePlayerPanel selectedCitation={selectedCitation} />
        </div>
      </div>
    </div>
  );
}
