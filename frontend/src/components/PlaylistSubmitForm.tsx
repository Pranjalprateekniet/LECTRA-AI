"use client";

import React, { useState } from "react";
import { AlertCircleIcon, CheckCircleIcon, PlayIcon, RefreshCwIcon } from "./Icons";

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
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
            Ingest YouTube Playlist
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Submit a playlist to discover videos, download captions, translate to English, chunk, and index into Qdrant.
          </p>
        </div>

        <button
          type="button"
          onClick={handleFillTestPlaylist}
          className="text-xs inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 text-indigo-300 border border-indigo-800/50 hover:border-indigo-700 transition"
        >
          <PlayIcon className="w-3 h-3 text-indigo-400" />
          <span>Fill Verified Greedy Playlist (5 Videos)</span>
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                if (clientError) setClientError(null);
              }}
              placeholder="https://www.youtube.com/playlist?list=PLgUwDviBIf0pmWCl2nepwGDO05a0-7EfJ"
              disabled={isSubmitting}
              className="w-full px-4 py-2.5 rounded-xl bg-slate-950/70 border border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-slate-100 text-sm placeholder-slate-500 outline-none transition disabled:opacity-60"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !url.trim()}
            className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-medium text-sm transition shadow-sm flex items-center justify-center gap-2 min-w-[130px]"
          >
            {isSubmitting ? (
              <>
                <RefreshCwIcon className="w-4 h-4 animate-spin text-white" />
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
