"use client";

import React, { useState } from "react";
import { AlertCircleIcon, PlayIcon, RefreshCwIcon } from "./Icons";

interface PlaylistSubmitFormProps {
  onSubmit: (url: string) => Promise<void>;
  isSubmitting: boolean;
}

const TEST_PLAYLIST_URL = "https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ";

export function PlaylistSubmitForm({ onSubmit, isSubmitting }: PlaylistSubmitFormProps) {
  const [url, setUrl] = useState("");
  const [clientError, setClientError] = useState<string | null>(null);

  const validateUrl = (input: string): boolean => {
    const trimmed = input.trim();
    if (!trimmed) {
      setClientError("Please enter a YouTube playlist URL.");
      return false;
    }
    if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
      setClientError("URL must start with http:// or https://");
      return false;
    }
    if (!trimmed.includes("list=") && !trimmed.includes("youtube.com") && !trimmed.includes("youtu.be")) {
      setClientError("URL must be a valid YouTube playlist (must contain 'list=' parameter).");
      return false;
    }
    setClientError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateUrl(url)) return;
    await onSubmit(url.trim());
  };

  const handleFillTestPlaylist = () => {
    setUrl(TEST_PLAYLIST_URL);
    setClientError(null);
  };

  return (
    <div className="bg-[#111111] border border-[#292929] rounded-xl p-4 sm:p-5 shadow-xs min-w-0">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3.5 min-w-0">
        <div>
          <h2 className="text-sm font-semibold text-[#F5F5F5] flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#F5F5F5]"></span>
            Ingest YouTube Playlist
          </h2>
          <p className="text-xs text-[#929292] mt-0.5">
            Submit a playlist to discover videos, download captions, translate to English, chunk, and index into Qdrant.
          </p>
        </div>

        <button
          type="button"
          onClick={handleFillTestPlaylist}
          className="text-xs inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#181818] hover:bg-[#202020] text-[#929292] hover:text-[#F5F5F5] border border-[#292929] transition-colors shrink-0"
        >
          <PlayIcon className="w-3 h-3 text-[#929292]" />
          <span>Fill Test Playlist (5 Videos)</span>
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3 min-w-0">
        <div className="flex flex-col sm:flex-row gap-2 min-w-0">
          <div className="relative flex-1 min-w-0">
            <input
              type="text"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (clientError) setClientError(null);
              }}
              placeholder="https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
              disabled={isSubmitting}
              className="w-full px-3 py-2 rounded-md bg-[#181818] border border-[#292929] focus:border-[#444] text-[#F5F5F5] text-xs sm:text-sm placeholder-[#626262] outline-none transition-colors disabled:opacity-60"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !url.trim()}
            className="px-4 py-2 rounded-md bg-[#F5F5F5] hover:bg-[#E5E5E5] disabled:bg-[#202020] disabled:text-[#626262] text-[#0A0A0A] font-medium text-xs sm:text-sm transition-colors flex items-center justify-center gap-2 min-w-[130px] shrink-0"
          >
            {isSubmitting ? (
              <>
                <RefreshCwIcon className="w-3.5 h-3.5 animate-spin text-[#0A0A0A]" />
                <span>Submitting...</span>
              </>
            ) : (
              <span>Start Ingestion</span>
            )}
          </button>
        </div>

        {clientError && (
          <div className="flex items-center gap-2 text-xs text-rose-400 bg-rose-950/30 border border-rose-900/50 px-3 py-2 rounded-lg">
            <AlertCircleIcon className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{clientError}</span>
          </div>
        )}
      </form>
    </div>
  );
}
