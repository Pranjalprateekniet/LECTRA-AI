"use client";

import React from "react";
import { HealthData } from "@/types/api";
import { RefreshCwIcon } from "./Icons";

interface HeaderProps {
  health: HealthData | null;
  healthLoading: boolean;
  isPolling?: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  isAdmin?: boolean;
}

export function Header({
  health,
  healthLoading,
  isPolling = false,
  isRefreshing,
  onRefresh,
  isAdmin = false,
}: HeaderProps) {
  const isHealthy = health?.status === "healthy";
  const device = health?.execution_device || "Unknown";

  return (
    <header className="border-b border-[#292929] bg-[#111111] sticky top-0 z-30 w-full">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 min-w-0">
        <div className="flex items-center justify-between h-14 gap-3 min-w-0">
          {/* Brand */}
          <div className="flex items-center gap-2.5 min-w-0 shrink-0">
            <div className="w-7 h-7 rounded-md bg-[#181818] border border-[#292929] flex items-center justify-center shrink-0">
              <span className="text-[#F5F5F5] font-semibold text-xs tracking-wider">L</span>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-semibold text-[#F5F5F5] tracking-tight">
                  {isAdmin ? "Lectra Admin" : "Lectra"}
                </span>
                <span className="text-[10px] px-1.5 py-0.2 rounded font-mono text-[#929292] bg-[#181818] border border-[#292929]">
                  {isAdmin ? "Ingestion & Index" : "Revision RAG"}
                </span>
              </div>
              <p className="text-[11px] text-[#626262] hidden md:block truncate">
                {isAdmin
                  ? "Playlist Ingestion & Vector Index Management"
                  : "Grounded Video Revision Knowledge Base"}
              </p>
            </div>
          </div>

          {/* Status & Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {/* Backend Health Badge */}
            <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-mono border bg-[#181818] border-[#292929]">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  healthLoading
                    ? "bg-amber-400 animate-pulse"
                    : isHealthy
                    ? "bg-emerald-500"
                    : "bg-rose-500"
                }`}
              />
              <span className="text-[#929292]">
                {healthLoading ? "Checking..." : isHealthy ? "Connected" : "Offline"}
              </span>
              {isHealthy && (
                <span className="text-[#626262] border-l border-[#292929] pl-1.5">
                  {device.includes("CUDA") ? "CUDA" : "CPU"}
                </span>
              )}
            </div>

            {/* Polling Indicator (Admin mode) */}
            {isAdmin && isPolling && (
              <span className="flex items-center gap-1 text-[11px] text-[#929292] font-mono bg-[#181818] border border-[#292929] px-2 py-0.5 rounded-md">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="hidden md:inline">Syncing</span>
              </span>
            )}

            {/* Manual Refresh */}
            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className="p-1.5 rounded-md text-[#929292] hover:text-[#F5F5F5] hover:bg-[#202020] border border-[#292929] transition-colors"
              title="Refresh data from backend"
            >
              <RefreshCwIcon
                className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-[#F5F5F5]" : ""}`}
              />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
