"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChatMessage, CitationItem, Playlist } from "@/types/api";
import { api } from "@/lib/api";
import { findFirstValidCitation, isValidCitation } from "@/lib/citations";
import {
  clearChatStorage,
  loadChatHistory,
  loadSelectedCitation,
  saveChatHistory,
  saveSelectedCitation,
} from "@/lib/chatStorage";
import {
  loadSelectedPlaylistId,
  saveSelectedPlaylistId,
} from "@/lib/playlistStorage";
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
  onSelectPlaylist?: (playlistId: string) => void;
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
export function generateMessageId(prefix: "user" | "assistant"): string {
  messageSeq += 1;
  return `${prefix}-${Date.now()}-${messageSeq}`;
}

export function ChatInterface({
  playlists,
  defaultPlaylistId,
  onSelectPlaylist,
}: ChatInterfaceProps) {
  const [isHydrated, setIsHydrated] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (typeof window === "undefined") return [];
    return loadChatHistory();
  });
  const [inputQuery, setInputQuery] = useState("");
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | "ALL">(() => {
    if (defaultPlaylistId) return defaultPlaylistId;
    if (typeof window !== "undefined") {
      const saved = loadSelectedPlaylistId();
      if (saved) return saved;
    }
    return "ALL";
  });
  const [prevDefaultId, setPrevDefaultId] = useState(defaultPlaylistId);
  if (defaultPlaylistId !== prevDefaultId) {
    setPrevDefaultId(defaultPlaylistId);
    if (defaultPlaylistId) {
      setSelectedPlaylistId(defaultPlaylistId);
    }
  }

  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  // Active Video Player Selection
  const [selectedCitation, setSelectedCitation] = useState<CitationItem | null>(() => {
    if (typeof window === "undefined") return null;
    const saved = loadSelectedCitation();
    if (saved) return saved;
    const history = loadChatHistory();
    for (let i = history.length - 1; i >= 0; i--) {
      if (history[i].role === "assistant" && history[i].citations) {
        const firstValid = findFirstValidCitation(history[i].citations!);
        if (firstValid) return firstValid;
      }
    }
    return null;
  });

  // Mobile View Switcher ("chat" | "player")
  const [mobileTab, setMobileTab] = useState<"chat" | "player">("chat");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const activeRequestIdRef = useRef<number>(0);

  // Hydrate chat history and citation state from localStorage on client mount
  useEffect(() => {
    const storedMessages = loadChatHistory();
    if (storedMessages.length > 0) {
      setMessages(storedMessages);
      const storedCitation = loadSelectedCitation();
      if (storedCitation) {
        setSelectedCitation(storedCitation);
      } else {
        for (let i = storedMessages.length - 1; i >= 0; i--) {
          if (storedMessages[i].role === "assistant" && storedMessages[i].citations) {
            const firstValid = findFirstValidCitation(storedMessages[i].citations!);
            if (firstValid) {
              setSelectedCitation(firstValid);
              break;
            }
          }
        }
      }
    }
    setIsHydrated(true);
  }, []);

  // Persist messages only AFTER initial hydration has completed
  useEffect(() => {
    if (!isHydrated) return;
    saveChatHistory(messages);
  }, [messages, isHydrated]);

  // Persist selectedCitation only AFTER initial hydration has completed
  useEffect(() => {
    if (!isHydrated) return;
    saveSelectedCitation(selectedCitation);
  }, [selectedCitation, isHydrated]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSelectCitation = (citation: CitationItem) => {
    setSelectedCitation(citation);
    // On mobile, auto-switch to player tab so the user sees the video immediately
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
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

      // Automatic video selection after every new answer
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
      clearChatStorage();
    }
  };

  const handleScopeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const nextId = e.target.value;
    setSelectedPlaylistId(nextId);
    saveSelectedPlaylistId(nextId);
    onSelectPlaylist?.(nextId);
  };

  const activePlaylist = playlists.find((p) => p.id === selectedPlaylistId);

  return (
    <div className="flex flex-col h-[calc(100vh-110px)] min-h-[580px] bg-[#111111] border border-[#292929] rounded-xl overflow-hidden min-w-0 w-full shadow-xs">
      {/* Top Filter & Control Bar */}
      <div className="px-3 sm:px-4 py-2 border-b border-[#292929] bg-[#111111] flex flex-wrap items-center justify-between gap-2.5 min-w-0">
        {/* Left: Playlist Scope Selector */}
        <div className="flex items-center gap-2 min-w-0">
          <label
            htmlFor="playlist-scope-select"
            className="text-[11px] font-medium text-[#929292] uppercase tracking-wider shrink-0"
          >
            Scope:
          </label>
          <div className="relative min-w-0">
            <select
              id="playlist-scope-select"
              value={selectedPlaylistId}
              onChange={handleScopeChange}
              className="text-xs bg-[#181818] border border-[#292929] rounded-md px-2.5 py-1 text-[#F5F5F5] focus:outline-none focus:border-[#444] font-medium max-w-[200px] sm:max-w-[280px] truncate"
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
            <span className="hidden xl:inline text-[11px] text-[#626262] font-mono truncate">
              {activePlaylist.video_count} videos
            </span>
          )}
        </div>

        {/* Center: Mobile View Toggle (hidden on desktop lg) */}
        <div className="flex lg:hidden items-center bg-[#181818] p-0.5 rounded-md border border-[#292929] text-xs">
          <button
            onClick={() => setMobileTab("chat")}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              mobileTab === "chat"
                ? "bg-[#202020] text-[#F5F5F5] border border-[#292929]"
                : "text-[#929292] hover:text-[#F5F5F5]"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileTab("player")}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1 ${
              mobileTab === "player"
                ? "bg-[#202020] text-[#F5F5F5] border border-[#292929]"
                : "text-[#929292] hover:text-[#F5F5F5]"
            }`}
          >
            <PlayIcon className="w-3 h-3 text-[#F5F5F5]" />
            <span>Lecture Video</span>
            {selectedCitation && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            )}
          </button>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {messages.length > 0 && (
            <button
              onClick={handleClearHistory}
              className="text-xs text-[#929292] hover:text-[#F5F5F5] px-2 py-1 rounded-md border border-[#292929] hover:bg-[#181818] transition-colors flex items-center gap-1.5 font-mono"
              title="Clear Chat"
              aria-label="Clear Chat"
            >
              <TrashIcon className="w-3 h-3" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          )}

          <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#929292] bg-[#181818] px-2 py-1 rounded-md border border-[#292929]">
            <SparklesIcon className="w-3 h-3 text-[#929292]" />
            <span className="hidden sm:inline">Groq GPT-OSS-120B</span>
          </div>
        </div>
      </div>

      {/* Main Split-Screen Workspace */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden min-w-0 w-full">
        {/* LEFT PANEL: Chat Interface (50% on desktop) */}
        <div
          className={`w-full lg:w-1/2 flex flex-col h-full border-b lg:border-b-0 lg:border-r border-[#292929] bg-[#0E0E0E] min-w-0 ${
            mobileTab === "chat" ? "flex" : "hidden lg:flex"
          }`}
        >
          {/* Scrollable Conversation History */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden p-3 sm:p-4 space-y-3 min-w-0">
            {/* Empty State */}
            {messages.length === 0 && (
              <div className="max-w-lg mx-auto py-8 text-center space-y-5 min-w-0">
                <div className="w-10 h-10 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center mx-auto text-[#929292]">
                  <BotIcon className="w-5 h-5" />
                </div>

                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-[#F5F5F5]">
                    Lectra Revision Chatbot
                  </h3>
                  <p className="text-xs text-[#929292] max-w-sm mx-auto leading-relaxed">
                    Ask questions about your lectures. Answers cite exact timestamps.
                    Click any citation to load the video in the split-screen player.
                  </p>
                </div>

                {/* Quick Starter Chips */}
                <div className="space-y-2 pt-2">
                  <span className="text-[10px] font-medium text-[#626262] uppercase tracking-wider">
                    Example revision queries
                  </span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                    {STARTER_QUESTIONS.map((item, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSend(item.query)}
                        className="p-2.5 rounded-md bg-[#181818] border border-[#292929] hover:border-[#383838] hover:bg-[#202020] transition-colors group text-left min-w-0"
                      >
                        <div className="text-xs font-medium text-[#F5F5F5] group-hover:text-white transition-colors truncate">
                          {item.title}
                        </div>
                        <div className="text-[11px] text-[#929292] truncate mt-0.5">
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
              <div className="flex gap-2.5 max-w-xl mr-auto min-w-0 animate-fade-in">
                <div className="w-6 h-6 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center shrink-0 text-[#929292] mt-0.5">
                  <BotIcon className="w-3.5 h-3.5" />
                </div>
                <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 text-xs text-[#929292] font-mono flex items-center gap-2">
                  <RefreshCwIcon className="w-3.5 h-3.5 animate-spin text-[#929292]" />
                  <span>Retrieving lecture context and generating grounded answer...</span>
                </div>
              </div>
            )}

            {/* Error Banner */}
            {errorBanner && (
              <div className="flex items-center gap-2 p-2.5 rounded-md bg-[#181818] border border-[#292929] text-xs text-[#F5F5F5] min-w-0">
                <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
                <span className="flex-1 break-words">{errorBanner}</span>
                <button
                  onClick={() => setErrorBanner(null)}
                  className="text-[#626262] hover:text-[#F5F5F5] text-xs font-mono ml-2 shrink-0"
                >
                  ✕
                </button>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Compact Bottom Message Input Bar */}
          <div className="p-2.5 sm:p-3 border-t border-[#292929] bg-[#111111] min-w-0">
            <div className="flex gap-2 items-center min-w-0">
              <div className="relative flex-1 min-w-0">
                <textarea
                  ref={textareaRef}
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about your revision lectures..."
                  rows={1}
                  disabled={isLoading}
                  className="w-full resize-none px-3 py-2 rounded-md bg-[#181818] border border-[#292929] focus:border-[#444] text-[#F5F5F5] text-xs sm:text-sm placeholder-[#626262] outline-none transition-colors disabled:opacity-50 min-h-[38px] max-h-[96px]"
                />
              </div>

              <button
                onClick={() => handleSend()}
                disabled={isLoading || !inputQuery.trim()}
                className="px-3.5 py-2 rounded-md bg-[#F5F5F5] hover:bg-[#E5E5E5] disabled:bg-[#202020] disabled:text-[#626262] text-[#0A0A0A] font-medium text-xs transition-colors flex items-center justify-center gap-1.5 shrink-0 shadow-xs h-[38px]"
                title="Send query (Enter)"
              >
                {isLoading ? (
                  <RefreshCwIcon className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <SendIcon className="w-3.5 h-3.5" />
                )}
                <span className="hidden sm:inline">Send</span>
              </button>
            </div>
            <p className="text-[10px] text-[#626262] text-center mt-1 font-mono">
              Press <kbd className="px-1 py-0.2 rounded bg-[#181818] border border-[#292929] text-[#929292]">Enter</kbd> to send, <kbd className="px-1 py-0.2 rounded bg-[#181818] border border-[#292929] text-[#929292]">Shift + Enter</kbd> for new line
            </p>
          </div>
        </div>

        {/* RIGHT PANEL: Embedded YouTube Lecture Player (50% on desktop) */}
        <div
          className={`w-full lg:w-1/2 h-full p-3 sm:p-4 overflow-y-auto bg-[#111111] min-w-0 ${
            mobileTab === "player" ? "flex flex-col" : "hidden lg:flex lg:flex-col"
          }`}
        >
          <YouTubePlayerPanel selectedCitation={selectedCitation} />
        </div>
      </div>
    </div>
  );
}
