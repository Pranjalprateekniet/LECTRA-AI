"use client";

import React from "react";
import { HealthData, PlaylistStatusResponse } from "@/types/api";
import { DatabaseIcon, CheckCircleIcon, ClockIcon } from "./Icons";

interface VectorIndexStatusProps {
  status: PlaylistStatusResponse | null;
  health: HealthData | null;
  loading: boolean;
}

export function VectorIndexStatus({ status, health, loading }: VectorIndexStatusProps) {
  const isHealthy = health?.status === "healthy";
  const isQdrantReady = health?.components?.qdrant_configured ?? true;
  const embeddingModel = status?.embedding_model || "google/embeddinggemma-2-27b";
  const device = health?.execution_device || "CPU";

  return (
    <div className="bg-[#111111] border border-[#292929] rounded-xl overflow-hidden shadow-xs min-w-0">
      <div className="p-3 sm:p-3.5 border-b border-[#292929] flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <DatabaseIcon className="w-3.5 h-3.5 text-[#929292] shrink-0" />
          <h3 className="font-medium text-xs sm:text-sm text-[#F5F5F5] truncate">
            Vector Index Status (Qdrant)
          </h3>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#181818] text-[#626262] font-mono border border-[#292929] shrink-0">
            revision_chunks
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-mono">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border ${
              isHealthy && isQdrantReady
                ? "bg-[#181818] text-emerald-500 border-[#292929]"
                : "bg-[#181818] text-amber-400 border-amber-900/40"
            }`}
          >
            {isHealthy && isQdrantReady ? (
              <CheckCircleIcon className="w-3 h-3" />
            ) : (
              <ClockIcon className="w-3 h-3" />
            )}
            <span>{isHealthy && isQdrantReady ? "Operational" : "Degraded"}</span>
          </span>
        </div>
      </div>

      <div className="p-3.5 sm:p-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs min-w-0">
        {/* Item 1: Collection */}
        <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 space-y-1 min-w-0">
          <span className="text-[10px] uppercase font-mono text-[#626262] tracking-wider block">
            Collection Name
          </span>
          <span className="font-mono text-xs text-[#F5F5F5] truncate block">
            revision_chunks
          </span>
          <span className="text-[10px] text-[#626262] font-mono block">
            Cosine Distance Metric
          </span>
        </div>

        {/* Item 2: Embedding Model */}
        <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 space-y-1 min-w-0">
          <span className="text-[10px] uppercase font-mono text-[#626262] tracking-wider block">
            Embedding Model
          </span>
          <span className="font-mono text-xs text-[#F5F5F5] truncate block" title={embeddingModel}>
            {embeddingModel.split("/").pop() || "EmbeddingGemma 2"}
          </span>
          <span className="text-[10px] text-[#626262] font-mono block">
            768 Dimensions ({device})
          </span>
        </div>

        {/* Item 3: Indexed Vectors */}
        <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 space-y-1 min-w-0">
          <span className="text-[10px] uppercase font-mono text-[#626262] tracking-wider block">
            Indexed Points
          </span>
          <span className="font-mono text-sm font-semibold text-[#F5F5F5] block">
            {loading ? "..." : (status?.total_vectors_indexed ?? 0).toLocaleString()}
          </span>
          <span className="text-[10px] text-[#626262] font-mono block">
            {status?.total_embeddings ?? 0} Embeddings
          </span>
        </div>

        {/* Item 4: Verified Chunks */}
        <div className="bg-[#181818] border border-[#292929] rounded-lg p-2.5 space-y-1 min-w-0">
          <span className="text-[10px] uppercase font-mono text-[#626262] tracking-wider block">
            Verified Chunks
          </span>
          <span className="font-mono text-sm font-semibold text-[#F5F5F5] block">
            {loading ? "..." : (status?.total_chunks ?? 0).toLocaleString()}
          </span>
          <span className="text-[10px] text-[#626262] font-mono block">
            {status?.total_transcript_segments ?? 0} Segments
          </span>
        </div>
      </div>
    </div>
  );
}
