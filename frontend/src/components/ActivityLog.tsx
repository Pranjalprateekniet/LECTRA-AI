"use client";

import React, { useState } from "react";
import { ActivityEventResponse } from "@/types/api";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ClockIcon,
  LayersIcon,
} from "./Icons";

interface ActivityLogProps {
  events: ActivityEventResponse[];
  loading: boolean;
}

export function ActivityLog({ events, loading }: ActivityLogProps) {
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");

  const filteredEvents = events.filter((ev) => {
    if (filterSeverity === "ALL") return true;
    return ev.severity === filterSeverity.toLowerCase();
  });

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "success":
        return {
          icon: CheckCircleIcon,
          color: "text-[#929292] bg-[#181818] border-[#292929]",
          dot: "bg-emerald-500",
          text: "Success",
        };
      case "error":
        return {
          icon: AlertCircleIcon,
          color: "text-[#929292] bg-[#181818] border-[#292929]",
          dot: "bg-rose-500",
          text: "Error",
        };
      case "warning":
        return {
          icon: AlertCircleIcon,
          color: "text-[#929292] bg-[#181818] border-[#292929]",
          dot: "bg-amber-400",
          text: "Warning",
        };
      default:
        return {
          icon: ClockIcon,
          color: "text-[#929292] bg-[#181818] border-[#292929]",
          dot: "bg-[#626262]",
          text: "Info",
        };
    }
  };

  return (
    <div className="bg-[#111111] border border-[#292929] rounded-xl overflow-hidden shadow-xs min-w-0">
      <div className="p-3 sm:p-3.5 border-b border-[#292929] flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <LayersIcon className="w-3.5 h-3.5 text-[#929292] shrink-0" />
          <h3 className="font-medium text-xs sm:text-sm text-[#F5F5F5] truncate">Live Activity Log</h3>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#181818] text-[#626262] font-mono border border-[#292929] shrink-0">
            {filteredEvents.length} events
          </span>
        </div>

        {/* Severity filter */}
        <div className="flex items-center gap-0.5 bg-[#181818] p-0.5 rounded-md border border-[#292929] text-[11px] shrink-0">
          {["ALL", "SUCCESS", "ERROR", "INFO"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterSeverity(s)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                filterSeverity === s
                  ? "bg-[#202020] text-[#F5F5F5] border border-[#292929]"
                  : "text-[#929292] hover:text-[#F5F5F5]"
              }`}
            >
              {s.charAt(0) + s.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && events.length === 0 ? (
        <div className="p-6 text-center text-[#929292] text-xs animate-pulse font-mono min-w-0">
          Loading pipeline activity records...
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="p-6 text-center text-[#626262] text-xs font-mono min-w-0">
          No ingestion activity recorded matching criteria.
        </div>
      ) : (
        <div className="max-h-64 overflow-y-auto divide-y divide-[#292929] font-mono text-xs min-w-0">
          {filteredEvents.map((ev) => {
            const badge = getSeverityBadge(ev.severity);
            const timeStr = new Date(ev.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });

            return (
              <div
                key={ev.id}
                className="p-2 sm:px-3 flex items-start gap-2 hover:bg-[#141414] transition-colors min-w-0"
              >
                <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${badge.dot}`} />
                  <span className="text-[10px] text-[#626262]">{timeStr}</span>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                    <span className="font-semibold text-[#F5F5F5] text-[11px] truncate">
                      {ev.event}
                    </span>
                    <span className="text-[10px] text-[#929292] font-mono">
                      [{ev.stage}]
                    </span>
                    {ev.video_id && (
                      <span className="text-[10px] text-[#626262] bg-[#181818] border border-[#292929] px-1 py-0.2 rounded shrink-0">
                        {ev.video_title ? ev.video_title : `video:${ev.video_id}`}
                      </span>
                    )}
                  </div>
                  {ev.details && (
                    <p className="text-[11px] text-[#929292] font-sans mt-0.5 break-words [overflow-wrap:anywhere]">
                      {ev.details}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
