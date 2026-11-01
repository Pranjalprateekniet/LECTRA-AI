"use client";

import React from "react";
import { PlaylistStatusResponse } from "@/types/api";
import {
  VideoIcon,
  CheckCircleIcon,
  ClockIcon,
  AlertCircleIcon,
  LayersIcon,
  SparklesIcon,
  DatabaseIcon,
} from "./Icons";

interface StatisticsDashboardProps {
  status: PlaylistStatusResponse | null;
  loading: boolean;
}

export function StatisticsDashboard({ status, loading }: StatisticsDashboardProps) {
  if (loading && !status) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 animate-pulse">
        {[...Array(7)].map((_, i) => (
          <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 h-24" />
        ))}
      </div>
    );
  }

  if (!status) return null;

  const cards = [
    {
      title: "Total Videos",
      value: status.video_count,
      subtext: `${status.discovered_count} discovered`,
      icon: VideoIcon,
      accent: "text-slate-100",
      bg: "bg-slate-900/60 border-slate-800",
      iconColor: "text-slate-400",
    },
    {
      title: "Completed",
      value: status.completed_count,
      subtext: "100% indexed",
      icon: CheckCircleIcon,
      accent: "text-emerald-400",
      bg: "bg-emerald-950/20 border-emerald-800/40",
      iconColor: "text-emerald-400",
    },
    {
      title: "In Progress",
      value: status.processing_count,
      subtext: "pipeline running",
      icon: ClockIcon,
      accent: "text-indigo-400",
      bg: "bg-indigo-950/20 border-indigo-800/40",
      iconColor: "text-indigo-400",
    },
    {
      title: "Failed",
      value: status.failed_count + status.unavailable_count,
      subtext: `${status.unavailable_count} unavailable`,
      icon: AlertCircleIcon,
      accent: status.failed_count > 0 ? "text-rose-400" : "text-slate-400",
      bg: status.failed_count > 0 ? "bg-rose-950/20 border-rose-800/40" : "bg-slate-900/60 border-slate-800",
      iconColor: status.failed_count > 0 ? "text-rose-400" : "text-slate-500",
    },
    {
      title: "Transcript Chunks",
      value: status.total_chunks,
      subtext: `${status.total_transcript_segments} segments`,
      icon: LayersIcon,
      accent: "text-amber-400",
      bg: "bg-amber-950/20 border-amber-800/40",
      iconColor: "text-amber-400",
    },
    {
      title: "Embeddings",
      value: status.total_embeddings,
      subtext: "768d Gemma 2",
      icon: SparklesIcon,
      accent: "text-violet-400",
      bg: "bg-violet-950/20 border-violet-800/40",
      iconColor: "text-violet-400",
    },
    {
      title: "Qdrant Points",
      value: status.total_vectors_indexed,
      subtext: "revision_chunks",
      icon: DatabaseIcon,
      accent: "text-cyan-400",
      bg: "bg-cyan-950/20 border-cyan-800/40",
      iconColor: "text-cyan-400",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className={`border rounded-xl p-3.5 flex flex-col justify-between transition ${card.bg}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider truncate">
                {card.title}
              </span>
              <Icon className={`w-4 h-4 shrink-0 ${card.iconColor}`} />
            </div>

            <div className="mt-2">
              <div className={`text-xl sm:text-2xl font-bold font-mono ${card.accent}`}>
                {card.value.toLocaleString()}
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-0.5 truncate">
                {card.subtext}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
