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
          color: "text-emerald-400 bg-emerald-950/40 border-emerald-800/40",
          text: "Success",
        };
      case "error":
        return {
          icon: AlertCircleIcon,
          color: "text-rose-400 bg-rose-950/40 border-rose-800/40",
          text: "Error",
        };
      case "warning":
        return {
          icon: AlertCircleIcon,
          color: "text-amber-400 bg-amber-950/40 border-amber-800/40",
          text: "Warning",
        };
      default:
        return {
          icon: ClockIcon,
          color: "text-indigo-400 bg-indigo-950/40 border-indigo-800/40",
          text: "Info",
        };
    }
  };

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LayersIcon className="w-4 h-4 text-indigo-400" />
          <h3 className="font-semibold text-sm text-slate-100">Live Ingestion Activity Log</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
            {filteredEvents.length} events
          </span>
        </div>

        {/* Severity filter */}
        <div className="flex items-center gap-1 bg-slate-950/80 p-0.5 rounded-lg border border-slate-800 text-[11px]">
          {["ALL", "SUCCESS", "ERROR", "INFO"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterSeverity(s)}
              className={`px-2 py-0.5 rounded font-medium transition ${
                filterSeverity === s
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {s.charAt(0) + s.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && events.length === 0 ? (
        <div className="p-8 text-center text-slate-400 text-xs animate-pulse font-mono">
          Loading pipeline activity records...
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="p-8 text-center text-slate-500 text-xs font-mono">
          No ingestion activity recorded matching criteria.
        </div>
      ) : (
        <div className="max-h-72 overflow-y-auto divide-y divide-slate-800/60 font-mono text-xs">
          {filteredEvents.map((ev) => {
            const badge = getSeverityBadge(ev.severity);
            const Icon = badge.icon;
            const timeStr = new Date(ev.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });

            return (
              <div
                key={ev.id}
                className="p-3 hover:bg-slate-850/40 transition flex items-start gap-3"
              >
                {/* Timestamp */}
                <span className="text-slate-500 text-[11px] shrink-0 mt-0.5">
                  {timeStr}
                </span>

                {/* Stage & Event */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                      {ev.stage}
                    </span>
                    <span className="font-medium text-slate-200">{ev.event}</span>
                    {ev.video_title && (
                      <span className="text-slate-400 text-[11px] truncate max-w-xs">
                        — {ev.video_title}
                      </span>
                    )}
                  </div>

                  {ev.details && (
                    <p className="text-[11px] text-slate-400 mt-0.5 truncate break-all">
                      {ev.details}
                    </p>
                  )}
                </div>

                {/* Severity pill */}
                <span
                  className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${badge.color}`}
                >
                  <Icon className="w-3 h-3" />
                  <span>{badge.text}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
