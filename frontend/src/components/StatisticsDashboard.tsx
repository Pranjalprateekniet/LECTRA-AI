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
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2.5 animate-pulse min-w-0">
        {[...Array(7)].map((_, i) => (
          <div key={i} className="bg-[#111111] border border-[#292929] rounded-lg p-3 h-20 min-w-0" />
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
    },
    {
      title: "Completed",
      value: status.completed_count,
      subtext: "100% indexed",
      icon: CheckCircleIcon,
    },
    {
      title: "In Progress",
      value: status.processing_count,
      subtext: "pipeline running",
      icon: ClockIcon,
    },
    {
      title: "Failed",
      value: status.failed_count + status.unavailable_count,
      subtext: `${status.unavailable_count} unavailable`,
      icon: AlertCircleIcon,
    },
    {
      title: "Transcript Chunks",
      value: status.total_chunks,
      subtext: `${status.total_transcript_segments} segments`,
      icon: LayersIcon,
    },
    {
      title: "Embeddings",
      value: status.total_embeddings,
      subtext: "768d Gemma 2",
      icon: SparklesIcon,
    },
    {
      title: "Qdrant Points",
      value: status.total_vectors_indexed,
      subtext: "revision_chunks",
      icon: DatabaseIcon,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2.5 min-w-0">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="bg-[#111111] border border-[#292929] rounded-lg p-3 flex flex-col justify-between min-w-0 shadow-xs"
          >
            <div className="flex items-center justify-between text-[#626262] mb-1 min-w-0">
              <span className="text-[10px] uppercase font-medium tracking-wider truncate">
                {card.title}
              </span>
              <Icon className="w-3.5 h-3.5 text-[#929292] shrink-0" />
            </div>

            <div>
              <div className="text-lg font-semibold font-mono text-[#F5F5F5] truncate">
                {card.value.toLocaleString()}
              </div>
              <div className="text-[10px] text-[#626262] font-mono truncate mt-0.5">
                {card.subtext}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
