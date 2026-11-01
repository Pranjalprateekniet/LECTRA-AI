"use client";

import React from "react";
import { HealthData } from "@/types/api";
import { RefreshCwIcon } from "./Icons";

interface HeaderProps {
  health: HealthData | null;
  healthLoading: boolean;
  isPolling: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  activeTab: "ingestion" | "qa";
  onTabChange: (tab: "ingestion" | "qa") => void;
}

export function Header({
  health,
  healthLoading,
  isPolling,
  isRefreshing,
  onRefresh,
  activeTab,
  onTabChange,
}: HeaderProps) {
  const isHealthy = health?.status === "healthy";
  const device = health?.execution_device || "Unknown";

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <span className="text-white font-bold text-lg tracking-wider">L</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-slate-100 tracking-tight">Lectra</span>
                <span className="text-xs px-2 py-0.5 rounded font-mono font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Revision RAG
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                Grounded Video Revision Knowledge Base
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-xl border border-slate-800/80">
            <button
              onClick={() => onTabChange("ingestion")}
              className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all ${
                activeTab === "ingestion"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              Tab 1: Data Ingestion
            </button>
            <button
              onClick={() => onTabChange("qa")}
              className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all flex items-center gap-1.5 ${
                activeTab === "qa"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
              }`}
            >
              <span>Tab 2: Revision Chatbot</span>
            </button>
          </nav>

          {/* Status & Actions */}
          <div className="flex items-center gap-3">
            {/* Backend Health Badge */}
            <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono border bg-slate-950/70 border-slate-800">
              <span
                className={`w-2 h-2 rounded-full ${
                  healthLoading
                    ? "bg-amber-400 animate-pulse"
                    : isHealthy
                    ? "bg-emerald-400"
                    : "bg-red-400"
                }`}
              />
              <span className="text-slate-300">
                {healthLoading ? "Checking backend..." : isHealthy ? "Connected" : "Offline"}
              </span>
              {isHealthy && (
                <span className="text-slate-500 border-l border-slate-800 pl-2">
                  {device.includes("CUDA") ? "CUDA" : "CPU"}
                </span>
              )}
            </div>

            {/* Polling Indicator */}
            {isPolling && (
              <span className="flex items-center gap-1.5 text-xs text-indigo-400 font-mono bg-indigo-950/40 border border-indigo-800/40 px-2 py-1 rounded-md animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                <span>Live Polling</span>
              </span>
            )}

            {/* Manual Refresh */}
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 border border-transparent hover:border-slate-700 transition"
              title="Refresh data from backend"
            >
              <RefreshCwIcon className={`w-4 h-4 ${isRefreshing ? "animate-spin text-indigo-400" : ""}`} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
