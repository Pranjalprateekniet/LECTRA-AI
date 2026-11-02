"use client";

import React, { useCallback, useEffect, useState } from "react";
import { HealthData, Playlist } from "@/types/api";
import { api } from "@/lib/api";
import { Header } from "@/components/Header";
import { ChatInterface } from "@/components/ChatInterface";
import {
  loadSelectedPlaylistId,
  resolveActivePlaylistId,
  saveSelectedPlaylistId,
} from "@/lib/playlistStorage";

export default function Home() {
  // Backend Health
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  // Playlists (for user scope selection in chat)
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selectedPlaylistId, setSelectedPlaylistId] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // 1. Fetch Backend Health
  const checkHealth = useCallback(async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch {
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // 2. Fetch Ingested Playlists
  const loadPlaylists = useCallback(async () => {
    try {
      const data = await api.getPlaylists();
      setPlaylists(data);
      if (data.length > 0) {
        setSelectedPlaylistId((prev) => {
          if (prev && data.some((p) => p.id === prev)) return prev;
          const savedId = loadSelectedPlaylistId();
          return resolveActivePlaylistId(data, savedId);
        });
      }
    } catch (err: unknown) {
      console.error("Failed to load playlists:", err);
    }
  }, []);

  // Playlist selection change handler
  const handlePlaylistChange = useCallback((id: string) => {
    setSelectedPlaylistId(id);
    saveSelectedPlaylistId(id);
  }, []);

  // Initial Load
  useEffect(() => {
    checkHealth();
    loadPlaylists();
  }, [checkHealth, loadPlaylists]);

  // Manual Refresh Handler
  const handleManualRefresh = async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([checkHealth(), loadPlaylists()]);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-[#F5F5F5] flex flex-col font-sans selection:bg-[#202020] selection:text-[#F5F5F5] w-full max-w-full overflow-x-hidden">
      {/* User Header without Ingestion Tabs or Admin Links */}
      <Header
        health={health}
        healthLoading={healthLoading}
        isRefreshing={isRefreshing}
        onRefresh={handleManualRefresh}
        isAdmin={false}
      />

      {/* Main Revision Chat Interface */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 lg:px-8 py-3.5 sm:py-5 min-w-0 overflow-x-hidden">
        <ChatInterface
          playlists={playlists}
          defaultPlaylistId={selectedPlaylistId}
          onSelectPlaylist={handlePlaylistChange}
        />
      </main>

      {/* Footer */}
      <footer className="border-t border-[#292929] bg-[#0A0A0A] py-3 text-center text-xs text-[#626262] font-mono">
        Lectra — YouTube Revision RAG Engine • EmbeddingGemma 2 (768d) • Qdrant Cloud • Groq GPT-OSS-120B
      </footer>
    </div>
  );
}
